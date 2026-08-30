# -*- coding: utf-8 -*-
"""Build the demo video from slides and a synthetic voice.

Everything here is local and free. Slides are HTML rendered by a headless
browser, narration comes from edge-tts, and ffmpeg cuts each slide to the exact
length of the sentence spoken over it. No editing timeline to drift out of sync
with the script, because the script IS the timeline.

    python make_video.py            build everything
    python make_video.py --slides   only redraw the slides
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "build")
VOICE = "en-US-AndrewNeural"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{width:1920px;height:1080px;background:#0e1116;color:#e8ecf1;
     font-family:'Segoe UI',Inter,Helvetica,Arial,sans-serif;
     display:flex;flex-direction:column;justify-content:center;padding:110px 130px}
h1{font-size:78px;line-height:1.06;font-weight:700;letter-spacing:-.02em}
h2{font-size:44px;line-height:1.18;font-weight:600;color:#9fb0c4;margin-bottom:44px}
p{font-size:38px;line-height:1.45;color:#c3ccd8;margin-top:26px;max-width:1500px}
.kicker{font-size:24px;letter-spacing:.22em;text-transform:uppercase;color:#5d8fb3;
        font-weight:700;margin-bottom:34px}
.big{font-size:150px;font-weight:800;letter-spacing:-.03em;color:#fff}
.warn{color:#ff8a7a}.ok{color:#6fd39b}.dim{color:#7d8896}
pre{font-family:'Cascadia Mono',Consolas,monospace;font-size:27px;line-height:1.48;
    background:#080a0e;border:1px solid #232a34;border-radius:14px;padding:34px 38px;
    color:#cfd8e3;white-space:pre-wrap;margin-top:30px}
.q{border-left:7px solid #ff8a7a;padding:18px 0 18px 34px;margin-top:34px;
   font-size:40px;line-height:1.4;color:#ffd9d2}
.row{display:flex;gap:34px;margin-top:34px}
.card{flex:1;background:#141922;border:1px solid #232a34;border-radius:16px;padding:34px}
.card b{font-size:34px;display:block;margin-bottom:14px}
.card span{font-size:29px;color:#9fb0c4;line-height:1.4}
img{max-width:100%;max-height:720px;border-radius:14px;margin-top:24px;background:#fff}
footer{position:absolute;bottom:58px;left:130px;font-size:24px;color:#5c6673;letter-spacing:.05em}
"""

