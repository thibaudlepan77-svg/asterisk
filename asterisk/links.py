# -*- coding: utf-8 -*-
"""Find the pages where the real conditions live.

The single biggest hole in a one page auditor. An offer page rarely contains
the clause that costs you. It contains a small grey link, and the clause is one
click away, on a page nobody opens. Reading the offer page alone and declaring
it clean is worse than useless, because it is reassuring.

So the agent needs to know which links are worth a click and which are not.
This module ranks them, it does not follow them. Following costs a request and
that decision belongs to the caller.
"""
from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse

# Weight per signal in the link text or the target path. Higher is more likely
# to hold a binding clause rather than marketing.
SIGNALS = [
    (r"official\s*rules", 10), (r"\bterms\b", 8), (r"conditions", 7),
    (r"eligibilit", 8), (r"\brules\b", 7), (r"fine\s*print", 9),
    (r"disclaimer", 7), (r"legal", 6), (r"\bpolicy\b", 4),
    (r"pricing", 5), (r"\bfees?\b", 6), (r"refund", 7),
    (r"cancel", 5), (r"privacy", 2), (r"faq", 3),
    (r"how it works", 2), (r"details", 2),
]
NOISE = re.compile(
    r"(facebook|twitter|x\.com|instagram|linkedin|youtube|discord|github\.com/[^/]+$|"
    r"mailto:|tel:|/careers|/blog|/about|/contact|/jobs|/press)", re.I)


def _score(text: str, href: str) -> int:
    blob = ("%s %s" % (text, href)).lower()
    if NOISE.search(blob):
        return 0
    return sum(w for pat, w in SIGNALS if re.search(pat, blob))


def candidates(html: str, base_url: str, limit: int = 6, same_site_only: bool = True):
    """Return [(score, absolute_url, link_text)], best first, deduplicated."""
    host = urlparse(base_url).netloc.lower()
    seen, out = set(), []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        url = urljoin(base_url, href).split("#")[0]
        if same_site_only and urlparse(url).netloc.lower() not in (host, ""):
            continue
        if url.rstrip("/") == base_url.rstrip("/") or url in seen:
            continue
        s = _score(text, url)
        if s <= 0:
            continue
        seen.add(url)
        out.append((s, url, text[:70] or "(no text)"))
    out.sort(key=lambda x: -x[0])
    return out[:limit]
