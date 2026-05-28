"""MCP wrapper for apply_xer_changes.

Thin adapter over xer_modify.apply_changes from schedule-toolbox/lib.  Handles:
  - Cache pinning (pin on entry, unpin in finally).
  - Pre-state CPM capture (get_cpm BEFORE the apply so D17's diff machinery
    has a baseline).
  - Writing the mutated doc to disk (unless dry_run or validation errors).
  - Inserting the written doc into the cache under the output path so
    downstream get_parsed / get_cpm calls hit fresh data without a re-read.
  - Marshalling ApplyResult into the spec's output JSON shape.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from xer_modify import apply_changes  # noqa: E402
from xer_io import write  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/xer_modify.py"


def apply_xer_changes_impl(
    xer_path: str,
    changes: list[dict],
    *,
    output_path: Optional[str] = None,
    strict: bool = False,
    dry_run: bool = False,
    target_milestone_id: Optional[str] = None,
    cache,
) -> dict:
    """Apply a list of change records to the XER at xer_path.

    Args:
        xer_path: Path to the source .xer file.
        changes: List of change-record dicts (see xer_modify.apply_changes).
        output_path: Where to write the modified XER.  Defaults to
            ``<input>-modified.xer`` beside the input file.  Raises
            FileExistsError if the file already exists — supply an explicit
            output_path to choose a different location.
        strict: If True, post-state warnings are promoted to errors.
        dry_run: If True, all four passes run and feedback is returned, but
            no file is written.
        target_milestone_id: P6 task_id for the milestone to use in the
            post-CPM completion-date comparison.  Auto-detected (latest
            TT_FinMile) when None.
        cache: CpmCache instance.

    Returns:
        JSON-serialisable dict with keys:
            output_path, dry_run, summary, post_cpm_summary,
            per_change_feedback.
    """
    cache.pin(xer_path)
    try:
        doc = cache.get_for_writing(xer_path)
        pre_cpm_results, _ = cache.get_cpm(xer_path)

        result = apply_changes(
            doc,
            changes,
            strict=strict,
            dry_run=dry_run,
            pre_state_cpm=pre_cpm_results,
            target_milestone_id=target_milestone_id,
        )

        out: dict = {
            "output_path": None,
            "dry_run": dry_run,
            "summary": {
                "changes_applied": result.changes_applied,
                "validation_errors": [
                    {
                        "change_index": e.change_index,
                        "code": e.code,
                        "message": e.message,
                    }
                    for e in result.validation_errors
                ],
                "validation_warnings": [
                    {
                        "change_index": w.change_index,
                        "code": w.code,
                        "message": w.message,
                    }
                    for w in result.validation_warnings
                ],
            },
            "post_cpm_summary": result.post_cpm_summary,
            "per_change_feedback": [
                {
                    "change_index": pcf.change_index,
                    "type": pcf.type,
                    "feedback": pcf.feedback,
                }
                for pcf in result.per_change_feedback
            ],
        }

        # Bail on error: file was not written, output_path stays null.
        if result.validation_errors or result.doc is None:
            return out

        # Bail on dry_run: all passes ran, feedback is populated, no write.
        if dry_run:
            return out

        # Derive the default output path if the caller didn't supply one.
        if output_path is None:
            input_path = Path(xer_path)
            output_path = str(input_path.with_name(f"{input_path.stem}-modified.xer"))

        if Path(output_path).exists():
            raise FileExistsError(
                f"Output already exists: {output_path}. "
                "Pass a different output_path or remove the existing file."
            )

        write(result.doc, output_path)
        # Lazy CPM: insert doc only; get_cpm will compute on demand.
        cache.put_doc(output_path, result.doc)
        out["output_path"] = output_path
        return out

    finally:
        cache.unpin(xer_path)


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="apply_xer_changes", lib_script=_LIB_SCRIPT)
    def apply_xer_changes(
        xer_path: str,
        changes: list[dict],
        output_path: Optional[str] = None,
        strict: bool = False,
        dry_run: bool = False,
        target_milestone_id: Optional[str] = None,
    ) -> dict:
        """Apply structured change records to an XER and write the result.

        Runs a 4-pass pipeline:
          Pass 1 — syntactic validation (unknown types rejected immediately).
          Pass 2 — handler loop on a deep copy (original never mutated).
          Pass 3 — post-state xer_validate (new error-severity issues block write).
          Pass 4 — post-state CPM diff vs pre-state baseline (feedback only).

        On success (and not dry_run), writes the mutated doc to output_path
        and inserts it into the cache so downstream tools can use it immediately.

        Args:
            xer_path: Path to the source .xer file.
            changes: List of change-record dicts.  Each must have a ``type``
                field naming the handler (e.g. ``set_duration``, ``add_logic``,
                ``remove_activity``).  See xer_modify.py for the full list of
                supported types and their required fields.
            output_path: Destination path for the modified XER.  Defaults to
                ``<input>-modified.xer`` beside the input.  Raises
                FileExistsError if the destination already exists.
            strict: If True, post-state warnings are promoted to errors and
                block the write.
            dry_run: If True, all validation passes run and feedback is
                returned, but no file is written.
            target_milestone_id: P6 task_id (numeric string) of the milestone
                to use in the completion-date diff inside post_cpm_summary.
                Auto-selects the latest TT_FinMile when None.

        Returns:
            ``{output_path, dry_run, summary: {changes_applied,
            validation_errors, validation_warnings}, post_cpm_summary:
            {target_milestone_id, completion_before, completion_after,
            net_days_change, critical_path_changed, substantial_cp_change},
            per_change_feedback: [{change_index, type, feedback}]}``
        """
        return apply_xer_changes_impl(
            xer_path,
            changes,
            output_path=output_path,
            strict=strict,
            dry_run=dry_run,
            target_milestone_id=target_milestone_id,
            cache=cache,
        )
