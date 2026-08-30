# -*- coding: utf-8 -*-
"""Build a held out set from pages the rules were never written against.

Why this matters more than the first benchmark. The deterministic rules in
asterisk/audit.py and asterisk/restrictions.py were written while reading
twenty two live contest pages. Scoring on those same pages measures memory,
not method. So this script draws a fresh sample from a different pool, pages
that ended months or years ago, and labels them with two targeted extractors
that are independent of the auditor.

  prize_is_not_cash  counts the non-cash disclaimers inside the prize block
                     only, using the wording that consumer law imposes
  students_only      reads the structured eligibility card, a closed field
                     filled in a form, not free text

Neither labeller shares code with the auditor. Both are printed with their
evidence so a human can check any row in ten seconds.
"""
from __future__ import annotations
import io
import json
import os
import random
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
API = "https://devpost.com/api/hackathons"

DISCLAIMER = re.compile(
    r"(this is not a cash prize|cannot be exchanged or redeemed for cash|"
    r"not redeemable for cash|no cash value)", re.I)
STUDENTS = re.compile(r"(students? only|college students? only)", re.I)


def _get(url, as_json=False):
    headers = {"User-Agent": UA}
    if as_json:
        headers.update({"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                        "Referer": "https://devpost.com/hackathons"})
    req = urllib.request.Request(url, headers=headers)
    raw = urllib.request.urlopen(req, timeout=35).read()
    return json.loads(raw) if as_json else raw.decode("utf-8", "replace")


def _flatten(html: str) -> str:
    c = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    c = re.sub(r"<[^>]+>", " ", c)
    return re.sub(r"\s+", " ", c.replace("&nbsp;", " ").replace("&amp;", "&"))


def label(url: str):
    flat = _flatten(_get(url))
    i = flat.find("Prizes")
    j = flat.find("Requirements", i) if i >= 0 else -1
    prize_block = flat[i:(j if j > i else i + 6000)] if i >= 0 else ""
    m = re.search(r"Who can participate(.{0,320})", flat)
    card = m.group(1).strip() if m else ""
    disc = DISCLAIMER.findall(prize_block)
    return {
        "prize_is_not_cash": len(disc) >= 3,
        "students_only": bool(STUDENTS.search(card)),
        "disclaimer_hits": len(disc),
        "eligibility_card": card[:160],
    }


def main(argv=None) -> int:
    want = int(argv[0]) if argv else 40
    seed = int(argv[1]) if argv and len(argv) > 1 else 20260830
    first = _get(API + "?status[]=ended&page=1", as_json=True)
    pages_max = (first["meta"]["total_count"] + 8) // 9
    random.seed(seed)

    picked, seen = [], set()
    while len(picked) < want * 3:
        page = random.randint(1, pages_max)
        try:
            d = _get(API + "?status[]=ended&page=%d" % page, as_json=True)
        except Exception:
            continue
        for h in d.get("hackathons", []):
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            amount = re.sub(r"[^\d]", "", re.sub(r"<[^>]+>", "", h.get("prize_amount") or ""))
            if not amount or int(amount) < 500:
                continue        # a page with no prize has nothing to contradict
            picked.append({"url": h["url"], "title": h["title"], "prize": int(amount)})
        time.sleep(0.2)

    cases = []
    for p in picked:
        if len(cases) >= want:
            break
        try:
            lab = label(p["url"])
        except Exception as e:
            print("skip %s, %s" % (p["title"][:34], type(e).__name__))
            continue
        cases.append({"url": p["url"], "title": p["title"], "prize": p["prize"],
                      "labels": {k: lab[k] for k in ("prize_is_not_cash", "students_only")},
                      "evidence": {"disclaimer_hits": lab["disclaimer_hits"],
                                   "eligibility_card": lab["eligibility_card"]}})
        print("%-46s notcash=%-5s students=%-5s hits=%d"
              % (p["title"][:46], lab["prize_is_not_cash"], lab["students_only"], lab["disclaimer_hits"]))
        time.sleep(0.2)

    out = {"note": "Held out set. Pages never read while writing the detection rules. "
                   "Labels produced by two targeted extractors that share no code with the auditor.",
           "collected": time.strftime("%Y-%m-%d"), "seed": seed, "cases": cases}
    with io.open(os.path.join(HERE, "holdout.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n%d cases, %d not cash, %d students only"
          % (len(cases), sum(c["labels"]["prize_is_not_cash"] for c in cases),
             sum(c["labels"]["students_only"] for c in cases)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
