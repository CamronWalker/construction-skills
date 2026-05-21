# Schedule Update — Procore Integration + Skill Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks in Wave 1 are independent and MUST be dispatched in parallel (one subagent per task, all at once). Wave 2 is sequential and starts only after Wave 1 fully completes and is reviewed.

**Goal:** Restructure `scheduling:schedule-update` into a router + phase files (forces full-skill reads, eliminates per-script `Read`s), and add a Procore publish step that imports the XER to the Schedule tool, creates a dated Documents subfolder, and uploads a user-curated attachment subset alongside the `.eml` draft.

**Architecture:** SKILL.md becomes a thin router with a command matrix naming the phase files each command must read. Phase files under `phases/` are self-contained — script signatures + dict shapes inlined. Procore phase is Claude-driven markdown that calls MCP tools (`find_project`, `procore_get`, `create_document_folder`, `create_document`, `import_xer_schedule`) and uses `AskUserQuestion` for folder choice. New preview-HTML fields (`share_to_procore` per attachment, `skip_procore` top-level) round-trip through the existing parse/generate pair. New `project-context.html` field (`procore_documents_folder_id`) round-trips through the existing schedule-project-init parse/generate pair.

**Tech Stack:** Python 3.10+ (stdlib only for new logic), HTML/JS for preview editing, Procore MCP via Claude tool layer, pytest/unittest for tests, `python build.py` for release packaging.

**Spec:** `docs/superpowers/specs/2026-05-18-schedule-update-procore-integration-design.md`

**Branch:** `feat/schedule-update-procore-integration` (already created)

---

## Shared Interface Contract

This is the **single source of truth** every Wave 1 task references. Lock these names exactly — every parallel task assumes the names below.

### Contract 1: `project-context.html` — new field

- **Python field name:** `procore_documents_folder_id`
- **Type:** `str` (integer-as-string, e.g. `"4592384"`; empty `""` until resolved)
- **Default:** `''` in the parser's result dict
- **HTML rendering:** editable text input with `data-field="procore_documents_folder_id"`, placeholder `"Auto-populated on first Procore run"`
- **Position in HTML:** inside the Basics card, immediately after `procore_project_id`
- **Editable:** yes (so user can blank to re-trigger discovery)

### Contract 2: Preview HTML attachment — new `share_to_procore` field

- **Python dict shape (per attachment):**
  ```python
  {
      'filename': str,
      'checked': bool,
      'status': 'active' | 'new' | 'removed' | 'archived',
      'date_archived': str,         # 'YYYY-MM-DD' or ''
      'share_to_procore': bool,     # NEW
  }
  ```
- **HTML on `<li class="attachment-item">`:** add `data-share-procore="true"` or `data-share-procore="false"` (sibling to existing `data-checked` and `data-status`).
- **HTML inside the LI:** add a second `<label class="attach-procore-toggle"><input type="checkbox" data-procore-checked {checked_attr}></label>` element immediately AFTER the existing `<label class="attach-toggle">` and BEFORE the `attachment-status-icon` span. The `data-procore-checked` attribute marker is what the parser uses to distinguish the Procore checkbox from the include checkbox (`data-item-checked`).
- **Label tooltip:** `title="Share to Procore"`
- **Visual cue:** label includes a small "P" badge (`<span class="procore-badge">P</span>`) so it's distinguishable at a glance. Specific CSS in Task 4.

### Contract 3: Preview HTML top-level — new `skip_procore` field

- **Python top-level dict key:** `skip_procore`
- **Type:** `bool`
- **Default:** `False`
- **HTML:** `<input type="checkbox" data-field="skip_procore" {checked_attr}>` wrapped in a label `<label class="skip-procore-toggle">⏭ Skip Procore this week</label>`
- **Position in HTML:** inside `.attachments-section`, BEFORE the `changes-report-option` div (so it sits at the top of the section, visually distinct).

### Contract 4: `carry_forward.transition_attachments` behavior

- **Signature unchanged:** `transition_attachments(last_week_attachments, fresh_filenames=None, today_iso=None, max_archived_days=MAX_ARCHIVED_DAYS)`
- **New behavior 1 — preserve:** for each fresh-glob match against last week's attachment, propagate `share_to_procore` from the last-week dict verbatim into the new dict.
- **New behavior 2 — bootstrap:** for each genuinely new attachment (no last-week match), default `share_to_procore` per the rule:
  - `True` if the filename matches `re.search(r'view', name, re.IGNORECASE)` OR matches `re.search(r'update[-_ ]request.*\.xlsm$', name, re.IGNORECASE)`
  - `False` otherwise
- **Returned dict shape:** add `'share_to_procore': bool` to each item the function returns (both matched-and-preserved items and new items).

### Contract 5: Preview HTML parser — `parse_preview_html` additions

- **Per-attachment dict:** include `'share_to_procore': bool` (read from the `data-share-procore` attribute on `<li class="attachment-item">`, with `'true'` → True, anything else → False).
- **Top-level dict key:** `'skip_procore': bool` (read from the `data-field="skip_procore"` checkbox in the attachments-section; `True` if the input has `checked` attribute).
- **Default on missing field:** `False` for both.

### Contract 6: `generate_email_preview_html.generate_preview_html` — new kwarg

- **New kwarg:** `skip_procore: bool = False` — controls the master toggle's initial state.
- **Attachment items:** each item dict in the `attachments` kwarg may include `share_to_procore`. If present, that value flows into the rendered `data-share-procore` and checkbox state. If absent, default `False`.
- **JS — `ATTACHMENT_TEMPLATE`:** the JS template literal used by `+ Browse files` / `+ Add by name` to spawn new attachment rows must include the new Procore checkbox (defaulting unchecked).
- **JS — `collectFields()` / saveEdits snapshot:** the saved HTML reflects checkbox state for both `data-item-checked` and `data-procore-checked`, and the master toggle. The existing `setAttribute('value', ...)` pattern handles text inputs; checkboxes need their `checked` attribute synced explicitly. Add a small JS helper called from `saveEdits()` before `_buildSnapshotHtml`:
  ```javascript
  function _syncCheckboxes() {
    document.querySelectorAll('input[type=checkbox]').forEach(el => {
      if (el.checked) el.setAttribute('checked', '');
      else el.removeAttribute('checked');
    });
    document.querySelectorAll('li.attachment-item').forEach(li => {
      const inc = li.querySelector('input[data-item-checked]');
      const pro = li.querySelector('input[data-procore-checked]');
      li.setAttribute('data-checked', (inc && inc.checked) ? 'true' : 'false');
      li.setAttribute('data-share-procore', (pro && pro.checked) ? 'true' : 'false');
    });
  }
  ```

### Contract 7: `phases/procore.md` — required Claude-side flow

The phase file must instruct Claude to perform, in order:

1. **Preflight — resolve project ID** (`find_project` → single-match silent write-back OR `AskUserQuestion` disambiguation).
2. **Preflight — resolve folder ID** (`procore_get` root folder listing → filter out `Schedules` → `AskUserQuestion` with candidates + "Create new 'Schedule Updates'" option → write back).
3. **Operation 1: XER import** (`import_xer_schedule` + Bash curl + `get_schedule_import_status` poll loop).
4. **Operation 2: Dated folder create** (`create_document_folder` with `parentId=procore_documents_folder_id, name=today_iso` + name-exists fallback via `procore_get`).
5. **Operation 3: Upload attachments** (iterate `parsed['attachments']` filtered by `share_to_procore AND checked AND status != 'archived'`; for each: `create_document` + Bash curl + verify by listing + one retry on failure).
6. **Summary** (table of per-operation results; mention `/schedule-update procore` for retry if any failed).

The "phase file structure" task (Task 13) lays out exact wording, MCP call shapes, and the verify-and-retry loop.

### Contract 8: Skill router — command matrix

| Invocation | Phase files to read first |
|---|---|
| `copy` | `phases/copy.md` |
| `screenshots` | `phases/screenshots.md` |
| `email` | `phases/email.md`, `phases/_carry_forward.md`, `phases/_attachments.md` |
| `report` | `phases/report.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/draft.md`, `phases/procore.md` |
| `draft` | `phases/draft.md`, `phases/_attachments.md`, `phases/procore.md` |
| `procore` | `phases/procore.md`, `phases/_attachments.md` |
| `status` | `phases/status.md` |
| no arg | `phases/status.md` |

### Version bump

- `scheduling/.claude-plugin/plugin.json`: `5.1.5` → `5.2.0`
- `.claude-plugin/marketplace.json` (scheduling entry): `5.1.5` → `5.2.0`

Minor bump because new functionality is added (Procore integration) without breaking the existing CLI surface.

---

## File Structure

**Modify (existing files):**
- `scheduling/skills/schedule-update/SKILL.md` — replace contents with router + command matrix
- `scheduling/skills/schedule-update/commands/write-weekly-schedule-email.md` — reduce to thin shell pointing at phase files
- `scheduling/skills/schedule-update/references/parse_email_html.py` — read `share_to_procore` per attachment + top-level `skip_procore`
- `scheduling/skills/schedule-update/references/generate_email_preview_html.py` — render new checkboxes/toggle + JS updates
- `scheduling/skills/schedule-update/references/carry_forward.py` — preserve `share_to_procore`; bootstrap rule for new attachments
- `scheduling/skills/schedule-update/tests/test_email_preview_html.py` — add tests for new fields
- `scheduling/skills/schedule-project-init/references/parse_project_context_html.py` — read `procore_documents_folder_id`
- `scheduling/skills/schedule-project-init/references/generate_project_context_html.py` — render `procore_documents_folder_id` row
- `scheduling/skills/schedule-project-init/tests/test_project_context_html.py` — add tests for new field
- `scheduling/.claude-plugin/plugin.json` — version bump
- `.claude-plugin/marketplace.json` — version bump

**Create (new files):**
- `scheduling/skills/schedule-update/phases/_attachments.md`
- `scheduling/skills/schedule-update/phases/_carry_forward.md`
- `scheduling/skills/schedule-update/phases/copy.md`
- `scheduling/skills/schedule-update/phases/screenshots.md`
- `scheduling/skills/schedule-update/phases/email.md`
- `scheduling/skills/schedule-update/phases/report.md`
- `scheduling/skills/schedule-update/phases/draft.md`
- `scheduling/skills/schedule-update/phases/procore.md`
- `scheduling/skills/schedule-update/phases/status.md`

---

## Wave 1 — Parallel Tasks (dispatch all at once)

The 16 tasks below have no inter-task dependencies. They all reference the **Shared Interface Contract** above. Dispatch one subagent per task in a single message. Each task is self-contained — a fresh agent with no prior context can pick it up cold.

**Coordination guarantee:** the contract section above pins every shared name, attribute, signature, and HTML structure. As long as each task follows its task description faithfully, the parallel outputs will compose correctly in Wave 2 integration.

---

### Task 1: Parser — `procore_documents_folder_id` field in `project-context.html`

**Files:**
- Modify: `scheduling/skills/schedule-project-init/references/parse_project_context_html.py`
- Test: `scheduling/skills/schedule-project-init/tests/test_project_context_html.py`

**Contract reference:** Contract 1 (project-context.html new field).

- [ ] **Step 1: Write the failing test**

Add to `test_project_context_html.py` at the bottom of the file (above `if __name__ == '__main__'`):

```python
class ProcoreDocumentsFolderTests(unittest.TestCase):
    """Field added 2026-05 for the Procore Documents upload workflow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def test_field_round_trips(self):
        ctx = dict(FULL_CTX)
        ctx['procore_documents_folder_id'] = '4592384'
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '4592384')

    def test_field_defaults_empty_on_missing(self):
        # Round-trip a context that omits the field. Parser must
        # tolerate older HTML files written before the field existed.
        ctx = dict(FULL_CTX)
        ctx.pop('procore_documents_folder_id', None)
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '')

    def test_user_blanks_field_to_re_trigger_discovery(self):
        # The Procore phase blanks this field when the user wants to
        # switch folders. Round-trip an empty value.
        ctx = dict(FULL_CTX)
        ctx['procore_documents_folder_id'] = ''
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest scheduling/skills/schedule-project-init/tests/test_project_context_html.py::ProcoreDocumentsFolderTests -v
```

Expected: FAIL (`KeyError: 'procore_documents_folder_id'` or `AssertionError` because parser returns no such key).

- [ ] **Step 3: Implement minimal parser change**

