"""Activity roster + adjacency helpers.

Pure, deterministic functions behind the four activity-roster MCP tools
(``list_activities``, ``get_activity``, ``get_wbs_branch``,
``next_free_activity_code``). No cache, no I/O, no CPM: callers pass already-
parsed table dicts, and — for the date/float fields — TASK dicts that already
carry the values ``schedule_forward_backward`` wrote back. That keeps this
module agnostic about whether it's looking at imported or CPM-computed dates;
the MCP tool layer owns that decision (it always feeds CPM'd tasks).

Trades are read from the P6 "Responsibility" global activity code:
``ACTVTYPE`` (type) -> ``ACTVCODE`` (values) -> ``TASKACTV`` (per-task
assignment). See references/xer-tables.md for the field definitions.
"""
from __future__ import annotations

import re
from typing import Optional


# --- small helpers -----------------------------------------------------------

def _to_float(value, default: float = 0.0) -> float:
    """Parse an XER numeric string to float; ``default`` on blank/garbage."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _nz(x: float) -> float:
    """Collapse negative zero to 0.0. CPM can leave ``-0.0`` in float fields;
    it serializes as ``-0.0`` in JSON, which reads as noise."""
    return 0.0 if x == 0 else x


def _normalize_rel_type(pred_type: str) -> str:
    """``PR_FS`` / ``FS`` -> ``FS``. Uppercased, ``PR_`` prefix stripped."""
    t = (pred_type or "").strip().upper()
    return t[3:] if t.startswith("PR_") else t


# --- WBS paths ---------------------------------------------------------------

def build_wbs_path_index(projwbs_rows: list) -> dict:
    """Return ``{wbs_id: "Root > Sub > Leaf"}`` for every WBS node.

    Walks ``parent_wbs_id`` to the root, guarding against cycles (a corrupt
    self-referential chain) and missing parents (an orphan node stops at
    itself). Names come from ``wbs_name``.
    """
    by_id = {str(w.get("wbs_id")): w for w in projwbs_rows}
    index: dict = {}
    for wbs_id, row in by_id.items():
        names: list = []
        seen: set = set()
        cur_id = wbs_id
        while cur_id and cur_id in by_id and cur_id not in seen:
            seen.add(cur_id)
            cur = by_id[cur_id]
            names.append(cur.get("wbs_name", "") or cur_id)
            parent = str(cur.get("parent_wbs_id", "") or "")
            cur_id = parent
        index[wbs_id] = " > ".join(reversed(names))
    return index


# --- calendars ---------------------------------------------------------------

def build_day_hr_index(calendar_rows: list) -> dict:
    """Return ``{clndr_id: hours_per_day}`` from CALENDAR/CLNDR rows."""
    idx: dict = {}
    for c in calendar_rows or []:
        idx[str(c.get("clndr_id"))] = _to_float(c.get("day_hr_cnt"), 8.0) or 8.0
    return idx


def _day_hr(day_hr_index: dict, clndr_id) -> float:
    return day_hr_index.get(str(clndr_id), 8.0) or 8.0


# --- responsibility (trade) activity code ------------------------------------

def resolve_responsibility_type(actvtype_rows: list, code_type: Optional[str] = None) -> Optional[str]:
    """Return the ``actv_code_type_id`` of the trade code type.

    Defaults to the type literally named "Responsibility"; pass ``code_type``
    to target a different activity-code type by name. When several types share
    the name, a global-scope (``AS_Global``) type wins over EPS/project scope.
    Returns ``None`` when no type matches.
    """
    rows = actvtype_rows or []
    if code_type:
        # Explicit type name: exact (case-insensitive) match.
        target = code_type.strip().lower()
        matches = [
            t for t in rows
            if (t.get("actv_code_type", "") or "").strip().lower() == target
        ]
    else:
        # Default: Westland's global trade code is named "Responsibility - Global";
        # also tolerate a bare "Responsibility" and the "Responsibilty" typo seen
        # in some project-scoped types. Prefix match catches all three.
        matches = [
            t for t in rows
            if (t.get("actv_code_type", "") or "").strip().lower().startswith("responsib")
        ]
    if not matches:
        return None
    # Prefer a global-scope type over EPS/project when several match.
    matches.sort(key=lambda t: 0 if t.get("actv_code_type_scope") == "AS_Global" else 1)
    return str(matches[0].get("actv_code_type_id"))


def build_task_responsibility(taskactv_rows: list, actvcode_rows: list,
                              resp_type_id: Optional[str]) -> dict:
    """Return ``{task_id: {"short": short_name, "name": actv_code_name}}``
    for the given code type. Empty dict when ``resp_type_id`` is ``None``.
    """
    if resp_type_id is None:
        return {}
    code_by_id = {
        str(c.get("actv_code_id")): {
            "short": c.get("short_name", ""),
            "name": c.get("actv_code_name", ""),
        }
        for c in (actvcode_rows or [])
        if str(c.get("actv_code_type_id")) == str(resp_type_id)
    }
    out: dict = {}
    for a in taskactv_rows or []:
        if str(a.get("actv_code_type_id")) != str(resp_type_id):
            continue
        tid = str(a.get("task_id"))
        if tid in out:
            continue  # first assignment wins
        code = code_by_id.get(str(a.get("actv_code_id")))
        if code:
            out[tid] = dict(code)
    return out


# --- rows --------------------------------------------------------------------

def _base_row(task: dict, wbs_index: dict, task_resp: dict, day_hr_index: dict) -> dict:
    tid = str(task.get("task_id"))
    wbs_id = str(task.get("wbs_id"))
    resp = task_resp.get(tid)
    float_hr = _to_float(task.get("total_float_hr_cnt"))
    day_hr = _day_hr(day_hr_index, task.get("clndr_id"))
    return {
        "task_id": tid,
        "task_code": task.get("task_code"),
        "task_name": task.get("task_name"),
        "task_type": task.get("task_type"),
        "status_code": task.get("status_code"),
        "wbs_id": wbs_id,
        "wbs_path": wbs_index.get(wbs_id, ""),
        "responsibility": resp["name"] if resp else None,
        "responsibility_short": resp["short"] if resp else None,
        "early_start": task.get("early_start_date"),
        "early_finish": task.get("early_end_date"),
        "late_start": task.get("late_start_date"),
        "late_finish": task.get("late_end_date"),
        "total_float_hr_cnt": _nz(float_hr),
        "total_float_days": _nz(round(float_hr / day_hr, 2)),
    }


def _logic_counts(preds: list) -> tuple:
    """Return ``(pred_count_by_task, succ_count_by_task)`` keyed by task_id."""
    pred_count: dict = {}
    succ_count: dict = {}
    for p in preds or []:
        succ_id = str(p.get("task_id"))
        pred_id = str(p.get("pred_task_id"))
        pred_count[succ_id] = pred_count.get(succ_id, 0) + 1
        succ_count[pred_id] = succ_count.get(pred_id, 0) + 1
    return pred_count, succ_count


def _matches_trade(row: dict, trade_filter: str) -> bool:
    needle = trade_filter.strip().lower()
    hay = f"{row.get('responsibility') or ''} {row.get('responsibility_short') or ''}".lower()
    return needle in hay


def roster_rows(tasks: list, preds: list, wbs_index: dict, task_resp: dict,
                day_hr_index: dict, wbs_filter: Optional[str] = None,
                trade_filter: Optional[str] = None, include_logic: bool = True) -> list:
    """Build the activity roster. See module docstring for field semantics."""
    pred_count, succ_count = ({}, {})
    if include_logic:
        pred_count, succ_count = _logic_counts(preds)

    rows: list = []
    for t in tasks:
        row = _base_row(t, wbs_index, task_resp, day_hr_index)
        if wbs_filter and wbs_filter.strip().lower() not in row["wbs_path"].lower():
            continue
        if trade_filter and not _matches_trade(row, trade_filter):
            continue
        if include_logic:
            tid = row["task_id"]
            row["pred_count"] = pred_count.get(tid, 0)
            row["succ_count"] = succ_count.get(tid, 0)
        rows.append(row)

    rows.sort(key=lambda r: (r["wbs_path"], str(r["task_code"])))
    return rows


# --- adjacency ---------------------------------------------------------------

def _adjacent_entry(related: dict, rel_type: str, lag_hr: float,
                    wbs_index: dict, task_resp: dict, day_hr_index: dict) -> dict:
    resp = task_resp.get(str(related.get("task_id")))
    day_hr = _day_hr(day_hr_index, related.get("clndr_id"))
    return {
        "task_code": related.get("task_code"),
        "task_name": related.get("task_name"),
        "wbs_path": wbs_index.get(str(related.get("wbs_id")), ""),
        "responsibility": resp["name"] if resp else None,
        "rel_type": _normalize_rel_type(rel_type),
        "lag_hr_cnt": _nz(lag_hr),
        "lag_days": _nz(round(lag_hr / day_hr, 2)),
    }


def _find_task(task_ref: str, tasks: list) -> Optional[dict]:
    ref = str(task_ref)
    for t in tasks:
        if t.get("task_code") == ref:
            return t
    for t in tasks:
        if str(t.get("task_id")) == ref:
            return t
    return None


def expand_activity(task_ref: str, tasks: list, preds: list, wbs_index: dict,
                    task_resp: dict, day_hr_index: dict) -> Optional[dict]:
    """Return one activity's base row plus expanded ``predecessors`` /
    ``successors`` (each with code, name, wbs_path, responsibility, rel_type,
    lag). Matches ``task_ref`` against ``task_code`` first, then ``task_id``.
    Returns ``None`` when not found.
    """
    task = _find_task(task_ref, tasks)
    if task is None:
        return None
    by_id = {str(t.get("task_id")): t for t in tasks}
    tid = str(task.get("task_id"))

    predecessors: list = []
    successors: list = []
    for p in preds or []:
        succ_id = str(p.get("task_id"))
        pred_id = str(p.get("pred_task_id"))
        lag = _to_float(p.get("lag_hr_cnt"))
        if succ_id == tid and pred_id in by_id:
            predecessors.append(_adjacent_entry(
                by_id[pred_id], p.get("pred_type", ""), lag,
                wbs_index, task_resp, day_hr_index))
        if pred_id == tid and succ_id in by_id:
            successors.append(_adjacent_entry(
                by_id[succ_id], p.get("pred_type", ""), lag,
                wbs_index, task_resp, day_hr_index))

    row = _base_row(task, wbs_index, task_resp, day_hr_index)
    row["pred_count"] = len(predecessors)
    row["succ_count"] = len(successors)
    row["predecessors"] = sorted(predecessors, key=lambda e: str(e["task_code"]))
    row["successors"] = sorted(successors, key=lambda e: str(e["task_code"]))
    return row


# --- WBS branch --------------------------------------------------------------

def _resolve_wbs(wbs_ref: str, projwbs_rows: list) -> Optional[str]:
    ref = str(wbs_ref)
    for w in projwbs_rows:
        if str(w.get("wbs_id")) == ref:
            return ref
    low = ref.strip().lower()
    for w in projwbs_rows:
        if (w.get("wbs_short_name", "") or "").strip().lower() == low:
            return str(w.get("wbs_id"))
    for w in projwbs_rows:
        if (w.get("wbs_name", "") or "").strip().lower() == low:
            return str(w.get("wbs_id"))
    return None


def _descendant_wbs_ids(wbs_id: str, projwbs_rows: list) -> set:
    """Return ``wbs_id`` plus all descendant WBS ids (transitive children)."""
    children: dict = {}
    for w in projwbs_rows:
        parent = str(w.get("parent_wbs_id", "") or "")
        children.setdefault(parent, []).append(str(w.get("wbs_id")))
    out: set = set()
    stack = [str(wbs_id)]
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def branch_activities(wbs_ref: str, tasks: list, preds: list, projwbs_rows: list,
                      wbs_index: dict, task_resp: dict, day_hr_index: dict,
                      include_descendants: bool = True,
                      include_logic: bool = True) -> Optional[dict]:
    """Return the activities in a WBS branch (optionally including descendant
    nodes), each optionally carrying expanded predecessors/successors. ``None``
    when ``wbs_ref`` resolves to no WBS node.
    """
    wbs_id = _resolve_wbs(wbs_ref, projwbs_rows)
    if wbs_id is None:
        return None
    target_ids = (_descendant_wbs_ids(wbs_id, projwbs_rows)
                  if include_descendants else {wbs_id})

    activities: list = []
    for t in tasks:
        if str(t.get("wbs_id")) not in target_ids:
            continue
        if include_logic:
            activities.append(expand_activity(
                str(t.get("task_id")), tasks, preds, wbs_index,
                task_resp, day_hr_index))
        else:
            row = _base_row(t, wbs_index, task_resp, day_hr_index)
            activities.append(row)

    activities.sort(key=lambda r: (r["wbs_path"], str(r["task_code"])))
    return {
        "wbs_id": wbs_id,
        "wbs_path": wbs_index.get(wbs_id, ""),
        "activity_count": len(activities),
        "activities": activities,
    }


# --- next free activity code -------------------------------------------------

_SUFFIX_RE = re.compile(r"^(\D*?)(\d+)$")


def next_free_code(tasks: list, prefix: str, step: int = 10) -> dict:
    """Find the next collision-free activity code for ``prefix``.

    Scans ``task_code`` values that start with ``prefix`` and end in a digit
    run. ``next_code = max_number + step``, formatted with the max code's
    separator (the non-digit chars between prefix and number) and zero-pad
    width. ``next_code`` is ``None`` when nothing matches — the format can't be
    guessed from zero examples.
    """
    best_num: Optional[int] = None
    best_code: Optional[str] = None
    best_sep = ""
    best_width = 0
    matched = 0
    for t in tasks:
        code = t.get("task_code", "") or ""
        if not code.startswith(prefix):
            continue
        m = _SUFFIX_RE.match(code[len(prefix):])
        if not m:
            continue
        matched += 1
        num = int(m.group(2))
        if best_num is None or num > best_num:
            best_num = num
            best_code = code
            best_sep = m.group(1)
            best_width = len(m.group(2))

    if best_num is None:
        return {
            "prefix": prefix,
            "matched_count": 0,
            "max_existing_code": None,
            "max_existing_number": None,
            "next_code": None,
            "step": step,
        }

    next_num = best_num + step
    next_code = f"{prefix}{best_sep}{str(next_num).zfill(best_width)}"
    return {
        "prefix": prefix,
        "matched_count": matched,
        "max_existing_code": best_code,
        "max_existing_number": best_num,
        "next_code": next_code,
        "step": step,
    }
