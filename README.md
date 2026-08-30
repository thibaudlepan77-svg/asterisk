# Asterisk

**Read the asterisk before you read the promise.**

Asterisk takes a web page and reports two things.

1. **Contradictions.** Where the page announces something loudly and takes it
   back quietly, somewhere else on the same page.
2. **Quiet conditions.** What the page requires of you without ever promising
   otherwise, so no contradiction detector would catch it.

Every line it prints is a verbatim quote from the page. A finding that cannot
be pointed at is dropped before you see it.

MIT licensed. The deterministic half has no dependencies at all. The model half
speaks the OpenAI chat completions shape, so it runs against any endpoint that
does, set by two environment variables. It was developed and measured against
an OpenAI compatible endpoint serving `openai/gpt-oss-120b`, and that is the
configuration the numbers below come from. Nothing in the code knows a vendor.

---

## Why it exists

On 30 August 2026 I was comparing open online contests, ranking them by prize
divided by number of entrants, looking for the best place to spend a month of
work. One entry topped the ranking by a wide margin. It advertised

> **$149,525 in prizes**

and its machine readable listing declared **five cash prizes**. Five hundred
and twelve people had registered. On paper it was the best opportunity on the
board by a factor of five.

Its own prize section says, fifteen times, under every single tier

> ⚠️ THIS IS NOT A CASH PRIZE. This award consists of sponsor-provided product
> credits, subscriptions, software licenses, domains, or other non-cash
> benefits and cannot be exchanged or redeemed for cash.

The real cash was zero. The number I was ranking on had been typed in by the
person who benefits from it being large, and the page contradicted it in plain
sight, in the one place the law forces an advertiser to tell the truth.

Then it got worse. I read the long legal rules of twenty two contests by hand
and published a figure, twelve of them open to an adult in my country. When I
pointed the first working build of this tool at the same twenty two pages, it
came back with `Students only` on pages I had cleared myself three hours
earlier. The real number was eight, not twelve. **The tool's first useful act
was to correct its own author.**

That is the problem. Not fraud, and usually not even a lie. A number in one
place and its cancellation in another, with a scroll bar in between.

---

## What it does, on a real page

```
$ python cli.py https://gibc-v2.devpost.com/

13 prominent claims checked. 3 contradictions, 0 quiet conditions.
Verdict, the page contradicts its own headline

CONTRADICTIONS, where the page takes back what it announced

1. [CRITICAL] The page calls the sum cash and then says it is not.
   found by   deterministic rule
   PROMISE    ... Online Public $149,525 in cash 513 participants ...
   FINE PRINT This award consists of sponsor-provided product credits,
              subscriptions, software licenses, domains, or other non-cash
              benefits and cannot be exchanged or redeemed for cash.

3. [HIGH] Open to all is announced and a residency or status condition is set
   elsewhere.
   found by   deterministic rule
   PROMISE    GIBC V1 brought together 552 participants worldwide with backing
              from sponsors including NordVPN.
   FINE PRINT Ages 13+ only Students only Companies/professional organizations
              excluded from participation
```

The count of quiet conditions is zero here on purpose. The students clause was
already reported above as a contradiction, because this page does claim to be
worldwide, so reporting it twice would pad the output. Quiet conditions are for
what nothing on the page contradicts.

![architecture](docs/architecture.png)

---

## How it works

Four stages. The interesting decisions are in the middle two, and both of them
came from a measurement that said the first design was wrong.

**1. Segment** (`asterisk/segment.py`). The page is cut into lines and each
line is scored for prominence from its tag, its nesting depth relative to the
rest of the page, and its position. Two things had to be learned on real
pages. Modern markup shatters a sentence, so `$`, `149,525` and `in cash`
arrive as three sibling elements and any matcher that keeps them apart finds
nothing at all. And real pages nest twelve to sixteen levels deep, so a
prominence score that divides by absolute depth collapses to zero everywhere.

**2. Sentences** (`asterisk/sentences.py`). The first design compared a loud
block with a quiet block. It scored zero on live pages, because the clause
that cancels a promise is very often in the **same** block, two sentences
later. The unit that carries a contradiction is the sentence.

**3. Detect** (`asterisk/audit.py`, `asterisk/restrictions.py`). Two layers.

- A deterministic layer with no model at all. Consumer law imposes the exact
  wording of the disclaimers that matter, so they can be matched exactly. It
  is free, instant, and it invents nothing.
- A model layer for everything the formulas miss, because most of the world's
  fine print was never standardised. This is where a model reads a claim
  against candidate passages and judges whether one cancels the other. On the
  contest page below it is the layer that caught a second denial the rules had
  no formula for, `THIS COMPETITION DOES NOT HAVE CASH PRIZE` sitting on the
  same page as `$292 in cash 500 winners`.

