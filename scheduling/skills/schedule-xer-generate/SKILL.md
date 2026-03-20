---
name: schedule-xer-generate
description: >
  Generate new Primavera P6 XER schedule files from scratch — typically by analyzing similar project
  schedules and a proposal/scope document to create a proposal or baseline schedule. Use this skill
  whenever the user wants to CREATE a new schedule, build a proposal schedule, generate an XER from
  a scope of work, assemble a schedule from similar projects, or produce a starting-point schedule
  for P6 import. Also trigger when the user says "create a schedule", "build me a schedule",
  "generate an XER", "proposal schedule", "starting point schedule", or asks to combine elements
  from multiple existing schedules into a new one. If the user just wants to READ or MODIFY an
  existing XER file, use the schedule-xer-read-modify skill instead.
---

# Generating Primavera P6 XER Schedule Files

This skill produces new, P6-importable XER files. The typical use case: given similar project schedules (as XER files) and a scope description, produce a proposal or baseline schedule as a starting point.

## Before You Start: Read the Reference Script

This skill folder contains `build_from_raw_template.py` — a proven, working script that generates a 96-task elementary school schedule and imports cleanly into P6. **Read it before writing any code.** It demonstrates every pattern in this doc and is the single best reference for how a successful generation script should look.

The script scored A- (91.4) on quality backcheck, so it's also a good structural template for WBS hierarchy, activity naming, and relationship logic patterns.

## How XER Generation Works

P6 is extremely picky about XER file structure. Subtle differences — a missing trailing tab, wrong line endings, reordered fields — cause P6 to silently reject the file with no error message (just an empty import grid). Because of this, the only reliable approach is **template-based generation**: start from a real P6 export and surgically replace the data rows while preserving the file's structural skeleton.

The workflow has two phases: **planning** (what to put in the schedule) and **implementation** (writing the XER file).

---

## Phase 1: Planning the Schedule

### Gather Inputs

You need two types of input:

**Reference XER files** — Real P6 exports from similar projects. Use the schedule-xer-read-modify skill to parse them and understand WBS patterns, activity sequences, duration ranges, relationship logic, and calendar configurations.

**Scope definition** — A proposal, SOW, or project description. Extract the project name, key dates, major work phases, known constraints (milestone dates, access dates, weather windows), and size/complexity indicators.

### Analyze Reference Schedules

Look across the reference schedules for:

- **Common WBS structure** — most construction schedules share a similar top-level pattern (Preconstruction, Sitework, Foundation, Structure, Envelope, MEP, Finishes, Closeout)
- **Recurring activity chains** — sequences like excavate → form → rebar → pour → strip
- **Duration ratios** — how durations relate to each other and scale with project size
- **Milestone patterns** — standard gates (NTP, Substantial Completion, Final Completion)
- **Calendar usage** — which calendar types map to which activity types

### Map Scope to Schedule Structure

1. **WBS hierarchy** — Adapt the common patterns from reference schedules. Add nodes for scope items not in the references, remove nodes for work not in this project, maintain hierarchical logic (phases → areas → disciplines → work types).

2. **Activities** — For each WBS node, create activities based on reference patterns. Use consistent **Verb + Noun** naming with allowed industry acronyms (HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB) and **&** in place of "and" (e.g., "Rough In HVAC Ductwork", "Tape & Finish Drywall", "HVAC Controls & TAB"). Always spell out contract-defined terms: Notice to Proceed, Substantial Completion, Final Completion. Assign durations scaled from reference statistics. Set activity types: `TT_Task` for work, `TT_Mile` for start milestones, `TT_FinMile` for finish milestones.

3. **Logic network** — Every activity needs at least one predecessor and one successor (except start/finish milestones). Default to FS relationships. In TASKPRED, `task_id` = **successor**, `pred_task_id` = predecessor. Use `PR_FS`, `PR_SS`, `PR_FF`, `PR_SF` for relationship types. Target a relationship ratio ≥ 1.5:1 (relationships ÷ activities).

