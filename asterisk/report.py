# -*- coding: utf-8 -*-
"""Turn findings into something a human reads in ten seconds.

Two sections, because they answer two different questions.
  CONTRADICTIONS  where does this page fight itself
  RESTRICTIONS    what does this page quietly require of me
"""
from __future__ import annotations
import json

BADGE = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def _split(findings):
    contra = [f for f in findings if getattr(f, "kind", "contradiction") == "contradiction"]
    restr = [f for f in findings if getattr(f, "kind", "contradiction") == "restriction"]
    return contra, restr


def verdict(findings) -> str:
    contra, restr = _split(findings)
    if any(f.severity == "critical" for f in contra):
        return "the page contradicts its own headline"
    if any(f.severity == "high" for f in contra):
        return "the fine print materially restricts the headline"
    if any(f.severity in ("critical", "high") for f in restr):
        return "no contradiction, but a serious condition is set quietly"
    if findings:
        return "minor conditions found"
    return "nothing found"


def as_json(url: str, claims, findings, unreadable: bool = False) -> str:
    contra, restr = _split(findings)
    return json.dumps({
        "url": url,
        "page_rendered": not unreadable,
        "verdict": "page did not render, result not meaningful" if unreadable else verdict(findings),
        "claims_checked": [{"kind": c.kind, "text": c.text, "context": c.context} for c in claims],
        "contradictions": [f.to_dict() for f in contra],
        "restrictions": [f.to_dict() for f in restr],
    }, ensure_ascii=False, indent=2)


def as_text(url: str, claims, findings, width: int = 96, unreadable: bool = False) -> str:
    contra, restr = _split(findings)
    out = ["=" * width, "ASTERISK  " + url, "=" * width]
    if unreadable:
        out.append("")
        out.append("!! THIS PAGE DID NOT RENDER FOR US. Almost no text came back, which usually")
        out.append("!! means the content is drawn by the browser. Anything below is a report on")
        out.append("!! an empty page, NOT a clean bill of health. Retry with --browser.")
        out.append("")
    out.append("%d prominent claims checked. %d contradictions, %d quiet conditions."
               % (len(claims), len(contra), len(restr)))
    out.append("Verdict, " + verdict(findings))

    if contra:
        out.append("")
        out.append("CONTRADICTIONS, where the page takes back what it announced")
        for i, f in enumerate(contra, 1):
            out.append("")
            out.append("-" * width)
            out.append("%d. [%s] %s" % (i, BADGE.get(f.severity, f.severity.upper()), f.explanation))
            d = f.distance()
            loin = ("   %s apart, as a share of the page"
                    % _pct(d)) if d is not None else ""
            out.append("   found by   %s%s" % ("deterministic rule" if f.source == "rule"
                                               else "model, quote verified against the page", loin))
            out.append("   PROMISE    %s" % _wrap(f.claim, width - 14))
            out.append("   FINE PRINT %s" % _wrap(f.counter, width - 14))

    if restr:
        out.append("")
        out.append("QUIET CONDITIONS, nothing on the page promised otherwise, and they still bind you")
        for i, f in enumerate(restr, 1):
            out.append("")
            out.append("-" * width)
            out.append("%d. [%s] %s  (%s)" % (i, BADGE.get(f.severity, f.severity.upper()),
                                              f.explanation, f.claim_kind))
            out.append("   QUOTED     %s" % _wrap(f.counter, width - 14))

    if not findings:
        out.append("")
        out.append("Nothing to report. That is a result, not a failure.")
        return "\n".join(out)

    out.append("")
    out.append("-" * width)
    out.append("Every quote above was checked against the page text before printing.")
    return "\n".join(out)


def _pct(d: float) -> str:
    return "%.0f %%" % (100 * d)


def _wrap(s: str, width: int) -> str:
    s = " ".join(s.split())
    lines, cur = [], ""
    for w in s.split(" "):
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    return ("\n" + " " * 14).join(lines)
