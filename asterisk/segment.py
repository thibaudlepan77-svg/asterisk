# -*- coding: utf-8 -*-
"""Cut a page into positioned lines and decide which ones are fine print.

The product rests on one asymmetry. A promise is displayed loudly and early.
The clause that cancels it is displayed quietly, or under a heading nobody
clicks. So we never ask a model whether a page is misleading. We hand it a
LOUD span and a QUIET span from the same page and let it compare the two.

Three things had to be learned the hard way on real pages.

1. Modern markup shatters a sentence. The currency symbol, the digits and the
   words "in cash" often live in three sibling elements. A tokeniser that
   keeps them apart finds no claims at all. So adjacent fragments are merged
   back into lines before anything is matched.
2. Real pages nest twelve to sixteen levels deep. Any prominence score that
   divides by depth collapses to zero everywhere. Depth is only meaningful
   RELATIVE to the rest of the page.
3. Fine print is not defined by size, it is defined by SECTION. Everything
   under a heading called Rules, Terms or Eligibility is fine print however
   large the font.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

HEADINGS = {"h1": 5.0, "h2": 4.0, "h3": 3.0, "h4": 2.2, "h5": 1.8, "h6": 1.6}
EMPHASIS = {"strong": 1.6, "b": 1.6, "em": 1.3, "title": 5.0}

LEGAL_SECTION = re.compile(
    r"(official rules|^rules$|terms|conditions|disclaimer|legal|fine\s*print|"
    r"eligibilit|restrictions|privacy|small\s*print|warrant|liabilit)", re.I)
QUIET_HINTS = re.compile(
    r"(subject to|void where prohibited|see (?:full |official )?(?:details|rules|terms)|"
    r"terms (?:and conditions )?apply|not redeemable|no purchase necessary|"
    r"at (?:our|the sponsor) (?:sole )?discretion)", re.I)

SKIP_TAGS = {"nav", "footer", "script", "style", "noscript", "svg", "select", "option"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "path", "use"}


@dataclass
class Line:
    text: str
    start: int
    end: int
    tag: str = "p"
    depth: int = 0
    index: int = 0
    section: str = ""
    loudness: float = 0.0
    fine_print: bool = False

    def excerpt(self, n: int = 240) -> str:
        t = " ".join(self.text.split())
        return t if len(t) <= n else t[: n - 1] + "…"


@dataclass
class Document:
    url: str
    flat: str
    lines: list = field(default_factory=list)

    @property
    def blocks(self):
        return self.lines

    def loud(self):
        return [b for b in self.lines if not b.fine_print]

    def quiet(self):
        return [b for b in self.lines if b.fine_print]

    def looks_unreadable(self, min_lines: int = 12, min_chars: int = 900) -> bool:
        """True when the page almost certainly did not render for us.

        The most dangerous failure this tool can have is not a wrong finding,
        it is a confident "nothing found" on a page it never actually read.
        Client rendered pricing pages arrive as a shell of one or two lines.
        Silence about those is indistinguishable from a clean bill of health,
        so the caller has to be able to tell the two apart.
        """
        return len(self.lines) < min_lines or len(self.flat) < min_chars

    def contains(self, quote: str) -> bool:
        """The grounding gate. A finding may only cite text that is really here."""
        return _norm(quote) in _norm(self.flat)

    def locate(self, quote: str) -> int:
        return _norm(self.flat).find(_norm(quote))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


_ENT = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&#39;": "'", "&apos;": "'", "&mdash;": ", ", "&ndash;": ", ", "&hellip;": "..."}


def _unescape(s: str) -> str:
    for k, v in _ENT.items():
        s = s.replace(k, v)
    return re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)


def _tokenise(html: str):
    """Yield (text, tag, depth) for every text node, skipping page chrome."""
    html = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    stack = []
    for token in re.split(r"(<[^>]+>)", html):
        if not token:
            continue
        if token.startswith("<"):
            m = re.match(r"</?\s*([a-zA-Z0-9]+)", token)
            if not m:
                continue
            tag = m.group(1).lower()
            if token.startswith("</"):
                if tag in stack:
                    while stack and stack.pop() != tag:
                        pass
            elif not token.endswith("/>") and tag not in VOID:
                stack.append(tag)
            continue
        if any(t in SKIP_TAGS for t in stack):
            continue
        text = re.sub(r"\s+", " ", _unescape(token)).strip()
        if not text:
            continue
        tag = next((t for t in reversed(stack) if t in HEADINGS), None)
        if tag is None:
            tag = next((t for t in reversed(stack) if t in EMPHASIS), "p")
        yield text, tag, len(stack)


JOIN_TIGHT_LEFT = ("$", "€", "£", "₹", "(")
JOIN_TIGHT_RIGHT = (",", ".", "%", ")")


def _merge(raw, max_len: int = 420):
    """Glue shattered fragments back into readable lines.

    A fragment joins the current line while the line is short, the depth is
    close, and neither side is a heading. Enough to rebuild a price, a
    sentence or a bullet, without gluing a whole section into one blob.
    """
    out = []
    for text, tag, depth in raw:
        if out:
            ptext, ptag, pdepth = out[-1]
            heading_here = tag in HEADINGS or ptag in HEADINGS
            joinable = (not heading_here
                        and abs(depth - pdepth) <= 3
                        and len(ptext) + len(text) < max_len
                        and not ptext.endswith((".", "!", "?", ":")))
            if joinable:
                glue = "" if (text.startswith(JOIN_TIGHT_RIGHT) or ptext.endswith(JOIN_TIGHT_LEFT)) else " "
                keep = ptag if (ptag in HEADINGS or ptag in EMPHASIS) else tag
                out[-1] = (ptext + glue + text, keep, min(depth, pdepth))
                continue
        out.append((text, tag, depth))
    return out


def segment(html: str, url: str = "") -> Document:
    merged = _merge(list(_tokenise(html)))
    if not merged:
        return Document(url=url, flat="", lines=[])

    depths = sorted(d for _, _, d in merged)
    median_depth = depths[len(depths) // 2]

    lines = []
    flat_parts = []
    cursor = 0
    section = ""
    for i, (text, tag, depth) in enumerate(merged):
        if tag in HEADINGS and len(text) < 120:
            section = text
        start = cursor
        cursor += len(text) + 1
        flat_parts.append(text)
        lines.append(Line(text=text, start=start, end=cursor - 1, tag=tag,
                          depth=depth, index=i, section=section))

    n = max(1, len(lines) - 1)
    for b in lines:
        base = HEADINGS.get(b.tag) or EMPHASIS.get(b.tag) or 1.0
        over = max(0, b.depth - median_depth)
        rank = b.index / n
        b.loudness = base * (1.0 - 0.30 * rank) / (1.0 + 0.06 * over)
        b.fine_print = bool(
            LEGAL_SECTION.search(b.section or "")
            or QUIET_HINTS.search(b.text)
            or (len(b.text) > 260 and b.tag == "p" and rank > 0.35)
        )
    return Document(url=url, flat=" ".join(flat_parts), lines=lines)