4. **Constraints** — Use SNET/FNET sparingly. Only the NTP milestone typically needs a start-no-earlier-than constraint (`CS_SNET`). Let logic drive dates for everything else.

### Duration Scaling

When adapting durations from reference schedules:

```python
def scale_duration(ref_hours, ref_sqft, new_sqft, complexity=1.0):
    """Square-root scaling — doubling size doesn't double duration."""
    scaled = ref_hours * (new_sqft / ref_sqft) ** 0.5 * complexity
    return round(scaled / 8) * 8  # round to nearest 8-hour day
```

Construction activities don't scale linearly because crews work in parallel and setup costs are fixed.

---

## Phase 2: Writing the XER File

### Why Template-Based Generation Is Required

Building XER files from scratch with Python dicts **does not work**. Multiple approaches were tested:

- Assembling dicts with correct table/field names and writing them out → P6 silently rejects
- Parsing a template into dicts, modifying, writing back → the round-trip loses subtle formatting P6 depends on
- Using `\r` (CR-only) instead of `\r\n` (CRLF) → file looks correct in editors but P6 shows empty import grid
- Putting `%E` after each table → P6 expects a single `%E` at the very end of the file

The root cause: P6 is sensitive to field ordering, exact whitespace, trailing tabs, and dozens of obscure default values in tables like PROJECT (71 fields) and SCHEDOPTIONS (25 fields). It gives no useful error messages when something is wrong.

**What does work:** Start from a real P6 export, preserve all `%T` and `%F` lines byte-for-byte, only replace `%R` data rows. This was confirmed via a byte-for-byte copy test — the raw template imports fine, and surgical data replacement also imports fine.

### Choose a Template

Pick the **smallest working XER** from the reference schedules. It must be a real P6 export (not a previously generated file). Smaller files have fewer tables and fields to worry about.

### The Generation Pattern

The approach has six steps (all demonstrated in `build_from_raw_template.py`):

**1. Read the template as raw bytes and decode as cp1252:**

```python
with open(template_path, 'rb') as f:
    content = f.read().decode('cp1252')
template_lines = content.split('\r\n')
```

**2. Parse into sections, preserving raw structural lines:**

```python
sections = []
header_line = None
current = None
for line in template_lines:
    if not line.strip():
        continue
    parts = line.split('\t')
    marker = parts[0]
    if marker == 'ERMHDR':
        header_line = line
    elif marker == '%T':
        current = {'name': parts[1], 't_line': line, 'f_line': None,
                   'fields': [], 'r_lines': []}
        sections.append(current)
    elif marker == '%F' and current:
        current['f_line'] = line
        current['fields'] = parts[1:]  # field names for make_r_line()
    elif marker == '%R' and current:
        current['r_lines'].append(line)
    elif marker == '%E':
        current = None  # only ONE %E at end of entire file
```

**3. Clone template records for PROJECT and SCHEDOPTIONS.** Parse the template's `%R` into a dict, `.copy()`, then override only the fields you need. This preserves dozens of obscure defaults:

```python
tmpl_proj_parts = proj_sec['r_lines'][0].split('\t')[1:]
tmpl_proj = dict(zip(proj_sec['fields'], tmpl_proj_parts))
new_proj = tmpl_proj.copy()
new_proj.update({'proj_id': PROJECT_ID, 'proj_short_name': PREFIX, ...})
proj_sec['r_lines'] = [make_r_line(proj_sec['fields'], new_proj)]
```

**4. Build new data rows using `make_r_line()`.** This is the key helper — it ensures every `%R` line has exactly the right number of tab-separated values to match the template's `%F`:

```python
def make_r_line(fields, data_dict):
    """Build a %R line with exactly len(fields) tab-separated values."""
    vals = []
    for f in fields:
        vals.append(str(data_dict.get(f, '')))
    return '%R\t' + '\t'.join(vals)
```

For each new record (WBS node, activity, relationship, calendar), start with `{f: '' for f in fields}`, update the fields you care about, and pass through `make_r_line()`.

