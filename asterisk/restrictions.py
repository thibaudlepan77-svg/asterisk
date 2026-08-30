# -*- coding: utf-8 -*-
"""Restrictions that no headline contradicts, and that still cost you.

This module exists because the benchmark said so. The contradiction engine
scored recall 0.29 on "the offer is reserved to students", and the reason was
not a tuning problem. Fourteen pages restrict entry to students while never
promising that entry is open, so there is no promise to contradict and nothing
for a contradiction detector to find.

A reader does not only need to know where a page fights itself. They need to
know what the page quietly requires of them. So the tool reports two kinds.

  CONTRADICTION  the page says A loudly and not A quietly
  RESTRICTION    the page never said A, and quietly requires B of you

Both are grounded the same way. Nothing is printed that is not on the page.
"""
from __future__ import annotations
import re

# Each entry, a label, a pattern, a severity, and what the reader loses.
RESTRICTIONS = [
    # "currently enrolled" alone was dropped after a false positive on a page
    # that used it in an invitation, not a condition. A restriction has to be
    # phrased as one.
    ("students only",
     r"(students? only|college students? only|student teams? only|"
     r"(?:must|has to) be (?:a )?(?:currently )?enrolled|"
     r"open (?:only )?to (?:currently )?enrolled students|"
     r"you must be a (?:full[- ]time )?student)",
     "high", "Entry is reserved to students, so a professional cannot take part."),
    ("organisations excluded",
     r"(compan(?:y|ies)[^.]{0,40}excluded|professional organizations? excluded|"
     r"organizations? excluded from participation|no (?:companies|businesses) may enter)",
     "high", "Companies and professional entities are excluded."),
    ("country restricted",
     r"(only open to[^.]{0,80}reside in|must (?:currently )?reside in [A-Z][a-z]+|"
     r"residents of [A-Z][a-z]+ only|only specific countries|"
     r"specific countries/territories excluded)",
     "high", "Entry depends on where you live."),
    ("age restricted",
     r"(ages? \d{1,2}(?: to \d{1,2})?\+? only|must be at least \d{1,2} years|"
     r"age of majority)",
     "low", "There is an age condition."),
    ("team required",
     r"(team required|teams? of \d+ to \d+|must (?:form|join) a team|minimum team size)",
     "medium", "You cannot enter alone."),
    ("prize not cash",
     r"(not a cash prize|cannot be exchanged or redeemed for cash|not redeemable for cash|"
     r"no cash (?:value|alternative))",
     "critical", "What is presented as a sum is not money you can receive."),
    ("payment before use",
     r"(payment (?:method|details) (?:is |are )?required|valid credit card required|"
     r"card required to start)",
     "high", "You must hand over a payment method before you get anything."),
    ("auto renewal",
     r"(auto[- ]?renew|renews automatically|will (?:be )?renew(?:ed)? unless)",
     "high", "It renews by itself unless you act."),
    ("no refund",
     r"(non[- ]refundable|no refunds?\b|all sales are final)",
     "high", "You cannot get your money back."),
    # Split in two after a mislabel. A refund window and a payment delay both
    # say "within N days" and mean opposite things to the reader.
    ("refund window",
     r"(within \d+ days of (?:purchase|buying|delivery|the order)|"
     r"\d+[- ]day money[- ]back)",
     "low", "There is a deadline to ask for your money back."),
    ("delay before payment",
     r"(delivered within \d+ days|payment (?:will be )?(?:made|sent) within \d+|"
     r"allow \d+ to \d+ (?:business )?days for (?:payment|delivery))",
     "low", "The money or the goods arrive later than the page suggests."),
    ("tax paperwork",
     r"(w-?8\s?ben|w-?9\b|tax form|withholding|form 1099)",
     "low", "A tax form stands between you and the payment."),
    ("licence handover",
     r"(grant(?:s)? (?:the )?sponsor a[^.]{0,60}(?:licen[cs]e|right)|"
     r"irrevocable[^.]{0,40}licen[cs]e|assign(?:s)? all rights)",
     "high", "You hand over rights on what you submit."),
    # Added 2026-08-30 after measuring fifteen open cash contests. Eleven
    # required this and not one eligibility card mentioned it. A reader can be
    # perfectly eligible, perfectly capable, and still unable to finish,
    # because finishing needs an account on a platform they do not control.
    ("third party publication required",
     r"((?:must|shall|required to|need to|provide|include)[^.]{0,80}"
     r"(?:video|link|url)[^.]{0,60}(?:youtube|vimeo|tiktok)|"
     r"(?:video|submission)[^.]{0,60}uploaded publicly|"
     r"publicly[- ]accessible (?:url|link|site|website|demo|deployment|version)|"
     r"(?:must|shall|required)[^.]{0,80}(?:apple app store|google play))",
     "high", "Finishing this requires publishing on a platform you may not control."),
    # Added the same day, from a page where being selected sends you a bill.
    # A hundred entrants advance, ten are paid, and ninety owe five hundred
    # dollars. The page shows one number, the prize, at the top.
    # WIDENED ON 2026-08-30 AFTER IT MISSED THE PAGE IT WAS WRITTEN FOR.
    #
    # The rule was drafted from one wording and then tried on another page of
    # the same kind. That page says
    #
    #   the remaining 90 selected teams will receive an invitation to Phase II
    #   and will be responsible for a registration fee and shipping costs
    #
    # and it missed three times over. `selected` to `fee` is eighty five
    # characters and the window was eighty. There is no `fee of`, there is `a
    # registration fee`. And it says `to receive their`, where the rule had
    # written `to receive your`.
    #
    # **Three near misses in one sentence is not bad luck, it is a rule written
    # from the cases its author had already seen.** Same failure as the video
    # detector the same morning. The fix is not a wider window, it is patterns
    # taken from wordings nobody chose.
    ("advancement costs money",
     r"((?:selected|advancing|qualifying|finalists?|shortlisted|remaining)"
     r"[^.]{0,140}(?:pay a|pays a|fee of|must pay|responsible for[^.]{0,40}(?:fee|cost)|"
     r"(?:registration|entry|participation|shipping|kit) (?:fee|cost))|"
     r"(?:pay|fee|cost)[^.]{0,80}to (?:advance|proceed|continue|"
     r"receive (?:your|their|the)))",
     "critical", "A good result here costs you money rather than paying you."),
]

