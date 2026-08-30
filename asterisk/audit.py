# -*- coding: utf-8 -*-
"""Match every prominent promise against the sentence that takes it back.

Two layers, and the order matters.

1. A deterministic layer that needs no model at all. It catches the family of
   contradiction written in fixed legal formulas, because the law forces the
   wording. It is fast, free, and it never invents anything.
2. A model layer for everything the formulas miss, gated by a rule the model
   cannot talk its way around. Any quote it returns must appear verbatim in
   the page, or the finding is discarded. A finding you cannot point at is
   not a finding.

The unit on both sides is the SENTENCE. That was a correction, not the first
design. See sentences.py for why.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict

from .claims import Claim, extract
from .sentences import sentences, Sentence
from . import restrictions as _restrictions
from . import llm

HARD_RULES = [
    ("cash", r"(this is not a cash prize|not a cash prize|cannot be exchanged or redeemed for cash|"
             r"no cash (?:value|alternative)|not redeemable for cash|non-cash (?:award|prize|benefit))",
     "critical", "The page calls the sum cash and then says it is not."),
    # A bare "in credits" was dropped. It matched "Built-in credits" on a
    # pricing page and paired an unrelated plan price with a feature bullet.
    # The phrase only means something when a verb of payment governs it.
    ("amount", r"(this is not a cash prize|cannot be exchanged or redeemed for cash|"
               r"approximate retail value|\barv\b|consists of sponsor-provided|"
               r"(?:paid|awarded|issued|granted|provided|delivered) in (?:product |sponsor[- ]provided )?credits)",
     "high", "The sum is shown as money and described as goods or credits elsewhere."),
    # "billed monthly" alone was dropped. On a pricing page it is a toggle
    # label, not a disclosure, and it fired on a page that discloses nothing.
    ("free", r"(after (?:the|your) (?:free )?trial|auto[- ]?renew(?:s|al)?|will be charged|"
             r"then \$?\d[\d,.]* ?(?:per|/|a ) ?(?:month|year|mo\b|yr\b)|"
             r"payment method (?:is )?required|then switch to standard|"
             r"billed (?:monthly|annually) (?:at|from) )",
     "high", "Free is announced and a charge is described elsewhere."),
    ("nofee", r"(processing fee|service fee|transaction fee|handling fee|a fee of|"
              r"fees may apply|plus applicable fees|commission of)",
     "high", "No fee is announced and a fee is named elsewhere."),
    ("unlimited", r"(fair use|acceptable use|subject to (?:a )?(?:limit|cap|throttl)|"
                  r"rate limit|may be throttled|up to \d+ (?:per|requests|gb))",
     "medium", "Unlimited is announced and a ceiling is described elsewhere."),
    ("anyone", r"(only open to|is open only to|must (?:currently )?reside in|"
               r"residents of the|void where prohibited|excluding residents of|"
               r"open to everyone except|must be (?:a )?(?:legal )?resident|"
               r"currently enrolled|students? only)",
     "high", "Open to all is announced and a residency or status condition is set elsewhere."),
    # A refund window is not a delay on a delivery promise. The first version
    # paired "instant setup" with "30 days for a full refund" and was wrong.
    ("instant", r"((?<!refund )within \d+ (?:business )?days(?! of purchase)|"
                r"allow \d+ (?:to \d+ )?(?:business )?days|processing time|"
                r"may take up to \d+|delivered within \d+)",
     "medium", "Immediacy is announced and a delay is stated elsewhere."),
    ("lifetime", r"(for as long as (?:the|we)|we may (?:discontinue|terminate|modify)|"
                 r"subject to change (?:at any time|without notice))",
     "medium", "Permanence is announced and a right to end it is reserved elsewhere."),
    ("cancel", r"(minimum term|commitment period|early termination|non[- ]refundable|no refunds)",
     "high", "Free cancellation is announced and a lock in is described elsewhere."),
    ("guarantee", r"(does not (?:apply|cover)|excludes|at (?:our|its) (?:sole )?discretion|"
                  r"no (?:warranty|guarantee) of|as is)",
     "medium", "A guarantee is announced and carved out elsewhere."),
    # You keep the title, they take a licence that does everything a title does.
    # Found by hand on a contest rulebook the tool had reported as clean.
    ("ownership", r"(perpetual[^.]{0,60}licen[cs]e|irrevocable[^.]{0,60}licen[cs]e|"
                  r"licen[cs]e[^.]{0,80}(?:perpetual|irrevocable|unlimited)|"
                  r"royalty[- ]free[^.]{0,60}(?:sub-?licen[cs]e|derivative works)|"
                  r"grants? [^.]{0,40}(?:unlimited|worldwide)[^.]{0,60}licen[cs]e|"
                  r"assigns? all right)",
     "high", "You are told you keep ownership and you grant a licence that does the same work."),
]

_HARD = [(k, re.compile(p, re.I), sev, why) for k, p, sev, why in HARD_RULES]
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    claim_kind: str
    claim: str
    counter: str
    severity: str
    explanation: str
    source: str
    section: str = ""
    kind: str = "contradiction"     # contradiction, or restriction
    claim_offset: int = -1
    counter_offset: int = -1
    page_length: int = 0

    def to_dict(self):
        d = asdict(self)
        d["distance"] = self.distance()
        return d

    def distance(self):
        """How far apart the promise and its denial sit, as a share of the page.

        The whole thesis of this tool is that a promise and its cancellation are
        separated by a scroll bar. That is an assertion until it carries a
        number, so every finding carries one. None when either side could not be
        located, which happens when a quote was normalised on the way in.
        """
        if self.page_length <= 0 or self.claim_offset < 0 or self.counter_offset < 0:
            return None
        return abs(self.counter_offset - self.claim_offset) / float(self.page_length)


def _dedupe(findings):
    seen, out = set(), []
    for f in sorted(findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.source != "rule")):
        k = (f.claim_kind, " ".join(f.counter.lower().split())[:110])
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


STOP = set("the a an and or of to in on for with your you our we is are be that this it as at "
           "by from any all not no can will may per".split())


def _shares_topic(claim, sentence) -> bool:
    """A counter sentence has to be about the same thing as the promise.

    Added after a false positive that paired an instant setup promise with a
    refund window. Both mentioned a number of days and nothing else, and on a
    long marketing page that is not a coincidence worth reporting.
    """
    a = {w for w in re.findall(r"[a-z]{4,}", claim.context.lower())} - STOP
    b = {w for w in re.findall(r"[a-z]{4,}", sentence.text.lower())} - STOP
    return bool(a & b)


# Rules loose enough that a shared subject is required before reporting.
NEEDS_TOPIC = {"instant", "unlimited", "lifetime", "guarantee"}

# Added 2026-08-30 after a measured false positive, and it is the same mistake
# in a new place. A contest paying $12,000 IN CASH says, in a section headed
# `Free AWS Credits for New Members`, that `AWS Promotional Credits are not
# redeemable for cash`. Both sentences are true, neither denies the other, and
# the tool reported that the prize was not money. A reader who believes it
# skips a contest that really pays. That is the worst direction for this error,
# because the reader never learns they were wrong.
#
# THE GATE. A denial only cancels a money promise when the denial is ABOUT the
# award. Either it sits under a prize heading, or it names the award itself.
# The standard legal wording carries its own subject, `this is not a cash
# prize`, `the award consists of`, so honest disclosures pass unaided. What
# fails is a sentence about a separately named item that happens to share the
# word cash.
NEEDS_PRIZE_SUBJECT = {"cash", "amount"}
PRIZE_SUBJECT = re.compile(r"\b(prizes?|awards?|winnings?|rewards?)\b", re.I)


def _about_the_award(sentence) -> bool:
    return bool(PRIZE_SUBJECT.search(sentence.text)
                or PRIZE_SUBJECT.search(sentence.section or ""))


def by_rules(doc, claims, sents):
    """Search every sentence of the page, not only the quiet ones.

    The first version only looked at blocks flagged as fine print and found
    nothing on real pages, because the denial sits inside the promise block.
    """
    out = []
    for c in claims:
        for kind, rx, sev, why in _HARD:
            if kind != c.kind:
                continue
            for s in sents:
                if " ".join(s.text.lower().split()) == " ".join(c.context.lower().split()):
                    continue                       # a sentence cannot deny itself
                m = rx.search(s.text)
                if not m:
                    continue
                if kind in NEEDS_TOPIC and not _shares_topic(c, s):
                    continue
                if kind in NEEDS_PRIZE_SUBJECT and not _about_the_award(s):
                    continue
                out.append(Finding(
                    claim_kind=c.kind, claim=c.context or c.text, counter=s.excerpt(300),
                    severity=sev, explanation=why, source="rule", section=s.section,
                    claim_offset=doc.locate(c.text), counter_offset=doc.locate(m.group(0)),
                    page_length=len(doc.flat),
                ))
                break
    return out


def _relevant(sents, claim, k: int = 8):
    """Cheap lexical retrieval, with a bonus for sentences that look legal."""
    words = {w for w in re.findall(r"[a-z]{4,}", claim.context.lower())}
    scored = []
    for s in sents:
        sw = set(re.findall(r"[a-z]{4,}", s.text.lower()))
        score = len(words & sw) + (2.0 if s.quiet else 0.0) + 0.002 * len(s.text)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:k]]


PROMPT = """You audit a web page for promises that the same page takes back.

