# -*- coding: utf-8 -*-
"""A self contained HTML report, one file, no server, no assets.

The terminal output is for a pipeline. This is for a person who has just been
told that the offer they were about to accept says two different things, and
who now has to decide. So it shows the two halves side by side, in the order
that matters, with the distance between them, and it says plainly when it could
not read the page.

Everything is inlined. The file can be mailed, attached to a complaint, or kept
as a dated record of what an offer said on the day you accepted it.
"""
from __future__ import annotations
import html as _h
import time

from .report import verdict

CSS = """
:root{--ink:#12161c;--dim:#5f6a78;--line:#e4e8ee;--bg:#fbfcfd;
      --crit:#c0392b;--high:#c8641b;--med:#9a7b12;--low:#5f6a78;--ok:#1f6f4a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.55;
     font:16px/1.55 -apple-system,'Segoe UI',Inter,Helvetica,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:52px 26px 90px}
h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}
.sub{color:var(--dim);font-size:15px;word-break:break-all}
.verdict{margin:26px 0 6px;padding:18px 22px;border-radius:12px;border:1px solid var(--line);
         background:#fff;font-size:19px;font-weight:600}
.verdict.bad{border-color:#f0c4bd;background:#fdf5f4;color:var(--crit)}
.verdict.warn{border-color:#f2dcc2;background:#fdf9f4;color:var(--high)}
.verdict.ok{border-color:#c8e6d5;background:#f4fbf7;color:var(--ok)}
h2{font-size:14px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
   margin:44px 0 14px;font-weight:700}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin:0 0 16px}
.head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.badge{font-size:11.5px;font-weight:800;letter-spacing:.1em;padding:4px 9px;border-radius:999px;
       color:#fff;background:var(--low)}
.badge.critical{background:var(--crit)}.badge.high{background:var(--high)}
.badge.medium{background:var(--med)}
.why{font-weight:650;font-size:17px}
.meta{color:var(--dim);font-size:13px;margin-left:auto}
.pair{display:grid;grid-template-columns:96px 1fr;gap:10px 16px;align-items:start}
.k{color:var(--dim);font-size:12px;letter-spacing:.1em;text-transform:uppercase;padding-top:3px}
.q{border-left:3px solid var(--line);padding-left:14px;font-size:15.5px}
.q.deny{border-left-color:var(--crit)}
.note{color:var(--dim);font-size:13.5px;margin-top:34px;border-top:1px solid var(--line);padding-top:18px}
.blind{border:1px solid #f0c4bd;background:#fdf5f4;border-radius:12px;padding:20px 22px;color:var(--crit)}
ul.checked{columns:2;font-size:14px;color:var(--dim);padding-left:18px}
"""


def _e(s):
    return _h.escape(s or "")


def _verdict_class(findings):
    v = verdict(findings)
    if "contradicts" in v:
        return "bad"
    if "restricts" in v or "serious condition" in v:
        return "warn"
    return "ok"


def _card(f, is_restriction=False):
    d = f.distance()
    meta = []
    meta.append("found by a rule" if f.source == "rule" else "found by a model, quote verified")
    if d is not None:
        meta.append("%.0f %% of the page apart" % (100 * d))
    body = ['<div class="card"><div class="head">'
            '<span class="badge %s">%s</span>'
            '<span class="why">%s</span>'
            '<span class="meta">%s</span></div>'
            % (_e(f.severity), _e(f.severity.upper()), _e(f.explanation), _e(" &middot; ".join(meta)))]
    body[0] = body[0].replace("&amp;middot;", "&middot;")
    if is_restriction:
        body.append('<div class="pair"><div class="k">it says</div>'
                    '<div class="q deny">%s</div></div>' % _e(f.counter))
    else:
        body.append('<div class="pair">'
                    '<div class="k">it promises</div><div class="q">%s</div>'
                    '<div class="k">and it says</div><div class="q deny">%s</div>'
                    '</div>' % (_e(f.claim), _e(f.counter)))
    body.append('</div>')
    return "".join(body)


def render(url: str, claims, findings, unreadable: bool = False) -> str:
    contra = [f for f in findings if getattr(f, "kind", "contradiction") == "contradiction"]
    restr = [f for f in findings if getattr(f, "kind", "contradiction") == "restriction"]
    now = time.strftime("%Y-%m-%d %H:%M")

    out = ["<!doctype html><html lang=en><meta charset=utf-8>",
           "<meta name=viewport content='width=device-width,initial-scale=1'>",
           "<title>Asterisk, %s</title><style>%s</style><main>" % (_e(url), CSS),
           "<h1>Asterisk</h1>",
           "<div class=sub>%s<br>read %s</div>" % (_e(url), now)]

    if unreadable:
        out.append("<div class=blind><b>This page did not render.</b><br>"
                   "Almost no text came back, which usually means the content is drawn by the "
                   "browser. What follows is a report on an empty page, and that is not the "
                   "same thing as a clean bill of health. Run it again with a rendered "
                   "fetch.</div></main></html>")
        return "".join(out)

    out.append('<div class="verdict %s">%s</div>' % (_verdict_class(findings), _e(verdict(findings))))
    out.append('<div class=sub>%d prominent claims checked, %d contradictions, '
               '%d quiet conditions.</div>' % (len(claims), len(contra), len(restr)))

    if contra:
        out.append("<h2>Where the page takes back what it announced</h2>")
        out += [_card(f) for f in contra]
    if restr:
        out.append("<h2>Quiet conditions, nothing promised otherwise and they bind you anyway</h2>")
        out += [_card(f, True) for f in restr]
    if not findings:
        out.append('<div class=card>Nothing found. That is a result, not a failure. No promise '
                   'on this page is contradicted by anything else on it, and no clause matched '
                   'a known restriction.</div>')

    if claims:
        out.append("<h2>What it looked at</h2><ul class=checked>")
        out += ["<li>%s</li>" % _e(c.context[:120] or c.text) for c in claims[:24]]
        out.append("</ul>")

    out.append('<div class=note>Every quote above was checked, character for character, against '
               'the text of the page before it was written here. A finding that could not be '
               'pointed at was dropped rather than shown.</div>')
    out.append("</main></html>")
    return "".join(out)