**5. Reassemble, skipping tables you can't populate:**

```python
skip_tables = {'ACTVTYPE', 'ACTVCODE', 'TASKACTV'}
output_lines = [updated_header]
for sec in sections:
    if sec['name'] in skip_tables:
        continue
    output_lines.append(sec['t_line'])   # byte-for-byte from template
    output_lines.append(sec['f_line'])   # byte-for-byte from template
    output_lines.extend(sec['r_lines'])  # new or cloned data
output_lines.append('%E')  # single %E terminates the file
```

ACTVTYPE, ACTVCODE, and TASKACTV reference project-specific activity code structures. Omit them entirely rather than generating incorrect data — P6 handles their absence gracefully.

**6. Write with CRLF line endings and cp1252 encoding:**

```python
with open(output_path, 'wb') as f:
    f.write('\r\n'.join(output_lines).encode('cp1252'))
    f.write(b'\r\n')
```

### ID Strategy

Use high starting IDs to avoid collisions with existing P6 data:

```python
PROJECT_ID = '99501'    # project
CLNDR_IDS = '99601'     # calendars
wbs_counter = 30000     # WBS nodes
task_counter = 40000    # activities
pred_counter = 50000    # relationships
```

### Calendar Data

Use `clndr_data` strings copied from real P6 exports. The nested parenthesis format is fragile — don't build it programmatically. Days are 1=Sun through 7=Sat. Two work periods per day (AM/PM with lunch break) is the standard pattern. See `build_from_raw_template.py` for proven 5-day, 6-day, and 7-day calendar strings.

---

## Validation

### File-Level Checks

After writing the XER, re-read it and verify:

```python
with open(output_path, 'rb') as f:
    check = f.read().decode('cp1252')

current_f_count = None
for line in check.split('\r\n'):
    parts = line.split('\t')
    if parts[0] == '%T':
        current_table = parts[1]
    elif parts[0] == '%F':
        current_f_count = len(parts) - 1
    elif parts[0] == '%R' and current_f_count is not None:
        rcount = len(parts) - 1
        if current_f_count != rcount:
            print(f"MISMATCH in {current_table}: %F={current_f_count}, %R={rcount}")
```

Also verify CRLF count is reasonable and no `None` values snuck into the output.

### Logic Checks

Before writing, verify the schedule data makes sense:

- Every activity has a WBS assignment
- Every non-milestone activity has at least one predecessor and one successor
- No circular logic (topological sort the relationship graph)
- Calendar IDs referenced by activities exist in the CALENDAR table
- No zero-duration tasks (except milestones), no absurdly large durations
- No duplicate IDs

### Quality Score Backcheck

After validation, run the `schedule-quality-score` skill's scoring engine:

```python
from score_schedule import compute_quality_score
score, grade, scored, info, deductions, scope, details = compute_quality_score(tasks, preds)
```

Use `details` to iterate on issues — `details['missing_logic']`, `details['constraints']`, `details['high_float']`, `details['dangling']`. Target B+ or higher before delivering.

## Output Checklist

Before delivering the generated XER:

- [ ] File re-reads without errors and all `%F`/`%R` field counts match
- [ ] CRLF line endings confirmed
- [ ] Quality score backcheck passes (B+ or higher)
- [ ] WBS structure makes sense for the project scope
- [ ] Activity count is reasonable (not too granular, not too summary)
- [ ] Logic network is complete — no dangling activities
- [ ] Durations are reasonable for the project type and size
- [ ] Calendar is appropriate (5-day, 6-day, etc.)
- [ ] Project start date matches the proposal
- [ ] Milestones are included with appropriate constraints

Tell the user: this is a starting point. After importing to P6, run the scheduler (F9), review the critical path, and adjust durations and logic as needed.

## Reference Files

- `build_from_raw_template.py` — Complete working generation script (bundled in this skill folder). Study this before generating any new XER.
- For XER format details and table schemas, see the schedule-xer-read-modify skill.
- A working template XER file (a real P6 export) is required as input. Use the smallest available.
