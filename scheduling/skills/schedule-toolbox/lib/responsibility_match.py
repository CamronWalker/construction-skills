"""Name-based Responsibility (trade) code matcher.

Assigns Westland's "Responsibility - Global" activity code to an activity from
its name, using a curated keyword map (``references/responsibility-codes.json``).
Deterministic and pure: the MCP tool layer supplies the parsed tasks and the
loaded code map. High-confidence matches are auto-suggested; ambiguous / no-hit
names go to an "unsure" bucket for human (or Claude) adjudication — the
first-pass-with-review workflow the schedulers asked for.

Matching is intentionally simple and inspectable (keyword presence + phrase
weighting), not a black-box model, so the keyword map stays hand-editable.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Optional

# Default location of the shipped code+keyword reference data.
_REFERENCE = (
    Path(__file__).parent.parent / "references" / "responsibility-codes.json"
)

# Two-tier keyword scoring. "keywords" are STRONG (trade-defining terms like
# "electrical", "sprinkler", "structural steel") — a single strong hit is
# enough to be confident. "weak_keywords" are SUPPORTING terms that appear
# across several trades ("ceiling", "panels") — they add signal but never
# carry a match alone. A matched multi-word phrase gets a bonus per extra word,
# since a phrase is far less likely to be a coincidental hit than a lone token.
_STRONG_WEIGHT = 2.0
_WEAK_WEIGHT = 1.0
_PHRASE_BONUS = 1.0  # per word beyond the first, in a matched multi-word keyword

# Confidence gate: the top code must clear this score AND beat the runner-up by
# this margin to be auto-assigned. Tuned against the 30k-assignment sample
# corpus (held-out): favors precision so ambiguous names fall to review.
_MIN_SCORE = 2.0
_MIN_MARGIN = 1.5


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse non-alphanumerics to single spaces,
    and pad with a leading/trailing space so whole-word tokens can be matched
    with a simple ``f" {tok} "`` containment test.
    """
    if not text:
        return " "
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    out = []
    for ch in stripped.lower():
        out.append(ch if ch.isalnum() else " ")
    return " " + " ".join("".join(out).split()) + " "


def _load_reference(path: Optional[str] = None) -> dict:
    p = Path(path) if path else _REFERENCE
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_codes(path: Optional[str] = None) -> list:
    """Load the code+keyword list from the reference JSON. Returns the
    ``codes`` array: ``[{code, name, keywords:[...], weak_keywords?:[...]}, ...]``."""
    return _load_reference(path).get("codes", [])


def load_reference_name(path: Optional[str] = None) -> str:
    """Return the activity-code type name the reference targets
    (``"Responsibility - Global"``)."""
    return _load_reference(path).get("code_type_name", "Responsibility - Global")


def _score_keyword(kw: str, name_norm: str, base_weight: float) -> tuple:
    """Return (weight, matched?) for one keyword against a normalized name.
    Multi-word phrases match as substrings and earn a per-extra-word bonus;
    single tokens match on word boundaries."""
    kw_norm = normalize(kw).strip()
    if not kw_norm:
        return 0.0, False
    words = kw_norm.split()
    if f" {kw_norm} " not in name_norm:
        return 0.0, False
    weight = base_weight + (_PHRASE_BONUS * (len(words) - 1) if len(words) > 1 else 0.0)
    return weight, True


def _score_code(name_norm: str, strong: list, weak: list) -> tuple:
    """Return (score, matched_keywords) for one code against a normalized name."""
    score = 0.0
    matched = []
    for kw in strong or []:
        w, hit = _score_keyword(kw, name_norm, _STRONG_WEIGHT)
        if hit:
            score += w
            matched.append(kw)
    for kw in weak or []:
        w, hit = _score_keyword(kw, name_norm, _WEAK_WEIGHT)
        if hit:
            score += w
            matched.append(kw)
    return score, matched


def match_activity(name: str, codes: list) -> dict:
    """Match one activity name to a Responsibility code.

    Returns ``{code, name, confident, score, margin, matched, candidates}``.
    ``code`` is ``None`` when there is no keyword signal. ``confident`` is True
    only when the top code clears the score/margin gates (safe to auto-assign);
    otherwise the caller should review ``candidates``.
    """
    name_norm = normalize(name)
    scored = []
    for c in codes:
        strong = c.get("keywords") or []
        weak = c.get("weak_keywords") or []
        if not strong and not weak:
            continue
        s, matched = _score_code(name_norm, strong, weak)
        if s > 0:
            scored.append((s, c["code"], c.get("name", ""), matched))
    scored.sort(key=lambda t: t[0], reverse=True)

    if not scored:
        return {"code": None, "name": None, "confident": False, "score": 0.0,
                "margin": 0.0, "matched": [], "candidates": []}

    top_score, top_code, top_name, top_matched = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    margin = top_score - runner
    confident = top_score >= _MIN_SCORE and margin >= _MIN_MARGIN
    candidates = [
        {"code": code, "name": nm, "score": round(s, 2), "matched": mk}
        for (s, code, nm, mk) in scored[:4]
    ]
    return {
        "code": top_code,
        "name": top_name,
        "confident": confident,
        "score": round(top_score, 2),
        "margin": round(margin, 2),
        "matched": top_matched,
        "candidates": candidates,
    }


def suggest_assignments(tasks: list, codes: list,
                        already_assigned: Optional[set] = None) -> dict:
    """First-pass Responsibility assignment over a list of activities.

    ``tasks`` are dicts with ``task_id``, ``task_code``, ``task_name``.
    ``already_assigned`` is a set of task_ids to skip (already coded).

    Returns ``{assigned: [...], unsure: [...]}`` where each ``assigned`` row is
    safe to write and each ``unsure`` row carries the top candidates for review.
    """
    already = already_assigned or set()
    assigned = []
    unsure = []
    for t in tasks:
        tid = str(t.get("task_id"))
        if tid in already:
            continue
        m = match_activity(t.get("task_name", ""), codes)
        row = {
            "task_id": tid,
            "task_code": t.get("task_code"),
            "task_name": t.get("task_name"),
        }
        if m["confident"]:
            row["suggested_code"] = m["code"]
            row["suggested_name"] = m["name"]
            row["matched"] = m["matched"]
            row["score"] = m["score"]
            assigned.append(row)
        else:
            row["candidates"] = m["candidates"]
            unsure.append(row)
    return {"assigned": assigned, "unsure": unsure}
