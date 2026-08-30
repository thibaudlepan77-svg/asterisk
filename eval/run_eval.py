# -*- coding: utf-8 -*-
"""Score the auditor against hand labelled real pages.

Most contest submissions show one good screenshot. This shows a number, and
the number is allowed to be bad. Two labels, both checkable by anyone who
opens the page.

  prize_is_not_cash    the prize block itself says the award cannot be
                       exchanged or redeemed for cash
  students_only        the eligibility card says Students only
  team_required        the structured eligibility card says Team required
  demo_video_required  the What to Submit section asks for a video

Every label is read from a source the auditor never parses, so the score is a
test and not a memory. **A label with no positive case in a set prints what the
set can show, not an f1 of zero**, because an f1 of zero on an empty class is a
lie about the detector.

Run it offline first. The deterministic layer alone should already be strong
on the first label, because the wording is imposed by consumer law. The model
layer is there for the wordings nobody standardised.
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from asterisk import fetch                       # noqa: E402
from asterisk.audit import audit                 # noqa: E402
from asterisk.segment import segment             # noqa: E402

# Which finding kinds count as a positive prediction for each label.
PREDICTS = {
    "prize_is_not_cash": {"cash", "amount", "prize not cash"},
    "students_only": {"anyone", "students only"},
    # ADDED 2026-08-30. The tool prints eleven families of restriction and two
    # of them had ever been scored. Nine tenths of what it says carried no
    # number, and a number nobody has is indistinguishable from a bad one.
    #
    # Both of these are labelled from a source the auditor never reads. The
    # first from the STRUCTURED eligibility card, a closed field filled in a
    # form. The second from the `What to Submit` section.
    "team_required": {"team required"},
    "demo_video_required": {"third party publication required", "video required"},
}
# A prediction only counts when the quoted counter evidence really is about it.
CONFIRMS = {
    "prize_is_not_cash": ("not a cash prize", "redeemed for cash", "non-cash",
                          "not redeemable for cash", "sponsor-provided"),
    "students_only": ("students only", "student teams", "currently enrolled",
                      "college students only"),
    "team_required": ("team required", "teams of", "form a team", "join a team",
                      "minimum team size"),
    # NO NEEDLE, ON PURPOSE, and it cost a false negative to work out why.
    #
    # The confirming needle is checked against the QUOTED EXCERPT, which is cut
    # at a fixed length. On one page the requirement sat past the cut, so the
    # excerpt said `Text description, PUBLIC URL to your code repo` and the
    # word `video` never appeared in it. The tool had found the right thing and
    # the scorer marked it a miss.
    #
    # A needle guards against a family that is too broad. This family is named
    # for exactly one thing, so the name is the evidence and a second check on
    # a truncated string only adds a way to be wrong.
    "demo_video_required": (),
}


def predict(findings, label: str) -> tuple[bool, str]:
    kinds = PREDICTS[label]
    needles = CONFIRMS[label]
    for f in findings:
        if f.claim_kind not in kinds:
            continue
        if not needles:
            return True, f.counter[:150]
        low = f.counter.lower()
        if any(n in low for n in needles):
            return True, f.counter[:150]
    return False, ""


def score(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="deterministic layer only")
    ap.add_argument("--holdout", action="store_true", help="score the held out set instead")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--show-errors", action="store_true")
    a = ap.parse_args(argv)

    name = "holdout.json" if a.holdout else "benchmark.json"
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        print("missing %s, run eval/build_holdout.py first" % name)
        return 2
    with io.open(path, encoding="utf-8") as f:
        bench = json.load(f)
    cases = bench["cases"][: a.limit] if a.limit else bench["cases"]

    counts = {k: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for k in PREDICTS}
    errors = []
    for c in cases:
        try:
            doc = segment(fetch.fetch(c["url"]), c["url"])
            _, findings = audit(doc, offline=a.offline)
        except Exception as e:
            print("skipped %s, %s" % (c["title"][:40], type(e).__name__))
            continue
        for label in PREDICTS:
            truth = bool(c["labels"][label])
            got, quote = predict(findings, label)
            bucket = "tp" if (truth and got) else "fp" if (not truth and got) \
                else "fn" if (truth and not got) else "tn"
            counts[label][bucket] += 1
            if bucket in ("fp", "fn"):
                errors.append((label, bucket, c["title"][:44], quote[:110]))

    print("=" * 78)
    print("ASTERISK %s, %d real pages, %s" % ("HELD OUT set" if a.holdout else "development set",
                                            len(cases), "offline" if a.offline else "with model"))
    print("labels collected %s" % bench["collected"])
    print("=" * 78)
    for label, k in counts.items():
        positives = k["tp"] + k["fn"]
        if positives == 0:
            # No positive example in this set. Reporting f1 zero here would be a
            # lie about the detector, so report what the set can actually show,
            # how often it stays silent when it should.
            spec = k["tn"] / (k["tn"] + k["fp"]) if k["tn"] + k["fp"] else 0.0
            print("%-20s no positive case in this set. false alarms %d on %d pages, "
                  "specificity %.2f" % (label, k["fp"], k["tn"] + k["fp"], spec))
            continue
        p, r, f1 = score(k["tp"], k["fp"], k["fn"])
        print("%-20s tp %2d  fp %2d  fn %2d  tn %2d   precision %.2f  recall %.2f  f1 %.2f"
              % (label, k["tp"], k["fp"], k["fn"], k["tn"], p, r, f1))
    if a.show_errors and errors:
        print("-" * 78)
        for label, bucket, title, quote in errors:
            print("%-4s %-20s %-44s %s" % (bucket.upper(), label, title, quote))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