In `parse_project_context_html.py`, find the `result = { ... }` dict initialization inside `parse_project_context_html` (around line 112) and add the new field next to the existing `procore_*` entries:

```python
    result = {
        'project_name': '',
        'job_number': '',
        'contractual_completion': '',
        'smartpm_url': '',
        'smartpm_trends_url': '',
        'smartpm_changelog_url': '',
        'smartpm_project_name': '',
        'signer_name': '',
        'signer_title': '',
        'signer_mobile': '',
        'procore_company_id': '',
        'procore_project_id': '',
        'procore_documents_folder_id': '',  # NEW — Procore Documents folder for weekly uploads
        'graph_screenshots': [],
        'project_log': [],
        'to_recipients': [],
        'cc_recipients': [],
    }
```

The existing scalar-input loop will pick up the field automatically because `scalar_fields = set(result.keys()) - {...}` already excludes only the list-valued fields.

Also update the module docstring at the top: change the line `procore_company_id, procore_project_id,` to `procore_company_id, procore_project_id, procore_documents_folder_id,`.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest scheduling/skills/schedule-project-init/tests/test_project_context_html.py::ProcoreDocumentsFolderTests -v
```

Expected: 3 tests PASS. Test 1 (round-trip) needs the generator change too — see Task 2. If only test 1 fails because the generator doesn't render the field yet, that's expected and the task is still passing this phase. Re-run after Task 2 completes.

Actually — the round-trip test depends on the generator rendering the new row. To keep this task self-contained and runnable in isolation, replace `test_field_round_trips` with a parser-only test that uses a static HTML string:

```python
    def test_parser_reads_field_from_static_html(self):
        # Don't depend on the generator (that's Task 2). Hand-craft minimal HTML.
        html = (
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="procore_documents_folder_id" '
            'value="4592384">'
            '</body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '4592384')
```

And drop the round-trip + blank-field tests from THIS task — they're round-trip tests that belong in Task 2 (the generator task) or in the integration smoke (Wave 2). This task validates parser-only behavior with a static HTML input.

Re-run; expect PASS.

- [ ] **Step 5: Run the existing test suite to verify no regression**

```bash
python -m pytest scheduling/skills/schedule-project-init/tests/test_project_context_html.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-project-init/references/parse_project_context_html.py \
        scheduling/skills/schedule-project-init/tests/test_project_context_html.py
git commit -m "$(cat <<'EOF'
feat(schedule-project-init): parser reads procore_documents_folder_id

Adds the new Procore Documents folder ID field to the project-context.html
parser. Defaults empty for older HTML files (no breaking change).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Generator — render `procore_documents_folder_id` row in `project-context.html`

**Files:**
- Modify: `scheduling/skills/schedule-project-init/references/generate_project_context_html.py`
- Test: `scheduling/skills/schedule-project-init/tests/test_project_context_html.py`

**Contract reference:** Contract 1.

- [ ] **Step 1: Write the failing test**

Append to `test_project_context_html.py` (this complements Task 1's parser-only test by exercising the generator and round-trip):

```python
class ProcoreDocumentsFolderGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def test_generator_renders_field_row(self):
        ctx = dict(FULL_CTX)
        ctx['procore_documents_folder_id'] = '4592384'
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        with open(self.path, 'r', encoding='utf-8') as f:
            html = f.read()
        self.assertIn('data-field="procore_documents_folder_id"', html)
        self.assertIn('value="4592384"', html)

    def test_generator_renders_empty_when_unset(self):
        ctx = dict(FULL_CTX)
        ctx.pop('procore_documents_folder_id', None)
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        with open(self.path, 'r', encoding='utf-8') as f:
            html = f.read()
        self.assertIn('data-field="procore_documents_folder_id"', html)
        # Empty value should render
        self.assertRegex(
            html,
            r'data-field="procore_documents_folder_id"[^>]*value=""',
        )

    def test_field_round_trips_through_generator_then_parser(self):
        ctx = dict(FULL_CTX)
        ctx['procore_documents_folder_id'] = '7777777'
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '7777777')
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest scheduling/skills/schedule-project-init/tests/test_project_context_html.py::ProcoreDocumentsFolderGeneratorTests -v
```

Expected: FAIL (HTML doesn't contain the new field).

- [ ] **Step 3: Implement generator change**

In `generate_project_context_html.py`, find the Basics card section (around line 294) and add a new field row immediately after the `procore_project_id` row. The change:

```python
    # --- Basics ---
    parts.append(_card_open('Basics'))
    parts.append('<div class="field-grid">')
    parts.append(_field_row(
        'Contractual Completion Date',
        _editable_text('contractual_completion', contractual_completion),
    ))
    parts.append(_field_row(
        'Procore Project ID',
        _editable_text('procore_project_id', str(procore_project_id),
                       placeholder='e.g. 2646569'),
    ))
    parts.append(_field_row(                                          # NEW
        'Procore Documents Folder ID',                                # NEW
        _editable_text(                                               # NEW
            'procore_documents_folder_id',                            # NEW
            str(procore_documents_folder_id),                         # NEW
            placeholder='Auto-populated on first Procore run',        # NEW
        ),                                                            # NEW
        note='Blank to re-trigger folder discovery next run',         # NEW
    ))                                                                # NEW
    parts.append(_field_row(
        'Procore Company ID',
        _locked_text('procore_company_id', str(procore_company_id),
                     cls='locked-input'),
        note='Locked',
    ))
    parts.append('</div>')
    parts.append(_card_close())
```

Also add the variable read at the top of `_build_html` (around line 250, with the other ctx reads):

```python
    procore_project_id = ctx.get('procore_project_id', '')
    procore_documents_folder_id = ctx.get('procore_documents_folder_id', '')  # NEW
    graph_screenshots = ctx.get('graph_screenshots', [])
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest scheduling/skills/schedule-project-init/tests/test_project_context_html.py -v
```

Expected: all tests in `ProcoreDocumentsFolderGeneratorTests` PASS plus all pre-existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-project-init/references/generate_project_context_html.py \
        scheduling/skills/schedule-project-init/tests/test_project_context_html.py
git commit -m "$(cat <<'EOF'
feat(schedule-project-init): generator renders procore_documents_folder_id

Adds an editable row in the Basics card for the Procore Documents folder
ID. Editable (not locked) so a user can blank it to re-trigger folder
discovery on the next Procore run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Parser — `share_to_procore` per attachment + top-level `skip_procore` in preview HTML

**Files:**
- Modify: `scheduling/skills/schedule-update/references/parse_email_html.py`
- Test: `scheduling/skills/schedule-update/tests/test_email_preview_html.py`

**Contract reference:** Contracts 2 (per-attachment), 3 (top-level), 5 (parser additions).

- [ ] **Step 1: Write failing tests**

Append to `test_email_preview_html.py`:

```python
class ProcoreFieldsParseTests(unittest.TestCase):
    """Parser surface for the Procore upload workflow (added 2026-05)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name,
                                 '2026-05-07-email-preview.html')

    def test_share_to_procore_true_parsed_from_data_attribute(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list">'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active" data-share-procore="true">'
            '<input type="checkbox" data-item-checked checked>'
            '<input type="checkbox" data-procore-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'View 01.pdf</span></li>'
            '</ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        atts = parsed['attachments']
        self.assertEqual(len(atts), 1)
        self.assertTrue(atts[0]['share_to_procore'])

    def test_share_to_procore_false_when_attribute_missing_or_false(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list">'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active" data-share-procore="false">'
            '<input type="checkbox" data-item-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'SmartPM Summary.pdf</span></li>'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active">'  # no data-share-procore
            '<input type="checkbox" data-item-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'Internal Notes.pdf</span></li>'
            '</ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        atts = parsed['attachments']
        self.assertEqual(len(atts), 2)
        self.assertFalse(atts[0]['share_to_procore'])
        self.assertFalse(atts[1]['share_to_procore'])

    def test_skip_procore_true(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<input type="checkbox" data-field="skip_procore" checked>'
            '<ul class="attachment-list"></ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertTrue(parsed['skip_procore'])

    def test_skip_procore_false_default(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list"></ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertFalse(parsed['skip_procore'])
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_email_preview_html.py::ProcoreFieldsParseTests -v
```

Expected: 4 FAIL (the keys don't exist in the result yet).

- [ ] **Step 3: Implement parser changes**

In `parse_email_html.py`, modify `_extract_attachment_item` (around line 455) to return the new field:

```python
def _extract_attachment_item(attrs, inner):
    classes = (attrs.get('class') or '').split()
    status = attrs.get('data-status', 'active')
    date_archived = attrs.get('data-archived', '')
    dc = attrs.get('data-checked')
    if dc is not None:
        checked = dc.lower() == 'true'
    else:
        checked = True
        for iattrs, _i, _r in _iter_elements(inner, 'input'):
            if (iattrs.get('type') or '').lower() == 'checkbox':
                checked = _is_checked(iattrs)
                break
    # NEW — share_to_procore from data attribute
    sp = (attrs.get('data-share-procore') or '').lower()
    share_to_procore = sp == 'true'
    filename = ''
    for sattrs, sinner, _ in _iter_elements(inner, 'span'):
        if (sattrs.get('data-field') == 'attachment_name'
                or 'attachment-name' in (sattrs.get('class') or '').split()):
            filename = html_to_markdown(sinner).strip()
            break
    if not filename:
        return None
    return {
        'filename': filename,
        'checked': checked,
        'status': status,
        'date_archived': date_archived,
        'share_to_procore': share_to_procore,  # NEW
    }
```

Then in `parse_preview_html` (around line 158), add a `skip_procore` extraction near where `changes_report` is parsed (around line 293). Insert AFTER the attachments section parse but BEFORE `attachment_paths` derivation:

```python
    # --- Skip-Procore master toggle -----------------------------------
    skip_procore = False
    m_sp = re.search(
        r'<input\b[^>]*data-field="skip_procore"[^>]*>', raw,
        re.IGNORECASE,
    )
    if m_sp:
        skip_procore = bool(
            re.search(r'\s+checked(\s|=|>|/)', m_sp.group(0), re.IGNORECASE)
        )
```

Then in the `result = { ... }` dict (around line 343), add the new key:

```python
        'attachments': attachments_full,
        'attachment_names': attachment_names,
        'attachment_paths': attachment_paths,
        'changes_report': changes_report,
        'skip_procore': skip_procore,                          # NEW
        'summary_screenshot_path': _rel_to_abs(summary_rel),
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_email_preview_html.py -v
```

Expected: all `ProcoreFieldsParseTests` PASS, pre-existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/parse_email_html.py \
        scheduling/skills/schedule-update/tests/test_email_preview_html.py
git commit -m "$(cat <<'EOF'
feat(schedule-update): parser reads share_to_procore + skip_procore

Adds per-attachment share_to_procore and top-level skip_procore to the
preview HTML parse result. Defaults False on missing attributes so older
preview HTMLs round-trip cleanly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Generator — render Procore checkbox + master toggle in preview HTML

**Files:**
- Modify: `scheduling/skills/schedule-update/references/generate_email_preview_html.py`
- Test: `scheduling/skills/schedule-update/tests/test_email_preview_html.py`

**Contract reference:** Contracts 2 (per-attachment), 3 (top-level toggle), 6 (generator kwarg + JS).

- [ ] **Step 1: Write failing tests**

Append to `test_email_preview_html.py` (after the `ProcoreFieldsParseTests` class):

```python
class ProcoreFieldsGenerateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name,
                                 '2026-05-07-email-preview.html')

    def _gen(self, **overrides):
        kw = dict(FULL_KWARGS)
        kw.update(overrides)
        gen.generate_preview_html(self.path, **kw)
        with open(self.path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_share_to_procore_true_renders_data_attr_and_checked(self):
        html = self._gen(attachments=[
            {'filename': 'View 01.pdf', 'checked': True, 'status': 'active',
             'share_to_procore': True},
        ])
        self.assertIn('data-share-procore="true"', html)
        # The Procore checkbox should be checked
        self.assertRegex(html, r'data-procore-checked[^>]*checked')

    def test_share_to_procore_false_renders_data_attr_and_unchecked(self):
        html = self._gen(attachments=[
            {'filename': 'Notes.pdf', 'checked': True, 'status': 'active',
             'share_to_procore': False},
        ])
        self.assertIn('data-share-procore="false"', html)
        # Procore checkbox present but NOT checked
        self.assertIn('data-procore-checked', html)
        # Use regex to ensure the procore checkbox specifically lacks `checked`
        m = re.search(
            r'<input[^>]*data-procore-checked[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertNotIn(' checked', m.group(0))

    def test_share_to_procore_defaults_false_when_omitted(self):
        html = self._gen(attachments=[
            {'filename': 'Notes.pdf', 'checked': True, 'status': 'active'},
        ])
        self.assertIn('data-share-procore="false"', html)

    def test_skip_procore_kwarg_renders_checked_master_toggle(self):
        html = self._gen(skip_procore=True)
        # Master toggle present and checked
        m = re.search(
            r'<input[^>]*data-field="skip_procore"[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertIn('checked', m.group(0))

    def test_skip_procore_default_renders_unchecked_master_toggle(self):
        html = self._gen()  # no skip_procore kwarg
        m = re.search(
            r'<input[^>]*data-field="skip_procore"[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertNotIn(' checked', m.group(0))

    def test_round_trip_preserves_procore_fields(self):
        gen.generate_preview_html(
            self.path,
            **dict(FULL_KWARGS,
                   skip_procore=True,
                   attachments=[
                       {'filename': 'View 01.pdf', 'checked': True,
                        'status': 'active', 'share_to_procore': True},
                       {'filename': 'Summary.pdf', 'checked': True,
                        'status': 'active', 'share_to_procore': False},
                   ]),
        )
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertTrue(parsed['skip_procore'])
        self.assertEqual(len(parsed['attachments']), 2)
        self.assertTrue(parsed['attachments'][0]['share_to_procore'])
        self.assertFalse(parsed['attachments'][1]['share_to_procore'])

    def test_attachment_template_js_includes_procore_checkbox(self):
        # The JS template used by + Browse files / + Add by name spawns new
        # rows. New rows must default share_to_procore=false (off) and include
        # the procore checkbox so users can opt in.
        html = self._gen()
        # Find the ATTACHMENT_TEMPLATE block in the generated JS
        m = re.search(
            r'const ATTACHMENT_TEMPLATE\s*=\s*`([^`]*)`', html, re.DOTALL,
        )
        self.assertIsNotNone(m, 'ATTACHMENT_TEMPLATE literal not found in JS')
        tmpl = m.group(1)
        self.assertIn('data-share-procore="false"', tmpl)
        self.assertIn('data-procore-checked', tmpl)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_email_preview_html.py::ProcoreFieldsGenerateTests -v
```

Expected: 7 FAIL.

- [ ] **Step 3: Modify `_render_attachment_item`**

Find `_render_attachment_item` in `generate_email_preview_html.py` (around line 448). Change it to read `share_to_procore` from the item dict and emit the new attribute + checkbox:

```python
def _render_attachment_item(item):
    f = _item_fields(item)
    filename = f['filename'] or f['text']
    checked = f['checked']
    status = f['status']
    date_archived = f['date_archived']
    share_to_procore = bool(item.get('share_to_procore', False))   # NEW
    checked_class = 'true' if checked else 'false'
    checked_attr = 'checked' if checked else ''
    procore_class = 'true' if share_to_procore else 'false'        # NEW
    procore_attr = 'checked' if share_to_procore else ''           # NEW
    archived_attr = (
        f' data-archived="{_esc(date_archived)}"' if date_archived else ''
    )
    return (
        f'<li class="attachment-item" data-checked="{checked_class}" '
        f'data-status="{_esc(status)}" '
        f'data-share-procore="{procore_class}"{archived_attr}>'      # MODIFIED
        '<span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag handle">⋮⋮</span>'
        '<label class="attach-toggle" title="Include in email">'
        f'<input type="checkbox" data-item-checked {checked_attr}>'
        '</label>'
        '<label class="attach-procore-toggle" title="Share to Procore">'  # NEW
        f'<input type="checkbox" data-procore-checked {procore_attr}>'    # NEW
        '<span class="procore-badge">P</span>'                            # NEW
        '</label>'                                                        # NEW
        '<span class="attachment-status-icon" aria-hidden="true"></span>'
        f'<span class="attachment-name" contenteditable="true" '
        f'data-field="attachment_name">{_esc(filename)}</span>'
        # ... rest unchanged
    )
```

(Preserve everything below the `<span class="attachment-name">` line — it includes the meta, archived note, and controls. Don't change that part.)

- [ ] **Step 4: Add `skip_procore` master toggle to attachments section**

Find the attachments-section render (around line 390) and insert the master toggle BEFORE the `changes-report-option` block:

```python
    skip_procore = bool(kwargs.get('skip_procore', False))   # NEW — pull from kwargs
    skip_procore_attr = 'checked' if skip_procore else ''    # NEW

    out = [
        '<div class="attachments-section" data-field="attachments">',
        '<h4 class="no-print">Attachments</h4>',
        '<p class="section-hint no-print">Files attached to the Outlook draft. '
        'Uncheck the leftmost ☐ to skip from the email. '
        'Tick the <span style="color:#0B4F66;font-weight:bold">P</span> on a row '
        'to publish that file to Procore. The folder is public — only check files '
        'safe to share publicly.</p>',
        # NEW — master skip-Procore toggle
        '<div class="skip-procore-option" data-field="skip_procore_option">',
        f'  <label class="skip-procore-toggle">',
        f'    <input type="checkbox" data-field="skip_procore" {skip_procore_attr}>',
        '    <span class="skip-procore-label">⏭ Skip Procore this week</span>',
        '  </label>',
        '  <span class="skip-procore-hint">Suppresses XER import + Documents '
        'upload. Email still sends.</span>',
        '</div>',
        # END NEW
        # Existing changes-report-option block continues below:
        '<div class="changes-report-option" data-field="changes_report">',
        # ... rest unchanged
    ]
```

(Tweak the indent/structure to fit your local style. The `kwargs` reference assumes the surrounding function signature uses `**kwargs` — if it uses explicit named parameters, add `skip_procore=False` to the signature.)

You'll need to thread `skip_procore` through `generate_preview_html`'s signature. Find the function definition (likely around line 60-100 — search for `def generate_preview_html`) and add `skip_procore=False` to the kwargs.

- [ ] **Step 5: Update `ATTACHMENT_TEMPLATE` JS literal**

Find the JS `ATTACHMENT_TEMPLATE` literal (around line 1762):

```python
const ATTACHMENT_TEMPLATE = `
<li class="attachment-item" data-checked="true" data-status="new" data-share-procore="false">
  <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag handle">⋮⋮</span>
  <label class="attach-toggle" title="Include in email"><input type="checkbox" data-item-checked checked></label>
  <label class="attach-procore-toggle" title="Share to Procore"><input type="checkbox" data-procore-checked><span class="procore-badge">P</span></label>
  <span class="attachment-status-icon" aria-hidden="true"></span>
  <span class="attachment-name" contenteditable="true" data-field="attachment_name">FILENAME</span>
  <span class="attachment-meta"><span class="note-archived">📁 Archived <span class="archived-date"></span></span></span>
  <div class="attachment-controls no-print">
    <!-- existing controls preserved -->
  </div>
</li>
`;
```

(Preserve any existing control buttons inside `attachment-controls`. The new defaults are `data-share-procore="false"` and the Procore checkbox unchecked.)

- [ ] **Step 6: Add the `_syncCheckboxes` JS helper and call it from saveEdits**

Find the `_buildSnapshotHtml` function in the JS block (search for `function _buildSnapshotHtml`). Add a new helper just above it, and call it as the first line of `_buildSnapshotHtml`:

```javascript
function _syncCheckboxes() {
  document.querySelectorAll('input[type=checkbox]').forEach(el => {
    if (el.checked) el.setAttribute('checked', '');
    else el.removeAttribute('checked');
  });
  document.querySelectorAll('li.attachment-item').forEach(li => {
    const inc = li.querySelector('input[data-item-checked]');
    const pro = li.querySelector('input[data-procore-checked]');
    li.setAttribute('data-checked', (inc && inc.checked) ? 'true' : 'false');
    li.setAttribute('data-share-procore', (pro && pro.checked) ? 'true' : 'false');
  });
}

function _buildSnapshotHtml() {
  _syncCheckboxes();   // NEW — keep data attributes and checkbox state aligned with reality
  document.querySelectorAll('input[type=text]').forEach(el => {
    el.setAttribute('value', el.value || '');
  });
  const clone = document.documentElement.cloneNode(true);
  return '<!DOCTYPE html>\n' + clone.outerHTML;
}
```

- [ ] **Step 7: Add minimal CSS for the new controls**

Find the attachments CSS block (around line 1137 — `.attachments-section {{` etc.) and add new rules. Insert at the end of the attachments CSS section:

```css
/* Procore toggle on each attachment row */
.attach-procore-toggle {{
  display: inline-flex; align-items: center; gap: 3px;
  cursor: pointer; user-select: none;
}}
.attach-procore-toggle input[type="checkbox"] {{
  width: 13px; height: 13px;
}}
.procore-badge {{
  display: inline-block; background: {TEAL}; color: #fff;
  font-size: 9pt; font-weight: bold;
  padding: 0 4px; border-radius: 2px;
  font-family: Arial, sans-serif;
}}
li.attachment-item[data-share-procore="true"] {{
  border-left: 3px solid {TEAL};
}}

/* Skip Procore master toggle */
.skip-procore-option {{
  display: flex; align-items: center; gap: 10px;
  padding: 6px 10px; margin: 4px 0 8px 0;
  background: #fff8e1; border: 1px dashed {AMBER};
  border-radius: 4px;
}}
.skip-procore-toggle {{
  display: inline-flex; align-items: center; gap: 6px;
  cursor: pointer; font-weight: bold; color: #6b4f0e;
}}
.skip-procore-hint {{
  font-size: 11px; color: #555; font-style: italic;
}}
```

(Insert these inside an `f"""..."""` CSS string. `{TEAL}`, `{AMBER}` are already defined as module constants.)

- [ ] **Step 8: Run tests to verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_email_preview_html.py -v
```

Expected: all `ProcoreFieldsGenerateTests` PASS, all pre-existing tests still PASS.

- [ ] **Step 9: Commit**

```bash
git add scheduling/skills/schedule-update/references/generate_email_preview_html.py \
        scheduling/skills/schedule-update/tests/test_email_preview_html.py
git commit -m "$(cat <<'EOF'
feat(schedule-update): preview renders share_to_procore + skip_procore

Adds a per-attachment 'P' (Share to Procore) checkbox on each attachment
row plus a master 'Skip Procore this week' toggle above the attachments
list. JS sync keeps data-share-procore in lockstep with the checkbox so
parse-on-save round-trips correctly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Carry-forward — preserve `share_to_procore` + bootstrap rule

**Files:**
- Modify: `scheduling/skills/schedule-update/references/carry_forward.py`
- Test: a new test file `scheduling/skills/schedule-update/tests/test_carry_forward.py`

**Contract reference:** Contract 4.

- [ ] **Step 1: Check if a carry-forward test file already exists**

```bash
ls scheduling/skills/schedule-update/tests/
```

If `test_carry_forward.py` does NOT exist, create it. If it does, append to it.

- [ ] **Step 2: Write failing tests**

Create `scheduling/skills/schedule-update/tests/test_carry_forward.py` (or append to existing):

```python
"""Tests for the carry_forward module's Procore-related behavior
(added 2026-05). Existing tests for transition_items/transition_attachments
without Procore concerns live elsewhere if they exist."""

import pathlib
import sys
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import carry_forward as cf  # noqa: E402


class TransitionAttachmentsProcoreTests(unittest.TestCase):
    """share_to_procore preservation + bootstrap rules."""

    def test_preserves_share_to_procore_true_when_file_carries_forward(self):
        last_week = [
            {'filename': 'Schedule View 2026-05-07.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': True},
        ]
        fresh = ['Schedule View 2026-05-14.pdf']  # same template, new date
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_preserves_share_to_procore_false_when_file_carries_forward(self):
        last_week = [
            {'filename': 'SmartPM Summary 2026-05-07.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': False},
        ]
        fresh = ['SmartPM Summary 2026-05-14.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['share_to_procore'])

    def test_new_file_with_View_name_bootstraps_to_true(self):
        last_week = []
        fresh = ['3-Week Look-Ahead View.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_new_file_with_update_request_xlsm_bootstraps_to_true(self):
        last_week = []
        fresh = ['W1177 Update Request 2026-05-14.xlsm']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['share_to_procore'])

    def test_new_file_matching_no_pattern_bootstraps_to_false(self):
        last_week = []
        fresh = ['Internal Notes.pdf']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]['share_to_procore'])

    def test_bootstrap_match_is_case_insensitive(self):
        last_week = []
        fresh = ['weekly view.pdf', 'WEEKLY UPDATE REQUEST.xlsm']
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        share = {r['filename']: r['share_to_procore'] for r in result}
        self.assertTrue(share['weekly view.pdf'])
        self.assertTrue(share['WEEKLY UPDATE REQUEST.xlsm'])

    def test_dropped_files_carry_share_to_procore_through_archive(self):
        # File from last week not in fresh list goes to status=removed.
        # share_to_procore should still be preserved on the dropped item.
        last_week = [
            {'filename': 'Old View.pdf', 'checked': True,
             'status': 'active', 'share_to_procore': True},
        ]
        fresh = []
        result = cf.transition_attachments(
            last_week, fresh, today_iso='2026-05-14',
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'removed')
        self.assertTrue(result[0]['share_to_procore'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run tests to verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_carry_forward.py -v
```

Expected: 7 FAIL (the field isn't being set anywhere yet).

- [ ] **Step 4: Implement the bootstrap rule and propagation**

In `carry_forward.py`, add a module-level helper near the top (after the constants):

```python
# Pattern-based bootstrap for share_to_procore. New attachments matching
# these patterns default to True (publicly shareable in the Procore Documents
# folder); everything else defaults to False (the folder is public, so
# unfamiliar files require an explicit opt-in via the preview checkbox).
_PROCORE_BOOTSTRAP_PATTERNS = [
    re.compile(r'view', re.IGNORECASE),
    re.compile(r'update[-_ ]request.*\.xlsm$', re.IGNORECASE),
]


def _bootstrap_share_to_procore(filename):
    """Return True if a brand-new attachment with this filename should
    default to share_to_procore=True."""
    if not filename:
        return False
    return any(p.search(filename) for p in _PROCORE_BOOTSTRAP_PATTERNS)
```

Then modify `transition_attachments` (around line 332) to thread `share_to_procore` through every returned dict:

```python
def transition_attachments(last_week_attachments, fresh_filenames=None,
                           today_iso=None,
                           max_archived_days=MAX_ARCHIVED_DAYS):
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_items = list(last_week_attachments or [])
    norm_index = {}
    for i, a in enumerate(last_items):
        norm = _normalize_attachment_name(a.get('filename', ''))
        if norm:
            norm_index.setdefault(norm, i)

    used = set()
    result = []

    # --- Match phase ---
    for fn in (fresh_filenames or []):
        if not fn:
            continue
        norm = _normalize_attachment_name(fn)
        if norm and norm in norm_index and norm_index[norm] not in used:
            i = norm_index[norm]
            used.add(i)
            last_a = last_items[i]
            last_status = last_a.get('status', 'active')

            if last_status in ('active', 'new'):
                status = 'active'
                checked = True
            elif last_status == 'removed':
                status = 'active'
                checked = True
            elif last_status == 'archived':
                status = 'new'
                checked = True
            else:
                status = 'active'
                checked = True

            # NEW — share_to_procore preserved from last week
            share_to_procore = bool(last_a.get('share_to_procore', False))

            result.append({
                'filename': fn,
                'checked': checked,
                'status': status,
                'date_archived': '',
                'share_to_procore': share_to_procore,   # NEW
            })
        else:
            # NEW — bootstrap for genuinely new attachments
            result.append({
                'filename': fn,
                'checked': True,
                'status': 'new',
                'date_archived': '',
                'share_to_procore': _bootstrap_share_to_procore(fn),   # NEW
            })

    # --- Drop phase ---
    for i, a in enumerate(last_items):
        if i in used:
            continue
        last_status = a.get('status', 'active')
        last_checked = bool(a.get('checked', True))
        # NEW — preserve share_to_procore on dropped items too
        share_to_procore = bool(a.get('share_to_procore', False))

        if last_status in ('active', 'new'):
            new_status = 'removed'
            new_checked = False
            new_archived = ''
        elif last_status == 'removed':
            new_status = 'archived'
            new_checked = False
            new_archived = today_iso
        elif last_status == 'archived':
            new_status = 'archived'
            new_checked = False
            new_archived = a.get('date_archived', today_iso)
        else:
            new_status = 'active'
            new_checked = last_checked
            new_archived = ''

        if (new_status == 'archived'
                and _too_old(new_archived, today, max_archived_days)):
            continue

        result.append({
            'filename': a.get('filename', ''),
            'checked': new_checked,
            'status': new_status,
            'date_archived': new_archived,
            'share_to_procore': share_to_procore,   # NEW
        })

    return result
```

- [ ] **Step 5: Run tests to verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/tests/test_carry_forward.py -v
```

Expected: 7 PASS.

- [ ] **Step 6: Run the full preview test suite for regression check**

```bash
python -m pytest scheduling/skills/schedule-update/tests/ -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/carry_forward.py \
        scheduling/skills/schedule-update/tests/test_carry_forward.py
git commit -m "$(cat <<'EOF'
feat(schedule-update): transition_attachments preserves share_to_procore

Adds a bootstrap rule (smart-on for *View* / *Update Request*.xlsm,
off for everything else) for genuinely new attachments, and propagates
share_to_procore verbatim for files that carry forward week-over-week.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Phase file — `phases/_attachments.md` (shared attachment data model)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/_attachments.md`

**Contract reference:** Contracts 2, 4, 5, 6.

This is a Markdown file with no test — verification is "the file exists and contains the documented shapes." Subagent reads the contract section above and writes the file.

- [ ] **Step 1: Create the file with the documented shapes**

```bash
mkdir -p scheduling/skills/schedule-update/phases
```

Write the file with the following content:

````markdown
# _attachments — shared attachment data model

> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `report.md`, `draft.md`, and `procore.md` per the router command matrix.

## Per-attachment dict shape

```python
{
    'filename': str,
    'checked': bool,                 # included in email
    'status': 'active' | 'new' | 'removed' | 'archived',
    'date_archived': str,            # 'YYYY-MM-DD' or ''
    'share_to_procore': bool,        # included in Procore Documents upload (the folder is public)
}
```

This dict shape is what `parse_email_html.parse_preview_html()` returns inside the top-level `'attachments'` list, and what `generate_email_preview_html.generate_preview_html()` expects in its `attachments=` kwarg.

## Top-level keys also relevant

```python
parsed = parse_preview_html(preview_path)
parsed['attachments']        # list of dicts as above
parsed['attachment_names']   # filtered: filename strings, checked & non-archived only
parsed['attachment_paths']   # filtered: absolute paths, checked & non-archived only
parsed['skip_procore']       # bool — master "skip Procore this week" toggle
```

## Carry-forward rules

`carry_forward.transition_attachments(last_week_attachments, fresh_filenames, today_iso)` returns a list of dicts in the shape above. Two Procore-specific rules:

- **Preserve:** for any file that matches an attachment from last week (date-stripped fuzzy name match), `share_to_procore` is propagated verbatim from the prior week's dict. The user's previous decision survives the week boundary.
- **Bootstrap (new attachments only):** for genuinely new files (no last-week match), `share_to_procore` defaults per pattern:
  - `True` when the filename matches `View` (case-insensitive) OR matches `Update Request*.xlsm` (case-insensitive).
  - `False` otherwise.
- **Rationale:** the Procore folder is public. New, unfamiliar files require an explicit opt-in via the preview's `P` checkbox.

## HTML representation (preview)

Each `<li class="attachment-item">` carries:

```html
<li class="attachment-item"
    data-checked="true|false"
    data-status="active|new|removed|archived"
    data-share-procore="true|false"
    data-archived="YYYY-MM-DD">          <!-- only when archived -->
  <span class="drag-handle">⋮⋮</span>
  <label class="attach-toggle" title="Include in email">
    <input type="checkbox" data-item-checked checked|unchecked>
  </label>
  <label class="attach-procore-toggle" title="Share to Procore">
    <input type="checkbox" data-procore-checked checked|unchecked>
    <span class="procore-badge">P</span>
  </label>
  <!-- attachment name, controls, etc. -->
</li>
```

The master skip-Procore toggle sits inside `.attachments-section`:

```html
<div class="skip-procore-option" data-field="skip_procore_option">
  <label class="skip-procore-toggle">
    <input type="checkbox" data-field="skip_procore">
    <span class="skip-procore-label">⏭ Skip Procore this week</span>
  </label>
</div>
```

## What to call, from each phase

| Phase | Reads | Writes |
|---|---|---|
| `email.md` (Camron path) | last week's preview parser for carry-forward + bootstrap | this week's preview via generator |
| `report.md` | same as email.md | same |
| `draft.md` | this week's preview parser (filtered lists for the `.eml`) | `.eml` file |
| `procore.md` | this week's preview parser (`share_to_procore` filter for Procore uploads) | nothing (Procore-side via MCP) |

## Do NOT

- Do NOT `Read` `parse_email_html.py` or `generate_email_preview_html.py` to learn the shape. This file is the canonical reference.
- Do NOT `Read` / `Edit` the preview HTML directly. Always parse → mutate dict → generate.
````

- [ ] **Step 2: Verify the file exists and contains the shapes**

```bash
ls scheduling/skills/schedule-update/phases/_attachments.md
grep -l "share_to_procore" scheduling/skills/schedule-update/phases/_attachments.md
```

Expected: file listed; grep prints the path.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_attachments.md
git commit -m "$(cat <<'EOF'
feat(schedule-update): add phases/_attachments.md shared chunk

Documents the per-attachment dict shape, carry-forward rules, HTML
representation, and per-phase responsibilities. Sourced from the
spec to avoid re-reads of parse_email_html.py and the preview HTML.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Phase file — `phases/_carry_forward.md` (shared carry-forward recipe)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/_carry_forward.md`

**Contract reference:** Contracts 4, 6.

This is the lift-and-restructure of the "Carry forward from last week" subsection currently in the email step of SKILL.md (lines ~370–410). The new file inlines the function signatures (no `Read` of carry_forward.py) and documents the recipe step-by-step.

- [ ] **Step 1: Write the file content**

Write `scheduling/skills/schedule-update/phases/_carry_forward.md`:

````markdown
# _carry_forward — week-over-week state propagation

> **Internal reference** (underscore-prefix). Loaded by `email.md` and `report.md`.

## Function signatures (inline)

```python
# carry_forward.transition_items(last_week_items, new_texts=None,
#                                today_iso=None, max_archived_days=90)
#     -> list of {text, checked, status, date_archived}
#
# Apply git-diff state transitions to list items (red_flags, successes,
# stalled_tasks, key_items). 90-day prune drops stale archives.

# carry_forward.transition_attachments(last_week_attachments,
#                                      fresh_filenames=None,
#                                      today_iso=None, max_archived_days=90)
#     -> list of {filename, checked, status, date_archived, share_to_procore}
#
# Date-stripped fuzzy match against last week. Preserves share_to_procore
# verbatim. Bootstrap rule for new attachments: True for *View* / *Update
# Request*.xlsm, False otherwise. See _attachments.md for details.

# carry_forward.reconcile_items(last_week_items, this_week_texts,
#                               today_iso=None, similarity_threshold=0.6,
#                               max_archived_days=90)
#     -> list of {text, previous_text, status, checked, date_archived}
#
# Fuzzy-matches this week's plain-text list against last week's tracked items.
# Use this when Claude has freshly-generated text and needs to reconcile
# against last week's history.
```

## Last week's preview — what to pull

Find last week's preview file:

```
prev_date_folder = most_recent_sibling_dated_folder(schedules_root)  # skip today
prev_preview = '{prev_date_folder}/{PREV_DATE}-email-preview.html'
```

If no prior preview exists, treat as "first update" and skip carry-forward.

Parse it:

```python
import parse_email_html
last = parse_email_html.parse_preview_html(prev_preview)
```

Pull the carry-forward values from `last`:

| Field | Pass to generator as | Purpose |
|---|---|---|
| `last['days_behind']`, `last['gain_loss']` | `previous_days_behind=`, `previous_gain_loss=` | week-over-week strikethrough on the metric lines |
| `last['gain_loss_narrative']`, `last['eot_recovery']`, `last['logic_changes']` | `previous_narratives=` dict | inline narrative diff |
| `last['successes_full']`, `last['red_flags_full']`, `last['stalled_tasks_full']`, `last['key_items_full']` | through `transition_items()` or `reconcile_items()` | per-item state transitions |
| `last['attachments']` | through `transition_attachments()` | file carry-forward + Procore preservation |
| `last['custom_paragraphs']` | `custom_paragraphs=` verbatim | closing paragraphs (no diff semantics) |
| `last['changes_report']['include']` | `include_changes_report=` default | changelog PDF toggle |
| `last['skip_procore']` | `skip_procore=` default | inherit master Procore-skip toggle |

## Reconciliation recipe

For list items (red_flags / successes / stalled_tasks / key_items):

```python
from carry_forward import reconcile_items
red_flags_new = reconcile_items(
    last['red_flags_full'],
    this_week_red_flag_texts,   # plain strings Claude wrote
    today_iso=today_iso,
)
```

For attachments:

```python
import glob, os
from carry_forward import transition_attachments
fresh = []
for ext in ('*.pdf', '*.xlsm', '*.xer'):
    fresh.extend(
        os.path.basename(p) for p in glob.glob(os.path.join(dated_folder, ext))
        if not os.path.basename(p).startswith('~$')  # skip Office lock files
    )
attachments_new = transition_attachments(
    last['attachments'], fresh, today_iso=today_iso,
)
```

## Pass into generator

```python
import generate_email_preview_html
generate_email_preview_html.generate_preview_html(
    output_path=this_week_preview_path,
    # ... all the usual kwargs ...
    red_flags=red_flags_new,
    successes=successes_new,
    stalled_tasks=stalled_new,
    key_items=key_items_new,
    attachments=attachments_new,
    custom_paragraphs=last['custom_paragraphs'],
    previous_days_behind=last['days_behind'],
    previous_gain_loss=last['gain_loss'],
    previous_narratives={
        'gain_loss_narrative': last['gain_loss_narrative'],
        'eot_recovery': last['eot_recovery'],
        'logic_changes': last['logic_changes'],
    },
    changed_narrative_fields=changed_field_set,   # see below
    skip_procore=last.get('skip_procore', False),
)
```

## Changed narrative fields

Diff each narrative against last week's value (trim + case-insensitive compare). If changed, add to `changed_narrative_fields` so the generator outlines it in green dashed (visual flag for the reviewer):

```python
changed_narrative_fields = set()
for field in ('gain_loss_narrative', 'eot_recovery', 'logic_changes'):
    if (this_week[field] or '').strip().lower() != (last[field] or '').strip().lower():
        changed_narrative_fields.add(field)
```

## On save — phantom diff handling

The parser already drops `<del>` content and unwraps `<ins>` content, so the markdown archive and the `.eml` body never carry diff markup. Nothing for you to do here — just trust the parser.
````

- [ ] **Step 2: Verify**

```bash
ls scheduling/skills/schedule-update/phases/_carry_forward.md
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_carry_forward.md
git commit -m "$(cat <<'EOF'
feat(schedule-update): add phases/_carry_forward.md shared chunk

Documents the parse-last-preview → transition → generate-this-week recipe
with inline function signatures. Eliminates Read of carry_forward.py in
the email and report flows.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Phase file — `phases/copy.md` (pre-meeting folder setup)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/copy.md`

This is a near-verbatim lift of the `## copy` section in the current SKILL.md (lines ~140–168). The agent must read the current SKILL.md once to extract the content, then write the new file with a self-contained header.

- [ ] **Step 1: Read the current `copy` section**

```bash
grep -n "## \`copy\`" scheduling/skills/schedule-update/SKILL.md
```

Note the start and end line. Read those lines from the file.

- [ ] **Step 2: Write `phases/copy.md`** with the content below (header + lifted section):

````markdown
# Phase: `copy` — Pre-Meeting Folder Setup

> Loaded by SKILL.md's router when the user invokes `/schedule-update copy`.

Creates a new dated folder for today's schedule update.

## Prerequisites

- `project-context.html` must exist in the Schedules root (created by `schedule-project-init`).
- Folder resolution rules: see SKILL.md.

## Step 1: Resolve root

Apply folder resolution. Identify the Schedules root.

## Step 2: Find most recent dated folder

List all `YYYY-MM-DD` subdirectories in the Schedules root, sort descending, take the most recent. This is the template folder.

If no dated folders exist, create the folder structure from scratch (ask the user what files/subfolders to include).

## Step 3: Create today's folder

Create `{root}/{YYYY-MM-DD}/` using today's date. Copy the **folder structure** (not file contents) from the most recent dated folder:

- Create matching subdirectories (`screenshots/`, `meeting/`, etc.)
- Do NOT copy schedule files, XER files, or PDFs — those are project deliverables
- Copy any batch scripts (`.bat`, `.ps1`) from the template folder — these are reusable tools

## Step 4: Report

List the created folder and its contents. Tell the user what's next:

> "Folder created at `{path}`. When you're ready to update the schedule, remind the team to send their Excel update file."
````

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/copy.md
git commit -m "feat(schedule-update): extract phases/copy.md from SKILL.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Phase file — `phases/screenshots.md` (SmartPM capture)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/screenshots.md`

This is a near-verbatim lift of the `## screenshots` section in current SKILL.md (lines ~170–286).

- [ ] **Step 1: Read the `screenshots` section** in the current SKILL.md.

- [ ] **Step 2: Write `phases/screenshots.md`**

The file should start with a router header and then include the full screenshots section (Step 0 Pre-Flight through Step 5 Report). Use this template:

```markdown
# Phase: `screenshots` — Capture SmartPM Graphs

> Loaded by SKILL.md's router when the user invokes `/schedule-update screenshots`.

Captures 17 screenshots from SmartPM v2: 1 Summary Report + 16 individual trend graphs. **Fully headless and auto-authenticated** — no manual login, no MCP, no visible browser.

<!-- Lifted from SKILL.md lines ~170–286, verbatim. Preserve all Step 0–5
     content including the 16-graph filename table, Step 3b tests block,
     and SmartPM processing warning. -->

## Step 0: Pre-Flight — credentials + Node setup
...
## Step 1: Read Project Context
...
## Step 2: Write Checklist
...
## Step 3: Capture via Node script
...
## Step 3b: Tests
...
## Step 4: Verify
...
## Step 5: Report
...
```

Replace the `<!-- ... -->` block with the actual content lifted from the source. Do not paraphrase — copy verbatim so behavior doesn't drift.

- [ ] **Step 3: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/screenshots.md
git add scheduling/skills/schedule-update/phases/screenshots.md
git commit -m "feat(schedule-update): extract phases/screenshots.md from SKILL.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Phase file — `phases/email.md` (Camron's email draft path)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/email.md`

Lifts the `## email` section from current SKILL.md (lines ~288–502). One material edit: references to "Carry forward from last week" and the attachment shape now point to `_carry_forward.md` and `_attachments.md` instead of inlining script reads.

- [ ] **Step 1: Read the `email` section** in current SKILL.md.

- [ ] **Step 2: Write `phases/email.md`** with this structure:

```markdown
# Phase: `email` — Generate Update Email Draft (Camron's path)

> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `_carry_forward.md` and `_attachments.md` loaded first.

Generates the Westland schedule update email from XER data, previous email, and meeting transcript.

## Step 0: Read Project Context & Previous Update
...

## Step 1: Check Inputs
...

## Step 2: Check Screenshots
...

## Step 3: Parse XER & Extract Metrics
...

## Step 4: Carry Forward from Previous Email

> See `_carry_forward.md` for the parse → transition → generate recipe.
> See `_attachments.md` for the attachment dict shape and the share_to_procore field.

## Step 5: Mine Meeting Transcript
...

## Step 6: Assemble Draft Email
...

## Step 7: Generate Editable HTML Preview

> See `_carry_forward.md` for the full last-week → this-week generation recipe
> including the new `skip_procore` carry-forward.

(Body of Step 7 explains the preview itself — what it renders, the per-item
cards, the new Procore checkboxes/master toggle, the user instructions on
how to edit and save.)

## Step 8: Save Archive Markdown
...

### Email changelog PDF attachment (sub-section)
...
```

Where `...` appears, copy verbatim from the source SKILL.md. The substitutions are:

- Replace the inline "Carry forward from last week" subsection (currently ~lines 370–410 of SKILL.md) with: **"See `_carry_forward.md`."** Move all the detailed parse/transition/generate prose to that shared file (done in Task 7) — don't duplicate.
- Replace any prose about the attachment dict shape with: **"See `_attachments.md`."**
- Keep all other steps (0–8) verbatim.
- In Step 7 "Tell the user" block, update the user-facing message to mention the new Procore controls:

> "Preview at `{path}`. Click into any list item to see its card. Each attachment now has TWO checkboxes — the ☐ on the left is 'Include in email' (existing), the **P** badge on the right is 'Share to Procore' (new, off by default for safety since the folder is public). Use the **⏭ Skip Procore this week** toggle above the attachments list to suppress the Procore upload entirely. When you're done: click **Save Edits**, save the download over this file, then tell me `done`."

- [ ] **Step 3: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/email.md
git add scheduling/skills/schedule-update/phases/email.md
git commit -m "feat(schedule-update): extract phases/email.md from SKILL.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Phase file — `phases/report.md` (colleague flow, with done-handler fan-out)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/report.md`

Lifts the `## report` section from current SKILL.md (lines ~504–591) with one critical edit: the "Wait For 'done', Then Draft" step (current Step 7) now fans out to both `.eml` creation AND Procore publish.

- [ ] **Step 1: Read the `report` section** in current SKILL.md.

- [ ] **Step 2: Write `phases/report.md`**:

```markdown
# Phase: `report` — Colleague Post-Meeting Flow (Steps 6–10)

> Loaded by SKILL.md's router when the user invokes `/schedule-update report`.
> Also requires `_carry_forward.md`, `_attachments.md`, `draft.md`, and `procore.md`.

End-to-end conversational flow that takes a colleague from "meeting is done" to "Outlook draft in Drafts folder + files in Procore." Covers steps 6–10 of the full pipeline.

## Step 1: Resolve Folder
... (lift verbatim)

## Step 2: Run Screenshots If Needed
... (lift verbatim)

## Step 3: Transcript Or Q&A?
... (lift verbatim — includes 3a and 3b sub-branches)

## Step 4: Carry Forward From Previous Email

> See `_carry_forward.md`.

## Step 5: Calculate Metrics From XER
... (lift verbatim)

## Step 6: Generate Editable HTML Preview

Run the shared preview generation step. See `_carry_forward.md` for the recipe and `_attachments.md` for the new Procore controls.

(Preserve the existing "Tell the colleague" block but extend it to mention the new Procore controls — same wording as Task 10's Step 7 update.)

(Preserve the existing JSON-paste regeneration sub-section.)

## Step 7: Wait For "done", Then Draft + Procore Publish

When the colleague says `done`:

1. Read the (now-edited) preview HTML via `parse_email_html.py:parse_preview_html(preview_path)`. The returned dict includes `attachments` (with `share_to_procore` per item) and the top-level `skip_procore` toggle.

2. **Write the `.eml`** by following `draft.md`. (Phase file already loaded per the command matrix.)

3. **Procore publish** (unless `parsed['skip_procore'] == True`) by following `procore.md`. (Also already loaded.)

4. **Write the archive markdown** `{dated_folder}/{YYYY-MM-DD}-update-email.md` from the parsed dict.

5. Report a unified summary:

   > "Done. `.eml` written to `{path}`. Procore: XER imported · Dated folder `{folder_id}` · {N} files uploaded · {M} skipped or failed. Open the `.eml` to review and send. (Or use `/schedule-update procore` to retry the Procore part if anything failed.)"

If the colleague set `Skip Procore this week`, the Procore line of the summary reads: `"Procore: skipped this week."`

If the HTML file looks unchanged (no edits detected) or fails to parse, surface the problem and ask whether to proceed with the unedited draft.
```

- [ ] **Step 3: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/report.md
git add scheduling/skills/schedule-update/phases/report.md
git commit -m "feat(schedule-update): extract phases/report.md with done-handler Procore fan-out

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Phase file — `phases/draft.md` (Outlook draft, with Procore fan-out)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/draft.md`

Lifts the `## draft` section from current SKILL.md (lines ~593–636) with one addition: a final step that triggers `procore.md` (unless `skip_procore` is set).

- [ ] **Step 1: Read the `draft` section** in current SKILL.md.

- [ ] **Step 2: Write `phases/draft.md`**:

```markdown
# Phase: `draft` — Create Outlook Draft + Procore Publish

> Loaded by SKILL.md's router when the user invokes `/schedule-update draft`.
> Also requires `_attachments.md` and `procore.md`.

Turns the approved email content into a draft the user opens, reviews, and sends from Outlook. Also fans out to the Procore Documents upload as a single user-visible step.

## Step 1: Locate Source File
... (lift verbatim from current SKILL.md draft step 1)

## Step 2: Generate the draft (default: `.eml` on disk)
... (lift verbatim — covers .eml writer and COM Outlook alternative)

## Step 3: Procore publish (fans out, fires unless skipped)

If `parsed['skip_procore'] == True`, log "Procore: skipped this week (per master toggle)." and proceed to Step 4.

Otherwise, follow `procore.md` to:
1. Import the XER to the Procore Schedule tool.
2. Create / reuse the dated `YYYY-MM-DD` subfolder under the configured documents folder.
3. Upload each attachment with `share_to_procore=True AND checked=True AND status != 'archived'`.
4. Verify each upload via folder listing; retry once on failure.

`procore.md` returns a per-operation result table. Include it in the summary.

## Step 4: Confirm

For the `.eml` path:

> "Draft written to `{eml_path}`. {procore_summary} Double-click the `.eml` to open in Outlook (classic or new), review, then Send."

Where `{procore_summary}` is one of:
- `"Procore: XER imported · folder {folder_id} · {N} uploaded · {M} skipped/failed. Retry with /schedule-update procore if needed."`
- `"Procore: skipped this week (per master toggle)."`
- `"Procore: not initialized — see `phases/procore.md` for first-time setup."`

For the COM path: same but mention Outlook Drafts instead of the `.eml`.
```

- [ ] **Step 3: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/draft.md
git add scheduling/skills/schedule-update/phases/draft.md
git commit -m "feat(schedule-update): extract phases/draft.md with Procore fan-out

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Phase file — `phases/procore.md` (NEW — Procore publish phase)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/procore.md`

This is the new phase. The agent must write this from scratch per Contract 7 and the spec's Approach section C.

- [ ] **Step 1: Write `phases/procore.md`**

Write the file with this exact structure:

````markdown
# Phase: `procore` — Publish XER + Attachments to Procore

> Loaded by SKILL.md's router when the user invokes `/schedule-update procore`, and bundled into `report.md` and `draft.md` as the final step of the weekly "done" handler.
> Also requires `_attachments.md`.

Publishes three artifacts to Procore in one step:

1. **XER → Schedule tool** (parsed into the live schedule).
2. **Dated `YYYY-MM-DD` folder → Documents tool** (created under the project's configured documents folder).
3. **Selected attachments → dated folder** (the `share_to_procore`-tagged subset, verified by listing, with one retry on failure).

All Procore work uses MCP tools called directly by Claude. There is no Python orchestrator. The bootstrap rule for `share_to_procore` defaults lives in `carry_forward.transition_attachments` — see `_attachments.md`.

## Skip conditions

- If `parsed['skip_procore'] == True`, **do not run this phase**. Print "Procore: skipped this week (per master toggle)." and return.
- If the user explicitly aborts during folder discovery, print "Procore: aborted by user." and return.

## Preflight 1 — Resolve `procore_project_id`

Load `project-context.html` via `parse_project_context_html.load_project_context(schedules_root)`. If `ctx['procore_project_id']` is non-empty, **skip to Preflight 2**.

Otherwise, call the MCP tool to look up the project by name + number:

```
mcp__a695fe63-..-bbf8965a4c43__find_project(
    name=ctx['project_name'],
    number=ctx['job_number'],
)
```

(Replace `..` with the full server prefix at runtime.)

Decision logic:

- **Single result whose `project_number` exactly matches `ctx['job_number']`** → silent write-back. Set `ctx['procore_project_id'] = result['id']` and immediately persist via:
  ```python
  import generate_project_context_html
  generate_project_context_html.generate_project_context_html(html_path, ctx)
  ```
- **Multiple results OR no exact job-number match** → call `AskUserQuestion`:
  - Question: "Multiple Procore projects matched. Which is the right one?"
  - Header: "Procore project"
  - Options: one per candidate, label `"{name} (#{number})"`, description `"ID {id} — {address or 'address unknown'}"`
  - After user selection, set `ctx['procore_project_id']`, write back.
- **Zero results** → call `AskUserQuestion`:
  - Question: "I couldn't find the Procore project for this job. Please enter the Procore project ID manually (find it in the URL when you open the project in Procore)."
  - Header: "Procore ID"
  - Options: "Provide ID manually" and "Cancel Procore publish"
  - On manual, follow up with a free-text prompt (`AskUserQuestion` "Other" path or a follow-up question).

## Preflight 2 — Resolve `procore_documents_folder_id`

If `ctx['procore_documents_folder_id']` is non-empty, **skip to Operation 1**.

Otherwise, list the project's top-level Documents folders:

```
mcp__a695fe63-..__procore_get(
    path=f"/rest/v1.0/projects/{ctx['procore_project_id']}/folders",
    params={'filters[parent_id]': 'null'},
)
```

**Filter out the `Schedules` folder.** This is owned by the Procore v1 Schedule API. Admins can see it but cannot edit it; uploads into it will fail or be hidden. It is NEVER a valid choice.

```python
candidates = [f for f in folders if f.get('name') != 'Schedules']
```

If `candidates` is non-empty: call `AskUserQuestion`:
- Question: "Which top-level Procore Documents folder should the weekly schedule updates go into? (The dated YYYY-MM-DD subfolder will be created inside.)"
- Header: "Procore folder"
- Options: one per candidate folder (label = folder name, description = `"ID {id}"`), PLUS a final option labeled "Create new folder 'Schedule Updates'" with description "I'll create a fresh top-level folder called Schedule Updates."

If `candidates` is empty: skip the question and offer only the "Create new" path.

On user selection:
- **Existing folder picked** → set `ctx['procore_documents_folder_id'] = chosen_folder['id']`.
- **Create new** → call:
  ```
  mcp__a695fe63-..__create_document_folder(
      projectId=ctx['procore_project_id'],
      name='Schedule Updates',
      confirm=True,
  )
  ```
  Set `ctx['procore_documents_folder_id'] = response['id']`.
- **User cancels** → print "Procore: aborted by user." and return.

Persist via `generate_project_context_html` immediately so the next run skips this step.

## Operation 1 — XER import to Schedule tool

Find the latest `.xer` in the dated folder (highest `-vN` suffix; if none, the unversioned file):

```python
import glob, os, re
xer_files = glob.glob(os.path.join(dated_folder, '*.xer'))
xer_files = [x for x in xer_files if not os.path.basename(x).startswith('~$')]
def _version(path):
    m = re.search(r'-v(\d+)\.xer$', path, re.IGNORECASE)
    return int(m.group(1)) if m else 0
latest_xer = max(xer_files, key=_version) if xer_files else None
```

If no XER, log "XER: no .xer in dated folder, skipping." and continue to Operation 2.

Otherwise call:

```
mcp__a695fe63-..__import_xer_schedule(
    projectId=ctx['procore_project_id'],
    filePath=latest_xer,
    confirm=True,
)
```

Response handling:

- **`schedule_tool_not_initialized`** → log "XER: Schedule tool needs first-time upload via Procore web UI. Skipping XER for this run." Continue to Operation 2.
- **Successful response** → response contains a `curl_command` and a `jobId`. Run the curl via Bash:
  ```bash
  bash -c "{curl_command}"
  ```
  Then poll status every 5 seconds, up to 60 seconds total:
  ```
  mcp__a695fe63-..__get_schedule_import_status(
      projectId=ctx['procore_project_id'],
      jobId=response['jobId'],
  )
  ```
  Until `status == 'completed'` (success), `status == 'failed'` (error), or 60s elapsed (timeout). Record the outcome.

## Operation 2 — Create dated folder

```
today_iso = '2026-05-18'  # or whatever today is
mcp__a695fe63-..__create_document_folder(
    projectId=ctx['procore_project_id'],
    name=today_iso,
    parentId=int(ctx['procore_documents_folder_id']),
    confirm=True,
)
```

- **Success** → capture `dated_folder_id = response['id']`.
- **`name_exists` / 422** (idempotent re-run on the same day) → list parent contents and find the folder with today's name:
  ```
  listing = mcp__a695fe63-..__procore_get(
      path=f"/rest/v1.0/folders/{ctx['procore_documents_folder_id']}/contents"
  )
  dated_folder_id = next(
      f['id'] for f in listing.get('folders', []) if f.get('name') == today_iso
  )
  ```

## Operation 3 — Upload selected attachments

Filter the parsed attachments:

```python
candidates = [
    a for a in parsed['attachments']
    if a.get('share_to_procore') and a.get('checked')
       and a.get('status') != 'archived'
]
```

Resolve each filename to an absolute path the same way the parser does — relative paths join against the dated folder:

```python
import os
def resolve(filename, dated_folder):
    return filename if os.path.isabs(filename) else os.path.normpath(
        os.path.join(dated_folder, filename)
    )
```

For each candidate, run the verify-and-retry loop:

```
for a in candidates:
    upload_path = resolve(a['filename'], dated_folder)
    upload_basename = os.path.basename(upload_path)

    # Pre-check: already uploaded? (idempotent retry on same day)
    listing = procore_get(f"/rest/v1.0/folders/{dated_folder_id}/contents")
    if upload_basename in [f['name'] for f in listing.get('files', [])]:
        results.append((upload_basename, 'already_uploaded'))
        continue

    for attempt in (1, 2):
        try:
            response = create_document(
                projectId=ctx['procore_project_id'],
                filePath=upload_path,
                folderId=dated_folder_id,
                confirm=True,
            )
            # Execute the returned curl via Bash. Capture stdout/stderr.
            bash(response['curl_command'])

            # Verify by listing.
            listing = procore_get(
                f"/rest/v1.0/folders/{dated_folder_id}/contents"
            )
            if upload_basename in [f['name'] for f in listing.get('files', [])]:
                results.append((upload_basename, 'ok'))
                break
            raise RuntimeError("upload did not appear in folder listing")
        except Exception as e:
            if attempt == 2:
                results.append((upload_basename, f'failed: {e}'))
            else:
                time.sleep(5)
```

(Pseudocode — when actually running, Claude calls each MCP tool, executes the curl via the Bash tool, and uses TaskCreate / printed text to track per-file outcomes.)

## Step Final — Summary

Print a table:

```
Operation        Status   Detail
---------------  -------  -----------------------------------------
Project ID       ok       resolved from find_project (id 2646569)
Documents folder ok       reused existing 'Schedule Updates' (id 4592384)
XER import       ok       Schedule tool import completed in 38s
Dated folder     ok       created '2026-05-18' (id 9182374)
Upload: View 01.pdf       ok
Upload: Update Request.xlsm  ok
Upload: 3-Week Look-Ahead.pdf  failed: curl exit 28 (timeout)
```

If any line is `failed:` or `skipped:`, end with:

> "Retry with `/schedule-update procore` once resolved."

## What this phase MUST NOT do

- Read `parse_email_html.py`, `parse_project_context_html.py`, `generate_*.py`, or any preview/project-context HTML directly. Use the documented function signatures only.
- Re-prompt for IDs already in `project-context.html`. The whole point of the write-back is that subsequent runs are silent.
- Upload `share_to_procore: false` attachments. The folder is public; explicit opt-in is the safety net.
- Upload the SmartPM Summary screenshot or any other file outside the user's curated `share_to_procore` set.
````

- [ ] **Step 2: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/procore.md
git add scheduling/skills/schedule-update/phases/procore.md
git commit -m "$(cat <<'EOF'
feat(schedule-update): add phases/procore.md (new phase)

Claude-driven Procore publish: XER import → dated folder create →
attachment upload with verify-and-retry. Uses Procore MCP tools and
AskUserQuestion for disambiguation. Writes back resolved IDs to
project-context.html so subsequent runs are silent.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Phase file — `phases/status.md` (phase detection)

**Files:**
- Create: `scheduling/skills/schedule-update/phases/status.md`

Lifts the `## status` section (current SKILL.md lines ~640–675) and extends the detection table to include Procore publish state.

- [ ] **Step 1: Read the `status` section** in current SKILL.md.

- [ ] **Step 2: Write `phases/status.md`**:

```markdown
# Phase: `status` — Pipeline Status

> Loaded by SKILL.md's router when the user invokes `/schedule-update status` or no arg.

Shows where the project is in the weekly update pipeline based on what files exist.

## Detection Logic

| Check | Indicates |
|-------|-----------|
| Today's dated folder exists | Step 1 (copy) done |
| `{dated_folder}/*.xer` exists | Export done (step 5) |
| `{dated_folder}/meeting/` has files | Transcript copied (step 7) |
| `{dated_folder}/screenshots/` has all required PNGs | Screenshots done (step 10) |
| `{dated_folder}/YYYY-MM-DD-email-preview.html` exists | Email preview generated (step 11) |
| `{dated_folder}/YYYY-MM-DD-update-email.md` exists | Email archived after review |
| `{dated_folder}/YYYY-MM-DD-update-email.eml` exists | `.eml` draft created (step 13, default path) |
| Outlook draft exists in Drafts folder | COM draft created (step 13, alternative path — only detectable while Outlook is open) |
| **Procore publish ran today** | check via `procore_get` on the dated folder under `procore_documents_folder_id`; presence of today's `YYYY-MM-DD` subfolder = ran |

Report each phase as DONE / PENDING / NOT STARTED, and name the recommended next step.

### No-arg routing

When invoked without a command, run detection above, then:

- If no dated folder for today → "Run `/schedule-update copy` to set up today's folder."
- If folder exists but no XER → "Export the schedule and drop the XER in `{path}`."
- If XER exists but no screenshots → "Run `/schedule-update screenshots`."
- If screenshots exist but no email → "Run `/schedule-update email` or `/schedule-update report`."
- If preview exists but no `.eml` → "Run `/schedule-update draft`."
- If `.eml` exists but Procore folder NOT detected → "Run `/schedule-update procore` to publish."
- If everything detected → "All steps done. `.eml` at `{path}`."
```

- [ ] **Step 3: Verify and commit**

```bash
ls scheduling/skills/schedule-update/phases/status.md
git add scheduling/skills/schedule-update/phases/status.md
git commit -m "feat(schedule-update): extract phases/status.md, add Procore detection

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Rewrite SKILL.md as router

**Files:**
- Modify: `scheduling/skills/schedule-update/SKILL.md`

The new SKILL.md is ~150 lines. It contains: front matter, the two absolute-rule banners (verbatim), folder resolution, project-context.html dict shape (with the new `procore_documents_folder_id` field), UNC pitfalls, the command matrix (Contract 8), and the full pipeline reference table.

- [ ] **Step 1: Write the new SKILL.md**

Full replacement content:

````markdown
---
name: schedule-update
description: >
  Full weekly schedule update pipeline for Westland Construction. Handles all post-meeting
  steps: folder setup, SmartPM screenshot capture, email draft generation, editable HTML
  preview, Outlook draft, and Procore publish (XER + Documents upload). Progressively
  disclosed -- routes by command arg or detects current phase from file system. Use for:
  "schedule update", "weekly update", "update email", "weekly schedule report email",
  "weekly report email", "schedule report email", "prep the update email", "help me
  with the email", "take screenshots", "smartpm screenshots", "schedule email", "draft
  the email", "copy schedule folder", "update status", "where are we in the update",
  "generate email", "create draft", "procore upload", or any schedule update workflow.
  Two main entry points: `copy` for pre-meeting folder setup, and `report` for the
  colleague-friendly post-meeting flow (steps 6-10 as a guided conversation with an
  editable HTML email preview, ending with .eml + Procore publish).
---

# Schedule Update Pipeline — Router

## ⚠️ Before invoking any sub-command — read the right phase files

Each sub-command names the phase files you MUST read in full before acting. **Do not Read the `.py` or HTML scripts those phase files reference** — every phase file inlines the signatures and dict shapes you need. Reading the underlying script is a sign you skipped the phase file.

### Command Matrix

| Invocation | Phase files to read first | Purpose |
|---|---|---|
| `/schedule-update copy` | `phases/copy.md` | Pre-meeting folder setup |
| `/schedule-update screenshots` | `phases/screenshots.md` | SmartPM capture |
| `/schedule-update email` | `phases/email.md`, `phases/_carry_forward.md`, `phases/_attachments.md` | Camron's email draft path |
| `/schedule-update report` | `phases/report.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/draft.md`, `phases/procore.md` | Colleague flow, steps 6–10 |
| `/schedule-update draft` | `phases/draft.md`, `phases/_attachments.md`, `phases/procore.md` | `.eml` / COM draft + Procore publish |
| `/schedule-update procore` | `phases/procore.md`, `phases/_attachments.md` | Retry / standalone Procore publish |
| `/schedule-update status` | `phases/status.md` | Phase detection |
| `/schedule-update` (no arg) | `phases/status.md` | Auto-detect, route to recommended step |
| `/write-weekly-schedule-email` | `commands/write-weekly-schedule-email.md` (thin shell) → same as `report` | Cowork drop-in |

Read **every file in the column** for your invocation, in full, before taking any action.

---

## ⚠️ Absolute rule — XER files are immutable

**Every `.xer` in dated Schedules folders is an immutable project record.** Applies to every phase below:

- **READ** any `.xer` freely.
- **MODIFY** by writing a **new versioned file** alongside the existing one, incrementing the suffix each time (`...xer` → `...-v2.xer` → `...-v3.xer`).
- **NEVER** edit in place (Edit / MultiEdit / overwriting Write).
- **NEVER** delete.

Enforced at the tool layer by the `westland` plugin's PreToolUse hook (`westland/hooks/westland_share_guard.py`, matcher: `Edit|Write|MultiEdit|NotebookEdit|Bash`), which blocks in-place edits, overwrites of existing `.xer` files, and Bash delete commands (`rm`, `del`, `Remove-Item`, `find -delete`) targeting `.xer` paths. The `westland` plugin is a required organizational dependency — if the hook isn't firing, the `westland` plugin isn't loaded.

---

## ⚠️ Absolute rule — HTML artifacts go through their parse/generate scripts

**Every editable HTML artifact in this pipeline is read via its parser and written via its generator.** Applies to every phase below:

- **READ** via the parser. Never `Read` / `Grep` / `cat` the HTML directly.
- **WRITE** via the generator. Never `Edit` / `Write` / `MultiEdit` / `sed` / hand-typed HTML patches.
- Even one-line changes (a checkbox flip, an attachment add, a recipient swap) round-trip through **parse → mutate dict → generate**.

| Artifact | Lives at | Read with | Write with |
|----------|----------|-----------|------------|
| `project-context.html` | Schedules root | `parse_project_context_html.parse_project_context_html(path)` | `generate_project_context_html.generate_project_context_html(path, ctx)` |
| `{YYYY-MM-DD}-email-preview.html` | dated folder | `parse_email_html.parse_preview_html(path)` | `generate_email_preview_html.generate_email_preview_html(...)` |

**Why:** the email preview is 100–160 KB and carries rich state. Reading it directly often exceeds 30K tokens; editing by hand silently corrupts the `contenteditable` state machine. `project-context.html` is ~47 KB with an embedded base64 logo that has historically corrupted mid-payload during direct tool I/O (W1177 Lubumbashi, 2026-05-07). Keep all HTML I/O inside the script pair.

**Cowork note:** when the Schedules / dated folder lives on a non-`C:\` drive (e.g. `\\orem-fs\Common\Westland Project Files` mounted as `G:\`), the bash sandbox may not see it. The discipline still holds. Run the generator with `output_path` pointing at the real destination if reachable; otherwise hand the invocation to a local Claude Code session — never round-trip the HTML through `Write` to "deliver" it.

---

## Shared Setup

### Common pitfalls on UNC shares

Every Westland project lives on `\\orem-fs\Common\Westland Project Files\...` (mapped to `G:\` on most machines). A few traps:

- **Opening a file on the share from a shell.** `start "" "\\orem-fs\..."` from `cmd` errors with "UNC paths are not supported." Use PowerShell `Invoke-Item "\\orem-fs\..."` or shell out to `explorer.exe "\\orem-fs\..."` from Bash.
- **`file://` URLs for local files.** Prefer `pathlib.Path(abs).as_uri()` in Python and `pathToFileURL(abs).href` in Node. Manual `'file:///' + path.replace('\\','/')` mangles UNC roots.
- **Cowork sandbox + non-`C:\` drives.** Cowork's bash sandbox doesn't see `G:\` or UNC paths. Run the underlying script in a local Claude Code session, or stage files in `%TEMP%` and copy back.

### Folder Resolution

All phases use this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** (`../`)
2. If CWD basename is `Schedules` → root is CWD
3. If CWD contains a `Schedules/` child directory → root is that child
4. Otherwise → ask the user for the Schedules folder path

The grandparent of the Schedules root should match `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`).

### project-context.html — dict shape

Lives in the **root Schedules folder**. Created and maintained by the `schedule-project-init` skill. Read via:

```python
from parse_project_context_html import load_project_context
ctx, html_path = load_project_context(schedules_root)
```

Returns `(None, None)` if the file doesn't exist — in that case, stop and tell the user to run `schedule-project-init`.

```python
{
  'project_name': str,
  'job_number': str,
  'contractual_completion': str,
  'smartpm_url': str, 'smartpm_trends_url': str, 'smartpm_changelog_url': str,
  'smartpm_project_name': str,
  'signer_name': str, 'signer_title': str, 'signer_mobile': str,
  'procore_company_id': str,            # locked in UI; always Westland '11093'
  'procore_project_id': str,            # auto-resolved on first Procore run
  'procore_documents_folder_id': str,   # auto-resolved on first Procore run
  'graph_screenshots': list[str],
  'to_recipients': list[{'name': str, 'email': str}],
  'cc_recipients': list[{'name': str, 'email': str}],
  'to_recipients_str': str,   # legacy "Name <email>; …" form
  'cc_recipients_str': str,
  'project_log': list[{'date': 'YYYY-MM-DD', 'body': str}],
}
```

Every phase reads `project-context.html` first. If it is missing, stop with:
> "No project-context.html found in the Schedules root. Run the `schedule-project-init` skill first."

If `procore_project_id` or `procore_documents_folder_id` is empty, the `procore` phase will resolve them on first run and write them back via the generator. No manual setup required.

### Weekly email file

Each dated folder gets a `YYYY-MM-DD-update-email.md` with two sections:

1. **Update Email** — the email content (successes, red flags, key items, etc.)
2. **Project Log** — cumulative delay notes for claims and delay analysis

---

## Full Pipeline Reference

| # | Step | Owner | Command |
|---|------|-------|---------|
| 1 | Copy schedule folder for today's date | Agent | `copy` |
| 2 | Email reminder to get Excel update file | Human | — |
| 3 | Update schedule using Excel file | Human | — |
| 4 | Make corrections, discussion, complete update | Human | (in meeting) |
| 5 | Export schedule files | Human | — |
| 6 | Upload XER to SmartPM | Human | — |
| 7 | Copy meeting transcript to meeting folder | Human | — |
| 8 | Export PDF attachments from schedule software | Human | — |
| 9 | Create next week's Excel files | Human | — |
| 10 | Capture SmartPM graphs for email | Agent | `screenshots` |
| 11 | Generate update email draft | Agent | `email` |
| 12 | Review email draft | Human | — |
| 13a | Create Outlook draft (`.eml`) | Agent | `draft` |
| 13b | Publish XER + attachments to Procore | Agent | `procore` (auto-fanned-out by `draft`) |
| 14 | Send email | Human | — |

Colleague-friendly shortcut: `report` covers rows 10–13b in a single guided conversation.
````

- [ ] **Step 2: Commit**

```bash
git add scheduling/skills/schedule-update/SKILL.md
git commit -m "$(cat <<'EOF'
refactor(schedule-update): rewrite SKILL.md as router

SKILL.md becomes a thin router with command matrix that names which phase
files each sub-command must read. Forces the model to load focused phase
files instead of guessing from a 726-line monolith.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Rewrite `commands/write-weekly-schedule-email.md` as thin shell

**Files:**
- Modify: `scheduling/skills/schedule-update/commands/write-weekly-schedule-email.md`

This cowork drop-in entry point currently includes a lot of report-flow content. With the phase split, it should just point at the same phase files the `report` command uses.

- [ ] **Step 1: Read the current file**

```bash
cat scheduling/skills/schedule-update/commands/write-weekly-schedule-email.md
```

(Reading the existing file to preserve any cowork-specific notes about starting-folder assumptions.)

- [ ] **Step 2: Replace with thin shell**

Write the new content:

````markdown
# Write Weekly Schedule Email (Cowork drop-in)

> Bundled launcher for cowork sessions. Lands in a dated `YYYY-MM-DD` folder where steps 1–5 (folder copy, schedule update, export) have already been done by a human, then runs the `report` flow for steps 6–10.

## How this differs from `/schedule-update report`

Just one thing: this entry point assumes the CWD is already the dated folder (or will resolve to one immediately). Pre-meeting setup is out of scope.

## What to do

Read these phase files in full **before** taking any action — same set as `/schedule-update report`:

1. `phases/report.md`
2. `phases/_carry_forward.md`
3. `phases/_attachments.md`
4. `phases/draft.md`
5. `phases/procore.md`

Then execute the `report` flow as documented in `phases/report.md`, starting from Step 1 (Resolve Folder). Folder resolution will default to CWD/parent — no human pre-prompt needed.

## What NOT to do

- Do not `Read` the underlying Python scripts. Phase files inline every signature you need.
- Do not skip the Procore publish unless the user has the **⏭ Skip Procore this week** toggle ticked in the preview.
- Do not re-prompt for Procore project ID or documents folder ID — `procore.md`'s preflight handles auto-resolution and write-back to `project-context.html`.

## Launcher (for reference)

The `Write Weekly Schedule Email.bat` at the Schedules root invokes Claude Code in the dated folder and pastes `/write-weekly-schedule-email`. Phase files load automatically per the matrix above.
````

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/commands/write-weekly-schedule-email.md
git commit -m "$(cat <<'EOF'
refactor(schedule-update): write-weekly-schedule-email becomes thin shell

Points at the same phase files /schedule-update report loads. Cowork
drop-in stays a one-line invocation; the actual workflow lives in
phases/report.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Wave 2 — Sequential Integration + Release

Wait until all 16 Wave 1 subagents complete and are reviewed. Then run these in order in a single session.

### Task 17: Verify cross-task integration

**Files:**
- (Run-only — no edits unless an issue is found)

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest scheduling/skills/schedule-update/tests/ scheduling/skills/schedule-project-init/tests/ -v
```

Expected: all PASS.

- [ ] **Step 2: Manual round-trip with Procore fields**

Run this one-liner to confirm parser/generator/carry-forward compose correctly:

```bash
python -c "
import sys, pathlib, tempfile, json
_REFS_SU = pathlib.Path('scheduling/skills/schedule-update/references').resolve()
_REFS_PI = pathlib.Path('scheduling/skills/schedule-project-init/references').resolve()
sys.path.insert(0, str(_REFS_SU))
sys.path.insert(0, str(_REFS_PI))
import generate_email_preview_html as gep
import parse_email_html as pem
import carry_forward as cf
import generate_project_context_html as gpc
import parse_project_context_html as ppc

# 1) Preview round-trip with new fields
with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w') as f:
    p1 = f.name
gep.generate_preview_html(
    p1, date_label='2026-05-18',
    project_info={'project_name': 'Test', 'job_number': 'W9999',
                  'contractual_completion': 'Jun 2027',
                  'projected_completion': 'Jul 2027'},
    days_behind=0, gain_loss=0,
    skip_procore=False,
    attachments=[
        {'filename': 'Update Request.xlsm', 'checked': True,
         'status': 'active', 'share_to_procore': True},
        {'filename': 'SmartPM Summary.pdf', 'checked': True,
         'status': 'active', 'share_to_procore': False},
    ],
)
parsed = pem.parse_preview_html(p1)
assert parsed['skip_procore'] is False
assert parsed['attachments'][0]['share_to_procore'] is True
assert parsed['attachments'][1]['share_to_procore'] is False
print('preview round-trip: OK')

# 2) project-context round-trip
with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w') as f:
    p2 = f.name
ctx = {'project_name': 'Test', 'job_number': 'W9999',
       'procore_project_id': '2646569',
       'procore_documents_folder_id': '4592384',
       'procore_company_id': '11093',
       'graph_screenshots': [], 'project_log': [],
       'to_recipients': [], 'cc_recipients': []}
gpc.generate_project_context_html(p2, ctx, today_iso='2026-05-18')
re_parsed = ppc.parse_project_context_html(p2)
assert re_parsed['procore_documents_folder_id'] == '4592384'
print('project-context round-trip: OK')

# 3) carry-forward bootstrap
result = cf.transition_attachments(
    [], ['Schedule View.pdf', 'Update Request.xlsm', 'Internal.pdf'],
    today_iso='2026-05-18',
)
share = {r['filename']: r['share_to_procore'] for r in result}
assert share['Schedule View.pdf'] is True
assert share['Update Request.xlsm'] is True
assert share['Internal.pdf'] is False
print('carry-forward bootstrap: OK')
print('All integration checks pass.')
"
```

Expected output:
```
preview round-trip: OK
project-context round-trip: OK
carry-forward bootstrap: OK
All integration checks pass.
```

If any assertion fails, **do not proceed**. Open a sub-task to fix the failing surface, re-run, then continue.

- [ ] **Step 3: Verify phase files are all present and the router matrix matches**

```bash
ls scheduling/skills/schedule-update/phases/
```

Expected: `_attachments.md`, `_carry_forward.md`, `copy.md`, `draft.md`, `email.md`, `procore.md`, `report.md`, `screenshots.md`, `status.md`.

```bash
grep -c "phases/" scheduling/skills/schedule-update/SKILL.md
```

Expected: at least 15 references (one per row in the command matrix, multiple per row).

- [ ] **Step 4: Commit (if any fixes were needed; otherwise skip)**

If Step 2 or Step 3 surfaced issues, fix them inline, then:

```bash
git add -A
git commit -m "fix(schedule-update): integration fixes after Wave 1"
```

---

### Task 18: Version bumps

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

Per CLAUDE.md release convention, both must move together to the same new version.

- [ ] **Step 1: Bump `scheduling/.claude-plugin/plugin.json`**

```bash
cat scheduling/.claude-plugin/plugin.json
```

Edit the `"version"` field from `"5.1.5"` → `"5.2.0"`.

- [ ] **Step 2: Bump `.claude-plugin/marketplace.json` scheduling entry**

Open `.claude-plugin/marketplace.json` and find the `scheduling` plugin entry. Change `"version": "5.1.5"` → `"version": "5.2.0"` on that entry only.

- [ ] **Step 3: Verify both match**

```bash
python -c "
import json
p = json.load(open('scheduling/.claude-plugin/plugin.json'))
m = json.load(open('.claude-plugin/marketplace.json'))
ms = next(e for e in m['plugins'] if e['name'] == 'scheduling')
print('plugin.json:', p['version'])
print('marketplace.json scheduling:', ms['version'])
assert p['version'] == ms['version'], 'VERSION MISMATCH'
print('versions match:', p['version'])
"
```

Expected:
```
plugin.json: 5.2.0
marketplace.json scheduling: 5.2.0
versions match: 5.2.0
```

- [ ] **Step 4: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "$(cat <<'EOF'
chore(scheduling): bump to v5.2.0 for Procore integration + skill restructure

New functionality (Procore publish phase, per-attachment share-to-procore
toggle, master skip-procore toggle, procore_documents_folder_id in
project-context). No breaking changes to the existing CLI surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: Build the plugin zip

**Files:**
- Generated: `src/scheduling.zip` (gitignored, not committed)

- [ ] **Step 1: Run the builder**

```bash
python build.py scheduling
```

Expected output: success, with the zip written to `src/scheduling.zip`.

- [ ] **Step 2: Sanity-check the zip contents**

```bash
python -c "
import zipfile, sys
z = zipfile.ZipFile('src/scheduling.zip')
names = z.namelist()
required = [
    'scheduling/skills/schedule-update/SKILL.md',
    'scheduling/skills/schedule-update/phases/_attachments.md',
    'scheduling/skills/schedule-update/phases/_carry_forward.md',
    'scheduling/skills/schedule-update/phases/copy.md',
    'scheduling/skills/schedule-update/phases/screenshots.md',
    'scheduling/skills/schedule-update/phases/email.md',
    'scheduling/skills/schedule-update/phases/report.md',
    'scheduling/skills/schedule-update/phases/draft.md',
    'scheduling/skills/schedule-update/phases/procore.md',
    'scheduling/skills/schedule-update/phases/status.md',
    'scheduling/skills/schedule-update/references/parse_email_html.py',
    'scheduling/skills/schedule-update/references/generate_email_preview_html.py',
    'scheduling/skills/schedule-update/references/carry_forward.py',
    'scheduling/skills/schedule-project-init/references/parse_project_context_html.py',
    'scheduling/skills/schedule-project-init/references/generate_project_context_html.py',
]
missing = [r for r in required if r not in names]
if missing:
    for m in missing: print('MISSING:', m)
    sys.exit(1)
print('All required files present in src/scheduling.zip')
"
```

Expected: `All required files present in src/scheduling.zip`.

- [ ] **Step 3: Verify build is gitignored (no commit needed)**

```bash
git status
```

The `src/` directory should not appear in modified/untracked. If it does, check `.gitignore` includes `src/`.

---

## Self-Review

This section is run by the planner (or the orchestrating agent) after writing the plan, NOT executed by Wave 1/2 subagents. Confirm before dispatching Wave 1:

1. **Spec coverage check.** Every numbered surface in the spec's "Components Touched" table maps to a Wave 1 task:
   - `SKILL.md` → Task 15
   - `commands/write-weekly-schedule-email.md` → Task 16
   - `phases/copy.md` → Task 8
   - `phases/screenshots.md` → Task 9
   - `phases/email.md` → Task 10
   - `phases/report.md` → Task 11
   - `phases/draft.md` → Task 12
   - `phases/procore.md` → Task 13
   - `phases/status.md` → Task 14
   - `phases/_carry_forward.md` → Task 7
   - `phases/_attachments.md` → Task 6
   - `references/generate_email_preview_html.py` → Task 4
   - `references/parse_email_html.py` → Task 3
   - `references/carry_forward.py` → Task 5
   - `references/parse_project_context_html.py` → Task 1
   - `references/generate_project_context_html.py` → Task 2
   - `scheduling/.claude-plugin/plugin.json` → Task 18
   - `.claude-plugin/marketplace.json` → Task 18

   ✓ All spec surfaces covered.

2. **Spec testing coverage:**
   - Unit: parse_email_html roundtrip with new fields → Task 3 + Task 4.
   - Unit: carry_forward share_to_procore preserve/bootstrap → Task 5.
   - Unit: parse_project_context_html `procore_documents_folder_id` → Tasks 1 + 2.
   - Unit: generate_email_preview_html new card render + master toggle → Task 4.
   - Manual smoke tests (happy path, retry) — left to the user post-build; not auto-executed.

   ✓ All listed testing coverage represented.

3. **Type / signature consistency:** every task uses `share_to_procore`, `skip_procore`, `procore_documents_folder_id`, `attach-procore-toggle`, `data-procore-checked` exactly as defined in the Shared Interface Contract.

   ✓ Names locked.

4. **Parallel-safety check:** every Wave 1 task lists its file boundaries (Files: Create / Modify). The only files modified by more than one task are the test files (`test_email_preview_html.py` — Tasks 3 and 4 both append). To avoid merge conflicts:
   - Task 3 appends `ProcoreFieldsParseTests` class.
   - Task 4 appends `ProcoreFieldsGenerateTests` class.
   - Both append at the end of the file before `if __name__ == '__main__'`. As long as the two subagents both APPEND (not insert mid-file), trivial merge resolution: place the two class blocks back-to-back.

   ✓ Safe to dispatch in parallel.

5. **Placeholder scan:** no TBD/TODO/"add error handling" / "similar to Task N" placeholders. Every step has either a verbatim code block or a precise lift-and-edit instruction (with an explicit pointer to the source line range in the current SKILL.md for the lift tasks).

   ✓ Clean.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-schedule-update-procore-integration.md`.

**Subagent-driven execution (recommended given the user's request):**

- **Wave 1:** Dispatch 16 subagents in parallel, one per Wave 1 task. Each gets a copy of this plan plus the contract section. Use one fresh subagent per task — they don't need to share context.
- **Review gate:** After Wave 1, review each subagent's commit(s) — verify the test suite passes from a clean checkout, the new phase files exist, and the SKILL.md router matrix references resolve.
- **Wave 2:** Run sequentially in a single session — Tasks 17, 18, 19. Smoke tests against a real Westland project happen post-build, manually.
