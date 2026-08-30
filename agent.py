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
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry  # noqa: E402
from strands.models.openai import OpenAIModel       # noqa: E402

from asterisk import fetch, links, guard            # noqa: E402
from asterisk.budget import PageBudget              # noqa: E402
from asterisk.audit import audit, _relevant         # noqa: E402
from asterisk.claims import extract                 # noqa: E402
from asterisk.segment import segment                # noqa: E402
from asterisk.sentences import sentences            # noqa: E402

_SEEN: dict[str, dict] = {}


@tool
def audit_page(url: str) -> str:
    """Audit one page for contradictions and quiet conditions.

    Returns the contradictions the deterministic rules found, the quiet
    conditions, and the promises the rules could NOT settle together with the
    passages most likely to bear on them. Judge those yourself. Every quote is
    verbatim from that page.

    Args:
        url: absolute URL of the page to audit.
    """
    try:
        html = fetch.fetch(url)
    except Exception as e:
        return json.dumps({"url": url, "error": "could not fetch, %s" % e})
    doc = segment(html, url)
    claims, findings = audit(doc, offline=True)
    _SEEN[url] = {"html": html, "doc": doc}

    # What the rules settled, and what they left open. The second list is the
    # reason this is a tool for an agent and not a script. The formulas only
    # cover the wordings that consumer law standardised, and most of the
    # world's fine print was written by a marketing team instead.
    settled = {" ".join(f.claim.lower().split()) for f in findings}
    sents = sentences(doc)
    unsettled = []
    for c in claims[:10]:
        if " ".join((c.context or c.text).lower().split()) in settled:
            continue
        unsettled.append({
            "promise": (c.context or c.text)[:220],
            "kind": c.kind,
            "candidate_passages": [s.excerpt(280) for s in _relevant(sents, c, k=4)],
        })
    if doc.looks_unreadable():
        return json.dumps({"url": url, "page_rendered": False,
                           "warning": "this page returned almost no text, it is drawn by the "
                                      "browser. Do not report it as clean, say it could not be read."},
                          ensure_ascii=False)
    return json.dumps({
        "url": url,
        "page_rendered": True,
        "claims_checked": len(claims),
        "unsettled_by_rules": unsettled,
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
    # THIS USED TO FETCH THE PAGE IF IT HAD NOT BEEN READ, and that was a hole
    # straight through the page budget. The budget hook guards `audit_page`, so
    # a model that wanted a fifth page only had to ask this tool to check a
    # quote from it. Found while writing the hook, by asking which other tool
    # touches the network. **A limit that one door enforces and another ignores
    # is not a limit.**
    #
    # Refusing also happens to be the correct answer. You cannot quote a page
    # you never read, and a check that silently reads it first is not checking
    # the claim, it is manufacturing the evidence for it.
    if url not in _SEEN:
        return json.dumps({
            "grounded": False,
            "reason": "that page has not been audited in this run, so nothing can be "
                      "checked against it. Audit it first, within your budget, or drop "
                      "the quote."})
    return json.dumps({"grounded": bool(_SEEN[url]["doc"].contains(quote))})


class Budget(HookProvider):
    """Enforces the page budget in the framework, not in the prompt.

    The task text used to say `Budget, at most 4 pages in total` and nothing
    checked it. **A tool that reports where a page contradicts its own headline
    had a headline its own agent could contradict.** The budget now lives in a
    `BeforeToolCall` hook, where `cancel_tool` turns a refusal into a refusal.

    The decision itself is in `asterisk/budget.py`, testable without a model,
    a network or an agent. This class is the adapter and holds no rule.
    """

    def __init__(self, limit: int):
        self.budget = PageBudget(limit)
        self.refused: list[str] = []

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before_tool)

    def before_tool(self, event: BeforeToolCallEvent) -> None:
        name = (event.tool_use or {}).get("name")
        if name != "audit_page":
            return                      # ranking links and checking a quote cost nothing
        url = ((event.tool_use or {}).get("input") or {}).get("url", "")
        motif = self.budget.decide(url)
        if motif:
            self.refused.append(url)
            event.cancel_tool = motif


SYSTEM = """You read an offer the way a careful person would if they had time.

Your job is to tell one reader what they are actually agreeing to.

The audit of the starting page is ALREADY DONE and given to you in the task.
Do not skip it, do not re-run it, and do not answer as if it were empty.

How to work.
1. Read the audit you were handed. Its findings are part of your answer.
2. Read `unsettled_by_rules`. Those are promises the deterministic rules could
   not settle, each with the passages most likely to bear on them. Decide
   yourself whether any passage cancels its promise. Most will not, and saying
   so is correct. This is the part no pattern can do for you.
3. Ask for the condition pages of the starting page. A clean offer page means
   nothing on its own, the binding clause is usually one click away. Audit the
   best ranked ones until the picture stops changing or the budget runs out.
4. Stop early when another page would add nothing. Say so.
5. If a page reports page_rendered false, say it could not be read. Never
   report such a page as clean.

How to answer.
- Lead with the single thing that would change the reader's mind.
- Quote verbatim, and call verify_quote before you show any quote.
- If you find nothing, say that plainly. It is a result, not a failure.
- No hedging, no marketing tone, no advice on whether to sign. Facts and quotes.
- Name the page each quote came from.
"""


def build_model():
    """Any OpenAI compatible endpoint, set by two environment variables."""
    base = os.environ.get("ASTERISK_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("ASTERISK_MODEL", "gpt-4o-mini")
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

    # The starting page is spent from the budget before the agent runs, because
    # it has already been fetched above. Counting it afterwards would let the
    # agent read one page more than the caller asked for, silently.
    budget = Budget(a.max_pages)
    budget.budget.decide(a.url)

    agent = Agent(model=build_model(), tools=[audit_page, find_condition_pages, verify_quote],
                  system_prompt=SYSTEM, callback_handler=None, hooks=[budget])
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
    print("\n%s. %d tool call(s) refused by the budget."
          % (budget.budget.summary(), len(budget.refused)))
    return 1 if any(c.status == "unsupported" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
