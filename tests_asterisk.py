# -*- coding: utf-8 -*-
"""Tests that would have caught the two design errors this project made.

Both errors were found by measurement rather than by reading the code, so
each one is pinned here to stop it coming back.
"""
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
