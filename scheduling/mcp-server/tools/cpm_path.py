"""CPM and path-analysis MCP tools (F1 batch).

Thin adapters around ``schedule-toolbox/lib/cpm_engine.py`` and
``schedule-toolbox/lib/path_analysis.py``. Each tool function pulls already-
parsed (and where helpful, already-CPM'd) data from the ``CpmCache`` and
returns a structured dict that the MCP serialization layer hands back to the
caller as JSON.

The four path-extraction tools (``get_critical_path``,
``get_near_critical_chains``, ``get_driving_paths``, ``get_parallel_branches``)
all read from a single call to :func:`extract_paths` -- they just project
different keys out of the same result. Re-running ``extract_paths`` per call
keeps the cache key flat (no per-milestone variants) and is cheap relative to
the CPM forward/backward passes that are cached.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so we can import the analysis modules without
# packaging them. Mirrors cache.py and structure.py.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cpm_engine import extract_paths  # noqa: E402


def _resolve_metadata_for_milestone(
    metadata: dict, milestone_id, tasks: list
) -> dict:
    """Return a metadata dict with ``sc_milestone_*`` fields set to the
    explicit ``milestone_id``. When ``milestone_id`` is None the original
    metadata is returned unchanged (no copy) so the common case is free.

    The CPM math already ran with the cache's default milestone resolution;
    only the post-processing path extraction needs to know which milestone
    counts as "the end" for SC-anchored chains. Updating metadata in place
    would corrupt the cache entry, hence the shallow copy.
    """
    if milestone_id is None:
        return metadata
    new_meta = dict(metadata)
    new_meta["sc_milestone_id"] = milestone_id
    # Best-effort lookup of name + code + date so the metadata dict matches
    # what schedule_forward_backward would have produced if given milestone_id
    # directly. Missing fields default to empty string (extract_paths only
    # uses sc_milestone_id, but other future consumers may read the name).
    for t in tasks:
        if t.get("task_id") == milestone_id:
            new_meta["sc_milestone_name"] = t.get("task_name", "")
            new_meta["sc_milestone_code"] = t.get("task_code", "")
            new_meta["sc_milestone_date"] = t.get("early_end_date", "")
            break
    return new_meta


def get_critical_path_impl(
    xer_path: str, milestone_id: Optional[str], cache
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Returns ``{"critical_path": [task_summary, ...]}`` where each
    ``task_summary`` comes straight from ``extract_paths`` -- a dict of
    ``task_id``, ``task_code``, ``task_name``, ``total_float_hr_cnt``,
    ``early_start_date``, ``early_end_date``, etc.
    """
    parsed = cache.get_parsed(xer_path)
    results, metadata = cache.get_cpm(xer_path)
    metadata = _resolve_metadata_for_milestone(
        metadata, milestone_id, parsed.get("TASK", [])
    )
    paths = extract_paths(results, metadata, parsed.get("TASKPRED", []))
    return {"critical_path": paths.get("critical_path", [])}


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def get_critical_path(
        xer_path: str, milestone_id: Optional[str] = None
    ) -> dict:
        """Return the longest contiguous TF<=0 chain ending at the project's
        terminal milestone (or at ``milestone_id`` if provided).

        Args:
            xer_path: Path to the .xer file.
            milestone_id: Optional task_id of the terminal milestone to walk
                back from. Omit on single-terminal schedules to auto-resolve.

        Returns:
            ``{ critical_path: [{task_id, task_code, task_name,
            total_float_hr_cnt, early_start_date, early_end_date, ...}, ...] }``.
            Empty list if no TF<=0 chain exists.
        """
        return get_critical_path_impl(xer_path, milestone_id, cache)
