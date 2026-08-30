# -*- coding: utf-8 -*-
"""The live demo. Paste an offer page, get both halves back.

Deliberately small. The interesting parts of this project are in the engine and
in the two gates, not here, and a demo that hides the engine behind a pretty
shell would be the wrong thing to build for a tool about hidden things.

Runs anywhere that serves a Gradio app.

    pip install gradio
    python demo/app.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr                                   # noqa: E402

from asterisk import fetch, llm                       # noqa: E402
from asterisk.audit import audit                      # noqa: E402
from asterisk.segment import segment                  # noqa: E402

EXAMPLES = [
    ["https://gibc-v2.devpost.com/"],
    ["https://www.spotify.com/us/premium/"],
    ["https://www.revolut.com/our-pricing-plans/"],
    ["https://www.shopify.com/pricing"],
]

BADGE = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "⚪ LOW"}


def run(url: str, use_browser: bool, use_model: bool):
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Give me a full address, starting with http.", ""
    try:
        html = fetch.get(url, browser=use_browser)
    except Exception as e:
        return "Could not fetch that page. %s" % e, ""

    doc = segment(html, url)
    if doc.looks_unreadable():
        return ("### This page did not render\n\n"
                "Almost no text came back, which usually means the content is drawn by the "
                "browser. **This is not a clean bill of health, it is blindness.** Tick "
                "*render in a browser* and try again.", "")

    claims, findings = audit(doc, offline=not (use_model and llm.available()))
    contra = [f for f in findings if getattr(f, "kind", "contradiction") == "contradiction"]
    restr = [f for f in findings if getattr(f, "kind", "contradiction") == "restriction"]

    out = ["### %d prominent claims checked" % len(claims)]
    if not findings:
        out.append("\nNothing found. That is a result, not a failure. It means no promise on "
                   "this page is contradicted by anything else on it, and no clause on it "
                   "matched a known restriction.")
    if contra:
        out.append("\n## Contradictions\n")
        for f in contra:
            out.append("**%s %s**  \n"
                       "_found by %s_\n\n"
                       "> **it promises** %s\n>\n"
                       "> **and it says** %s\n"
                       % (BADGE.get(f.severity, f.severity.upper()), f.explanation,
                          "a deterministic rule" if f.source == "rule" else "a model, quote verified",
                          f.claim[:400], f.counter[:400]))
    if restr:
        out.append("\n## Quiet conditions\n")
        out.append("Nothing on the page promised otherwise, and these bind you anyway.\n")
        for f in restr:
            out.append("- **%s** %s  \n  > %s"
                       % (BADGE.get(f.severity, f.severity.upper()), f.explanation, f.counter[:300]))
    out.append("\n---\n_Every quote above was checked against the page text before it was shown._")

    inspected = "\n".join("- `%s`  %s" % (c.kind, c.context[:150]) for c in claims[:20])
    return "\n".join(out), inspected or "no prominent claim found"


with gr.Blocks(title="Asterisk", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# Asterisk\n"
        "**Read the asterisk before you read the promise.**\n\n"
        "Paste an offer page. You get back the promises it makes loudly, and the sentences "
        "elsewhere on the same page that take them back or quietly bind you. Every line is "
        "copied from the page, and a finding that cannot be pointed at is dropped before you "
        "see it."
    )
    with gr.Row():
        url = gr.Textbox(label="Page to audit", placeholder="https://example.com/pricing", scale=4)
        go = gr.Button("Audit", variant="primary", scale=1)
    with gr.Row():
        br = gr.Checkbox(label="render in a browser, for pages drawn in JavaScript", value=False)
        ml = gr.Checkbox(label="use the model layer as well as the rules", value=True)
    report = gr.Markdown()
    with gr.Accordion("what it looked at", open=False):
        looked = gr.Markdown()
    gr.Examples(EXAMPLES, inputs=[url])
    go.click(run, inputs=[url, br, ml], outputs=[report, looked])
    url.submit(run, inputs=[url, br, ml], outputs=[report, looked])

if __name__ == "__main__":
    demo.launch()
