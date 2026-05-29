# Schedule Toolbox MCP — Tier 3 Modification + Generation — Design

**Date:** 2026-05-27
**Status:** Draft — pending user review
**Owner:** Camron
**MCP server:** Westland Scheduler Local MCP
**Predecessor specs:** [2026-05-24-schedule-toolbox-mcp-design.md](2026-05-24-schedule-toolbox-mcp-design.md) (overall MCP spec)
**Predecessor plans:** [Plan 1 — Foundation](../plans/2026-05-24-westland-scheduler-mcp-plan-1-foundation.md) (shipped 7.x), [Plan 2 — Analytics](../plans/2026-05-26-westland-scheduler-mcp-plan-2-analytics.md) (shipped 8.x)

## Problem

Plans 1 and 2 made the MCP a powerful read-only surface — 33 analysis tools plus 8 cross-baseline / delay-analytics tools, all running through the cached parsed XER. What's missing: any way for Claude to *change* an XER. Schedulers still hand-edit P6 for the routine bulk of mutations (renumber duplicates, splice in a new activity, dissolve a redundant one, switch a Pattern A schedule to Pattern B, build a fresh proposal schedule from scratch). The proposal-schedule iteration loop in particular regenerates files via `build_from_raw_template.py` — a hand-crafted byte-fidelity template script that works but isn't reachable from the MCP and isn't compositional.

Tier 3 closes the gap: read-write parity. Claude can answer schedule questions *and* commit changes back to disk, with the same atomicity, cache-awareness, and post-CPM feedback that make the analytics tools useful.

## Goals

1. Five new MCP tools for XER mutation and generation, all sharing the cache, all writing new files (immutable input).
2. One round-trip-safe XER I/O module (`lib/xer_io.py`) that the write-path tools share. Existing read-only tools keep working — no churn.
3. One hand-curated `westland-skeleton-v1.xer` template + sidecar notes file, produced via agent-per-table investigation of a corpus of 10–15 known-good Westland XERs.
4. Unified cache: one parse per file, one entry per file, with explicit pinning + recency guards so a 20-minute edit session doesn't evict the active target.
5. End-to-end smoke against a real Westland project before release.

## Non-goals

- **Not deprecating `build_from_raw_template.py`.** It stays in `lib/` as a working reference. `create_xer_from_template` is the new canonical entry point, but the standalone script is still importable for non-Claude callers and historical comparison.
- **Not adding a `prepare_xer` handle or any explicit lifecycle to the caller.** The cache is transparent. Claude does not manage pinning manually except for the rare long-session case.
- **Not validating against P6 import semantics inside the MCP.** `validate_xer_structure` catches the file-integrity failures we can detect from the XER bytes alone. The "will P6 actually accept this?" question is answered by the manual import gate at skeleton-curation time and by the end-to-end smoke before release.

---

## Section 1 — Scope and architecture

**Five new MCP tools** (plus the unified cache and the new I/O module):

| Tool | Source module | Role |
|------|--------------|------|
| `validate_xer_structure` | `lib/xer_validate.py` (new) | Comprehensive file-integrity check — duplicates, dangling refs, cycles, negative durations, orphans. Read-only; reports `import_ready: bool`. |
| `fix_duplicate_activity_ids` | `lib/xer_modify.py` (new) | Targeted fix for the single most common bug. Writes a new XER. |
| `apply_xer_changes` | `lib/xer_modify.py` (new) | Polymorphic mutation. 14 change types. Atomic, post-CPM feedback, dry-run capable. |
| `create_xer_from_template` | `lib/xer_modify.py` (new) | Copies `westland-skeleton-v1.xer`, sets project metadata, returns NTP/SC milestone IDs. |
| `invalidate_cache_for` | `mcp-server/tools/structure.py` (extend) | Thin cache wrapper. ~10 lines. |

**Two supporting deliverables:**

- `mcp-server/templates/westland-skeleton-v1.xer` — hand-curated skeleton (corpus + agent-per-table investigation)
- `mcp-server/templates/westland-skeleton-v1.notes.md` — sidecar documenting corpus, per-table findings, judgement calls

**One foundational new module:**

- `lib/xer_io.py` — round-trip-safe parser + writer (preserves ERMHDR, per-table `%F` field-order lists, `%E` markers). Used only by write-path tools. Existing read-only tools see the same dict shape via projection from the new rich form.

**One module reorganization (cache):**

- Single parse pipeline through `xer_io.parse_for_writing`; `get_parsed()` projects from `XerDoc` to the existing lossy dict shape. Cache adds `get_for_writing()`, `pin()`, `unpin()`, `is_pinned()`, and a 30-minute recency guard. LRU bound grows 8 → 16.

---

## Section 2 — `apply_xer_changes` change types

Fourteen change types, all tagged unions discriminated by `"type"`:

