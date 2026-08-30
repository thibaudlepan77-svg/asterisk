# -*- coding: utf-8 -*-
"""Tests that would have caught the two design errors this project made.

Both errors were found by measurement rather than by reading the code, so
each one is pinned here to stop it coming back.
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asterisk.segment import segment
from asterisk.sentences import split
from asterisk.audit import audit

SHATTERED = (
    "<h1>Grand prize</h1>"
    "<div><span>$</span><span>149,525</span><span> in cash</span></div>"
    "<div><p>Gold tier. $585 in cash. THIS IS NOT A CASH PRIZE. "
    "It cannot be exchanged or redeemed for cash.</p></div>"
)


class Segmentation(unittest.TestCase):
    def test_shattered_amount_is_rebuilt(self):
        """Regression. Markup splits a price across sibling elements."""
        doc = segment(SHATTERED)
        self.assertTrue(any("149,525" in b.text and "in cash" in b.text for b in doc.lines),
                        "the amount and its unit must end up on one line")

    def test_deep_nesting_does_not_flatten_prominence(self):
        deep = "<div>" * 16 + "<h1>Free forever</h1>" + "</div>" * 16
        doc = segment(deep)
        self.assertGreater(max(b.loudness for b in doc.lines), 1.0)


class Sentences(unittest.TestCase):
    def test_disclaimer_separates_from_promise_in_same_block(self):
        """Regression. The denial sits inside the promise block."""
        parts = split("Gold tier. $585 in cash. THIS IS NOT A CASH PRIZE. Enjoy.")
        self.assertTrue(any("585 in cash" in p for p in parts))
        self.assertTrue(any("NOT A CASH PRIZE" in p for p in parts))
        self.assertFalse(any("585 in cash" in p and "NOT A CASH PRIZE" in p for p in parts))

    def test_decimals_and_abbreviations_survive(self):
        self.assertEqual(len(split("It costs 9.99 per month. That is all.")), 2)


class Detection(unittest.TestCase):
    def test_finds_the_cash_contradiction_offline(self):
        doc = segment(SHATTERED, "test")
        claims, findings = audit(doc, offline=True)
        self.assertTrue(claims)
        crit = [f for f in findings if f.severity == "critical"]
        self.assertTrue(crit, "a denied cash prize must raise a critical finding")
        self.assertIn("cash", crit[0].counter.lower())

    def test_clean_page_reports_nothing(self):
        doc = segment("<h1>A quiet page</h1><p>We sell chairs made of oak.</p>", "test")
        _, findings = audit(doc, offline=True)
        self.assertEqual(findings, [])


class Grounding(unittest.TestCase):
    def test_quote_must_exist_in_the_page(self):
        doc = segment("<p>We deliver in thirty days.</p>", "test")
        self.assertTrue(doc.contains("deliver in thirty days"))
        self.assertFalse(doc.contains("we deliver in three days"))

    def test_grounding_is_whitespace_insensitive(self):
        doc = segment("<p>We   deliver in thirty days.</p>", "test")
        self.assertTrue(doc.contains("We deliver in thirty days"))




class OutputGrounding(unittest.TestCase):
    """Witness tests. A gate that has never refused anything proves nothing."""

    PAGE = {"http://x": ("This award consists of sponsor-provided product credits, "
                         "subscriptions, software licenses, domains, or other non-cash "
                         "benefits and cannot be exchanged or redeemed for cash.")}

    def test_exact_quote_passes(self):
        from asterisk import guard
        a = 'The page says "software licenses, domains, or other non-cash benefits".'
        c = guard.check(a, self.PAGE)
        self.assertEqual([x.status for x in c], ["exact"])

    def test_british_respelling_is_caught(self):
        """The real failure. The model tidied licenses into licences and called it verified."""
        from asterisk import guard
        a = 'The page says "software licences, domains, or other non-cash benefits".'
        c = guard.check(a, self.PAGE)
        self.assertEqual(c[0].status, "altered")
        self.assertIn("licenses", c[0].actual)

    def test_invented_quote_is_refused(self):
        from asterisk import guard
        a = 'The page says "winners are paid in cash within seven days by bank transfer".'
        c = guard.check(a, self.PAGE)
        self.assertEqual(c[0].status, "unsupported")

    def test_annotation_names_the_true_wording(self):
        from asterisk import guard
        a = 'The page says "software licences, domains, or other non-cash benefits".'
        txt = guard.annotate(a, guard.check(a, self.PAGE))
        self.assertIn("ALTERED", txt)
        self.assertIn("the page says", txt)


class Blindness(unittest.TestCase):
    """A confident nothing found on a page we never read is the worst output."""

    def test_shell_page_is_flagged(self):
        doc = segment("<html><body><div id=root></div><h1>Pricing</h1></body></html>", "x")
        self.assertTrue(doc.looks_unreadable())

    def test_real_page_is_not_flagged(self):
        body = "".join("<p>Sentence number %d, with enough words to count as real text here.</p>" % i
                       for i in range(30))
        doc = segment("<html><body><h1>Pricing</h1>%s</body></html>" % body, "x")
        self.assertFalse(doc.looks_unreadable())

    def test_report_says_so_loudly(self):
        from asterisk import report
        txt = report.as_text("x", [], [], unreadable=True)
        self.assertIn("DID NOT RENDER", txt)
        self.assertIn("NOT a clean bill of health", txt)


class Watching(unittest.TestCase):
    """An offer is a moving thing, and the changes that matter are unannounced."""

    def setUp(self):
        import tempfile
        from asterisk import watch
        self.tmp = tempfile.mkdtemp()
        self.old_store = watch.STORE
        watch.STORE = self.tmp
        self.watch = watch

    def tearDown(self):
        self.watch.STORE = self.old_store

    def audit_of(self, html):
        doc = segment(html, "http://x")
        return audit(doc, offline=True)

    CLEAN = "<h1>Win $500 in cash</h1><p>Open to everyone worldwide.</p>"
    DIRTY = ("<h1>Win $500 in cash</h1><p>Open to everyone worldwide.</p>"
             "<div class='rules'><p>THIS IS NOT A CASH PRIZE. "
             "It cannot be exchanged or redeemed for cash.</p></div>")

    def test_first_look_has_nothing_to_compare(self):
        c, f = self.audit_of(self.CLEAN)
        d, _ = self.watch.diff("http://x", c, f)
        self.assertIsNone(d)

    def test_a_new_clause_is_reported_as_appeared(self):
        c, f = self.audit_of(self.CLEAN)
        self.watch.save("http://x", c, f)
        c2, f2 = self.audit_of(self.DIRTY)
        d, _ = self.watch.diff("http://x", c2, f2)
        self.assertTrue(d["findings_appeared"], "a clause added later must show up")
        self.assertIn("cash", d["findings_appeared"][0].lower())

    def test_a_removed_clause_is_reported_as_disappeared(self):
        c, f = self.audit_of(self.DIRTY)
        self.watch.save("http://x", c, f)
        c2, f2 = self.audit_of(self.CLEAN)
        d, _ = self.watch.diff("http://x", c2, f2)
        self.assertTrue(d["findings_disappeared"])

    def test_a_rewording_is_not_read_as_two_events(self):
        a = ["The winner is paid within 30 days of the announcement of results."]
        b = ["The winner is paid within 90 days of the announcement of results."]
        gone, appeared, reworded = self.watch._pair(a, b)
        self.assertEqual(gone, [])
        self.assertEqual(appeared, [])
        self.assertEqual(len(reworded), 1)

    def test_no_change_says_so(self):
        c, f = self.audit_of(self.DIRTY)
        self.watch.save("http://x", c, f)
        c2, f2 = self.audit_of(self.DIRTY)
        d, _ = self.watch.diff("http://x", c2, f2)
        self.assertIn("Nothing changed", self.watch.render(d))


class TableNoise(unittest.TestCase):
    """A pricing grid is not a clause, and the model kept quoting grids."""

    def test_a_price_grid_is_rejected(self):
        from asterisk.audit import _is_table
        self.assertTrue(_is_table("Pay monthly $27 USD/mo $72 USD/mo $399 USD/mo "
                                  "Pay yearly $24 USD/mo $65 USD/mo $359 USD/mo"))

    def test_a_real_clause_survives_even_with_numbers(self):
        from asterisk.audit import _is_table
        self.assertFalse(_is_table("A fee of 2% (or minimum fee 1 pound) applies per "
                                   "transaction after your rolling monthly limit."))

    def test_prose_without_numbers_survives(self):
        from asterisk.audit import _is_table
        self.assertFalse(_is_table("Entry is reserved to students currently enrolled."))

    def test_three_prices_in_one_sentence_is_a_grid(self):
        """The case the digit density test let through, because a grid has words too."""
        from asterisk.audit import _is_table
        self.assertTrue(_is_table("Pay monthly $27 USD/mo Pay yearly $24 USD/mo Core features "
                                  "Earn 1% back on all sales Up to $4,500 USD"))
        self.assertTrue(_is_table("Standard Free Standard Plus 3.99 GBP/month Plus Premium "
                                  "7.99 GBP/month Premium Metal 14.99 GBP/month"))

    def test_one_price_in_a_real_clause_survives(self):
        from asterisk.audit import _is_table
        self.assertFalse(_is_table("Try 3 months of Premium Individual for $0, "
                                   "then $12.99/month."))


class Distance(unittest.TestCase):
    """The thesis of this tool is a distance, so a finding has to carry it."""

    def test_a_finding_reports_how_far_apart_the_two_halves_are(self):
        doc = segment(SHATTERED, "test")
        _, findings = audit(doc, offline=True)
        d = findings[0].distance()
        self.assertIsNotNone(d)
        self.assertTrue(0.0 <= d <= 1.0)

    def test_distance_is_none_when_a_side_cannot_be_located(self):
        from asterisk.audit import Finding
        f = Finding(claim_kind="cash", claim="a", counter="b", severity="high",
                    explanation="x", source="rule")
        self.assertIsNone(f.distance())


class HtmlReport(unittest.TestCase):
    def test_it_escapes_what_it_quotes(self):
        """A page can put a script tag inside its own fine print."""
        from asterisk import html as H
        from asterisk.audit import Finding
        f = Finding(claim_kind="cash", claim="<script>alert(1)</script>", counter="b & c",
                    severity="critical", explanation="x", source="rule")
        out = H.render("http://x", [], [f])
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_an_unread_page_says_so_and_shows_nothing_else(self):
        from asterisk import html as H
        out = H.render("http://x", [], [], unreadable=True)
        self.assertIn("did not render", out)
        self.assertNotIn("Nothing found", out)

    def test_a_clean_page_says_it_is_a_result(self):
        from asterisk import html as H
        out = H.render("http://x", [], [])
        self.assertIn("not a failure", out)


class Service(unittest.TestCase):
    """The call the front end makes, tested without starting a server."""

    def test_a_bad_address_is_refused_before_any_request(self):
        from asterisk.service import audit_url
        r = audit_url("not a url")
        self.assertFalse(r["ok"])
        self.assertIn("full address", r["error"])

    def test_markdown_of_a_failure_leads_with_the_reason(self):
        from asterisk.service import as_markdown
        out = as_markdown({"ok": False, "error": "Could not fetch that page."})
        self.assertTrue(out.startswith("### Could not fetch"))

    def test_markdown_of_a_clean_page_says_it_is_a_result(self):
        from asterisk.service import as_markdown
        out = as_markdown({"ok": True, "claims": [], "contradictions": [], "restrictions": []})
        self.assertIn("not a failure", out)

    def test_markdown_shows_both_halves_of_a_contradiction(self):
        from asterisk.service import as_markdown
        out = as_markdown({"ok": True, "claims": [], "restrictions": [], "contradictions": [
            {"severity": "critical", "explanation": "it says two things",
             "claim": "win money", "counter": "not a cash prize", "distance": 0.3}]})
        self.assertIn("win money", out)
        self.assertIn("not a cash prize", out)
        self.assertIn("30 %", out)


class OwnershipVersusLicence(unittest.TestCase):
    """You keep the title, they take a licence that does everything a title does.

    Added after a miss on a real contest rulebook, which the tool called clean.
    """

    PAGE = ("<h1>Rules</h1>"
            "<p>Teams retain full ownership of original code, AI models, and application "
            "designs.</p>"
            "<p>By participating, each team grants the sponsor a perpetual, irrevocable, "
            "worldwide, royalty-free, and unlimited license to use, reproduce, modify, "
            "adapt, distribute, sub-license, and create derivative works from any data "
            "submitted in connection with the competition.</p>")

    def test_the_pair_is_caught(self):
        doc = segment(self.PAGE, "test")
        claims, findings = audit(doc, offline=True)
        self.assertTrue(any(c.kind == "ownership" for c in claims),
                        "the promise that you keep your rights must be picked up")
        own = [f for f in findings if f.claim_kind == "ownership"]
        self.assertTrue(own, "a perpetual unlimited licence must answer that promise")
        self.assertIn("perpetual", own[0].counter.lower())

    def test_ownership_alone_raises_nothing(self):
        doc = segment("<h1>Rules</h1><p>Teams retain full ownership of their code.</p>", "test")
        _, findings = audit(doc, offline=True)
        self.assertEqual([f for f in findings if f.claim_kind == "ownership"], [])




class SponsorCreditsAreNotThePrize(unittest.TestCase):
    """Regression, measured 2026-08-30 on a live page and scored on the bench.

    A contest paying $12,000 in cash carried, under a heading about free
    partner credits, the sentence `AWS Promotional Credits are not redeemable
    for cash`. Both statements are true and neither denies the other. The tool
    reported that the prize was not money, which is the worst direction for
    this error, because a reader who believes it skips a contest that pays and
    never finds out they were wrong.
    """

    CREDITS_ASIDE = (
        "<h1>OpenCV AI Competition</h1><p>$12,000 in cash</p>"
        "<h2>Free AWS Credits for New Members</h2>"
        "<p>AWS Promotional Credits are not redeemable for cash and can only "
        "be applied to AWS Services.</p>"
    )
    REAL_DENIAL = (
        "<h1>Global Innovation Build</h1><p>$149,525 in cash</p>"
        "<h2>Gold tier</h2><p>This award consists of sponsor-provided product "
        "credits, subscriptions, software licenses, domains, or other non-cash "
        "benefits and cannot be exchanged or redeemed for cash.</p>"
    )

    def _cash_findings(self, html):
        doc = segment(html)
        _, findings = audit(doc, offline=True)
        return [f for f in findings if f.claim_kind in ("cash", "amount")]

    def test_an_aside_about_partner_credits_does_not_deny_the_prize(self):
        self.assertEqual([], self._cash_findings(self.CREDITS_ASIDE),
                         "a sentence about a separately named item must not "
                         "cancel the cash promise")

    def test_a_denial_that_names_the_award_still_fires(self):
        """The guard must not be a mute button. This is the witness."""
        self.assertTrue(self._cash_findings(self.REAL_DENIAL),
                        "a denial whose subject is the award itself must "
                        "still be reported")


class PublicationAndAdvancementCost(unittest.TestCase):
    """Two restriction families added 2026-08-30, both paid for the same day.

    Eleven of fifteen open cash contests required publishing on a platform the
    entrant does not control, and not one eligibility card said so. And on one
    page, being selected sends you a bill of five hundred dollars while the
    only number shown at the top is the prize.
    """

    def _labels(self, text):
        from asterisk import restrictions
        from asterisk.sentences import split
        from asterisk.segment import segment as seg

        doc = seg("<p>%s</p>" % text)
        from asterisk.sentences import sentences
        return {r["label"] for r in restrictions.find(doc, sentences(doc))}

    def test_video_link_requirement_is_reported(self):
        self.assertIn("third party publication required",
                      self._labels("Provide a link to a YouTube or TikTok "
                                   "video of no more than three minutes."))

    def test_hosted_demo_requirement_is_reported(self):
        self.assertIn("third party publication required",
                      self._labels("Submissions must include a publicly "
                                   "accessible URL where judges can test it."))

    def test_being_selected_can_cost_money(self):
        self.assertIn("advancement costs money",
                      self._labels("The remaining 90 selected teams pay a "
                                   "$500 USD fee per team."))

    def test_a_channel_mention_is_not_a_requirement(self):
        """Witness. The detector has to stay quiet on an ordinary mention."""
        self.assertNotIn("third party publication required",
                         self._labels("Follow the challenge on YouTube for "
                                      "weekly updates from the organisers."))




class Budgeting(unittest.TestCase):
    """The page budget, which used to be a sentence in a prompt.

    Written before the hook, and the first version of the hook failed the
    fourth of these because the starting page was not counted.
    """

    def setUp(self):
        from asterisk.budget import PageBudget
        self.PageBudget = PageBudget

    def test_a_page_within_budget_is_allowed(self):
        b = self.PageBudget(3)
        self.assertIsNone(b.decide("https://example.com/a"))

    def test_the_page_past_the_limit_is_refused(self):
        b = self.PageBudget(2)
        b.decide("https://example.com/a")
        b.decide("https://example.com/b")
        motif = b.decide("https://example.com/c")
        self.assertIsNotNone(motif)
        self.assertIn("budget", motif.lower())

    def test_the_same_page_written_two_ways_is_one_page(self):
        """A trailing slash and a fragment are not a second request."""
        b = self.PageBudget(4)
        self.assertIsNone(b.decide("https://example.com/Terms"))
        self.assertIsNotNone(b.decide("https://example.com/terms/"))
        self.assertIsNotNone(b.decide("https://example.com/terms#refunds"))
        self.assertEqual(b.spent, 1)

    def test_a_refusal_still_leaves_room_for_another_page(self):
        """Refusing a repeat must not spend a slot, or the budget shrinks by use."""
        b = self.PageBudget(2)
        b.decide("https://example.com/a")
        b.decide("https://example.com/a")          # refuse, repeat
        self.assertIsNone(b.decide("https://example.com/b"))

    def test_an_empty_url_is_refused_without_spending(self):
        b = self.PageBudget(1)
        self.assertIsNotNone(b.decide(""))
        self.assertEqual(b.spent, 0)

    def test_a_budget_of_zero_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            self.PageBudget(0)

    def test_the_refusal_tells_the_model_what_to_do_next(self):
        """A refusal a model cannot act on becomes a retry loop.

        Not a style check. The first refusal message said only `over budget`,
        and the obvious next move for a model reading that is to try again.
        """
        b = self.PageBudget(1)
        b.decide("https://example.com/a")
        motif = b.decide("https://example.com/b")
        self.assertTrue(any(m in motif.lower() for m in ("stop", "answer now")))


class VerifyQuoteDoesNotFetch(unittest.TestCase):
    """The hole the budget hook did not cover, found by asking who else fetches.

    `verify_quote` used to fetch a page it had not seen, so a model that wanted
    one more page only had to ask it to check a quote from that page. The
    budget hook guards the audit tool and nothing else. **A limit one door
    enforces and another ignores is not a limit.**
    """

    def test_the_agent_module_never_fetches_inside_verify_quote(self):
        import io as _io
        import re as _re
        src = _io.open("agent.py", encoding="utf-8").read()
        i = src.index("def verify_quote(")
        j = src.index("class Budget(", i)
        corps = src[i:j]
        appels = [l for l in corps.splitlines()
                  if "fetch.fetch(" in l and not l.strip().startswith("#")]
        self.assertEqual(appels, [], "verify_quote fetches again, the budget is bypassed")




class TheSdkContractTheBudgetRelieson(unittest.TestCase):
    """Pins the two SDK facts the budget hook depends on.

    The hook reads `tool_use["name"]` and `tool_use["input"]["url"]`, and hands
    the agent a `hooks=` argument. If a future version of the SDK renames
    either, the budget stops firing **and nothing else fails**, because a hook
    that never runs looks exactly like a hook that always allows. That silent
    mode is why these two lines are a test and not a comment.
    """

    def test_the_agent_still_takes_hooks(self):
        import inspect
        from strands import Agent
        self.assertIn("hooks", inspect.signature(Agent.__init__).parameters)

    def test_a_tool_use_still_carries_name_and_input(self):
        from strands.types.tools import ToolUse
        champs = getattr(ToolUse, "__annotations__", {})
        self.assertIn("name", champs)
        self.assertIn("input", champs)

    def test_the_before_tool_event_can_still_cancel(self):
        from strands.hooks import BeforeToolCallEvent
        self.assertIn("cancel_tool", getattr(BeforeToolCallEvent, "__annotations__", {}))




class AdvancementCost(unittest.TestCase):
    """The rule that missed the page it was written for.

    Drafted from one wording, then tried on another page of the same kind and
    missed three times in a single sentence. The window was eighty characters
    and the distance was eighty five. There was no `fee of`, there was `a
    registration fee`. And the page said `to receive their` where the rule had
    written `to receive your`.

    **Three near misses in one sentence is not bad luck, it is a rule written
    from the cases its author had already seen.** The positives below are
    verbatim from real pages, and the negatives include the sentence that says
    the opposite, because a rule that fires on `no registration fee` would be
    worse than a rule that misses.
    """

    def setUp(self):
        import re
        from asterisk.restrictions import RESTRICTIONS
        self.re = re
        self.pat = dict((n, p) for n, p, _, _ in RESTRICTIONS)["advancement costs money"]

    def _fires(self, txt):
        return bool(self.re.search(self.pat, txt, self.re.I))

    def test_the_page_it_missed(self):
        self.assertTrue(self._fires(
            "the remaining 90 selected teams will receive an invitation to Phase II "
            "and will be responsible for a registration fee and shipping costs to "
            "receive their developer kit"))

    def test_the_wording_it_was_written_for_still_fires(self):
        self.assertTrue(self._fires(
            "The other 40 selected teams pay a $250 fee to advance to the final round"))

    def test_a_page_saying_there_is_no_fee_stays_silent(self):
        """The most expensive false positive available, and it must not happen."""
        self.assertFalse(self._fires(
            "There is no entry fee and no registration fee to take part in Phase I"))

    def test_a_prize_paid_to_the_winner_is_not_a_cost(self):
        self.assertFalse(self._fires(
            "Finalists will each receive a cash prize of five thousand dollars"))

    def test_the_absurd_witness_stays_silent(self):
        self.assertFalse(self._fires(
            "The cafeteria serves lunch between eleven and two"))




class VideoRequired(unittest.TestCase):
    """The plainest wording there is, and the family above missed all of it.

    `third party publication required` needs a platform named or the words
    `uploaded publicly`. Measured against ground truth on 22 pages, that rule
    caught four of the pages that ask for a video. So this family was added at
    one severity lower, because a page alone cannot tell you whether the place
    hosts video, only that many do not.

    The negatives matter here. A page that merely SHOWS a video must not be
    read as a page that REQUIRES one from you.
    """

    def setUp(self):
        import re
        from asterisk.restrictions import RESTRICTIONS
        self.re = re
        self.pat = dict((n, p) for n, p, _, _ in RESTRICTIONS)["video required"]

    def _fires(self, txt):
        return bool(self.re.search(self.pat, txt, self.re.I))

    def test_the_bare_wording_fires(self):
        self.assertTrue(self._fires(
            "What to Submit A 2 minute demo video showcasing your project"))

    def test_the_reversed_wording_fires(self):
        self.assertTrue(self._fires(
            "Each team must provide a video demo of up to three minutes"))

    def test_a_duration_alone_fires(self):
        self.assertTrue(self._fires("A 3 minute video explaining your idea"))

    def test_a_video_the_page_shows_you_is_not_a_video_it_asks_for(self):
        self.assertFalse(self._fires("Watch the promotional video on our home page"))

    def test_the_absurd_witness_stays_silent(self):
        self.assertFalse(self._fires("The cafeteria serves lunch between eleven and two"))


class ModelComparison(unittest.TestCase):
    """The comparison bench must not lie in the two ways a scoreboard usually does.

    A benchmark that spends money without warning, and a benchmark that prints
    a confident zero for a class it never saw. Both are pinned here because
    both are silent, and a silent wrong number outlives every loud one.
    """

    def setUp(self):
        from eval import compare_models
        self.cm = compare_models

    def quietly(self, fn, *a):
        """The bench talks to a human. Under test we want the return code, and
        a suite that prints its own fixtures is a suite nobody reads."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fn(*a)
        return code, out.getvalue()

    def test_metered_run_refuses_without_confirmation(self):
        """Naming a model must not start spending on its own."""
        code, _ = self.quietly(self.cm.main, ["--models", "some-model", "--limit", "1"])
        self.assertEqual(code, 1, "a metered run must stop and ask before spending")

    def test_estimate_prints_without_running(self):
        code, text = self.quietly(self.cm.main, ["--models", "a,b", "--limit", "3",
                                                 "--estimate-only"])
        self.assertEqual(code, 0)
        self.assertIn("worst case model calls", text)

    def test_empty_class_is_not_scored_as_zero(self):
        """An f1 of zero on a class with no positive case is a lie about the tool.

        The bench must exclude such a class from the ranking rather than rank
        every model last on it.
        """
        counts = self.cm.empty_counts()
        label = next(iter(self.cm.PREDICTS))
        counts[label] = {"tp": 0, "fp": 1, "fn": 0, "tn": 9}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cm.table([("a model", counts, 10)])
        text = out.getvalue()
        self.assertIn("no positive case", text)
        self.assertNotIn("0.00", text.split(label)[1][:200],
                         "an empty class must not be printed as a score of zero")

    def test_verdict_names_a_model_that_adds_nothing(self):
        """The point of the table. A model that ties the baseline must be told so."""
        label = next(iter(self.cm.PREDICTS))
        base = self.cm.empty_counts()
        base[label] = {"tp": 5, "fp": 0, "fn": 0, "tn": 5}
        same = self.cm.empty_counts()
        same[label] = {"tp": 5, "fp": 0, "fn": 0, "tn": 5}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cm.verdict([(self.cm.BASELINE, base, 10), ("costly model", same, 10)])
        self.assertIn("NOTHING", out.getvalue())

    def test_verdict_credits_a_model_that_actually_wins(self):
        label = next(iter(self.cm.PREDICTS))
        base = self.cm.empty_counts()
        base[label] = {"tp": 2, "fp": 0, "fn": 3, "tn": 5}
        better = self.cm.empty_counts()
        better[label] = {"tp": 5, "fp": 0, "fn": 0, "tn": 5}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cm.verdict([(self.cm.BASELINE, base, 10), ("good model", better, 10)])
        text = out.getvalue()
        self.assertIn("beats the baseline on", text)
        self.assertNotIn("NOTHING", text)


if __name__ == "__main__":

    unittest.main(verbosity=2)
