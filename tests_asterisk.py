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


if __name__ == "__main__":
    unittest.main(verbosity=2)