```jsonc
// --- Activity-level (5) ---
{ "type": "add_activity",
    "spec": { "code", "name", "duration_days",
              "calendar_id", "wbs_id", "activity_type" } }

{ "type": "remove_activity", "activity_id": "..." }

{ "type": "dissolve_activity", "activity_id": "..." }
    // P6 Dissolve: removes activity; for every (pred, succ) pair creates
    //   pred -FS+(pred_lag + dissolved_duration + succ_lag)-> succ

{ "type": "pop_activity",
    "predecessor_id": "...", "successor_id": "...",
    "spec": { /* same shape as add_activity.spec */ },
    "split_lag": "preserve_total" | "drop" }
    // Insert new X between existing A->B edge:
    //   - replace A->B with A->X (FS, lag=0) and X->B (FS, lag=original lag if preserve_total, else 0)
    //   - inherits A->B relationship type for both new edges

{ "type": "set_duration",
    "activity_id": "...", "new_duration_days": int }

{ "type": "set_calendar",
    "activity_id": "...", "new_calendar_id": "..." }

// --- Logic-level (3) ---
{ "type": "add_logic",
    "predecessor_id", "successor_id",
    "relationship": "FS"|"SS"|"FF"|"SF",
    "lag_days": int }

{ "type": "remove_logic",
    "predecessor_id", "successor_id",
    "relationship": "FS"|"SS"|"FF"|"SF" }   // selector

{ "type": "modify_logic",
    "predecessor_id", "successor_id",
    "relationship":     "FS"|"SS"|"FF"|"SF",   // selects the edge
    "new_relationship": "FS"|"SS"|"FF"|"SF",   // optional, defaults to existing
    "new_lag_days":     int }                  // optional, defaults to existing

// --- WBS-level (4) ---
{ "type": "add_wbs",
    "spec": { "wbs_code", "wbs_name", "parent_wbs_id", "wbs_short_name"? } }

{ "type": "remove_wbs",
    "wbs_id": "...",
    "cascade": "fail_if_used" | "move_to_parent" }

{ "type": "modify_wbs",
    "wbs_id": "...",
    "new_wbs_code"?, "new_wbs_name"?, "new_parent_wbs_id"?, "new_wbs_short_name"? }

{ "type": "move_activities_to_wbs",
    "activity_ids": ["..."], "new_wbs_id": "..." }

// --- Composite (1) ---
{ "type": "apply_anchor_absorption",
    "anchor_slip":      { /* one entry from get_anchor_conflicts */ },
    "suggestion_index": int }
    // Lowered internally to a set of set_duration changes when validated.
    // Kept high-level so callers don't reconstruct the absorption logic.
```

**Asymmetry note on logic edges:** P6 allows multiple edges between the same activity pair with different relationship types (A —FS→ B *and* A —SS→ B can coexist). `(predecessor_id, successor_id)` alone is not a unique key. `remove_logic` and `modify_logic` therefore take `relationship` as a selector; `modify_logic` accepts an optional `new_relationship` for relationship-type changes (default: keep existing).

**`set_duration` / `set_calendar` kept separate (not merged into a single `modify_activity`):** validation rules differ — calendar-change requires the new calendar to exist; duration-change is a simple delta. Per-change feedback also differs — `set_calendar` triggers a recompute of working days; `set_duration` is straightforward.

---

## Section 3 — Validation, output, transaction semantics

**Validation runs in 3 passes, all in-memory, no file touched until commit:**

1. **Per-record syntactic check** — required fields present, enum values valid, numeric ranges sane.
2. **Order-aware reference resolution** — apply each change against the cached parsed XER in order; track post-state IDs (calendars, WBS, activities) so `add_activity` at index N can satisfy `add_logic` at index N+1.
3. **Post-state graph check** — orphan rule, cycle check (full DFS on `TASKPRED` post-state), duplicate-edge check.

If pass 2 or 3 fails: no file written. Errors and warnings come back in `summary`.

**Validation rules (atomic, all-or-nothing):**

| # | Rule | Severity |
|---|------|----------|
| 1 | Orphan rule (post-state): no activity has zero predecessors AND zero successors, except project start milestone and terminal milestones. Catches `add_activity` without logic and `remove_logic` orphaning an existing activity. | error |
| 2 | Referenced IDs (activity, calendar, WBS) must exist in post-state after order-aware resolution. | error |
| 3 | No duplicate activity IDs introduced. | error |
| 4 | No circular logic introduced (full graph cycle check). | error |
| 5 | Durations > 0. | error |
| 6 | `dissolve_activity` on a task with 0 predecessors OR 0 successors splices the existing side gracefully (not an error). | n/a |
| 7 | `pop_activity` requires the named `(pred, succ)` edge to exist. | error |
| 8 | `remove_logic` / `modify_logic` require exactly one matching `(pred, succ, relationship)` triple. | error |
| 9 | `add_wbs.parent_wbs_id` must exist in post-state. | error |
| 10 | `remove_wbs` with `fail_if_used` errors if any activity or child WBS references the removed ID. | error |
| 11 | `modify_wbs.new_parent_wbs_id` must not create a WBS cycle. | error |
| 12 | `move_activities_to_wbs.new_wbs_id` must exist; all `activity_ids` must exist. | error |
| 13 | `dissolve_activity` producing > 20 new edges (high cartesian fanout). | warning |
| 14 | `add_activity` with no WBS reference. | warning |

**Severity controls:**

