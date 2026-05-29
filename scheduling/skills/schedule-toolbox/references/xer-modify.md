# XER Modification — `apply_xer_changes`

==============================================================================
NEVER OVERWRITE THE ORIGINAL XER FILE. WRITE TO A NEW OUTPUT PATH ONLY.
CONFIRM OUTPUT PATH WITH USER BEFORE WRITING.
==============================================================================

## Use `apply_xer_changes`, not hand-rolled line editing

The old line-slicing write-back recipe that previously lived in this file is gone. `apply_xer_changes` supersedes it entirely. The MCP tool delegates to `lib/xer_io.py` + `lib/xer_modify.py`, which handle cp1252 encoding, CRLF endings, byte-fidelity for untouched rows, field-order preservation, and the post-write CPM run. Writing XER bytes by hand risks corrupting adjacent tables, dropping required fields, or introducing encoding artifacts that P6 silently rejects. Call the tool.

---

## Change-type catalog

All change records are tagged unions discriminated by `"type"`. Pass them as a list to `apply_xer_changes(xer_path, changes=[...])`.

### Activity-level (6 types)

**`set_duration`** — change an activity's remaining and target duration.

```json
{ "type": "set_duration",
  "activity_id": "A1050",
  "new_duration_days": 10 }
```

**`set_calendar`** — reassign an activity to a different calendar. The new calendar must exist in the file.

```json
{ "type": "set_calendar",
  "activity_id": "A1050",
  "new_calendar_id": "CAL-7DAY" }
```

**`add_activity`** — insert a new activity. `calendar_id` and `wbs_id` must exist in post-state (a preceding `add_wbs` in the same call satisfies this).

```json
{ "type": "add_activity",
  "spec": {
    "code": "A2010",
    "name": "Install Drywall - Level 1",
    "duration_days": 8,
    "calendar_id": "CAL-5DAY",
    "wbs_id": "WBS-INTERIOR",
    "activity_type": "TT_Task"
  }
}
```

**`remove_activity`** — delete an activity and all of its TASKPRED rows (both predecessor and successor sides).

```json
{ "type": "remove_activity",
  "activity_id": "A1099" }
```

**`dissolve_activity`** — P6 Dissolve semantics. Removes the activity and for every `(pred, succ)` pair creates a new edge: `pred -FS+(pred_lag + dissolved_duration + succ_lag)-> succ`. Useful for collapsing a placeholder that was holding two chains together. Fires a warning if the cartesian product exceeds 20 new edges.

```json
{ "type": "dissolve_activity",
  "activity_id": "A1040" }
```

See "Notes on dissolve and pop" below for the cartesian-product semantics.

**`pop_activity`** — inverse of dissolve. Inserts a new activity into an existing edge, replacing `A -> B` with `A -> X -> B`. The `(predecessor_id, successor_id)` edge must exist.

```json
{ "type": "pop_activity",
  "predecessor_id": "A1010",
  "successor_id":   "A1020",
  "spec": {
    "code": "A1015",
    "name": "Install Blocking",
    "duration_days": 3,
    "calendar_id": "CAL-5DAY",
    "wbs_id": "WBS-FRAMING",
    "activity_type": "TT_Task"
  },
  "split_lag": "preserve_total"
}
```

`split_lag` options:

- `"preserve_total"` — the original `A -> B` lag migrates to the `X -> B` leg; `A -> X` gets lag 0.
- `"drop"` — both new edges get lag 0.

Both new edges inherit the relationship type of the original `A -> B` edge.

---

### Logic-level (3 types)

P6 allows multiple edges between the same activity pair with different relationship types (FS and SS can coexist on the same pair). The `(predecessor_id, successor_id)` pair alone is not a unique key. `remove_logic` and `modify_logic` therefore require `relationship` as a selector to identify the specific edge.

**`add_logic`** — add a new relationship.

```json
{ "type": "add_logic",
  "predecessor_id": "A1010",
  "successor_id":   "A1020",
  "relationship":   "FS",
  "lag_days":       2 }
```

**`remove_logic`** — remove a specific edge by its `(predecessor_id, successor_id, relationship)` triple.

```json
{ "type": "remove_logic",
  "predecessor_id": "A1010",
  "successor_id":   "A1020",
  "relationship":   "FS" }
```

**`modify_logic`** — change the lag or relationship type of an existing edge. `new_relationship` and `new_lag_days` are both optional; omit either to keep the existing value.

```json
{ "type": "modify_logic",
  "predecessor_id":  "A1010",
  "successor_id":    "A1020",
  "relationship":    "FS",
  "new_relationship": "SS",
  "new_lag_days":    0 }
```

---

### WBS-level (4 types)

**`add_wbs`** — add a new WBS node. `parent_wbs_id` must exist in post-state. `wbs_short_name` is optional (recommended — P6 uses it in column views).

```json
{ "type": "add_wbs",
  "spec": {
    "wbs_code":       "DEMO",
    "wbs_name":       "DEMOLITION",
    "parent_wbs_id":  "WBS-CONSTRUCTION",
    "wbs_short_name": "DEMO"
  }
}
```

