# -*- coding: utf-8 -*-
"""The page budget, enforced instead of requested.

WHY THIS FILE EXISTS, and it is the same mistake this whole project is about.

The agent's task text said `Budget, at most 4 pages in total`. Nothing enforced
it. It was a sentence in a prompt, and a prompt is a promise the program makes
to itself. A model that finds page four interesting fetches page five, and the
only thing that was ever going to stop it was a paragraph asking politely.

**A tool that reports where a page contradicts its own headline had a headline
its own agent could contradict.** So the budget moved out of the prose and into
the framework, where a refusal is a refusal.

The decision lives here, in twenty lines that need no model, no network and no
agent to test. The hook in `agent.py` is a five line adapter over it, for the
same reason the demo is a shell over `service.py`. Logic that can only be
exercised through a language model is logic nobody checks.
"""
from __future__ import annotations


class PageBudget:
    """Counts distinct pages fetched and refuses the one past the limit.

    Two refusals, and the second is not about cost.

    - **Over budget.** The agent asked for one page more than it may have.
    - **Already read.** The agent asked for a page it has already audited. That
      one costs a request and returns nothing new, and in an early run it was
      the more common of the two.
    """

    def __init__(self, limit: int = 4):
        if limit < 1:
            raise ValueError("a budget of less than one page cannot audit anything")
        self.limit = limit
        self.seen: list[str] = []

    @staticmethod
    def _key(url: str) -> str:
        """Same page, written two ways, is still the same request."""
        u = (url or "").strip()
        u = u.split("#", 1)[0]
        return u.rstrip("/").lower()

    def decide(self, url: str) -> str | None:
        """None if the page may be read, otherwise the reason for refusing.

        The message is written for the model, so it says what to do next
        rather than only what went wrong. A refusal a model cannot act on
        turns into a retry loop.
        """
        k = self._key(url)
        if not k:
            return ("No URL was given. Do not retry, name the page you mean.")
        if k in self.seen:
            return ("Page already audited in this run, its findings are in your "
                    "context. Do not fetch it again. Use what you have, or audit "
                    "a different page.")
        if len(self.seen) >= self.limit:
            return ("Page budget of %d exhausted. Stop looking and answer now with "
                    "what you already have. Say plainly which pages you did not "
                    "get to, so the reader knows the picture is partial."
                    % self.limit)
        self.seen.append(k)
        return None

    @property
    def spent(self) -> int:
        return len(self.seen)

    def summary(self) -> str:
        return "%d of %d pages read" % (len(self.seen), self.limit)