You get ONE prominent claim and several other passages from the SAME page.
Decide whether any passage contradicts, restricts, or nullifies the claim.

Rules you must obey.
- Quote the passage VERBATIM. Copy characters exactly. Never paraphrase a quote.
- Report only a real conflict. A passage that merely adds detail is not a conflict.
- If nothing conflicts, return an empty list.

Return JSON only, a list of objects with keys
  counter       the verbatim quote, at most 300 characters
  severity      one of critical, high, medium, low
  explanation   one sentence in plain language, what the reader loses

CLAIM ({kind}): {claim}

OTHER PASSAGES FROM THE SAME PAGE:
{passages}
"""


# A price table is not a clause. Measured on six live pages, the model layer
# doubles the number of findings, and a good share of what it adds is a pricing
# grid quoted back against a price claim. That is not a contradiction, it is a
# table. A counter has to read like a sentence before it can cancel a promise.
PRIX = re.compile(r"[$€£₹]\s?\d[\d,.]*|\d[\d,.]*\s?(?:USD|EUR|GBP)\b")
CLAUSE = re.compile(r"\b(is|are|was|were|will|shall|may|must|can|cannot|applies|apply|"
                    r"charged|renews?|excluded?|requires?|includes?|means|does|do|"
                    r"subject|entitled|reserved|available|only|unless|after|before|"
                    r"provided that|except)\b", re.I)


def _is_table(text: str) -> bool:
    """A price grid is not a clause.

    Two signals, and the second is the one that actually works. A sentence with
    three or more separate monetary amounts in it is a pricing table that lost
    its columns on the way through the parser, whatever else it contains. The
    digit density test alone let those through, because a grid also carries
    plenty of words.
    """
    if not re.search(r"[A-Za-z]{2,}", text):
        return True
    if len(PRIX.findall(text)) >= 3:
        return True
    digits = sum(ch.isdigit() for ch in text)
    return digits / max(1, len(text)) > 0.10 and not CLAUSE.search(text)


def by_model(doc, claims, sents, model=None, max_claims: int = 12, verbose: bool = False):
    out = []
    for c in claims[:max_claims]:
        cands = _relevant(sents, c)
        if not cands:
            continue
        body = "\n\n".join("[%d] %s" % (i, s.excerpt(400)) for i, s in enumerate(cands))
        prompt = PROMPT.format(kind=c.kind, claim=c.context or c.text, passages=body)
        try:
            raw = llm.chat([{"role": "user", "content": prompt}], model=model)
        except Exception as e:
            if verbose:
                print("  model failed on claim %r, %s" % (c.text, e))
            continue
        items = llm.json_block(raw) or []
        if isinstance(items, dict):
            items = [items]
        for it in items:
            quote = str(it.get("counter", "")).strip()
            if not quote or not doc.contains(quote):
                if verbose and quote:
                    print("  dropped ungrounded quote, %r" % quote[:70])
                continue
            if _is_table(quote):
                if verbose:
                    print("  dropped, reads as a table and not a clause, %r" % quote[:70])
                continue
            out.append(Finding(
                claim_kind=c.kind, claim=c.context or c.text, counter=quote,
                severity=str(it.get("severity", "medium")).lower(),
                explanation=str(it.get("explanation", "")).strip(),
                source="model", claim_offset=doc.locate(c.text),
                counter_offset=doc.locate(quote), page_length=len(doc.flat),
            ))
    return out


def by_restrictions(doc, sents):
    """Quiet requirements that no headline contradicts, and that still cost you.

    Added after the benchmark scored recall 0.29 on "reserved to students".
    See restrictions.py, the shortfall was structural and not a threshold.
    """
    out = []
    for r in _restrictions.find(doc, sents):
        out.append(Finding(
            claim_kind=r["label"], claim="(the page makes no claim to the contrary)",
            counter=r["quote"], severity=r["severity"], explanation=r["explanation"],
            source="rule", section=r["section"], counter_offset=r["offset"],
            page_length=len(doc.flat), kind="restriction",
        ))
    return out


def audit(doc, offline: bool = False, model=None, min_loudness: float = 0.6, verbose: bool = False):
    claims = extract(doc, min_loudness=min_loudness)
    sents = sentences(doc)
    findings = by_rules(doc, claims, sents)
    if not offline and llm.available():
        findings += by_model(doc, claims, sents, model=model, verbose=verbose)
    contradictions = _dedupe(findings)
    quoted = {" ".join(f.counter.lower().split())[:110] for f in contradictions}
    extra = [f for f in by_restrictions(doc, sents)
             if " ".join(f.counter.lower().split())[:110] not in quoted]
    return claims, contradictions + extra
