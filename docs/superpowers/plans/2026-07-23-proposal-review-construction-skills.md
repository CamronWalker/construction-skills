# Proposal Schedule Online Review + Final XER Gate (construction-skills) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the local Gantt review HTML in favor of the westland-mcps online review link, add a `feedback_ingest.py pull` verb that reconciles online comments drift-aware, and add a visible final XER-validation gate at proposal hand-off. Ship as scheduling `10.2.0`.

**Architecture:** The proposal flow no longer renders a local `schedule-review.html`. Instead Claude publishes the current `schedule-activities.json` to the online link (MCP tool `generate_proposal_review_link`) and later pulls attributed comments (MCP tool `get_proposal_review_comments`), writes them to disk, and runs `propsched feedback pull` — which maps them onto the existing `westland-reviewer-feedback` shape and reuses `_detect_drift` for reconciliation. The final approval sequence gains a `validate_xer_structure` pass/fail report.

**Tech Stack:** Python 3 (stdlib `unittest`, `argparse`, `json`, `pathlib`), the `propsched.py` CLI, the westland-scheduler MCP tools, markdown skill/phase docs.

## Global Constraints

- The westland-mcps PR (deploy) MUST ship first — these skill changes call `generate_proposal_review_link` / `get_proposal_review_comments`, which only exist after that deploy.
- XER files are immutable — the final gate READS only (the PreToolUse hook blocks edits; never Edit/Write/rm a `.xer`).
- Do NOT wrap existing scripts; extend them. Tests go in a dedicated `tests/` dir (unittest), never a `test_*.py` sibling in `tools/`.
- Version bump in lockstep: `scheduling/.claude-plugin/plugin.json` and the scheduling entry in `.claude-plugin/marketplace.json` both `10.1.2 → 10.2.0`; rebase onto `origin/main` before opening the PR (version-bump CI diffs base..head).
- Retire the local HTML fully — blast radius (all references to `build_gantt_html` / `schedule-review.html` / `gantt-review.html` / `frappe-gantt`): `proposal_iterate.py`, `_layout.py` (`html_path`), `REFERENCE.md`, `README.md`, `02-iterate.md`, `01-draft.md`, `examples/iterate.py`, `SKILL.md`, `cpm-usage.md`, `plugin.json`/`marketplace.json` descriptions, and delete `scheduling/tools/build_gantt_html.py`, `scheduling/templates/gantt-review.html`, `scheduling/lib/frappe-gantt/` (after the westland-mcps PR has copied the vendor files).

## File Structure

```
scheduling/tools/
  feedback_ingest.py          # MODIFY: add `pull` subcommand + online→reviewer-feedback mapping
  proposal_iterate.py         # MODIFY: remove the build_gantt_html subprocess block (L420-449) + html_path use
  build_gantt_html.py         # DELETE
  _layout.py                  # MODIFY: drop html_path (or mark removed) + docstring
  REFERENCE.md                # MODIFY: feedback verb doc (add pull), remove HTML render mentions, add publish/pull + final-gate flow
  README.md                   # MODIFY: folder layout + files list
  examples/iterate.py         # MODIFY: drop build_gantt_html usage
  tests/
    __init__.py               # CREATE
    test_feedback_pull.py     # CREATE: mapping + drift reuse unit tests
scheduling/templates/gantt-review.html   # DELETE
scheduling/lib/frappe-gantt/              # DELETE (after mcps copy)
scheduling/skills/schedule-create-proposal-schedule/
  SKILL.md                    # MODIFY: workflow steps, disclosure table, iteration-tools table, folder layout
  phases/01-draft.md          # MODIFY: hand-off line (render HTML → publish link)
  phases/02-iterate.md        # MODIFY: replace HTML/Copy-for-Claude/Download flow with publish+pull; add final gate to PDF sequence
  phases/03-score.md          # MODIFY: tail note points to the final gate
scheduling/skills/schedule-toolbox/references/cpm-usage.md  # MODIFY: drop build_gantt_html mention
scheduling/.claude-plugin/plugin.json     # MODIFY: 10.2.0 + description
.claude-plugin/marketplace.json           # MODIFY: 10.2.0 + description (lockstep)
```