**4. Ground** (`Document.contains`). The gate the model cannot argue with.
Any quote the model returns is checked, character for character, against the
page. If it is not there, the finding is discarded and never reaches the
report. This is the only defence against a confident summary of something the
page never said.

---

## Results

Two evaluations. Both run from this repository, both on live pages, and the
labels for both are checkable by anyone who opens the page.

### Development set, 22 pages the rules were written against

| label | precision | recall | F1 |
|---|---|---|---|
| prize is not cash | 0.75 | 1.00 | 0.86 |
| reserved to students | 1.00 | 1.00 | 1.00 |

```
python eval/run_eval.py --offline --show-errors
```

The single false positive is a page whose main prize is real cash and whose
side prize is cloud credits. The tool quoted `AWS Promotional Credits are not
redeemable for cash`, which is true and worth knowing. The label is binary and
the page is not. That is a limit of the label, and it is left in the table
rather than tuned away.

### Held out set, 40 pages never read while writing the rules

Drawn at random from a pool of 13,632 finished contests, labelled by two
targeted extractors that share no code with the auditor.

| label | result |
|---|---|
| reserved to students | precision 1.00, recall 1.00, on 4 positives and 36 negatives |
| prize is not cash | no positive case in this set, 0 false alarms on 40 pages |

```
python eval/build_holdout.py 40      # draws a fresh random sample and labels it
python eval/run_eval.py --holdout --offline
```

Two honest remarks about that table.

The students rule was **tightened because of this set**, not before it. The
first version matched a bare `currently enrolled` and fired on a page that used
the phrase to invite school pupils to write in, not to exclude anyone. A
restriction has to be phrased as a restriction. That one false positive is the
only thing the held out set changed, and it is worth more than the score.

The second row is not a score, it is a silence, and the difference matters. No
page in the held out set carries the non-cash disclaimer, so the row can only
tell you the detector does not cry wolf. It is also a hint worth a sentence.
Three of the twenty two contests running **today** carry that disclaimer, and
none of the forty finished ones drawn across the platform's whole history do.
That looks like a recent practice. With three cases it is a hypothesis, not a
finding, and it is written here as one.

### Off its home ground, ten ordinary consumer offers

Everything above is contest pages. The README claimed the method generalises,
so the claim was tested rather than repeated. Ten public pricing and offer
pages from music, storage, hosting, VPN, banking, email, design, video, code
hosting and commerce. No labels, so this is a read of what the tool says and
whether a human agrees, not a score.

What it found, and these are real.

| offer | quoted back at it |
|---|---|
| music subscription | `Try 3 months of Premium Individual for $0, then $12.99/month.` |
| online bank, against a no fee claim | `A fee of 2% (or minimum fee £1) applies per transaction after your rolling monthly limit` |
| commerce platform | `After your trial, most plans start at just $1 per month for the first 3 months, then switch to standard monthly pricing.` |
| email, against unlimited | `The Proton Mail Free plan comes with 500 MB of Mail storage` |
| commerce, against unlimited | `Import unlimited orders from marketplaces 50 synced marketplace orders per month` |

What it got wrong on the first pass, and what changed.

- It paired an **instant setup** promise with a **thirty day refund window**.
  Both say a number of days and mean opposite things. Weak rules now require
  the two sentences to share a subject word, and refund windows became their
  own category with their own wording.
- It read `billed monthly` off a **pricing toggle** and called it a charge
  disclosure. Dropped.
- It matched `in credits` inside **Built-in credits** and paired a plan price
  with a feature bullet. The phrase now needs a verb of payment in front of it.

**And the gap that mattered most, now closed.** Two of the ten pages draw
their prices in the browser, so a plain fetch sees a one line shell and the
tool honestly finds nothing in nothing. Reporting that as "nothing found" is
the worst thing this tool could do, because silence and a clean bill of health
look identical to a reader.

So the tool now refuses to be silent about it.

```
$ python cli.py --offline https://www.canva.com/pricing/

!! THIS PAGE DID NOT RENDER FOR US. Almost no text came back, which usually
!! means the content is drawn by the browser. Anything below is a report on
!! an empty page, NOT a clean bill of health. Retry with --browser.
```

It exits with code 2 in that case, distinct from 0 for clean and 1 for a
finding, and the JSON output carries `page_rendered: false`. Adding
`--browser` renders the page properly, and the same Canva page goes from one
claim to eight. The browser path is optional and imported only when asked for,
because the deterministic path having zero dependencies is worth keeping.

---

## The agent, and the failure that shaped it

`cli.py` reads one page. That is not enough, and pretending otherwise is the
dangerous part. The clause that costs you is usually not on the offer page, it
is behind a small grey link, and a one page auditor that answers "nothing
found" on such an offer is worse than useless because it reassures.