# PORTEE, ajoutee le 2026-08-30 apres une fausse alerte mesuree sur le banc.
#
# LE CAS. Un concours dote de 12 000 USD EN ESPECES ecrit, dans une section de
# remerciement a son partenaire, `AWS Promotional Credits are not redeemable
# for cash`. La phrase est vraie et elle ne parle PAS du prix, elle parle d'un
# lot annexe. L'outil concluait que le prix n'etait pas en especes, et un
# lecteur qui le croit ecarte un concours qui paie vraiment.
#
# LA REGLE. Une phrase qui NIE le caractere monetaire ne vaut pour LE PRIX que
# si elle se trouve dans une section de prix. Ailleurs, elle reste montree,
# parce que cacher une information n'est jamais la bonne reponse, mais elle est
# montree pour ce qu'elle est, un lot annexe non monetaire, et non comme un
# verdict sur la dotation.
#
# Ce n'est pas un reglage de seuil, c'est la definition meme de l'etiquette de
# reference, `the prize block itself states the award cannot be exchanged`.
# L'outil lisait toute la page la ou la verite terrain lit un bloc.
PORTEE = {
    "prize not cash": (
        re.compile(r"(prize|award|winnings|what you (?:can )?win|rewards?)", re.I),
        ("a listed item is not cash", "medium",
         "Something named on this page cannot be exchanged for cash. Check whether "
         "that is the whole award or only one item beside it."),
    ),
}

_R = [(lab, re.compile(p, re.I), sev, why) for lab, p, sev, why in RESTRICTIONS]


def find(doc, sents, max_per_label: int = 1):
    """Return raw dicts, the audit module wraps them into Findings."""
    out = []
    seen = {}
    for s in sents:
        for label, rx, sev, why in _R:
            if seen.get(label, 0) >= max_per_label:
                continue
            m = rx.search(s.text)
            if not m:
                continue
            portee = PORTEE.get(label)
            if portee is not None and not portee[0].search(s.section or ""):
                label, sev, why = portee[1]
                if seen.get(label, 0) >= max_per_label:
                    continue
            seen[label] = seen.get(label, 0) + 1
            out.append({
                "label": label,
                "quote": s.excerpt(300),
                "severity": sev,
                "explanation": why,
                "section": s.section,
                "offset": doc.locate(m.group(0)),
            })
    return out