SLIDES = [
    ("the number",
     """<div class="kicker">30 august 2026</div>
        <h1>I ranked contests by prize<br>divided by entrants.</h1>
        <div class="row"><div class="card"><b class="big">$149,525</b><span>in cash, said the listing</span></div>
        <div class="card"><b class="big">513</b><span>people registered</span></div></div>""",
     "I was ranking online contests by prize divided by entrants. This one topped the list "
     "by a factor of five. A hundred and forty nine thousand dollars, in cash, five hundred "
     "and thirteen people registered."),

    ("the same page",
     """<div class="kicker">on that same page, fifteen times</div>
        <h1>Under every prize tier.</h1>
        <div class="q">THIS IS NOT A CASH PRIZE. This award consists of sponsor-provided
        product credits, subscriptions, software licenses, domains, or other non-cash
        benefits and cannot be exchanged or redeemed for cash.</div>
        <p class="dim">The real cash was zero. Nothing was hidden.</p>""",
     "Under every prize tier on that same page, fifteen times, it says this is not a cash "
     "prize, and that nothing can be exchanged or redeemed for cash. The real cash was zero. "
     "Nothing was hidden. I had simply read the number and not the page."),

    ("the problem",
     """<div class="kicker">the shape of it</div>
        <h1>A number in one place.<br>Its cancellation in another.</h1>
        <div class="row">
          <div class="card"><b>Free<span class="warn">*</span></b><span>then charged</span></div>
          <div class="card"><b>Unlimited<span class="warn">*</span></b><span>then capped</span></div>
          <div class="card"><b>No fees<span class="warn">*</span></b><span>until a fee</span></div>
        </div>
        <p>With a scroll bar in between.</p>""",
     "This is not fraud and usually not even a lie. It is a number in one place and its "
     "cancellation in another, with a scroll bar in between. Free that becomes charged. "
     "Unlimited that becomes capped. No fees, until a fee."),

    ("what it does",
     """<div class="kicker">asterisk</div>
        <h2>Both halves, side by side.</h2>
        <pre>1. [CRITICAL] The page calls the sum cash and then says it is not.
   found by   deterministic rule
   PROMISE    Online Public $149,525 in cash 513 participants
   FINE PRINT This award consists of sponsor-provided product credits,
              subscriptions, software licenses, domains, or other
              non-cash benefits and cannot be exchanged or redeemed
              for cash.</pre>""",
     "Asterisk reads the offer and shows you both halves. The promise, and the sentence that "
     "takes it back. Every line it prints is copied from the page. A finding it cannot point "
     "at is dropped before you see it."),

    ("quiet conditions",
     """<div class="kicker">and the other half</div>
        <h1>What no headline<br>ever contradicted.</h1>
        <pre>QUIET CONDITIONS, nothing on the page promised otherwise,
and they still bind you

1. [HIGH] Entry is reserved to students.
2. [HIGH] It renews by itself unless you act.
3. [HIGH] You cannot get your money back.
4. [HIGH] You hand over rights on what you submit.</pre>""",
     "It also reports what no headline contradicts. Reserved to students. Renews by itself. "
     "Non refundable. Nothing promised otherwise, and it binds you anyway."),

    ("the agent",
     """<div class="kicker">strands agents</div>
        <h1>One page is not enough.</h1>
        <p>The clause that costs you is usually behind a small grey link.
        The agent ranks the links that could hold binding conditions, follows the ones
        worth a request, and stops when another page would add nothing.</p>
        <pre>find_condition_pages  ->  official rules   score 10
                          ->  terms of service score  8
                          ->  eligibility      score  8</pre>""",
     "One page is not enough. The clause that costs you is usually behind a small grey link. "
     "Built on Strands Agents, it ranks the links that could hold binding conditions, follows "
     "the ones worth a request, and stops when another page would add nothing."),

    ("the failure",
     """<div class="kicker">the failure that shaped it</div>
        <h1>It verified its own quote.<br>Then it changed it.</h1>
        <pre>[grounding] 3 quotes checked, 2 exact, <span class="warn">1 altered</span>, 0 unsupported.
  <span class="warn">ALTERED</span>   the answer wrote
            software licences, domains, or other non-cash benefits
            the page says
            software <span class="ok">licenses</span>, domains, or other non-cash benefits</pre>
        <p>So verification moved to after the last token.</p>""",
     "It had a tool to verify its own quotes. It called it. It passed. And its answer still "
     "respelled the quote, and labelled it verified. So verification moved to after the last "
     "token, on the text you actually read. An altered quote is now shown as altered, next to "
     "what the page really says."),

    ("the numbers",
     """<div class="kicker">held out set</div>
        <h2>40 pages drawn at random from 13,632 finished contests,<br>
        pages the rules were never written against.</h2>
        <pre>students_only      tp  4  fp  0  fn  0  tn 36
                   precision <span class="ok">1.00</span>  recall <span class="ok">1.00</span>  f1 <span class="ok">1.00</span>

prize_is_not_cash  no positive case in this set.
                   false alarms <span class="ok">0</span> on 40 pages</pre>""",
     "On forty pages drawn at random from thirteen thousand finished contests, pages the rules "
     "were never written against, it finds every restricted one and raises no false alarm on "
     "the rest. The tables and the script that prints them are in the repository."),

    ("watching",
     """<div class="kicker">an offer is a moving thing</div>
        <h1>10 &rarr; 1, in thirty five minutes.</h1>
        <p>One contest's published count of cash prizes changed that morning.
        Its prize page did not. Nobody was told.</p>
        <pre><span class="dim">example output, not a captured run</span>
WHAT CHANGED, an offer is a moving thing
Compared with the snapshot taken 2026-08-30 07:31:02, 3 stored.
  <span class="warn">APPEARED</span>     Subscriptions renew automatically unless cancelled
  <span class="warn">REWORDED</span>     91 % the same
               was  paid <span class="ok">within 30 days</span> of the announcement
               now  paid <span class="warn">within 90 days</span> of the announcement</pre>""",
     "And an offer is a moving thing. One contest's published count of cash prizes went from "
     "ten to one in thirty five minutes that same morning. Its prize page had not changed, and "
     "nobody was told. So it keeps a snapshot, and every run after that reports what moved. A "
     "rewording is matched, because thirty days becoming ninety is one event, and it is the "
     "interesting one."),

    ("the limit",
     """<div class="kicker">the limit I will not hide</div>
        <h1>Silence and a clean bill<br>look identical.</h1>
        <pre class="warn">!! THIS PAGE DID NOT RENDER FOR US. Almost no text came back,
!! which usually means the content is drawn by the browser.
!! Anything below is a report on an empty page,
!! NOT a clean bill of health. Retry with --browser.</pre>""",
     "Two pages in ten draw their prices in the browser. On those, a plain fetch sees nothing, "
     "and reporting nothing found would be the worst thing this tool could do. So it says so, "
     "loudly, and exits with its own code."),

    ("close",
     """<div class="kicker">mit licensed</div>
        <h1>Asterisk.</h1>
        <h2>Read the asterisk before you read the promise.</h2>
        <p class="ok">github.com/thibaudlepan77-svg/asterisk</p>""",
     "Asterisk. Read the asterisk before you read the promise. MIT licensed, and the "
     "measurements are rerunnable."),
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def draw_slides():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        for i, (name, body, _) in enumerate(SLIDES):
            html = ("<html><head><meta charset='utf-8'><style>%s</style></head><body>%s"
                    "<footer>asterisk &nbsp;&middot;&nbsp; %s</footer></body></html>"
                    % (CSS, body, name))
            path = os.path.join(OUT, "s%02d.html" % i)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            pg.goto("file:///" + path.replace("\\", "/"))
            pg.wait_for_timeout(180)
            pg.screenshot(path=os.path.join(OUT, "s%02d.png" % i))
            print("slide %02d  %s" % (i, name))
        b.close()


def speak():
    os.makedirs(OUT, exist_ok=True)
    for i, (_, _, text) in enumerate(SLIDES):
        mp3 = os.path.join(OUT, "a%02d.mp3" % i)
        run([sys.executable, "-m", "edge_tts", "--voice", VOICE, "--rate=-4%",
             "--text", text, "--write-media", mp3])
        print("voice %02d  %.1f s" % (i, duration(mp3)))


def duration(path: str) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "json", path]).stdout
    return float(json.loads(out)["format"]["duration"])


