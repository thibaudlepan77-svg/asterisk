# -*- coding: utf-8 -*-
"""Get the page. Nothing clever, but two things that matter in practice.

A plain request is refused by a lot of commercial sites, so we send the header
set of an ordinary browser. And we cache to disk, because an auditing tool that
hammers a site while you iterate on prompts is a tool that gets you blocked.
"""
from __future__ import annotations
import hashlib
import os
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
CACHE = os.environ.get("ASTERISK_CACHE", os.path.join(os.path.dirname(__file__), "..", ".cache"))


def fetch(url: str, *, use_cache: bool = True, max_age: int = 86400, timeout: int = 40) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if use_cache and os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        with open(path, encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "replace")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def fetch_rendered(url: str, *, timeout_ms: int = 45000) -> str:
    """Fetch with a real browser, for pages that draw themselves in JavaScript.

    Optional on purpose. The deterministic path has no dependencies at all and
    that is worth keeping, so this is imported only when asked for. Two of ten
    ordinary pricing pages we tested return a one line shell to a plain
    request, and reporting "nothing found" on those is the worst thing this
    tool could do.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "browser mode needs playwright, pip install playwright "
            "&& python -m playwright install chromium") from e
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="en-US",
                                  viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            html = page.content()
        finally:
            ctx.close()
            browser.close()
    return html


def get(url: str, *, browser: bool = False, use_cache: bool = True) -> str:
    """One entry point. Plain fetch, or a rendered one when asked."""
    if not browser:
        return fetch(url, use_cache=use_cache)
    import hashlib
    import os as _os
    _os.makedirs(CACHE, exist_ok=True)
    path = _os.path.join(CACHE, "r" + hashlib.sha256(url.encode()).hexdigest()[:23] + ".html")
    if use_cache and _os.path.exists(path) and time.time() - _os.path.getmtime(path) < 86400:
        with open(path, encoding="utf-8") as f:
            return f.read()
    html = fetch_rendered(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return html