**`remove_wbs`** — remove a WBS node. `cascade` controls behavior when activities or child WBS nodes reference it.

- `"fail_if_used"` — error if any activity or child WBS references the removed node. Safe default.
- `"move_to_parent"` — reparent referencing activities and child WBS nodes to the removed node's parent before deleting.

```json
{ "type": "remove_wbs",
  "wbs_id":  "WBS-DEMO",
  "cascade": "fail_if_used" }
```

**`modify_wbs`** — rename or reparent a WBS node. All fields are optional; supply only what changes. `new_parent_wbs_id` is cycle-checked.

```json
{ "type": "modify_wbs",
  "wbs_id":          "WBS-SITEWORK",
  "new_wbs_name":    "SITEWORK & UTILITIES",
  "new_wbs_short_name": "SITE" }
```

**`move_activities_to_wbs`** — bulk-reassign a list of activities to a different WBS node. All `activity_ids` and `new_wbs_id` must exist.

```json
{ "type": "move_activities_to_wbs",
  "activity_ids": ["A2010", "A2020", "A2030"],
  "new_wbs_id":   "WBS-INTERIOR-L2" }
```

---

### Composite (1 type)

**`apply_anchor_absorption`** — select one absorption suggestion from a prior `get_anchor_absorption_suggestions` call and apply it. Lowered internally to a set of `set_duration` changes at validation time. Use when `get_anchor_conflicts` has flagged a slip and the scheduler has reviewed the suggestions.

```json
{ "type": "apply_anchor_absorption",
  "anchor_slip":      { "...one entry from get_anchor_conflicts output..." },
  "suggestion_index": 0 }
```

---

## `dry_run` and `strict` semantics

| Flag | Behavior |
|------|----------|
| default | Errors block the write; warnings are advisory only |
| `strict: true` | Both errors and warnings block the write |
| `dry_run: true` | Runs all validation passes + post-CPM; returns the full output shape but writes nothing. `output_path` is null in the response. Does not touch the output cache. |

Use `dry_run: true` to preview the impact of a change set before committing — especially useful for large batch edits or before handing a file to a client.

---

## Output shape summary

```jsonc
{
  "output_path": "...",          // null on dry_run or any blocking error
  "dry_run": false,
  "summary": {
    "changes_applied": 3,
    "validation_errors":   [{ "change_index": 1, "code": "DANGLING_CALENDAR", "message": "..." }],
    "validation_warnings": [{ "change_index": 2, "code": "ORPHAN_ACTIVITY",   "message": "..." }]
  },
  "post_cpm_summary": {
    "target_milestone_id":   "SC-001",
    "completion_before":     "2027-03-15",
    "completion_after":      "2027-03-08",
    "net_days_change":       -7,
    "critical_path_changed": true,
    "substantial_cp_change": false
  },
  "per_change_feedback": [
    { "change_index": 0, "type": "set_duration",
      "feedback": { "activity_end_before": "2026-11-01", "activity_end_after": "2026-10-25",
                    "milestone_impact_days": -7, "now_on_critical_path": true } }
  ]
}
```

One CPM run occurs at the end of all changes; per-change feedback is derived by diffing pre-state (cached) vs post-state. Avoid submitting N separate `apply_xer_changes` calls when a single call with N records will do — one CPM run vs N.

---

## Notes on dissolve_activity and pop_activity

**`dissolve_activity` — cartesian semantics.** If the dissolved activity has M predecessors and N successors, the result is M × N new edges. Each new edge carries the combined lag: `pred_lag + dissolved_activity_duration + succ_lag`. This matches P6's built-in Dissolve behavior. High-fanout dissolves (> 20 new edges) trigger a warning; use `strict: true` to make that an error.

**`pop_activity` — the inverse.** Where `dissolve_activity` collapses a node and splices its neighbors directly, `pop_activity` inserts a new node into an existing edge. The named `(predecessor_id, successor_id)` edge must exist before the call. The inserted activity inherits the relationship type of the edge it replaces on both legs.

These two operations compose: you can dissolve a placeholder and pop in a replacement in the same `changes` list. Order-aware reference resolution means the dissolved activity's ID is gone by the time a later `pop_activity` runs — make sure the pop references an edge that still exists in post-state.

---

## Fixing duplicate IDs

Use `fix_duplicate_activity_ids` rather than a manual correction when a file has duplicate `task_code` values (the most common XER export bug). Three strategies:

- `"renumber"` (default) — keep the first occurrence; rename the rest to a free ID. Returns a mapping for downstream reconciliation (Procore import logs, etc.).
- `"report_only"` — detect and report only; write nothing.
- `"merge_consolidate"` — for true duplicates (same code, same duration, same WBS), keep one row and reroute all logic to it. Use sparingly; confirm with the user before invoking.

After running `fix_duplicate_activity_ids`, call `validate_xer_structure` on the output to confirm `import_ready: true` before importing.
