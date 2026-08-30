# -*- coding: utf-8 -*-
"""The live demo, a shell around asterisk.service.

Deliberately thin. Everything it does is one call to `audit_url`, which is
tested without a server in tests_asterisk.py. A front end that carried logic of
its own would be logic nobody could test, in a project about claims that rest
on nothing.

    pip install gradio
    python demo/app.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr                                        # noqa: E402

from asterisk.service import audit_url, as_markdown        # noqa: E402

EXAMPLES = [
    ["https://gibc-v2.devpost.com/"],
    ["https://www.spotify.com/us/premium/"],
    ["https://www.revolut.com/our-pricing-plans/"],
    ["https://www.shopify.com/pricing"],
]

BLURB = (
    "# Asterisk\n"
    "**Read the asterisk before you read the promise.**\n\n"
    "Paste an offer page. You get back the promises it makes loudly, and the sentences "
    "elsewhere on the same page that take them back or quietly bind you. Every line is "
    "copied from the page, and a finding that cannot be pointed at is dropped before you "
    "see it."
)


def run(url: str, use_browser: bool, use_model: bool):
    r = audit_url(url, browser=use_browser, model=use_model)
    looked = "\n".join("- `%s`  %s" % (c["kind"], c["text"][:150])
                       for c in r.get("claims", []))
    return as_markdown(r), looked or "no prominent claim found"


with gr.Blocks(title="Asterisk", theme=gr.themes.Soft()) as demo:
    gr.Markdown(BLURB)
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
