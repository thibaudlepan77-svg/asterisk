# -*- coding: utf-8 -*-
"""Split a document into sentences that can be quoted and pointed at.

Why this exists, and it was not in the first design. On real offer pages the
clause that cancels a promise is very often in the SAME visual block as the
promise, two sentences later. A prize tier reads

    $585 in cash, 3 winners, 1-year subscriptions for a partner product.
    THIS IS NOT A CASH PRIZE. It cannot be exchanged or redeemed for cash.

Anything that only compares one block against another block never sees it.
The unit that carries a contradiction is the sentence, not the block.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

# Abbreviations that must not end a sentence.
_PROTECT = [
    (r"\bU\.S\.", "\x01US\x01"), (r"\bU\.K\.", "\x01UK\x01"), (r"\be\.g\.", "\x01EG\x01"),
    (r"\bi\.e\.", "\x01IE\x01"), (r"\bNo\.", "\x01NO\x01"), (r"\bInc\.", "\x01INC\x01"),
    (r"\bLtd\.", "\x01LTD\x01"), (r"\bSt\.", "\x01ST\x01"), (r"\bvs\.", "\x01VS\x01"),
    (r"\bApprox\.", "\x01APX\x01"), (r"(\d)\.(\d)", "\\1\x02\\2"),
]
_RESTORE = [("\x01US\x01", "U.S."), ("\x01UK\x01", "U.K."), ("\x01EG\x01", "e.g."),
            ("\x01IE\x01", "i.e."), ("\x01NO\x01", "No."), ("\x01INC\x01", "Inc."),
            ("\x01LTD\x01", "Ltd."), ("\x01ST\x01", "St."), ("\x01VS\x01", "vs."),
            ("\x01APX\x01", "Approx."), ("\x02", ".")]

_SPLIT = re.compile(r"(?<=[.!?\u2022\u26a0])\s+|(?<=[.!?])(?=[A-Z]{3,})|\s\u2022\s|\s\|\s")


@dataclass
class Sentence:
    text: str
    line_index: int
    order: int          # position among all sentences of the page
    section: str
    loudness: float
    quiet: bool

    def excerpt(self, n: int = 300) -> str:
        t = " ".join(self.text.split())
        return t if len(t) <= n else t[: n - 1] + "…"


def split(text: str):
    for pat, rep in _PROTECT:
        text = re.sub(pat, rep, text)
    parts = [p.strip() for p in _SPLIT.split(text) if p and p.strip()]
    out = []
    for p in parts:
        for a, b in _RESTORE:
            p = p.replace(a, b)
        if len(p) >= 3:
            out.append(p)
    return out


def sentences(doc):
    """Flatten a Document into ordered, attributed sentences."""
    out = []
    order = 0
    for line in doc.lines:
        for s in split(line.text):
            out.append(Sentence(text=s, line_index=line.index, order=order,
                                section=line.section, loudness=line.loudness,
                                quiet=line.fine_print))
            order += 1
    return out
