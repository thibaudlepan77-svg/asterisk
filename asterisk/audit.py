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
    ("amount", r"(this is not a cash prize|cannot be exchanged or redeemed for cash|"
               r"approximate retail value|\barv\b|in (?:product |sponsor-provided )?credits|"
               r"consists of sponsor-provided)",
     "high", "The sum is shown as money and described as goods or credits elsewhere."),
    ("free", r"(after (?:the|your) (?:free )?trial|auto[- ]?renew|will be charged|"
             r"billed (?:monthly|annually|automatically)|payment method (?:is )?required|"
             r"then \$?\d+(?:\.\d+)? ?(?:per|/) ?(?:month|year))",
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
    ("instant", r"(within \d+ (?:business )?days|allow \d+ (?:to \d+ )?(?:business )?days|"
                r"processing time|may take up to|delivered within \d+)",
     "medium", "Immediacy is announced and a delay is stated elsewhere."),
    ("lifetime", r"(for as long as (?:the|we)|we may (?:discontinue|terminate|modify)|"
                 r"subject to change (?:at any time|without notice))",
     "medium", "Permanence is announced and a right to end it is reserved elsewhere."),
    ("cancel", r"(minimum term|commitment period|early termination|non[- ]refundable|no refunds)",
     "high", "Free cancellation is announced and a lock in is described elsewhere."),
    ("guarantee", r"(does not (?:apply|cover)|excludes|at (?:our|its) (?:sole )?discretion|"
                  r"no (?:warranty|guarantee) of|as is)",
     "medium", "A guarantee is announced and carved out elsewhere."),
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

    def to_dict(self):
        return asdict(self)


def _dedupe(findings):
    seen, out = set(), []
    for f in sorted(findings, key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.source != "rule")):
        k = (f.claim_kind, " ".join(f.counter.lower().split())[:110])
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


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
                out.append(Finding(
                    claim_kind=c.kind, claim=c.context or c.text, counter=s.excerpt(300),
                    severity=sev, explanation=why, source="rule", section=s.section,
                    claim_offset=doc.locate(c.text), counter_offset=doc.locate(m.group(0)),
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
            out.append(Finding(
                claim_kind=c.kind, claim=c.context or c.text, counter=quote,
                severity=str(it.get("severity", "medium")).lower(),
                explanation=str(it.get("explanation", "")).strip(),
                source="model", claim_offset=doc.locate(c.text),
                counter_offset=doc.locate(quote),
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
            kind="restriction",
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
