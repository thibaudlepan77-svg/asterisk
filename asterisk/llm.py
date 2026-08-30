# -*- coding: utf-8 -*-
"""Thin client for any OpenAI-compatible endpoint.

Defaults point at Nebius Token Factory with an NVIDIA Nemotron model, which is
what this project is built for. Nothing else in the codebase knows the vendor,
so pointing it somewhere else is two environment variables.
"""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("ASTERISK_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
DEFAULT_MODEL = os.environ.get("ASTERISK_MODEL", "nvidia/NVIDIA-Nemotron-3-Super")
KEY_VARS = ("ASTERISK_API_KEY", "NEBIUS_API_KEY", "OPENAI_API_KEY")


class NoCredentials(RuntimeError):
    pass


def api_key() -> str:
    for v in KEY_VARS:
        k = os.environ.get(v)
        if k:
            return k
    raise NoCredentials(
        "No API key. Set one of " + ", ".join(KEY_VARS) + ". "
        "Run with --offline to use the deterministic detector only."
    )


def available() -> bool:
    return any(os.environ.get(v) for v in KEY_VARS)


def chat(messages: list[dict], *, model: str | None = None, temperature: float = 0.0,
         max_tokens: int = 900, retries: int = 3, timeout: int = 90) -> str:
    body = json.dumps({
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        DEFAULT_BASE.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
            # Some providers sit behind a bot filter that rejects a request with
            # no browser-like agent, and answers 403 error code 1010 rather than
            # anything about authentication. Cost one debugging round.
            "User-Agent": "asterisk/0.1 (+https://github.com/) python-urllib",
            "Accept": "application/json",
        },
    )
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.load(r)
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.read()[:300]!r}"
            if e.code in (400, 401, 403, 404):
                break            # a wrong key or model will not fix itself
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:      # noqa: BLE001 - network shape varies
            last = f"{type(e).__name__} {e}"
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"inference failed after {retries} attempts, last error {last}")


def json_block(text: str):
    """Models wrap JSON in prose and fences. Pull the first real object out."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0], default=-1)
    if start < 0:
        return None
    depth, opening = 0, text[start]
    closing = "]" if opening == "[" else "}"
    for i in range(start, len(text)):
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
