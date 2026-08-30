# -*- coding: utf-8 -*-
"""The audit as one call, with no user interface attached.

Split out of the demo for a reason worth stating. The demo README said the
front end had not been run, and a repository about unbacked claims should not
leave a claim resting on nothing. The audit logic now lives here, where a test
can call it without starting a server, and the front end is a shell around it.

Anything a web page, a bot, or an agent needs from this project goes through
`audit_url`.
"""
from __future__ import annotations

from . import fetch, llm
from .audit import audit
from .segment import segment

BADGE = {"critical": "\U0001F534 CRITICAL", "high": "\U0001F7E0 HIGH",
         "medium": "\U0001F7E1 MEDIUM", "low": "⚪ LOW"}


class Result(dict):
    """A plain dict, so it serialises anywhere without a schema."""


def audit_url(url: str, *, browser: bool = False, model: bool = True) -> Result:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return Result(ok=False, error="Give me a full address, starting with http.")
    try:
        html = fetch.get(url, browser=browser)
    except Exception as e:                       # noqa: BLE001, the shapes vary by provider
        return Result(ok=False, error="Could not fetch that page. %s" % e)

    doc = segment(html, url)
    if doc.looks_unreadable():
        return Result(ok=False, rendered=False, url=url,
                      error="This page did not render. Almost no text came back, which usually "
                            "means the content is drawn by the browser. That is blindness, not "
                            "a clean bill of health. Try again with a rendered fetch.")

    claims, findings = audit(doc, offline=not (model and llm.available()))
    return Result(
        ok=True, rendered=True, url=url,
        claims=[{"kind": c.kind, "text": c.context or c.text} for c in claims],
        contradictions=[f.to_dict() for f in findings
                        if getattr(f, "kind", "contradiction") == "contradiction"],
        restrictions=[f.to_dict() for f in findings
                      if getattr(f, "kind", "contradiction") == "restriction"],
    )


def as_markdown(r: Result) -> str:
    """One report a person reads in ten seconds. Used by the front end."""
    if not r.get("ok"):
        return "### %s" % r.get("error", "Something went wrong.")
    out = ["### %d prominent claims checked" % len(r["claims"])]
    if not r["contradictions"] and not r["restrictions"]:
        out.append("\nNothing found. That is a result, not a failure. No promise on this page "
                   "is contradicted by anything else on it, and no clause matched a known "
                   "restriction.")
    if r["contradictions"]:
        out.append("\n## Contradictions\n")
        for f in r["contradictions"]:
            far = ("  ·  %.0f %% of the page apart" % (100 * f["distance"])) if f.get("distance") else ""
            out.append("**%s %s**%s\n\n> **it promises** %s\n>\n> **and it says** %s\n"
                       % (BADGE.get(f["severity"], f["severity"].upper()), f["explanation"], far,
                          f["claim"][:400], f["counter"][:400]))
    if r["restrictions"]:
        out.append("\n## Quiet conditions\n")
        out.append("Nothing on the page promised otherwise, and these bind you anyway.\n")
        for f in r["restrictions"]:
            out.append("- **%s** %s  \n  > %s"
                       % (BADGE.get(f["severity"], f["severity"].upper()),
                          f["explanation"], f["counter"][:300]))
    out.append("\n---\n_Every quote above was checked against the page text before it was shown._")
    return "\n".join(out)