`agent.py` is built on the **Strands Agents SDK**. It audits the offer, ranks
the links that could hold binding conditions, follows the ones worth a request
inside a page budget, and stops when another page would add nothing.

```bash
pip install strands-agents openai
export ASTERISK_API_KEY=...
export ASTERISK_BASE_URL=https://your-provider.example/v1
export ASTERISK_MODEL=the-model-id
python agent.py https://example.com/offer --max-pages 4
```

Two things in that loop were built after watching it fail.

**The first audit is not the agent's decision.** In the first build the model
was told to audit the starting page and then look further. It went straight to
the linked pages, found them clean, and reported that a page carrying three
contradictions had none. So the starting audit now runs deterministically and
its result is handed to the model. Anything that can be decided without
judgement should not be left to judgement.

**A tool that lets a model attest to its own output has verified nothing.**
The agent had a `verify_quote` tool. It called it. Its answer still read

> sponsor-provided product credits, subscriptions, software **licences**

where the page says `licenses`, and turned `organizations` into
`organisations`, with every line labelled verified. The model had checked the
real string and then written a tidied one, because tidying prose is what a
language model does.

So verification moved to where it cannot be talked around. `asterisk/guard.py`
runs **after the last token**, on the text the reader will see. It pulls every
quoted span out of the answer and looks it up in the pages that were actually
fetched.

```
[grounding] 3 quotes checked against the fetched pages, 2 exact, 1 altered, 0 unsupported.
  ALTERED   the answer wrote
            software licences, domains, or other non-cash benefits
            the page says
            software licenses, domains, or other non-cash benefits
```

An answer containing an unsupported quote exits non zero. The four tests in
`tests_asterisk.py` under `OutputGrounding` are witness tests, they feed the
guard a respelled quote and an invented one and require it to refuse both. A
gate that has never refused anything proves nothing.

---

## Install and run

No dependencies beyond the Python standard library for the deterministic path.

```bash
git clone <this repo>
cd asterisk
python cli.py --offline https://example.com/offer     # rules only, no API call
```

For the model layer, point it at any OpenAI compatible endpoint.

```bash
export ASTERISK_API_KEY=...
export ASTERISK_BASE_URL=https://your-provider.example/v1
export ASTERISK_MODEL=the-model-id
python cli.py https://example.com/offer
```

Pages are cached on disk so that iterating on prompts does not hammer
somebody's site.

One portability note that cost a debugging round. Some providers sit behind a
bot filter that answers **403 with error code 1010** to a request carrying no
browser like agent, and says nothing about authentication. The client sends a
`User-Agent` for that reason.

```
python cli.py --json URL          machine readable output
python cli.py --offline URL       deterministic layer only
python cli.py --browser URL       render in a real browser first
python cli.py --loudness 0.4 URL  check less prominent claims too
python cli.py file.html           audit a saved page
```

Exit codes, 0 nothing found, 1 a critical or high contradiction, 2 the page did
not render so the result means nothing. It drops into a shell pipeline or a CI
check without extra glue, and the third code exists so that a monitor cannot
mistake blindness for a clean result.

---

## What it does not do, stated plainly

- **It is not a lie detector.** It finds a promise and a clause that disagree.
  Deciding whether that is deception, a legal necessity, or sloppy copywriting
  is the reader's job, and the tool gives them the two quotes to do it with.
- **It reads one page.** A condition kept on a separate terms page, behind a
  login, or rendered only by client side script is invisible to it today.
- **The deterministic layer is English first.** The legal formulas it matches
  are the English ones. The model layer is not language bound, the rules are.
- **The development set is small and specialised.** Twenty two contest pages.
  The held out set widens it, and neither is a survey of the web.
- **It reads what a browser would show, not what a login would show.** Prices
  behind an account, a geofence or a paywall are out of reach.
- **A false negative is silent.** The tool proves that something is on the
  page. It never proves that nothing else is.

---

## Layout

```
asterisk/segment.py       page to prominence scored lines
asterisk/sentences.py     lines to quotable sentences
asterisk/claims.py        the promises worth checking
asterisk/audit.py         contradictions, rules and model, with the grounding gate
asterisk/restrictions.py  quiet conditions that no headline contradicts
asterisk/links.py         which links could hold a binding clause, ranked
asterisk/guard.py         verifies the quotes in the FINAL answer, after the model
asterisk/report.py        text and JSON output
asterisk/llm.py           any OpenAI compatible endpoint
eval/                     labelled pages, scorer, held out set builder
cli.py                    one page, deterministic entry point
agent.py                  multi page agent on the Strands Agents SDK
tests_asterisk.py         regression and witness tests, 15 of them
docs/architecture.svg     the diagram above, source
video/make_video.py       builds the demo video from slides and a synthetic voice
```
