# -*- coding: utf-8 -*-
"""Check the quotes in the final answer, not just the ones inside the tools.

This module exists because of a specific failure that is easy to miss and
embarrassing to ship. The agent had a verify_quote tool, it called it, and its
final answer still said

    "sponsor-provided product credits, subscriptions, software licences"

where the page says `licenses`. It also turned `organizations` into
`organisations`. Every one of those lines was labelled "verified". The model
had verified the real string and then written a tidied one, because tidying
prose is what a language model does.

The lesson generalises past spelling. A tool that lets a model attest to its
own output has not verified anything. **Verification has to happen after the
last token the model writes, on the text the reader will actually see.**

So this runs on the finished answer. Every quoted span is looked up in the
pages that were fetched. Exact match passes. A near match is reported as
altered, with the true wording. No match at all is reported as unsupported.
"""
from __future__ import annotations
import difflib
import re
from dataclasses import dataclass

# Straight and curly quotes, plus the markdown blockquote form.
QUOTED = re.compile(r"[\"“«]([^\"”»\n]{25,400})[\"”»]")


@dataclass
class Checked:
    quote: str
    status: str
    source_url: str = ""
    actual: str = ""
    ratio: float = 0.0


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‑", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def _best_window(quote: str, haystack: str):
    """Closest substring of the same length, so we can show the true wording."""
    q, h = _norm(quote), _norm(haystack)
    n = len(q)
    if n == 0 or n > len(h):
        return 0.0, ""
    best, at = 0.0, 0
    step = max(1, n // 8)
    for i in range(0, len(h) - n + 1, step):
        r = difflib.SequenceMatcher(None, q, h[i:i + n]).quick_ratio()
        if r > best:
            best, at = r, i
    lo, hi = max(0, at - n), min(len(h), at + 2 * n)
    r2, at2 = best, at
    for i in range(lo, hi - n + 1):
        r = difflib.SequenceMatcher(None, q, h[i:i + n]).ratio()
        if r > r2:
            r2, at2 = r, i
    return r2, h[at2:at2 + n]


def check(answer: str, pages: dict, altered_threshold: float = 0.82):
    """pages maps url to the flattened page text. Returns a list of Checked."""
    out = []
    for m in QUOTED.finditer(answer):
        quote = m.group(1).strip()
        exact_url = next((u for u, t in pages.items() if _norm(quote) in _norm(t)), None)
        if exact_url:
            out.append(Checked(quote=quote, status="exact", source_url=exact_url, ratio=1.0))
            continue
        best = (0.0, "", "")
        for u, t in pages.items():
            r, actual = _best_window(quote, t)
            if r > best[0]:
                best = (r, actual, u)
        if best[0] >= altered_threshold:
            out.append(Checked(quote=quote, status="altered", source_url=best[2],
                               actual=best[1], ratio=best[0]))
        else:
            out.append(Checked(quote=quote, status="unsupported", ratio=best[0]))
    return out


def annotate(answer: str, checks) -> str:
    """Append a verification block. The reader sees what survived and what did not."""
    if not checks:
        return answer + "\n\n[grounding] no quotes to check in this answer."
    bad = [c for c in checks if c.status != "exact"]
    lines = ["", "-" * 72,
             "[grounding] %d quotes checked against the fetched pages, %d exact, %d altered, %d unsupported."
             % (len(checks), sum(c.status == "exact" for c in checks),
                sum(c.status == "altered" for c in checks),
                sum(c.status == "unsupported" for c in checks))]
    for c in bad:
        if c.status == "altered":
            lines.append("  ALTERED   the answer wrote")
            lines.append("            %s" % c.quote[:150])
            lines.append("            the page says")
            lines.append("            %s" % c.actual[:150])
        else:
            lines.append("  UNSUPPORTED, no page contains this, best match %.2f" % c.ratio)
            lines.append("            %s" % c.quote[:150])
    if not bad:
        lines.append("  every quote is character for character what the page says.")
    return answer + "\n".join(lines)
