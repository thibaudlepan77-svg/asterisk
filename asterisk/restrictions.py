# -*- coding: utf-8 -*-
"""Restrictions that no headline contradicts, and that still cost you.

This module exists because the benchmark said so. The contradiction engine
scored recall 0.29 on "the offer is reserved to students", and the reason was
not a tuning problem. Fourteen pages restrict entry to students while never
promising that entry is open, so there is no promise to contradict and nothing
for a contradiction detector to find.

A reader does not only need to know where a page fights itself. They need to
know what the page quietly requires of them. So the tool reports two kinds.

  CONTRADICTION  the page says A loudly and not A quietly
  RESTRICTION    the page never said A, and quietly requires B of you

Both are grounded the same way. Nothing is printed that is not on the page.
"""
from __future__ import annotations
import re

# Each entry, a label, a pattern, a severity, and what the reader loses.
RESTRICTIONS = [
    # "currently enrolled" alone was dropped after a false positive on a page
    # that used it in an invitation, not a condition. A restriction has to be
    # phrased as one.
    ("students only",
     r"(students? only|college students? only|student teams? only|"
     r"(?:must|has to) be (?:a )?(?:currently )?enrolled|"
     r"open (?:only )?to (?:currently )?enrolled students|"
     r"you must be a (?:full[- ]time )?student)",
     "high", "Entry is reserved to students, so a professional cannot take part."),
    ("organisations excluded",
     r"(compan(?:y|ies)[^.]{0,40}excluded|professional organizations? excluded|"
     r"organizations? excluded from participation|no (?:companies|businesses) may enter)",
     "high", "Companies and professional entities are excluded."),
    ("country restricted",
     r"(only open to[^.]{0,80}reside in|must (?:currently )?reside in [A-Z][a-z]+|"
     r"residents of [A-Z][a-z]+ only|only specific countries|"
     r"specific countries/territories excluded)",
     "high", "Entry depends on where you live."),
    ("age restricted",
     r"(ages? \d{1,2}(?: to \d{1,2})?\+? only|must be at least \d{1,2} years|"
     r"age of majority)",
     "low", "There is an age condition."),
    ("team required",
     r"(team required|teams? of \d+ to \d+|must (?:form|join) a team|minimum team size)",
     "medium", "You cannot enter alone."),
    ("prize not cash",
     r"(not a cash prize|cannot be exchanged or redeemed for cash|not redeemable for cash|"
     r"no cash (?:value|alternative))",
     "critical", "What is presented as a sum is not money you can receive."),
    ("payment before use",
     r"(payment (?:method|details) (?:is |are )?required|valid credit card required|"
     r"card required to start)",
     "high", "You must hand over a payment method before you get anything."),
    ("auto renewal",
     r"(auto[- ]?renew|renews automatically|will (?:be )?renew(?:ed)? unless)",
     "high", "It renews by itself unless you act."),
    ("no refund",
     r"(non[- ]refundable|no refunds?\b|all sales are final)",
     "high", "You cannot get your money back."),
    ("delay before payment",
     r"(within \d+ (?:business )?days of|delivered within \d+ days|allow \d+ to \d+ (?:business )?days)",
     "low", "The money or the goods arrive later than the page suggests."),
    ("tax paperwork",
     r"(w-?8\s?ben|w-?9\b|tax form|withholding|form 1099)",
     "low", "A tax form stands between you and the payment."),
    ("licence handover",
     r"(grant(?:s)? (?:the )?sponsor a[^.]{0,60}(?:licen[cs]e|right)|"
     r"irrevocable[^.]{0,40}licen[cs]e|assign(?:s)? all rights)",
     "high", "You hand over rights on what you submit."),
]

_R = [(lab, re.compile(p, re.I), sev, why) for lab, p, sev, why in RESTRICTIONS]


def find(doc, sents, max_per_label: int = 1):
    """Return raw dicts, the audit module wraps them into Findings."""
    out = []
    seen = {}
    for s in sents:
        for label, rx, sev, why in _R:
            if seen.get(label, 0) >= max_per_label:
                continue
            m = rx.search(s.text)
            if not m:
                continue
            seen[label] = seen.get(label, 0) + 1
            out.append({
                "label": label,
                "quote": s.excerpt(300),
                "severity": sev,
                "explanation": why,
                "section": s.section,
                "offset": doc.locate(m.group(0)),
            })
    return out