| Caller flag | Behavior |
|--|--|
| default | Errors block write; warnings allowed |
| `strict: true` | Errors block write; warnings also block |
| `dry_run: true` | Run all 3 passes + post-CPM, return full output shape, skip the write |

**Output shape:**

```jsonc
{
  "output_path": "...",  // null on dry_run or any error
  "dry_run":     bool,
  "summary": {
    "changes_applied":     int,
    "validation_errors":   [{ "change_index": int|null, "code": "...", "message": "..." }],
    "validation_warnings": [{ "change_index": int|null, "code": "...", "message": "..." }]
  },
  "post_cpm_summary": {
    "target_milestone_id":   "...",
    "completion_before":     "YYYY-MM-DD",
    "completion_after":      "YYYY-MM-DD",
    "net_days_change":       int,
    "critical_path_changed": bool,
    "substantial_cp_change": bool   // > 5 activities moved on/off CP
  },
  "per_change_feedback": [
    { "change_index": 0, "type": "set_duration",
      "feedback": { "activity_end_before", "activity_end_after",
                    "milestone_impact_days", "now_on_critical_path": bool } },
    { "change_index": 1, "type": "add_logic",
      "feedback": { "path_through_new_link": [...], "critical_path_changed": bool,
                    "near_critical_chains_affected": int } },
    { "change_index": 2, "type": "dissolve_activity",
      "feedback": { "new_edges_created": int,
                    "edges_summary": [{ "from", "to", "relationship", "lag_days" }] } },
    { "change_index": 3, "type": "pop_activity",
      "feedback": { "new_activity_path": [...], "new_activity_float": float,
                    "near_critical_chains_affected": int } }
    // one entry per change; shape varies by type
  ]
}
```

**One CPM run** at the end of all changes — per-change feedback is derived by diffing pre-state (cached) vs post-state. Avoids N CPM runs for N changes; same information.

**Cache integration:**

- Input XER read through `CpmCache.get_cpm` (free if warm from earlier tool call).
- Output XER's mutated `XerDoc` + freshly-computed CPM result inserted into cache with new file's `(size, mtime)` key. First downstream call against the new path is a hot hit.
- `dry_run: true` does not touch the output cache.
- `output_path` collisions return an error with suggested suffix (`-v2`, `-v3`, ...). Never silent overwrite.

**File naming when `output_path` omitted:** `<input_basename>-modified.xer`. If that exists, `-modified-v2.xer`, `-modified-v3.xer`, etc.

---

## Section 4 — `validate_xer_structure` + `fix_duplicate_activity_ids`

### `validate_xer_structure`

Read-only comprehensive file-integrity check. Distinct from `quality_checks` (those are schedule-health, this is "will this import").

Issue codes by category:

| Category | Codes | Severity |
|----------|-------|----------|
| **Duplicates** | `DUPLICATE_ACTIVITY_ID`, `DUPLICATE_RELATIONSHIP`, `DUPLICATE_CALENDAR_ID`, `DUPLICATE_WBS_CODE` | error |
| **Dangling refs** | `DANGLING_PREDECESSOR`, `DANGLING_SUCCESSOR`, `DANGLING_CALENDAR`, `DANGLING_WBS`, `DANGLING_RESOURCE` | error |
| **Logic** | `CIRCULAR_LOGIC` (returns cycle path), `SELF_LOOP` | error |
| **Data** | `NEGATIVE_DURATION`, `INVALID_DATE`, `INVALID_RELATIONSHIP_TYPE`, `INVALID_STATUS_CODE` | error |
| **Network** | `ORPHAN_ACTIVITY` (zero preds AND zero succs, non-terminal) | warning |
| **Structure** | `ORPHANED_WBS_BRANCH`, `MISSING_PROJECT_ROW`, `MULTIPLE_PROJECT_ROWS` | warning |
| **Status** | `STATUS_DATE_MISMATCH`, `ACTUAL_AFTER_DATA_DATE` | warning |

Output:

```jsonc
{
  "import_ready": bool,            // true iff zero error-severity issues
  "issues": [
    { "severity": "error"|"warning"|"info",
      "category": "Duplicates",
      "code":     "DUPLICATE_ACTIVITY_ID",
      "message":  "Activity code 'A1010' appears in 2 rows (task_id 1234, 5678)",
      "affected": ["1234", "5678"] }
  ],
  "summary": { "errors": int, "warnings": int, "info": int }
}
```

The same check engine and `affected` shape feed `apply_xer_changes` post-state validation — one issue format, two callers.

### `fix_duplicate_activity_ids`

Targeted fix for the single most common XER bug.

Inputs:
```jsonc
{ xer_path,
  strategy?: "renumber" | "report_only" | "merge_consolidate"  // default "renumber"
  output_path? }
```

Output:
```jsonc
{ output_path,
  duplicates_found: int,
  mapping:    [{ original_id, new_id, task_name, reason }],
  unresolved: []   // populated if strategy chose to skip some
}
```

Three strategies:

