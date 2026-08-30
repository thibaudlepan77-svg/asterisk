# -*- coding: utf-8 -*-
"""Watch an offer and report what changed in it.

The idea came from a measurement rather than a brainstorm. On 30 August 2026,
between 06:38 and 07:14, one contest's published count of cash prizes went from
ten to one. Nothing on its prize page changed. Nobody was told. Anyone who had
read it at 07:14 and compared it with a note taken at 06:38 would have seen it,
and nobody keeps such notes.

That is the gap. A page is audited once, at the moment you happen to look. An
offer is a moving thing. What was true when you signed up is not what is true
today, and the changes that matter are exactly the ones nobody announces.

So a snapshot stores the audit, and a later run diffs it. Three questions get
answered.

  APPEARED    a contradiction or a condition that was not there before
  DISAPPEARED one that has gone, which is not always good news
  REWORDED    the same clause, different words, which is often the interesting one
"""
from __future__ import annotations
import difflib
import hashlib
import io
import json
import os
import time

STORE = os.environ.get("ASTERISK_WATCH", os.path.join(os.path.dirname(__file__), "..", ".watch"))


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def _path(url: str) -> str:
    os.makedirs(STORE, exist_ok=True)
    return os.path.join(STORE, _key(url) + ".json")


def _shape(claims, findings):
    return {
        "taken": time.strftime("%Y-%m-%d %H:%M:%S"),
        "claims": sorted({" ".join((c.context or c.text).split())[:220] for c in claims}),
        "findings": [
            {"kind": getattr(f, "kind", "contradiction"), "what": f.claim_kind,
             "severity": f.severity, "quote": " ".join(f.counter.split())[:300]}
            for f in findings
        ],
    }


def save(url: str, claims, findings) -> dict:
    snap = _shape(claims, findings)
    with io.open(_path(url), "w", encoding="utf-8") as f:
        json.dump({"url": url, "snapshots": load_all(url) + [snap]}, f,
                  ensure_ascii=False, indent=1)
    return snap


def load_all(url: str):
    p = _path(url)
    if not os.path.exists(p):
        return []
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f).get("snapshots", [])
    except Exception:
        return []


def _pair(old_quotes, new_quotes, floor: float = 0.72):
    """Match quotes across snapshots so a rewording is not read as two events."""
    remaining = list(new_quotes)
    gone, reworded = [], []
    for q in old_quotes:
        if q in remaining:
            remaining.remove(q)
            continue
        best, at = 0.0, None
        for r in remaining:
            ratio = difflib.SequenceMatcher(None, q.lower(), r.lower()).ratio()
            if ratio > best:
                best, at = ratio, r
        if at is not None and best >= floor:
            reworded.append((q, at, best))
            remaining.remove(at)
        else:
            gone.append(q)
    return gone, remaining, reworded


def diff(url: str, claims, findings):
    """Compare the current audit with the last stored one. None when first seen."""
    history = load_all(url)
    now = _shape(claims, findings)
    if not history:
        return None, now
    before = history[-1]
    oq = [f["quote"] for f in before["findings"]]
    nq = [f["quote"] for f in now["findings"]]
    gone, appeared, reworded = _pair(oq, nq)
    claims_gone, claims_new, claims_reworded = _pair(before["claims"], now["claims"])
    return {
        "since": before["taken"],
        "snapshots": len(history),
        "findings_appeared": appeared,
        "findings_disappeared": gone,
        "findings_reworded": reworded,
        "promises_appeared": claims_new,
        "promises_disappeared": claims_gone,
        "promises_reworded": claims_reworded,
    }, now


def render(d) -> str:
    if d is None:
        return ("First time this page is watched. Nothing to compare against yet, the "
                "snapshot is stored. Run it again later and this becomes a diff.")
    out = ["Compared with the snapshot taken %s, %d stored." % (d["since"], d["snapshots"])]
    quiet = True
    for label, rows in (("APPEARED", d["findings_appeared"]),
                        ("DISAPPEARED", d["findings_disappeared"])):
        for q in rows:
            quiet = False
            out.append("  %-12s %s" % (label, q[:150]))
    for old, new, ratio in d["findings_reworded"]:
        quiet = False
        out.append("  %-12s %.0f %% the same" % ("REWORDED", 100 * ratio))
        out.append("               was  %s" % old[:130])
        out.append("               now  %s" % new[:130])
    for label, rows in (("PROMISE NEW", d["promises_appeared"]),
                        ("PROMISE GONE", d["promises_disappeared"])):
        for q in rows:
            quiet = False
            out.append("  %-12s %s" % (label, q[:150]))
    for old, new, ratio in d["promises_reworded"]:
        quiet = False
        out.append("  %-12s %.0f %% the same" % ("PROMISE EDITED", 100 * ratio))
        out.append("               was  %s" % old[:130])
        out.append("               now  %s" % new[:130])
    if quiet:
        out.append("  Nothing changed. That is worth knowing too.")
    return "\n".join(out)
