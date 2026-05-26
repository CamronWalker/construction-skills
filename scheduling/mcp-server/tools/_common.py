"""Shared helpers across the MCP tool modules.

Consolidates the four pieces that were duplicated across ``quality.py``,
``omnibus.py``, and ``cpm_path.py`` in Plan 1:

* :func:`data_date_str` -- pull the data_date string out of parsed PROJECT.
* :func:`data_date_dt` -- like ``data_date_str`` but parsed to a ``datetime``.
* :const:`FUTURE_DATE_SENTINEL` -- far-future date used when a caller doesn't
  pass an explicit window for activities-to-start / activities-to-finish.
* :func:`resolve_metadata_for_milestone` -- shallow-copy CPM metadata with
  ``sc_milestone_*`` keys overridden to point at a caller-supplied milestone.

The F-batch modules import from here. New analytics modules in Plan 2 do the
same so a fifth copy doesn't sprout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

# Sentinel future date used internally when ``expected_updates`` (or similar
# date-windowed helpers) need an upper bound but the caller didn't pass one.
# Mirrors the value that lived in ``tools/omnibus.py`` and the same constant
# inlined into ``tools/update_review.py`` -- one canonical home now.
FUTURE_DATE_SENTINEL = "2099-12-31"


def data_date_str(parsed: dict) -> Optional[str]:
    """Pull the data_date string out of the parsed PROJECT table.

    Returns ``None`` in three cases:
      * the PROJECT table is missing from ``parsed``
      * the PROJECT table is present but empty
      * the PROJECT row's ``last_recalc_date`` and ``data_date`` are both
        absent or empty strings

    Downstream library checks branch on ``if data_date is None`` to skip
    date-aware comparisons, so collapsing empty strings to ``None`` is the
    intended behavior -- empty strings would otherwise compare unequal to
    anything and produce spurious "after data date" hits.
    """
    project_rows = parsed.get("PROJECT") or [{}]
    return (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
        or None
    )


def data_date_dt(parsed: dict) -> Optional[datetime]:
    """Like :func:`data_date_str` but returns a parsed ``datetime``.

    Accepts both ``%Y-%m-%d %H:%M`` and ``%Y-%m-%d`` -- the two formats
    seen in real Westland XERs. Returns ``None`` when no format matches
    so the library's no-date branches take over rather than raising.
    """
    s = data_date_str(parsed)
    if s is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def resolve_metadata_for_milestone(
    metadata: dict, milestone_id, tasks: list
) -> dict:
    """Return a metadata dict with ``sc_milestone_*`` fields set to the
    explicit ``milestone_id``.

    When ``milestone_id`` is ``None`` the original metadata is returned
    unchanged (no copy) so the common case is free. When non-None, a
    shallow copy is made and the ``sc_milestone_*`` keys are overridden to
    point at the caller-supplied milestone -- the cached CPM result is
    never mutated.
    """
    if milestone_id is None:
        return metadata
    new_meta = dict(metadata)
    new_meta["sc_milestone_id"] = milestone_id
    for t in tasks:
        if t.get("task_id") == milestone_id:
            new_meta["sc_milestone_name"] = t.get("task_name", "")
            new_meta["sc_milestone_code"] = t.get("task_code", "")
            new_meta["sc_milestone_date"] = t.get("early_end_date", "")
            break
    return new_meta