- **`renumber`** (default) — for each duplicate group, keep the first occurrence, rename the rest to a free ID. Mapping preserved in output for downstream reconciliation (Procore import logs, etc.). Uses the same ID-generation policy as `add_activity` — lowest unused suffix in the activity_code namespace.
- **`report_only`** — runs the check, writes nothing. Same shape as a dry-run.
- **`merge_consolidate`** — for true duplicates (same code, same duration, same WBS — likely an XER export bug), keep one row and reroute all logic referencing the dupes to point at the kept row. Use rarely; surface a confirmation prompt before invoking.

---

## Section 5 — `lib/xer_io.py` + unified cache

### `lib/xer_io.py`

Pure I/O module. No cache awareness, no state, no semantics.

**API:**
```python
def parse_for_writing(xer_path: str) -> XerDoc: ...
def write(doc: XerDoc, output_path: str) -> None: ...

class XerDoc:
    header_line: str                              # ERMHDR\t...
    encoding:    str                              # "cp1252" | "utf-8-sig" | etc.
    sections:    list[XerSection]                 # ordered, preserved

class XerSection:
    name:        str                              # "PROJECT", "TASK", ...
    field_order: list[str]                        # ordered field names from %F line
    rows:        list[dict[str, str]]             # mutable dicts, key = field name
    raw_lines:   list[str] | None                 # original %R lines, byte-for-byte
                                                  #   None for new sections
    e_line:      str                              # original %E line text
```

**Read pass** captures everything the lossy `_parse_xer` drops:
- `header_line` — ERMHDR with version/timestamp/user, verbatim
- `encoding` — detected via the existing fallback chain (cp1252 → utf-8-sig → utf-8 → latin-1)
- `field_order` per section — needed so we write `%R` columns in the same order P6 emitted them
- `raw_lines` per section — for unchanged rows, the writer emits the original line verbatim; only mutated/new rows reconstruct

**Write pass strategy — byte-fidelity for unchanged rows:**

