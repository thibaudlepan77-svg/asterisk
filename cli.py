# -*- coding: utf-8 -*-
"""asterisk, command line entry point.

    python cli.py https://example.com/offer
    python cli.py --offline page.html
    python cli.py --json https://example.com/offer > report.json
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asterisk import fetch, report, watch               # noqa: E402
from asterisk.audit import audit                        # noqa: E402
from asterisk.segment import segment                    # noqa: E402
from asterisk import llm                                # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Find where a page's fine print takes back its headline.")
    p.add_argument("target", help="a URL, or a path to a saved HTML file")
    p.add_argument("--offline", action="store_true", help="deterministic rules only, no inference call")
    p.add_argument("--json", action="store_true", help="machine readable output")
    p.add_argument("--model", default=None, help="model id, defaults to %s" % llm.DEFAULT_MODEL)
    p.add_argument("--loudness", type=float, default=0.6, help="how prominent a claim must be to be checked")
    p.add_argument("--watch", action="store_true",
                   help="store a snapshot and report what changed since the last one")
    p.add_argument("--browser", action="store_true",
                   help="render the page in a real browser, for sites drawn in JavaScript")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    if os.path.exists(a.target):
        with open(a.target, encoding="utf-8", errors="replace") as f:
            html = f.read()
        url = a.target
    else:
        url = a.target
        try:
            html = fetch.get(url, browser=a.browser, use_cache=not a.no_cache)
        except Exception as e:
            print("could not fetch %s, %s" % (url, e), file=sys.stderr)
            return 2

    doc = segment(html, url)
    blind = doc.looks_unreadable()
    if blind and not a.browser:
        print("this page returned almost no text, retrying in a browser would be wise",
              file=sys.stderr)
    offline = a.offline or not llm.available()
    if offline and not a.offline and a.verbose:
        print("no API key found, running deterministic rules only", file=sys.stderr)
    claims, findings = audit(doc, offline=offline, model=a.model,
                             min_loudness=a.loudness, verbose=a.verbose)
    print(report.as_json(url, claims, findings, unreadable=blind) if a.json
          else report.as_text(url, claims, findings, unreadable=blind))
    if a.watch and not blind:
        d, _ = watch.diff(url, claims, findings)
        watch.save(url, claims, findings)
        print("")
        print("-" * 96)
        print("WHAT CHANGED, an offer is a moving thing")
        print(watch.render(d))
    if blind:
        return 2
    return 1 if any(f.severity in ("critical", "high") for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