---

### Task 1: `feedback_ingest.py pull` verb + online→reviewer-feedback mapping

**Files:**
- Modify: `scheduling/tools/feedback_ingest.py`
- Create: `scheduling/tools/tests/__init__.py`
- Create: `scheduling/tools/tests/test_feedback_pull.py`

**Interfaces:**
- Consumes: existing `_activities_index(project, layout)`, `_detect_drift(payload, current_version, by_id, by_code)`, `_layout.reviewer_feedback_dir`.
- Produces: `map_online_comments(online) → [westland-reviewer-feedback payloads]` (one per reviewer, grouped) and a `pull` subcommand: `feedback pull "<project>" --file online.json`. The online JSON is the `get_proposal_review_comments` result: `{ job_number, current_version, versions, comments: [{ id, version_label, task_code, task_name_snapshot, orig_duration_snapshot, reviewer_id, reviewer_name, body, suggested_duration_days, resolved, created_at }] }`.

Mapping rule (per reviewer, per version group → one `westland-reviewer-feedback` payload):
- `reviewer.name = reviewer_name`; `review_date` = latest comment `created_at` date; `version_reviewed` = int parsed from `version_label` (`"v3"→3`, else null).
- Each comment → activity `{ id: task_code, task_code, name: task_name_snapshot, comment: body, task_snapshot: { name: task_name_snapshot, duration_days: orig_duration_snapshot } }`; if `suggested_duration_days` present → `duration_change: { from_days: orig_duration_snapshot, to_days: suggested_duration_days }`.
- `resolved` comments are excluded by default (already addressed); include with `--include-resolved`.

- [ ] **Step 1: Write failing tests**

```python
# scheduling/tools/tests/test_feedback_pull.py
import json, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tools/ on path
import feedback_ingest as fi


ONLINE = {
    "job_number": "W1234",
    "current_version": "v3",
    "versions": ["v1", "v2", "v3"],
    "comments": [
        {"id": "c1", "version_label": "v2", "task_code": "A0010",
         "task_name_snapshot": "Mobilize", "orig_duration_snapshot": 5,
         "reviewer_id": "r1", "reviewer_name": "Steve Westover",
         "body": "Too short", "suggested_duration_days": 8, "resolved": False,
         "created_at": "2026-07-20T10:00:00Z"},
        {"id": "c2", "version_label": "v2", "task_code": "A0020",
         "task_name_snapshot": "Excavate", "orig_duration_snapshot": 10,
         "reviewer_id": "r1", "reviewer_name": "Steve Westover",
         "body": "ok", "suggested_duration_days": None, "resolved": False,
         "created_at": "2026-07-20T10:05:00Z"},
        {"id": "c3", "version_label": "v3", "task_code": "A0010",
         "task_name_snapshot": "Mobilize", "orig_duration_snapshot": 8,
         "reviewer_id": "r2", "reviewer_name": "Jane PM",
         "body": "resolved note", "suggested_duration_days": None, "resolved": True,
         "created_at": "2026-07-21T09:00:00Z"},
    ],
}


class TestMapOnlineComments(unittest.TestCase):
    def test_groups_by_reviewer_and_version(self):
        payloads = fi.map_online_comments(ONLINE)
        # Steve v2 (2 comments) + Jane v3 excluded (resolved) => 1 payload
        self.assertEqual(len(payloads), 1)
        p = payloads[0]
        self.assertEqual(p["schema"], "westland-reviewer-feedback")
        self.assertEqual(p["reviewer"]["name"], "Steve Westover")
        self.assertEqual(p["version_reviewed"], 2)
        self.assertEqual(len(p["activities"]), 2)

    def test_maps_suggested_duration_to_change(self):
        p = fi.map_online_comments(ONLINE)[0]
        a = next(x for x in p["activities"] if x["task_code"] == "A0010")
        self.assertEqual(a["duration_change"], {"from_days": 5, "to_days": 8})
        self.assertEqual(a["task_snapshot"]["duration_days"], 5)

    def test_include_resolved_flag(self):
        payloads = fi.map_online_comments(ONLINE, include_resolved=True)
        names = sorted(p["reviewer"]["name"] for p in payloads)
        self.assertEqual(names, ["Jane PM", "Steve Westover"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run — expect FAIL** (`map_online_comments` not defined)

Run: `python -m unittest scheduling.tools.tests.test_feedback_pull -v` (from repo root) — or `cd scheduling/tools && python -m unittest tests.test_feedback_pull -v`.
Expected: FAIL (AttributeError).

- [ ] **Step 3: Implement `map_online_comments` + `cmd_pull` in `feedback_ingest.py`**

Add near the top helpers:

```python
def _version_int(label):
    import re as _re
    m = _re.match(r'^v(\d+)$', str(label or ''))
    return int(m.group(1)) if m else None