For each section, for each row in `rows`:
1. If the row dict is identity-equal to its `raw_lines[i]` parse (tracked via a dirty bit set on every mutation) — emit `raw_lines[i]` verbatim. Zero risk of format drift on untouched columns.
2. If dirty (or no `raw_lines[i]` because it's a newly-added row) — reconstruct: `'%R\t' + '\t'.join(row.get(f, '') for f in field_order)`.

Same pattern `build_from_raw_template.py` uses inline, factored as a reusable lib.

**Field-order handling for new sections** (created by `create_xer_from_template`): the skeleton XER ships with canonical field order per table; new `XerDoc` instances inherit it.

**Encoding:** writes in the same encoding the input used (default cp1252). CRLF line endings. Single trailing `%E\n`.

### Unified cache (extends `CpmCache`)

**API:**

```python
# Existing tools see no change - get_parsed() now projects from XerDoc
cache.get_parsed(xer_path)        -> dict[str, list[dict]]
cache.get_cpm(xer_path)           -> tuple[list[dict], dict]

# New for write-path tools
cache.get_for_writing(xer_path)   -> XerDoc

# Cache pinning - explicit guard for long sessions
cache.pin(xer_path)               -> None    # exempt from LRU eviction
cache.unpin(xer_path)             -> None
cache.is_pinned(xer_path)         -> bool

# Recency guard - automatic
# Entries touched in the last RECENCY_GRACE_MINUTES (default 30) are
# exempt from LRU eviction.
```

**Single parse pipeline:** `_parse(xer_path)` now calls `xer_io.parse_for_writing()` (rich form). The old lossy `_parse_xer` is deleted; `get_parsed()` projects `XerDoc.sections` down to `{table: [dict, ...]}`. First parse slightly slower (~100ms on a 5K-activity schedule, vs ~50ms previously) but cache hits after that. Net win on multi-tool sessions.

**Eviction priority:**

| Priority | Conditions |
|--|--|
| Highest (evicted first) | Not pinned, not touched in last 30 min, oldest by LRU |
| Middle | Not pinned, touched in last 30 min |
| Never | `cache.pin(path)` was called and not yet `unpin`'d |

LRU max: 8 → **16 entries**. Worst-case memory (16 × ~8 MB per Wellington-grade `XerDoc`) ≈ 128 MB. Comfortable for a scheduler workstation.

**Auto-pin during writes:** `apply_xer_changes`, `fix_duplicate_activity_ids`, and `create_xer_from_template` automatically pin the input path on entry and unpin on exit (`try`/`finally`). Output XER inserts into cache with post-write `(size, mtime)` key AND post-CPM result populated — next tool call against the new path is a hot cache hit, no re-parse, no re-CPM.

**Why move CPM into the cache too:** CPM ran during `apply_xer_changes` post-state validation. Throwing the result away just for the next tool to recompute is wasteful.

**Multi-file residency capacity (16 slots):**

| Workflow | Slots used | Headroom |
|--|--|--|
| Score one XER | 1 | 15 |
| Weekly update (baseline + current) | 2 | 14 |
| Proposal iteration over 5 revisions | 5 | 11 |
| `apply_xer_changes` writing v2 + comparing to v1 | 2 | 14 |
| TIA against 3 fragnet scenarios | 4 | 12 |

---

## Section 6 — Skeleton extraction methodology

**Goal:** Hand-curated `westland-skeleton-v1.xer` that imports cleanly into P6 + Procore, ships with the plugin, contains the minimum-viable Westland boilerplate (PROJECT, CALENDAR(s), PROJWBS roots per Westland standard, SCHEDOPTIONS, ACTVTYPE/ACTVCODE, NTP + SC milestones with FS edge). Sidecar `.notes.md` documents every judgement call.

### Corpus (10-15 files)

```
40 Cowork/training_data/Proposal Schedules/
    BTLP.xer, CVTH.xer, MMHS.xer, NSD-WE.xer, NSSD-HS-AC.xer, RCSP.xer, TES-BESD.xer   (7)
40 Cowork/training_data/Schedules & Schedule Grades/
    ~5 recent A-graded submitted schedules                                              (5)
01 Projects/<Project>/Schedules/
    1-2 recent unprogressed production XERs                                             (2)
```

The 7 proposal schedules are the primary donors — they ARE skeletons by construction (no actuals, minimal activity content). Graded + production XERs add variety so the curation doesn't lock in a single scheduler's habits.

**Excluded:** `40 Cowork/training_data/Sample (in-progress) Schedules/` — those were generated, not real P6 exports.

### Investigation: agent-per-table

For each major XER table — `PROJECT`, `CALENDAR`, `PROJWBS`, `RSRC`, `ACTVTYPE`, `ACTVCODE`, `UDFTYPE`, `SCHEDOPTIONS`, `FINDATES`, `ROLES`, plus an "everything else" pass — dispatch one `Explore`-style subagent. Each:

1. Reads the raw `%T <TABLE>` block from every file in the corpus (just the bytes — not the parsed view).
2. Reports back, in structured prose:
   - Which fields are populated in every file
   - Which fields hold identical values across all N (true constants — copy these verbatim)
   - Which fields vary by project (become parameters in `create_xer_from_template`)
   - Text-level quirks: whitespace, sentinel values (`Yes`/`No` vs `Y`/`N` vs `1`/`0`), encoding artifacts, field-order conventions
   - Anomalies — a field populated in only 1 of 12 (probably project-specific, not boilerplate)

Agent-per-table catches what a tabulating script flattens. P6 cares about field-level text quirks (`Yes` vs `1` in boolean columns, varying date formats in different columns); `pd.read_csv`-style analysis loses that nuance.

### Curation (human-driven, agent-assisted)

The curator session takes the ~10 subagent reports as input and produces:

1. **`westland-skeleton-v1.xer`** — written by hand-applying the constants per table to a chosen base donor (likely the cleanest proposal schedule, e.g. `BTLP.xer`), then stripping all activity content except 2 milestones (NTP, SC) and 1 FS edge.

2. **`westland-skeleton-v1.notes.md`** — table-by-table commentary:
   - Which corpus file was the base donor and why
   - Per-table: which fields are constants (with values), which are parameters, what each kept field is for (best-known)
   - Drop list: any tables intentionally omitted from v1 + reason
   - Each subagent's headline finding, verbatim
   - Curator judgement calls (e.g. "kept FINDATES verbatim because every donor had it populated, even though its purpose is unclear")

### Default WBS — Westland standard, no demolition

Per [`scheduling/skills/schedule-create-proposal-schedule/references/westland-procedures-summary.md`](../../../scheduling/skills/schedule-create-proposal-schedule/references/westland-procedures-summary.md) (p.5/p.11 of the procedures PDF). Skeleton ships with the canonical tree, no DEMOLITION branch — that's pattern-specific (A/B/C from [`wbs-patterns.md`](../../../scheduling/skills/schedule-create-proposal-schedule/references/wbs-patterns.md)) and gets added at proposal-build time via `apply_xer_changes`:

```
PROJECT
  SUMMARY & MILESTONES
    CONTRACT MILESTONES & SUMMARY BARS
    KEY PERFORMANCE MILESTONES
  PRE-CONSTRUCTION
    DESIGN
      ESTIMATES - CONSTRUCTABILITY REPORTS - SCHEDULE UPDATES
      BIM MODELING
      TRADE PRE-QUALIFICATION
      BUY OUT - PROPOSAL & AWARD
      OWNER PERMIT / CONSENT PROCESS
  PROCUREMENT
    SUBMITTALS - APPROVALS - FABRICATION - DELIVERY
  CONSTRUCTION
    SITEWORK
      INITIAL SITEWORK
        CLEAR & GRUB - CUT & FILL - ROUGH GRADE - UTILITIES
      BALANCE OF SITEWORK
        HARDSCAPE - LANDSCAPE - EQUIPMENT ENCLOSURES
    STRUCTURE & SUBROUGH
      AREA - LEVEL
    BUILDING ENCLOSURE - WINDOWS - ENTRIES - FINISH SYSTEMS
      ELEVATION - AREA - LEVEL
    INTERIOR ROUGH-IN & FINISHES
      AREA - LEVEL
  COMMISSIONING & CLOSE-OUT
```

**Plus carried verbatim from the source corpus:**

- Westland standard activity code types + values (responsibility, area, level, trade) — procedures doc requires standard responsibility codes on every task
- 7-day workweek calendar + standard holiday calendar (whichever the donor uses as defaults; notes file documents which)
- SCHEDOPTIONS with Westland standard settings (retained-logic, late-finish-time-of-day, etc.)
- 2 milestones: NTP (project start) and SC (Substantial Completion) with FS edge
- 2 summary-bar placeholders under SUMMARY & MILESTONES per Westland convention

**Cross-references baked into the curation pass:**

- `scheduling/skills/schedule-create-proposal-schedule/references/wbs-patterns.md` — canonical tree shape, pattern variants
- `scheduling/skills/schedule-create-proposal-schedule/references/westland-procedures-summary.md` — proposal-stage standards summary
- `scheduling/skills/schedule-create-proposal-schedule/references/westland-procedures.md` — full procedures doc
- `scheduling/skills/schedule-toolbox/references/xer-generation.md` — existing XER-generation guidelines
- `scheduling/skills/schedule-toolbox/lib/build_from_raw_template.py` — comments document template-based generation patterns

Notes file documents which guidelines drove each per-table decision.

**Pattern A/B/C application is downstream, not in the skeleton.** A scheduler builds a Pattern B proposal by:

1. `create_xer_from_template("westland-skeleton-v1", { project_name, ... })` — skeleton on disk
2. `apply_xer_changes` adds the DEMOLITION top-level WBS node after CONSTRUCTION + FINAL SITEWORK nested below it (3 `add_wbs` records)
3. Subsequent `add_activity` + `add_logic` records populate the demolition activities

Keeps the skeleton single-shape and version-stable.

### Skeleton verification gate (Phase E)

Before committing `westland-skeleton-v1.xer`:

1. Round-trip identity test: `xer_io.parse_for_writing` → `xer_io.write` → byte-equal to source
2. `validate_xer_structure(skeleton.xer)` → `import_ready: true`, zero errors, zero warnings
3. Manual P6 import: no errors, no warnings about missing tables
4. Manual Procore import: same
5. `create_xer_from_template` smoke: minimal metadata → instantiate → `validate_xer_structure` clean

If any gate fails, iterate on the skeleton and re-run. Notes file records each iteration as a dated entry.

### Future skeletons

If Procore or P6 schemas evolve, or Westland coding conventions change, repeat the methodology. Bump to `westland-skeleton-v2.xer` with a fresh notes file. The skeleton path is a versioned parameter to `create_xer_from_template`, so v1-built projects keep building.

---

## Section 7 — Tests, fixtures, smoke

### New test fixtures

| Path | Purpose |
|------|---------|
| `mcp-server/tests/fixtures/duplicate_ids.xer` | 3 activities with duplicate `task_code` "A1010". Drives `fix_duplicate_activity_ids` strategy tests. |
| `mcp-server/tests/fixtures/dangling_refs.xer` | TASKPRED row pointing at non-existent task_id; TASK row pointing at non-existent calendar_id. Drives `validate_xer_structure` `DANGLING_*` codes. |
| `mcp-server/tests/fixtures/circular_logic.xer` | 3-activity cycle A→B→C→A. Drives `CIRCULAR_LOGIC` detection in both `validate_xer_structure` and `apply_xer_changes` post-state check. |
| `mcp-server/tests/fixtures/orphan_branch.xer` | PROJWBS row with no children + no task references. Drives `ORPHANED_WBS_BRANCH` warning. |
| `mcp-server/tests/fixtures/multi_edge.xer` | Pair of activities with both an FS edge and an SS edge between them. Drives `remove_logic` / `modify_logic` relationship-selector tests. |
| `mcp-server/tests/fixtures/dissolve_fanout.xer` | Activity X with 3 predecessors + 4 successors. Drives the cartesian-product dissolve test (12 new edges) and the high-fanout warning. |
| `mcp-server/tests/fixtures/wbs_pattern_b_target.xer` | Reference XER hand-built to Pattern B layout. Drives "skeleton + change set produces valid Pattern B" integration test. |

Each fixture ≤ 20 activities, committed verbatim — tests parse the bytes, not regenerate via `apply_xer_changes` (regeneration would couple two tools' bugs).

### New test modules

| Path | Coverage |
|------|----------|
| `schedule-toolbox/tests/test_xer_io.py` | Round-trip identity against 7 proposal corpus XERs; mutate-one-field test; new-row test. |
| `mcp-server/tests/test_xer_modify.py` | Lib-level tests for each of the 14 change types: success path + each validation-rule failure path. |
| `mcp-server/tests/test_validate_structure.py` | Each issue code raised when expected; severity classification stable; `import_ready` correct. |
| `mcp-server/tests/test_apply_xer_changes.py` | MCP-wrapper smoke: dry_run vs commit; pre-CPM and post-CPM cache hits; per-change feedback shape; atomic-on-failure (no file written when errors present). |
| `mcp-server/tests/test_create_xer_from_template.py` | Skeleton load + project-metadata substitution + NTP/SC milestone-id return; subsequent `validate_xer_structure` reports `import_ready: true`. |
| `mcp-server/tests/test_fix_duplicate_ids.py` | Three strategies covered; mapping output shape verified. |
| `mcp-server/tests/test_cache_pinning.py` | Pin survives LRU pressure; recency window survives; auto-pin/unpin in `apply_xer_changes`; post-write cache hit on output path. |

### Modified tests

| Path | Why |
|------|-----|
| `mcp-server/tests/test_cache.py` | Switch parse target from `_parse_xer` to `xer_io.parse_for_writing`. Add lossy-projection equivalence test. |
| `mcp-server/tests/test_server.py` | Add `apply_xer_changes`, `validate_xer_structure`, `fix_duplicate_activity_ids`, `create_xer_from_template`, `invalidate_cache_for` to registered-tool assertions. |

### End-to-end smoke (manual, runs once before release)

1. **Skeleton-to-proposal smoke** — on a real proposal-stage project the user picks:
   - `create_xer_from_template("westland-skeleton-v1", { Wellington-grade metadata })`
   - `apply_xer_changes` with a 50-activity Pattern B change set (WBS reparenting, demo activities, FS chains)
   - `validate_xer_structure` on the output → `import_ready: true`, zero errors
   - Manually import the output into P6 and Procore — clean, no warnings about missing tables
   - Open in P6 and confirm: WBS tree matches expected Pattern B layout, NTP and SC present, dates flow

2. **Modify-existing smoke** — on a current Westland project XER (Wellington Temple or similar):
   - `apply_xer_changes` with 5-change mixed set (1 add_activity, 1 dissolve_activity, 1 set_duration, 1 add_logic, 1 modify_wbs)
   - Open output in P6 — changes landed, file imports clean

3. **Validation smoke** — against the same Wellington XER:
   - `validate_xer_structure` returns `import_ready: true` (known-good file)
   - Hand-corrupt a copy (duplicate an activity_code, introduce a dangling reference) and re-run — issues reported with correct codes and `affected` arrays

If any smoke step fails, release held until fixed. Smoke results land in the release PR description as the final gate.

---

## Section 8 — Integration, file naming, release

### Existing skill updates

| Skill | Change |
|--|--|
| `schedule-toolbox/SKILL.md` | Routing table gains 5 new MCP tool names. New "modifying XER files" subsection: "All XER writes go through `apply_xer_changes` or `create_xer_from_template`. Both write to a new path — never overwrite the input." |
| `schedule-create-proposal-schedule/SKILL.md` | `iterate.py` continues to import `lib/cpm_engine` directly (non-Claude caller, unchanged). Claude-facing phases switch to compositional flow: `create_xer_from_template` → `apply_xer_changes` with bulk records. `wbs-patterns.md` references WBS-mutation change types so pattern application is mechanical, not narrative. |
| `schedule-toolbox/references/xer-modify.md` | Updated to point at `apply_xer_changes` for all modification. Removes any "edit the script" guidance. |
| `schedule-toolbox/references/xer-generation.md` | Documents `create_xer_from_template` as the canonical generation entry point. `build_from_raw_template.py` stays in `lib/` as historical reference; doc explains it's not the recommended path. |

### File naming conventions (write-path tools)

Default `output_path` when omitted:

| Tool | Suffix |
|------|--------|
| `apply_xer_changes` | `<input>-modified.xer` |
| `apply_xer_changes` with single change type X | `<input>-<X>.xer` (e.g. `<input>-set_duration.xer`) when exactly one change record is in the call |
| `fix_duplicate_activity_ids` | `<input>-fixed.xer` |
| `create_xer_from_template` | `<project_name>.xer` in caller's working directory (or `output_path` if supplied) |
| `run_cpm` (existing, unchanged) | `<input>-cpm.xer` |

On `output_path` collision: tools return an error with `suggested_path: <input>-<op>-v2.xer` (and v3, v4…). Never silent overwrite. The existing PreToolUse immutable-XER hook catches anything that slips through.

### Cache invalidation rules

- Input XER: read-through cache; auto-pinned during write tool execution; unpinned in `finally`.
- Output XER: post-write, mutated `XerDoc` + freshly-computed CPM result inserted into cache with new file's `(size, mtime)` key. First downstream call against the new path is a hot hit.
- `invalidate_cache_for(xer_path)` tool: explicit busting; returns `{ invalidated: bool }`. For schedulers who edit XERs outside the MCP and want belt-and-suspenders.

### Release path (per repo CLAUDE.md release convention)

1. Branch `feat/scheduler-mcp-tier-3` from main
2. Phase E (skeleton extraction) runs early; commits `westland-skeleton-v1.xer` + `.notes.md`
3. Phases B–G ship tool implementation; each phase tested at lib level + MCP wrapper level
4. End-to-end smoke (per Section 7) before merge
5. Bump `scheduling/.claude-plugin/plugin.json` 8.1.3 → **9.0.0**
6. Bump `.claude-plugin/marketplace.json` scheduling entry → **9.0.0** (lockstep)
7. PR review, CI passes (version-bump check + personal-path lint)
8. Merge to main
9. From the main checkout (NOT a worktree): `git switch main && git pull --ff-only && python build.py scheduling`
10. Distribute updated `src/scheduling.zip` to the 4 schedulers

### Why 9.0.0 (major bump)

- New file-writing capability is a categorical step up — plugin gains XER-mutation
- `CpmCache` API gains `get_for_writing()`, `pin()`, `unpin()`, `is_pinned()` — back-compat for `get_parsed` / `get_cpm` but contract expanded
- `_parse_xer` removal is internal-only but symbolically marks the shift from "read-only analysis" to "read + write"

### Lessons-learned hook (per repo CLAUDE.md)

Once the first scheduler uses `create_xer_from_template + apply_xer_changes` to build a real proposal, save the Claude-generated XER side-by-side with the final human-submitted version. Write `Lessons Learned - <Project> - Tier 3.md` documenting divergences (WBS shape Claude got wrong, change types missing, validation rules too strict or too loose). Drives the next skill-improvement cycle.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `xer_io.write` round-trip produces a file P6 rejects on import | Phase E gate includes manual P6 import test on the skeleton; Section 7 end-to-end smoke gates the release. Round-trip identity test against 7 corpus XERs verifies zero-mutation = zero-byte-change. |
| `apply_xer_changes` validation rejects a change set the scheduler genuinely wants (false positive) | `strict: false` is the default; warnings are advisory. `dry_run: true` lets schedulers see exactly what would happen before committing. Each rejected case becomes a lessons-learned input. |
| Curation drops a table that turns out to be load-bearing for a P6/Procore feature we don't exercise in the gate | Subagent reports flag "present in all N" tables; curator default is keep-everything-consistently-present. Notes file records each drop so a future regression points at the right place. |
| Skeleton hand-curation introduces a typo or sentinel-value bug | Round-trip test + import gate catches structural breakage; `validate_xer_structure` catches data-level issues; manual P6 + Procore import gate catches semantic issues no script can detect. |
| Cache memory bloat with 16-entry bound and `XerDoc` rich form (~8 MB per Wellington-grade schedule) | LRU + recency + pin model self-limits. Worst case ~128 MB on a scheduler workstation — well within budget. If the limit becomes painful, drop to 12 (still 50% more than Plan 1+2). |
| Multi-edge `(pred, succ)` ambiguity not caught by validation | `validate_xer_structure` includes `DUPLICATE_RELATIONSHIP` check; `apply_xer_changes` refuses to apply `remove_logic`/`modify_logic` when more than one edge matches. Same engine, same shape. |
| `dissolve_activity` cartesian explosion overwhelms the output (e.g., 8 preds × 8 succs = 64 new edges) | Warning fires at > 20 new edges; scheduler can use `strict: true` to make it an error. Per-change feedback includes `new_edges_created` for visibility. |
| `apply_anchor_absorption` lowering logic diverges from `get_anchor_absorption_suggestions` output | Both live in the same plugin; `apply_xer_changes` re-invokes the suggestion logic at validation time rather than trusting the caller's pre-computed list. Suggestion shape is the contract. |
| Schedulers on different plugin versions diverge on skeleton content | Skeleton is versioned (`westland-skeleton-v1`); plugin version controls which is bundled. Cross-scheduler drift becomes a release-rollout issue, not a silent divergence. |
| Pattern A/B/C application via `apply_xer_changes` is verbose enough to be error-prone | First few real proposals built via the compositional path get hand-reviewed by a Westland scheduler. Lessons-learned cycle tightens; we may eventually add a higher-level `apply_wbs_pattern("B")` helper, but Plan 3 doesn't require it. |
| Phase E (skeleton extraction) runs in parallel with Phase B–D tool implementation but `create_xer_from_template` depends on the skeleton existing | Phase E commits first (before `create_xer_from_template` implementation in Phase F). Implementation plan enforces the ordering. |

---

## Open questions for the implementation plan

1. **WBS short-name (`wbs_short_name`) default.** When `add_wbs.spec.wbs_short_name` is omitted, derive it from `wbs_code` or `wbs_name` or require it explicit? Westland convention says short name = the all-caps abbreviation; need to confirm whether that's mechanical or a scheduler judgement call.
2. **`apply_anchor_absorption` suggestion-index semantics.** Spec says `suggestion_index: int` selects which suggestion from `get_anchor_absorption_suggestions` to apply. Need to confirm the index is stable across calls (i.e., suggestions are deterministically ordered) or whether a `suggestion_id` field would be more robust.
3. **`renumber` strategy in `fix_duplicate_activity_ids` — namespace policy.** Where does the new ID space live? Spec says "lowest unused suffix" but doesn't pin whether suffixes follow the activity_code naming pattern of the original schedule (e.g. `A1010` → `A1015` if `A1011-A1014` are taken) or use a synthetic suffix (`A1010-DUP1`). Confirm with a scheduler.
4. **Procore-specific XER quirks.** Some Procore-targeted XERs include UDFTYPE entries Procore expects. Skeleton extraction will surface these; need to know whether v1 should ship with the Procore UDFs included by default or as an opt-in flag.
5. **Pinning auto-release on cache eviction failure.** If pinned entries exceed the LRU bound (e.g., 17 pins on a 16-bound cache), what happens? Recommendation: refuse the 17th pin with an error. Confirm.

---

**Next step:** user reviews this document and the open questions. After approval, `writing-plans` produces the Plan 3 implementation plan.
