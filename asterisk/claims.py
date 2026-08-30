# -*- coding: utf-8 -*-
"""Find the promises a page makes loudly enough to be worth checking.

Deliberately deterministic. A model is good at judging whether a clause
cancels a promise, and bad at being exhaustive over a long page at low cost.
So the regular expressions do the sweeping and the model does the judging.
Every pattern here was written against a page we had already read by hand.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

from .segment import Document

MONEY = r"(?:[$\u20ac\u00a3\u20b9]|USD|EUR|GBP)\s?\d[\d,.]*\s*(?:k|K|m|M|million|billion)?"

PATTERNS: list[tuple[str, str, str]] = [
    # kind, regex, why a buyer cares
    ("amount",      rf"{MONEY}(?:\s*\+)?", "a sum the page puts forward"),
    ("cash",        r"\bin cash\b|\bcash prize\b|\bpaid in cash\b", "the money is said to be cash"),
    ("free",        r"\bfree\b(?!\s*(?:trial\s*ends|to\s*leave))|\bno cost\b|\bat no charge\b|\b100% free\b", "no payment is implied"),
    ("nofee",       r"\bno fees?\b|\bzero fees?\b|\bno hidden (?:fees|charges)\b|\bno commission\b", "no deduction is implied"),
    ("unlimited",   r"\bunlimited\b|\bunmetered\b|\bas much as you (?:want|need)\b", "no ceiling is implied"),
    ("guarantee",   r"\bguarantee(?:d|s)?\b|\bmoney[- ]back\b|\brisk[- ]free\b", "a promise of recourse"),
    ("anyone",      r"\bopen to (?:everyone|anyone|all)\b|\bworldwide\b|\banyone can\b|\bno experience (?:needed|required)\b", "no barrier is implied"),
    ("instant",     r"\binstant(?:ly)?\b|\bimmediate(?:ly)?\b|\bsame[- ]day\b|\bright away\b", "no delay is implied"),
    ("lifetime",    r"\blifetime\b|\bforever\b|\bone[- ]time payment\b|\bnever expires?\b", "no expiry is implied"),
    ("cancel",      r"\bcancel any ?time\b|\bno commitment\b|\bno contract\b", "no lock in is implied"),
]

_COMPILED = [(k, re.compile(p, re.I), w) for k, p, w in PATTERNS]


@dataclass
class Claim:
    kind: str
    text: str            # the exact span as it appears on the page
    context: str         # the sentence it sits in, for the model
    block_index: int
    loudness: float
    why: str

    def key(self) -> str:
        return f"{self.kind}:{self.text.strip().lower()}"


def _sentence_around(block_text: str, start: int, end: int) -> str:
    left = block_text.rfind(".", 0, start)
    right = block_text.find(".", end)
    left = 0 if left < 0 else left + 1
    right = len(block_text) if right < 0 else right + 1
    return block_text[left:right].strip()


def extract(doc, min_loudness: float = 0.6, max_claims: int = 40) -> list[Claim]:
    """Return the loud promises, most prominent first, deduplicated."""
    found: dict[str, Claim] = {}
    for i, b in enumerate(doc.blocks):
        if b.loudness < min_loudness:
            continue
        for kind, rx, why in _COMPILED:
            for m in rx.finditer(b.text):
                c = Claim(
                    kind=kind,
                    text=m.group(0).strip(),
                    context=_sentence_around(b.text, m.start(), m.end()),
                    block_index=i,
                    loudness=b.loudness,
                    why=why,
                )
                prev = found.get(c.key())
                if prev is None or c.loudness > prev.loudness:
                    found[c.key()] = c
    out = sorted(found.values(), key=lambda c: -c.loudness)
    return out[:max_claims]