def map_online_comments(online, include_resolved=False):
    """Map a get_proposal_review_comments result into a list of
    westland-reviewer-feedback payloads, grouped by (reviewer, version)."""
    project = online.get('job_number') or online.get('project') or ''
    groups = {}  # (reviewer_name, version_label) -> {info, activities}
    for c in online.get('comments', []) or []:
        if c.get('resolved') and not include_resolved:
            continue
        rn = (c.get('reviewer_name') or '').strip()
        vl = c.get('version_label')
        if not rn:
            continue
        key = (rn, vl)
        g = groups.setdefault(key, {'created': [], 'activities': []})
        g['created'].append(c.get('created_at') or '')
        item = {
            'id': c.get('task_code'),
            'task_code': c.get('task_code'),
            'name': c.get('task_name_snapshot') or '',
        }
        if c.get('body'):
            item['comment'] = c['body']
        sug = c.get('suggested_duration_days')
        orig = c.get('orig_duration_snapshot')
        if sug is not None:
            item['duration_change'] = {'from_days': orig, 'to_days': sug}
        item['task_snapshot'] = {
            'name': c.get('task_name_snapshot') or '',
            'duration_days': orig,
        }
        g['activities'].append(item)
    payloads = []
    for (rn, vl), g in groups.items():
        review_date = max(g['created'])[:10] if g['created'] else 'unknown-date'
        payloads.append({
            'schema': 'westland-reviewer-feedback',
            'schema_version': 1,
            'reviewer': {'name': rn, 'email': ''},
            'review_date': review_date,
            'project': project,
            'version_reviewed': _version_int(vl),
            'activities': g['activities'],
            'comment_count': sum(1 for a in g['activities'] if a.get('comment')),
            'change_count': sum(1 for a in g['activities'] if a.get('duration_change')),
        })
    return payloads
