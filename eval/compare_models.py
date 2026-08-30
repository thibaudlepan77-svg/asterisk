# -*- coding: utf-8 -*-
"""Score the same labelled pages against several models, and against no model.

WHY THIS EXISTS. The auditor has two layers, a deterministic one that needs no
model and a model one for the wordings nobody standardised. Every number ever
published for this tool mixed the two. So the honest question was never
answered, what does the model layer actually buy, and does the cheapest model
buy the same thing as the dearest?

That question is worth a table and not an opinion. The offline row is the
baseline, every model row is measured against it, and a model that does not
beat the baseline on any label is a model this tool should not pay for.

    python eval/compare_models.py --models nano,super --limit 8
    python eval/compare_models.py --estimate-only

WHAT IT REFUSES TO DO. Spend without saying so first. Inference is metered, and
a benchmark loop is the easiest way to burn a prepaid balance without noticing.
It prints the number of model calls it is about to make and needs --yes to go
ahead, unless the run is offline only.
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from asterisk import fetch                       # noqa: E402
from asterisk.audit import audit                 # noqa: E402
from asterisk.segment import segment             # noqa: E402
from eval.run_eval import PREDICTS, predict, score   # noqa: E402

# Upper bound of model calls the auditor makes per page. by_model caps the
# claims it sends at max_claims, so this is the worst case and never a
# surprise in the other direction.
CALLS_PER_PAGE = 12

BASELINE = "no model, deterministic layer only"


def empty_counts():
    return {k: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for k in PREDICTS}


def tally(counts, label, truth, got):
    bucket = "tp" if (truth and got) else "fp" if (not truth and got) \
        else "fn" if (truth and not got) else "tn"
    counts[label][bucket] += 1


def run_one(cases, model, offline):
    """Score one configuration. Returns (counts, pages actually scored)."""
    counts, seen = empty_counts(), 0
    for c in cases:
        try:
            doc = segment(fetch.fetch(c["url"]), c["url"])
            _, findings = audit(doc, offline=offline, model=model)
        except Exception as e:
            print("  skipped %s, %s" % (c["title"][:40], type(e).__name__))
            continue
        seen += 1
        for label in PREDICTS:
            got, _ = predict(findings, label)
            tally(counts, label, bool(c["labels"][label]), got)
    return counts, seen


def table(rows):
    """rows is a list of (name, counts, pages). Prints one block per label.

    Sorted by f1 descending inside each label, so the answer to `which model`
    is the first line and not something the reader has to compute.
    """
    for label in PREDICTS:
        print("")
        print(label)
        print("  %-34s %5s %5s %5s %5s   %9s %6s %5s" %
              ("configuration", "tp", "fp", "fn", "tn", "precision", "recall", "f1"))
        measured = []
        for name, counts, _ in rows:
            k = counts[label]
            if k["tp"] + k["fn"] == 0:
                # No positive case in the set. An f1 of zero here would be a lie
                # about the detector, so we say what the set can actually show.
                spec = k["tn"] / (k["tn"] + k["fp"]) if k["tn"] + k["fp"] else 0.0
                print("  %-34s no positive case, false alarms %d, specificity %.2f"
                      % (name[:34], k["fp"], spec))
                continue
            measured.append((score(k["tp"], k["fp"], k["fn"]), name, k))
        for (p, r, f1), name, k in sorted(measured, key=lambda x: -x[0][2]):
            print("  %-34s %5d %5d %5d %5d   %9.2f %6.2f %5.2f"
                  % (name[:34], k["tp"], k["fp"], k["fn"], k["tn"], p, r, f1))


def verdict(rows):
    """Says out loud whether any model earned its keep. The point of the table."""
    base = next((c for n, c, _ in rows if n == BASELINE), None)
    if base is None:
        return
    print("")
    print("=" * 78)
    for name, counts, _ in rows:
        if name == BASELINE:
            continue
        gains = []
        for label in PREDICTS:
            k, b = counts[label], base[label]
            if k["tp"] + k["fn"] == 0:
                continue
            f1 = score(k["tp"], k["fp"], k["fn"])[2]
            f1b = score(b["tp"], b["fp"], b["fn"])[2]
            if f1 - f1b > 0.01:
                gains.append("%s +%.2f" % (label, f1 - f1b))
        if gains:
            print("%-34s beats the baseline on %s" % (name[:34], ", ".join(gains)))
        else:
            print("%-34s beats the baseline on NOTHING. It costs and adds nothing here."
                  % name[:34])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="",
                    help="comma separated model ids to compare, empty means offline only")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--estimate-only", action="store_true",
                    help="print what it would cost in calls, run nothing")
    ap.add_argument("--yes", action="store_true", help="confirm the metered run")
    a = ap.parse_args(argv)

    path = os.path.join(HERE, "holdout.json" if a.holdout else "benchmark.json")
    if not os.path.exists(path):
        print("missing %s, run eval/build_holdout.py first" % os.path.basename(path))
        return 2
    with io.open(path, encoding="utf-8") as f:
        bench = json.load(f)
    cases = bench["cases"][: a.limit] if a.limit else bench["cases"]
    models = [m.strip() for m in a.models.split(",") if m.strip()]

    budget = len(cases) * len(models) * CALLS_PER_PAGE
    print("pages %d, models %d, worst case model calls %d"
          % (len(cases), len(models), budget))
    print("base url %s" % os.environ.get("ASTERISK_BASE_URL", "(provider default)"))
    if a.estimate_only:
        return 0
    if models and not a.yes:
        print("this run is metered. Re-run with --yes once the number above is acceptable.")
        return 1

    rows = []
    started = time.time()
    counts, seen = run_one(cases, None, offline=True)
    rows.append((BASELINE, counts, seen))
    print("scored baseline on %d pages" % seen)
    for m in models:
        counts, seen = run_one(cases, m, offline=False)
        rows.append((m, counts, seen))
        print("scored %s on %d pages" % (m, seen))

    print("")
    print("=" * 78)
    print("ASTERISK model comparison, %s set, %d pages, %.0f s"
          % ("held out" if a.holdout else "development", len(cases), time.time() - started))
    print("labels collected %s" % bench["collected"])
    print("=" * 78)
    table(rows)
    verdict(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