def assemble():
    parts = []
    for i in range(len(SLIDES)):
        png = os.path.join(OUT, "s%02d.png" % i)
        mp3 = os.path.join(OUT, "a%02d.mp3" % i)
        mp4 = os.path.join(OUT, "p%02d.mp4" % i)
        d = duration(mp3) + 0.65          # a beat of silence after each sentence
        run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-i", mp3,
             "-f", "lavfi", "-t", "%.3f" % d, "-i", "anullsrc=r=44100:cl=stereo",
             "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest[a]",
             "-map", "0:v", "-map", "[a]",
             "-c:v", "libx264", "-t", "%.3f" % d, "-pix_fmt", "yuv420p", "-r", "25",
             "-c:a", "aac", "-b:a", "160k", "-shortest", mp4])
        parts.append(mp4)
        print("part %02d  %.1f s" % (i, d))
    lst = os.path.join(OUT, "parts.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    final = os.path.join(HERE, "asterisk-demo.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", final])
    print("\nvideo, %s, %.1f s" % (final, duration(final)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", action="store_true")
    ap.add_argument("--voice", action="store_true")
    a = ap.parse_args(argv)
    if a.slides:
        return draw_slides() or 0
    if a.voice:
        return speak() or 0
    draw_slides()
    speak()
    assemble()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