```

Add the `pull` subcommand (parks each mapped payload via the existing storage + runs `_detect_drift`, reusing `_activities_index`):

```python
def cmd_pull(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    src = Path(args.file)
    if not src.exists():
        return _err(f'online-comments file not found: {src}')
    try:
        online = _read_json(src)
    except (OSError, json.JSONDecodeError) as e:
        return _err(f'unreadable JSON: {e}')

    payloads = map_online_comments(online, include_resolved=args.include_resolved)
    if not payloads:
        print('No unresolved online comments to pull.')
        return 0

    cur_version, by_id, by_code = _activities_index(project, layout)
    rf_dir = _layout.reviewer_feedback_dir(project, layout)
    rf_dir.mkdir(parents=True, exist_ok=True)

    worst = 0
    for p in payloads:
        rv = p.get('version_reviewed')
        rv_str = f'v{rv}' if rv is not None else 'unknown'
        fname = f"{_slugify(p['reviewer']['name'])}-{p['review_date']}-{rv_str}.json"
        dest = rf_dir / fname
        dest.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
        drift = _detect_drift(p, cur_version, by_id, by_code)
        print(f"Ingested: {dest.relative_to(project)}")
        print(f"  Reviewer:        {p['reviewer']['name']}")
        print(f"  Version reviewed:{rv_str}"
              + (f"   Current: v{cur_version}" if cur_version is not None else ''))
        print(f"  Comments + edits: {len(p['activities'])}")
        print('  Drift report:')
        print(_format_drift(drift))
        print()
        if any(s == 'error' for s, _ in drift):
            worst = max(worst, 1)
        elif any(s == 'warn' for s, _ in drift):
            worst = max(worst, 2)
    return worst
```

Register the subparser in `main()` (beside `ingest`/`list`/`show`):

```python
    p_pull = sub.add_parser('pull', help='Reconcile online review comments (from get_proposal_review_comments)')
    p_pull.add_argument('project', help='Path to the project folder')
    p_pull.add_argument('--file', required=True, help='Path to the get_proposal_review_comments JSON')
    p_pull.add_argument('--include-resolved', action='store_true',
                        help='Also ingest comments already marked resolved')
    # ...and in the dispatch tail:
    if args.subcommand == 'pull':
        return cmd_pull(args)
```

- [ ] **Step 4: Run — expect PASS.** `python -m unittest scheduling.tools.tests.test_feedback_pull -v`

- [ ] **Step 5: Commit**

```bash
git add scheduling/tools/feedback_ingest.py scheduling/tools/tests/__init__.py scheduling/tools/tests/test_feedback_pull.py
git commit -m "feat(scheduling): feedback_ingest pull verb — reconcile online review comments drift-aware"
```

---

### Task 2: Remove the local HTML render from `proposal_iterate.py`

**Files:**
- Modify: `scheduling/tools/proposal_iterate.py`

**Interfaces:**
- Removes the `build_gantt_html` subprocess (L420-449) and `_layout.html_path` usage. The iterate loop still writes `schedule-activities.json`, scores, archives the paste-back — it just no longer emits HTML. Update the docstring (drop `schedule-review.html` from the folder layout).

- [ ] **Step 1: Replace the parallel HTML/score block.** Remove the `html_path`/`builder`/`html_proc = subprocess.Popen(...)` render and the `html_proc.communicate()` + returncode handling. Keep impact + score compute. The block becomes:

```python
    # Compute impact + score the new state. (HTML rendering retired — the
    # review surface is now the online link; publish via generate_proposal_review_link.)
    impact = _impact.compute_impact(old_snap, results, anchors)
    score_data = _score_results(results, preds, data_date)
```

Remove the now-unused `subprocess` import only if nothing else uses it (grep first; keep if other calls remain).

- [ ] **Step 2: Update the docstring** — delete the `schedule-review.html` line from the folder-layout block (L18 region) and the exit-code line mentioning "+ HTML" (change "new XER + JSON + HTML written" → "new XER + JSON written").

- [ ] **Step 3: Sanity-run the iterate CLI on a fixture project if one exists** (else defer to manual). No unit test exists for this script; verify import + `--help` still work:

Run: `python scheduling/tools/proposal_iterate.py --help`
Expected: argparse help prints, no ImportError.

- [ ] **Step 4: Commit**

```bash
git add scheduling/tools/proposal_iterate.py
git commit -m "refactor(scheduling): iterate no longer renders local HTML (online link is the review surface)"
```

---

### Task 3: Delete retired files + purge references

**Files:**
- Delete: `scheduling/tools/build_gantt_html.py`, `scheduling/templates/gantt-review.html`, `scheduling/lib/frappe-gantt/` (whole dir)
- Modify: `scheduling/tools/_layout.py`, `scheduling/tools/REFERENCE.md`, `scheduling/tools/README.md`, `scheduling/tools/examples/iterate.py`, `scheduling/skills/schedule-toolbox/references/cpm-usage.md`

**Interfaces:**
- `_layout.html_path` is removed. Confirm the ONLY remaining caller was `proposal_iterate.py` (fixed in Task 2) — grep before deleting.

- [ ] **Step 1: Confirm no live consumer of the deletions remains.**

Run: `grep -rn "build_gantt_html\|schedule-review.html\|gantt-review.html\|frappe-gantt\|html_path" scheduling --include=*.py`
Expected: only the doc files + the lines this task edits; no live `.py` import beyond `_layout.html_path` definition.

- [ ] **Step 2: Delete the files.**

```bash
git rm scheduling/tools/build_gantt_html.py scheduling/templates/gantt-review.html
git rm -r scheduling/lib/frappe-gantt
```

- [ ] **Step 3: Remove `html_path` from `_layout.py`** (lines 142-143) and scrub `schedule-review.html` from the module docstring (lines ~9, ~20).

- [ ] **Step 4: Update docs** — `REFERENCE.md` (folder-layout block line ~20: drop `schedule-review.html`; `iterate` verb: remove the "renders schedule-review.html (subprocess)" bullet; rewrite the `feedback` section to document `pull` + the online-link flow, replacing the download-JSON-by-email narrative; add publish/pull to Quick reference + Common patterns), `README.md` (folder layout + files list: drop `build_gantt_html.py`/`schedule-review.html`), `examples/iterate.py` (drop the build_gantt_html invocation), `cpm-usage.md` (drop the build_gantt_html mention).

- [ ] **Step 5: Re-grep to confirm zero dangling references in code + only intended doc mentions.**

Run: `grep -rn "build_gantt_html\|frappe-gantt" scheduling`
Expected: no matches (or only a historical-note mention you deliberately keep).

- [ ] **Step 6: Commit**

```bash
git add -A scheduling
git commit -m "refactor(scheduling): retire local Gantt review HTML + purge references"
```

---

### Task 4: Rewrite the proposal phases + SKILL.md for the online link

**Files:**
- Modify: `scheduling/skills/schedule-create-proposal-schedule/phases/01-draft.md`, `phases/02-iterate.md`, `SKILL.md`

**Interfaces:**
- The publish step: after v1 (and each iteration), Claude reads the project's `schedule-activities.json` and calls `generate_proposal_review_link({ job_number, project_name, activities_json, new_version? })`; hands the returned `review_url` to Camron. Solo iteration re-publishes (update-in-place); after a review round, publish with `new_version: true`. Optionally `append_project_log(category="schedule_published")`.
- The pull step: Claude calls `get_proposal_review_comments({ job_number })`, writes the result to `<project>/Old Iterations/online-comments-<date>.json`, then runs `python scheduling/tools/propsched.py feedback pull "<project>" --file <that file>`; applies non-drifted feedback in the iterate loop.

- [ ] **Step 1: `phases/01-draft.md` (L267)** — change the hand-off line from "render the Gantt review HTML and start iterating" to: after v1 is written, publish the review link (`generate_proposal_review_link`) and start iterating — load `phases/02-iterate.md`.

- [ ] **Step 2: `phases/02-iterate.md`** — replace "Phase 6.5: Gantt Review HTML" (L13-26) and the "Iteration loop" intro (L36-38) with the online-link model: no local HTML; the online link is the review surface for solo + distributed review. Document publish (update-in-place vs `new_version`) and the pull+reconcile flow (`get_proposal_review_comments` → write to disk → `propsched feedback pull`). Rewrite the paste-back schema block (L40-67) as the pull-comments shape. Keep the CPM/anchors iterate steps; drop "regenerates schedule-review.html" / "Camron refreshes the HTML" → "Camron refreshes the online link". Update the postmortem `reviewer-feedback/` note to say feedback now arrives via `propsched feedback pull`.

- [ ] **Step 3: `phases/02-iterate.md` final-approval sequence (L264-269)** — insert the XER-validation gate as a step (implemented in Task 5): between "Generate the plan PDF" and "Confirm the latest -v{N}.xer is the deliverable", add "Run the final XER-validation gate (`validate_xer_structure`) and report pass/fail."

- [ ] **Step 4: `SKILL.md`** — Workflow list (L22-32): step 6 "Iterate via Gantt Review HTML" → "Iterate via the online review link"; step 8 add "run the final XER-validation gate". Disclosure table (L38-43): the `schedule-review.html` row → "Camron left comments on the online review link (workflow step 7)". Iteration-tools table (L47-62): `iterate` row drop "+ HTML", add a `feedback pull` row. Folder layout (L63-82): remove `schedule-review.html` from outputs; add a note that the review link is hosted (no local artifact).

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-create-proposal-schedule
git commit -m "docs(scheduling): proposal phases + SKILL use the online review link (publish + pull)"
```

---

### Task 5: Final XER-validation gate step

**Files:**
- Modify: `scheduling/skills/schedule-create-proposal-schedule/phases/02-iterate.md` (the PDF sequence), `phases/03-score.md` (tail)

**Interfaces:**
- The gate: at final approval, call `validate_xer_structure` on the latest `-v{N}.xer` (the deliverable). Print a pass/fail banner: PASS → "Import-ready ✓ (0 errors, N warnings)"; FAIL → list each error-severity issue (category + row identity) and stop, directing back to iterate/regenerate. Read-only.

- [ ] **Step 1: Add the gate procedure to `02-iterate.md`** (in the "Generate the Plan PDF" sequence). Include the exact instruction:

```markdown
### Final XER validation gate (before declaring the deliverable)

Generation already refuses to write a malformed .xer, but confirm it explicitly on the final file:

1. Call `validate_xer_structure` on the latest `-v{N}.xer` (the deliverable).
2. If `import_ready` is true → print: **"Import-ready ✓ — 0 errors, {W} warnings"** and proceed.
3. If false → print each error-severity issue as `[error] {category}: {message} ({row})`, state **"NOT import-ready — do not deliver"**, and return to the iterate loop to regenerate. Never edit the .xer by hand (immutable).
```

- [ ] **Step 2: Update `03-score.md` tail (L74)** — after "Present the final quality report...", add: "Then run the final XER-validation gate (see `02-iterate.md`) — import-readiness is a hard gate on the deliverable."

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-create-proposal-schedule/phases/02-iterate.md scheduling/skills/schedule-create-proposal-schedule/phases/03-score.md
git commit -m "docs(scheduling): visible final XER-validation gate at proposal hand-off"
```

---

### Task 6: Version bump + description updates (lockstep)

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: Bump `plugin.json`** version `10.1.2 → 10.2.0` and update its `description` to drop "self-contained Gantt review HTML + Copy-for-Claude iteration loop" and mention "online proposal review link (attributed task comments) + final XER-import validation gate".

- [ ] **Step 2: Bump the scheduling entry in `marketplace.json`** to `10.2.0` (exact match) and mirror the description change (drop "Gantt review HTML + Copy-for-Claude loop").

- [ ] **Step 3: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(scheduling): 10.2.0 — online review link + final XER validation gate"
```

---

### Task 7: Full verification + self-review

- [ ] **Step 1: Run the new tests + any adjacent suites.**

Run: `python -m unittest scheduling.tools.tests.test_feedback_pull -v`
Expected: PASS.

Run (regression — the toolbox validator + schedule-update suites must stay green): `python -m unittest discover -s scheduling/skills/schedule-toolbox/tests` and `... -s scheduling/skills/schedule-update/tests`
Expected: PASS (unchanged).

- [ ] **Step 2: Grep for any missed HTML/Copy-for-Claude references** across the whole plugin (docs included) and fix stragglers.

Run: `grep -rn "Copy for Claude\|Download Feedback\|schedule-review.html\|build_gantt_html" scheduling`
Expected: none, except intentional historical notes.

- [ ] **Step 3: Self-review against the spec** — publish + pull + final gate + retirement all covered; version lockstep correct; no `test_*.py` sibling in `tools/`.

---

## Self-Review (run after all tasks)

- `feedback pull` reuses `_detect_drift`/`_activities_index` unchanged (mapping only adapts the shape).
- `proposal_iterate.py` still writes `schedule-activities.json` and scores; only HTML removed; `--help` works.
- No live `.py` references `build_gantt_html`/`html_path`/`frappe-gantt`; docs updated.
- Phases/SKILL describe: publish (update-in-place vs new_version), pull+reconcile, final gate.
- `plugin.json` == `marketplace.json` version (`10.2.0`); rebased onto origin/main before PR.
- westland-mcps PR deployed first (dependency).
