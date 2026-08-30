# -*- coding: utf-8 -*-
"""Asterisk as an agent, built on the Strands Agents SDK.

Why an agent and not just the command line tool. The tool reads one page. The
clause that actually costs you is very often not on that page, it is behind a
small grey link that nobody clicks, and a one page auditor that reports
"nothing found" on such an offer is worse than useless because it reassures.

Deciding which links deserve a request, when the picture is complete, and when
one more page would add nothing, is a judgement call on content the tool has
not read yet. That is the part worth an agent. Everything the agent asserts
still has to survive the same grounding gate, so the loop can wander but the
output cannot drift.

    python agent.py https://example.com/offer
    python agent.py https://example.com/offer --max-pages 4
"""
from __future__ import annotations
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strands import Agent, tool                     # noqa: E402
from strands.models.openai import OpenAIModel       # noqa: E402

from asterisk import fetch, links, guard            # noqa: E402
from asterisk.audit import audit                    # noqa: E402
from asterisk.segment import segment                # noqa: E402

_SEEN: dict[str, dict] = {}


@tool
def audit_page(url: str) -> str:
    """Audit one page for contradictions and quiet conditions.

    Returns JSON with the claims checked, the contradictions found, and the
    quiet conditions found. Every quote is verbatim from that page.

    Args:
        url: absolute URL of the page to audit.
    """
    try:
        html = fetch.fetch(url)
    except Exception as e:
        return json.dumps({"url": url, "error": "could not fetch, %s" % e})
    doc = segment(html, url)
    claims, findings = audit(doc, offline=True)     # rules only inside a tool call
    _SEEN[url] = {"html": html, "doc": doc}
    return json.dumps({
        "url": url,
        "claims_checked": len(claims),
        "contradictions": [
            {"severity": f.severity, "why": f.explanation,
             "promise": f.claim[:200], "quote": f.counter[:280]}
            for f in findings if getattr(f, "kind", "contradiction") == "contradiction"],
        "quiet_conditions": [
            {"severity": f.severity, "what": f.claim_kind, "why": f.explanation,
             "quote": f.counter[:280]}
            for f in findings if getattr(f, "kind", "contradiction") == "restriction"],
    }, ensure_ascii=False)


@tool
def find_condition_pages(url: str) -> str:
    """List links on a page that are likely to hold binding conditions.

    Use this when a page looks clean, because the clause that matters is often
    one click away. Returns a ranked list, best first, with a score.

    Args:
        url: absolute URL of the page whose links you want ranked.
    """
    try:
        html = _SEEN[url]["html"] if url in _SEEN else fetch.fetch(url)
    except Exception as e:
        return json.dumps({"url": url, "error": "could not fetch, %s" % e})
    ranked = links.candidates(html, url)
    return json.dumps({"url": url,
                       "links": [{"score": s, "url": u, "text": t} for s, u, t in ranked]},
                      ensure_ascii=False)


@tool
def verify_quote(url: str, quote: str) -> str:
    """Check that a quote really appears on a page, character for character.

    Use before writing any quote into your answer. Anything this returns false
    for must not be shown to the reader.

    Args:
        url: the page the quote is supposed to come from.
        quote: the exact text you intend to show.
    """
    if url not in _SEEN:
        try:
            html = fetch.fetch(url)
            _SEEN[url] = {"html": html, "doc": segment(html, url)}
        except Exception as e:
            return json.dumps({"grounded": False, "reason": "could not fetch, %s" % e})
    return json.dumps({"grounded": bool(_SEEN[url]["doc"].contains(quote))})


SYSTEM = """You read an offer the way a careful person would if they had time.

Your job is to tell one reader what they are actually agreeing to.

The audit of the starting page is ALREADY DONE and given to you in the task.
Do not skip it, do not re-run it, and do not answer as if it were empty.

How to work.
1. Read the audit you were handed. Its findings are part of your answer.
2. Ask for the condition pages of the starting page. A clean offer page means
   nothing on its own, the binding clause is usually one click away. Audit the
   best ranked ones until the picture stops changing or the budget runs out.
3. Stop early when another page would add nothing. Say so.

How to answer.
- Lead with the single thing that would change the reader's mind.
- Quote verbatim, and call verify_quote before you show any quote.
- If you find nothing, say that plainly. It is a result, not a failure.
- No hedging, no marketing tone, no advice on whether to sign. Facts and quotes.
- Name the page each quote came from.
"""


def build_model():
    """Any OpenAI compatible endpoint. Nebius Token Factory by default."""
    base = os.environ.get("ASTERISK_BASE_URL", "https://api.tokenfactory.nebius.com/v1")
    model = os.environ.get("ASTERISK_MODEL", "nvidia/NVIDIA-Nemotron-3-Super")
    key = (os.environ.get("ASTERISK_API_KEY") or os.environ.get("NEBIUS_API_KEY")
           or os.environ.get("OPENAI_API_KEY"))
    if not key:
        raise SystemExit("No API key. Set ASTERISK_API_KEY, or use cli.py --offline "
                         "for the deterministic report without an agent.")
    return OpenAIModel(client_args={"api_key": key, "base_url": base}, model_id=model)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Agentic fine print audit across an offer and its condition pages.")
    p.add_argument("url")
    p.add_argument("--max-pages", type=int, default=4)
    a = p.parse_args(argv)

    # The first audit is deterministic on purpose. An earlier build let the
    # model decide when to run it, and the model skipped the starting page and
    # reported that a page with three contradictions on it was clean. Anything
    # that can be decided without judgement should not be left to judgement.
    first = audit_page(a.url)

    agent = Agent(model=build_model(), tools=[audit_page, find_condition_pages, verify_quote],
                  system_prompt=SYSTEM, callback_handler=None)
    task = ("Tell me what I would actually be agreeing to at %s\n\n"
            "The audit of that page is already done, here it is.\n%s\n\n"
            "Budget, at most %d pages in total including this one. Now look for its "
            "condition pages and audit the ones that could change the picture."
            % (a.url, first, a.max_pages))
    result = agent(task)
    answer = str(result)

    # The last line of defence, and the one that actually holds. A tool that
    # lets the model attest to its own output has verified nothing. This runs
    # after the final token, on the text the reader will see.
    pages = {u: v["doc"].flat for u, v in _SEEN.items()}
    checks = guard.check(answer, pages)
    print(guard.annotate(answer, checks))
    return 1 if any(c.status == "unsupported" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
