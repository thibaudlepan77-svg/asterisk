# -*- coding: utf-8 -*-
"""Add two more labels to both scored sets, with independent ground truth.

WHY. The tool carries ten families of restriction and exactly two of them were
ever measured. Nine tenths of what it prints had no number against it, and a
number nobody has is indistinguishable from a number that is bad.

The two added here were chosen because their ground truth can be read from a
source the auditor never looks at.

  team_required          the STRUCTURED eligibility card, a closed field filled
                         in a form, says `Team required`. The auditor reads the
                         page's free text and never parses that card.
  demo_video_required    the submission requirements ask for a video. The
                         place hosts no video file of its own, proved at
                         help.devpost.com/article/85-uploading-a-demo-video on
                         2026-08-30, so asking for a video IS requiring a
                         publication on a third party.

    python eval/add_labels.py

It rewrites benchmark.json and holdout.json in place, keeping every existing
label and its evidence untouched. It prints the count of each new label,
because **a label with no positive case measures nothing** and it is better to
find that out here than in a results table.
"""
from __future__ import annotations
import io
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

TEAM = re.compile(r"Team required", re.I)
VIDEO = re.compile(
    r"\b(?:demo|submission|pitch|presentation|walkthrough)\s+video\b|"
    r"\bvideo\s+(?:demo|submission|pitch|presentation)\b|"
    r"\b\d+\s*(?:to\s*\d+\s*)?(?:minute|min)\s+video\b|"
    r"\bvideo\b[^.]{0,60}\b(?:youtube|vimeo|youku)\b", re.I)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=35).read().decode("utf-8", "replace")


def _flat(html):
    c = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    c = re.sub(r"<[^>]+>", " ", c)
    return re.sub(r"\s+", " ", c.replace("&nbsp;", " ").replace("&amp;", "&"))


def label(url):
    flat = _flat(_get(url))
    m = re.search(r"Who can participate(.{0,320})", flat)
    card = m.group(1).strip() if m else ""
    # THE FIRST VERSION OF THIS LABELLER WAS WRONG, and it took a bad score to
    # find out. It read four hundred characters after the heading `What to
    # Submit`, and on that ground truth the auditor scored precision 0.27 with
    # eleven false positives. Every one of those eleven was a page that plainly
    # requires a video, `Include a demonstration video of your project (about
    # three minutes), uploaded to YouTube or Vimeo and made public` among them.
    #
    # **The tool was right and the measurement was wrong.** The heading is not
    # always used, and the requirement often sits in a numbered list further
    # down. I had built the ground truth from the one wording I had read, which
    # is the same mistake this project keeps finding in its own rules.
    #
    # The scope is now the structural region between `Requirements` and
    # `Prizes`, which every page on this place has. It is still a different
    # scope from the auditor's, which reads the whole page, so the comparison
    # still tests something.
    i = flat.find("Requirements")
    j = flat.find("Prizes", i) if i >= 0 else -1
    submit = flat[i:j] if (i >= 0 and j > i) else (flat[i:i + 2500] if i >= 0 else "")
    return {
        "team_required": bool(TEAM.search(card)),
        "demo_video_required": bool(VIDEO.search(submit)),
        "what_to_submit": submit[:240],
        "eligibility_card_seen": bool(card),
    }


def enrich(nom):
    chemin = os.path.join(HERE, nom)
    with io.open(chemin, encoding="utf-8") as f:
        d = json.load(f)
    faits, rates = 0, []
    for c in d["cases"]:
        try:
            lab = label(c["url"])
        except Exception as e:
            rates.append((c["title"][:40], type(e).__name__))
            continue
        c["labels"]["team_required"] = lab["team_required"]
        c["labels"]["demo_video_required"] = lab["demo_video_required"]
        c.setdefault("evidence", {})["what_to_submit"] = lab["what_to_submit"]
        c["evidence"]["eligibility_card_seen"] = lab["eligibility_card_seen"]
        faits += 1
        time.sleep(0.15)
    with io.open(chemin, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    t = sum(1 for c in d["cases"] if c["labels"].get("team_required"))
    v = sum(1 for c in d["cases"] if c["labels"].get("demo_video_required"))
    print("%-16s %d case(s) relabelled, %d unreachable. team_required %d, "
          "demo_video_required %d" % (nom, faits, len(rates), t, v))
    for titre, err in rates:
        print("     unreachable, %-40s %s" % (titre, err))
    return t, v, faits


def main():
    total_t = total_v = 0
    for nom in ("benchmark.json", "holdout.json"):
        t, v, _ = enrich(nom)
        total_t += t
        total_v += v
    print()
    if total_t == 0 or total_v == 0:
        print("A LABEL WITH NO POSITIVE CASE MEASURES NOTHING. One of the two new")
        print("labels is empty across both sets, so its score would be an artefact.")
        print("Say so in the results table rather than printing a number.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
