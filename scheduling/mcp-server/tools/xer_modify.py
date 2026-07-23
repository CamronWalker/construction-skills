"""MCP wrappers for xer_modify lib functions.

Thin adapters over functions from xer_modify in schedule-toolbox/lib.

apply_xer_changes — apply structured change records to an XER.
create_xer_from_template — instantiate a skeleton XER with project metadata.
fix_duplicate_activity_ids — detect and resolve duplicate task_code values.

Common responsibilities handled here:
  - Cache pinning (pin on entry, unpin in finally) for write-path tools.
  - Writing the mutated doc to disk and inserting it into the cache.
  - Marshalling lib return values into the spec's output JSON shapes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from xer_modify import apply_changes, create_from_template, fix_duplicate_ids  # noqa: E402
from xer_io import write  # noqa: E402
import xer_validate  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/xer_modify.py"

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Characters that are illegal in filenames on Windows or that act as path
# separators on any platform.  Replace them all with "_".
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


def _sanitize_filename(name: str) -> str:
    """Replace path separators and illegal filename characters with '_'."""
    return _UNSAFE_FILENAME_RE.sub("_", name)


def create_xer_from_template_impl(
    skeleton_name: str,
    metadata: dict,
    *,
    output_path: Optional[str] = None,
    cache,
) -> dict:
    """Instantiate a skeleton XER and stamp it with project metadata.

    Args:
        skeleton_name: Base name of the skeleton file (without .xer extension),
            e.g. "westland-skeleton-v1".  Must exist under
            scheduling/mcp-server/templates/.
        metadata: Dict of project metadata keys.  Required: project_name,
            project_id.  Optional: planned_start, planned_data_date,
            task_code_prefix.  See xer_modify.create_from_template for full
            details.
        output_path: Where to write the new XER.  Defaults to
            ``{project_name}.xer`` (sanitized) in the current working
            directory.  Raises FileExistsError if the file already exists.
        cache: CpmCache instance.

    Returns:
        JSON-serialisable dict with keys:
            output_path, project_name, ntp_milestone, sc_milestone,
            validation.
    """
    skeleton_path = _TEMPLATES_DIR / f"{skeleton_name}.xer"
    if not skeleton_path.exists():
        available = [p.stem for p in _TEMPLATES_DIR.glob("*.xer")]
        raise FileNotFoundError(
            f"Skeleton not found: {skeleton_path}. "
            f"Available skeletons: {available or ['(none)']}"
        )

    doc = create_from_template(str(skeleton_path), metadata)

    if output_path is None:
        safe_name = _sanitize_filename(metadata.get("project_name", "output"))
        output_path = str(Path.cwd() / f"{safe_name}.xer")

    if Path(output_path).exists():
        raise FileExistsError(
            f"Output already exists: {output_path}. "
            "Pass a different output_path or remove the existing file."
        )

    # Validate BEFORE writing and refuse to persist a file that would fail
    # P6/SmartPM import — matches the apply_xer_changes Pass-3 gate, so neither
    # entry point can ever emit a malformed .xer to disk.
    report = xer_validate.validate(doc)
    if not report.import_ready:
        errors = [i for i in report.issues if i.severity == "error"]
        detail = "; ".join(f"{i.code}: {i.message}" for i in errors[:10])
        raise ValueError(
            f"create_xer_from_template: generated schedule failed import validation "
            f"({len(errors)} error-severity issue(s)); refusing to write {output_path}. "
            f"{detail}"
        )

    write(doc, output_path)
    cache.put_doc(output_path, doc)

    # Extract NTP and SC milestone task_ids from the written doc.
    task_section = doc.section("TASK")
    ntp_milestone: dict = {}
    sc_milestone: dict = {}
    if task_section is not None:
        for row in task_section.rows:
            code = row.get("task_code", "")
            if code == "MILESTONE-NTP":
                ntp_milestone = {"task_id": row["task_id"], "task_code": code}
            elif code == "MILESTONE-SC":
                sc_milestone = {"task_id": row["task_id"], "task_code": code}

    return {
        "output_path": output_path,
        "project_name": metadata.get("project_name"),
        "ntp_milestone": ntp_milestone or None,
        "sc_milestone": sc_milestone or None,
        "validation": {
            "import_ready": report.import_ready,
            "summary": report.summary,
        },
    }


def fix_duplicate_activity_ids_impl(
    xer_path: str,
    *,
    strategy: str = "renumber",
    output_path: Optional[str] = None,
    cache,
) -> dict:
    """Detect and resolve duplicate task_code values in an XER.

    Args:
        xer_path: Path to the source .xer file.
        strategy: One of "renumber" (default), "report_only",
            "merge_consolidate".  See xer_modify.fix_duplicate_ids for
            semantics.
        output_path: Destination path for the fixed XER (ignored for
            report_only).  Defaults to ``<input>-fixed.xer`` beside the
            input.  Raises FileExistsError if the file already exists.
        cache: CpmCache instance.

    Returns:
        JSON-serialisable dict with keys:
            output_path, strategy, duplicates_found, mapping, unresolved.
    """
    cache.pin(xer_path)
    try:
        doc = cache.get_for_writing(xer_path)
        new_doc, result = fix_duplicate_ids(doc, strategy)

        out: dict = {
            "output_path": None,
            "strategy": strategy,
            "duplicates_found": result["duplicates_found"],
            "mapping": result["mapping"],
            "unresolved": result.get("unresolved", []),
        }

        if strategy == "report_only":
            return out

        # Derive the default output path if the caller didn't supply one.
        if output_path is None:
            input_path = Path(xer_path)
            output_path = str(input_path.with_name(f"{input_path.stem}-fixed.xer"))

        if Path(output_path).exists():
            raise FileExistsError(
                f"Output already exists: {output_path}. "
                "Pass a different output_path or remove the existing file."
            )

        write(new_doc, output_path)
        cache.put_doc(output_path, new_doc)
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

    @mcp.tool()
    @wrap_tool_errors(tool_name="create_xer_from_template", lib_script=_LIB_SCRIPT)
    def create_xer_from_template(
        skeleton_name: str,
        metadata: dict,
        output_path: Optional[str] = None,
    ) -> dict:
        """Instantiate a Westland skeleton XER with project-specific metadata.

        Resolves the skeleton from scheduling/mcp-server/templates/{skeleton_name}.xer,
        stamps it with the supplied metadata (project_name, project_id, dates),
        writes the result to output_path, and returns the NTP/SC milestone
        task_ids plus a validation summary.

        Args:
            skeleton_name: Base name of the skeleton file without the .xer
                extension.  Example: "westland-skeleton-v1".  Must exist in
                the templates directory.  If not found, the error message
                lists the available skeletons.
            metadata: Project metadata dict.  Required keys: project_name
                (string), project_id (string).  Optional keys: planned_start
                (YYYY-MM-DD or YYYY-MM-DD HH:MM), planned_data_date
                (YYYY-MM-DD), task_code_prefix (string).
            output_path: Destination path for the new XER.  Defaults to
                ``{project_name}.xer`` (sanitized) in the current working
                directory.  Raises FileExistsError if the file already exists.

        Returns:
            ``{output_path, project_name,
            ntp_milestone: {task_id, task_code},
            sc_milestone: {task_id, task_code},
            validation: {import_ready, summary: {errors, warnings, info}}}``
        """
        return create_xer_from_template_impl(
            skeleton_name,
            metadata,
            output_path=output_path,
            cache=cache,
        )

    @mcp.tool()
    @wrap_tool_errors(tool_name="fix_duplicate_activity_ids", lib_script=_LIB_SCRIPT)
    def fix_duplicate_activity_ids(
        xer_path: str,
        strategy: str = "renumber",
        output_path: Optional[str] = None,
    ) -> dict:
        """Detect and resolve duplicate task_code values in an XER.

        Strategies:
          renumber (default) — keep the first occurrence of each duplicate
            task_code and rename the rest to unused codes.  Logic edges
            (TASKPRED) are unaffected because they reference task_id, not
            task_code.
          report_only — detect duplicates and compute proposed renames without
            mutating or writing anything.  output_path is null in the result.
          merge_consolidate — for true duplicates (same code AND same duration
            AND same WBS — likely an XER-export double-emit), keep the first
            row, delete the rest, and reroute logic edges to the survivor.
            Groups where rows differ on duration or WBS are placed in
            'unresolved' and left untouched.

        Args:
            xer_path: Path to the source .xer file.
            strategy: One of "renumber", "report_only", "merge_consolidate".
                Defaults to "renumber".
            output_path: Destination for the fixed XER (ignored for
                report_only).  Defaults to ``<input>-fixed.xer`` beside the
                input.  Raises FileExistsError if the file already exists.

        Returns:
            ``{output_path (null for report_only), strategy,
            duplicates_found, mapping: [{original_id, new_id, task_name,
            reason}], unresolved: [{original_id, reason}]}``
        """
        return fix_duplicate_activity_ids_impl(
            xer_path,
            strategy=strategy,
            output_path=output_path,
            cache=cache,
        )
