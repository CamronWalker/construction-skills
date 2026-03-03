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

This skill covers creating new, valid XER files that can be imported into Primavera P6. The primary use case: given similar project schedules (as XER files) and a proposal or scope document, produce a proposal schedule as a starting point.

## The Workflow

### Step 1: Gather Inputs

You need two types of input:

**Similar project XER files** — These are the templates. Parse them using the approach from the schedule-xer-read-modify skill to understand:
- WBS structure patterns
- Typical activity sequences and naming conventions
- Relationship logic patterns
- Duration ranges for similar work
- Calendar configurations
- Activity codes used

**Scope document** — The proposal, SOW, or project description. Extract:
- Project name and key dates
- Major work phases or areas
- Scope items that map to WBS nodes or activity groups
- Known constraints (milestone dates, access dates, weather windows)
- Project size/complexity indicators to calibrate durations

### Step 2: Analyze the Reference Schedules

Parse all reference XER files and build a composite understanding:

```python
def analyze_reference_schedules(xer_files):
    """Extract patterns from multiple similar schedules."""
    all_wbs = []
    all_activities = []
    all_relationships = []

    for xer_path in xer_files:
        tables = parse_xer(xer_path)
        all_wbs.append(tables.get('PROJWBS', []))
        all_activities.append(tables.get('TASK', []))
        all_relationships.append(tables.get('TASKPRED', []))

    # Identify common WBS patterns
    # Look for recurring activity sequences
    # Calculate duration statistics (mean, median, range)
    # Map typical logic patterns (which activities usually follow which)
    return {
        'wbs_patterns': extract_wbs_patterns(all_wbs),
        'activity_sequences': extract_sequences(all_activities, all_relationships),
        'duration_stats': compute_duration_stats(all_activities),
        'logic_patterns': extract_logic_patterns(all_relationships)
    }
```

Things to look for across the reference schedules:
- **Common WBS levels** — most construction schedules share a similar top-level structure (Preconstruction, Site Work, Foundation, Structure, Envelope, MEP, Finishes, Closeout)
- **Recurring activity chains** — sequences that appear in every schedule (e.g., excavate → form → rebar → pour → strip)
- **Duration ratios** — how durations relate to each other within a phase and how they scale with project size
- **Milestone patterns** — standard milestone gates (NTP, Substantial Completion, Final Completion)
- **Calendar usage** — which calendar types are assigned to which activity types

### Step 3: Map Scope to Schedule Structure

This is the creative step. Take the proposal scope and map it to a WBS and activity structure:

1. **Create WBS hierarchy** — Use the common patterns from reference schedules as a template. Adjust for the specific project scope:
   - Add nodes for scope items not in the references
   - Remove nodes for work not in this project's scope
   - Maintain the hierarchical logic (phases → areas → disciplines → work types)

2. **Populate activities** — For each WBS node, create activities based on the reference patterns:
   - Use consistent naming conventions from the reference schedules
   - Assign initial durations based on reference duration statistics, scaled for project scope
   - Set activity types (Task, Milestone, LOE) appropriately
   - Assign calendars matching the reference patterns

3. **Build logic network** — Establish relationships:
   - Use the reference logic patterns as a starting point
   - Ensure every activity has at least one predecessor and one successor (except project start/finish milestones)
   - Default to FS relationships unless the reference schedules show a specific pattern
   - Use `PR_` prefix format for pred_type (`PR_FS`, `PR_SS`, `PR_FF`, `PR_SF`) — this matches real P6 exports
   - In TASKPRED: `task_id` = **successor**, `pred_task_id` = predecessor
   - Apply lag values from reference statistics
   - Target relationship ratio ≥ 1.5:1 (relationships ÷ activities)

4. **Set constraints and milestones** — From the proposal:
   - Project start date
   - Known milestone dates (owner-mandated, permit-driven, weather-dependent)
   - Use SNET/FNET constraints sparingly — prefer logic-driven dates

### Step 4: Generate the XER File

Build the XER data structure in memory, then write it out.

#### ID Generation Strategy

P6 uses integer IDs internally. When generating a new XER, use a simple incrementing scheme:

```python
class IDGenerator:
    def __init__(self, start=1000):
        self._next = start

    def next(self):
        val = self._next
        self._next += 1
        return val

ids = IDGenerator(start=10000)
```

Start at 10000+ to avoid conflicts with low-numbered IDs that P6 might reserve or that exist in the target database.

#### Building the Data Tables

```python
def build_new_schedule(project_info, wbs_tree, activities, relationships, calendar):
    """Assemble a complete XER data structure."""
    tables = {}

    # Header
    tables['_header'] = ['21.00']

    # Currency (usually needed)
    tables['CURRTYPE'] = [{
        'curr_id': '1',
        'curr_type': 'US Dollar',
        'curr_short_name': 'USD',
        'decimal_digit_cnt': '2',
        'base_exch_rate': '1'
    }]

    # Calendar
    tables['CLNDR'] = [calendar]

    # Project
    tables['PROJECT'] = [{
        'project_id': project_info['id'],
        'proj_short_name': project_info['short_name'],
        'project_name': project_info['name'],
        'start_date': project_info['start_date'],
        'end_date': '',  # Let P6 calculate
        'data_date': project_info['start_date'],
        'default_clndr_id': calendar['clndr_id'],
        'sched_data': 'Y',
        'def_complete_pct_type': 'CP_Phys',
        'task_code_prefix': project_info.get('prefix', 'A'),
        'task_code_base': '1000'
    }]

    # WBS
    tables['PROJWBS'] = wbs_tree

    # Activities
    tables['TASK'] = activities

    # Relationships
    tables['TASKPRED'] = relationships

    return tables
```

#### Standard Calendar Template

Most construction projects use a 5-day, 8-hour calendar. Here's a reusable template:

```python
def standard_5day_calendar(clndr_id='100', name='Standard 5-Day'):
    """Generate a standard Mon-Fri 8hr calendar."""
    # Calendar data encoding:
    # Days 0=Sun through 6=Sat
    # Non-working days have empty parens
    # Working days: (s|08:00|f|17:00) = 8am to 5pm
    clndr_data = (
        '(0||DaysOfWeek()'
        ' (0||0())'                           # Sunday - off
        ' (0||1(s|08:00|f|17:00))'            # Monday
        ' (0||2(s|08:00|f|17:00))'            # Tuesday
        ' (0||3(s|08:00|f|17:00))'            # Wednesday
        ' (0||4(s|08:00|f|17:00))'            # Thursday
        ' (0||5(s|08:00|f|17:00))'            # Friday
        ' (0||6())'                           # Saturday - off
        ' ()'
        ' (0||Exceptions())'
        ')'
    )
    return {
        'clndr_id': clndr_id,
        'clndr_name': name,
        'clndr_type': 'CA_Base',
        'clndr_data': clndr_data,
        'base_clndr_id': '',
        'proj_id': '',
        'last_chng_date': ''
    }
```

You can also create 6-day and 7-day variants for accelerated schedules:

```python
def six_day_calendar(clndr_id='101', name='6-Day Calendar'):
    clndr_data = (
        '(0||DaysOfWeek()'
        ' (0||0())'
        ' (0||1(s|07:00|f|17:30))'
        ' (0||2(s|07:00|f|17:30))'
        ' (0||3(s|07:00|f|17:30))'
        ' (0||4(s|07:00|f|17:30))'
        ' (0||5(s|07:00|f|17:30))'
        ' (0||6(s|07:00|f|17:30))'
        ' ()'
        ' (0||Exceptions())'
        ')'
    )
    return {
        'clndr_id': clndr_id,
        'clndr_name': name,
        'clndr_type': 'CA_Base',
        'clndr_data': clndr_data,
        'base_clndr_id': '',
        'proj_id': '',
        'last_chng_date': ''
    }
```

### Step 5: Write the XER File

```python
def write_xer(tables, output_path, encoding='cp1252'):
    """Write complete XER file from data tables."""
    # Table order matters for clean imports — put dependencies first
    table_order = [
        'CURRTYPE', 'OBS', 'CLNDR', 'PROJECT', 'PROJWBS',
        'ACTVTYPE', 'ACTVCODE', 'RSRC', 'ACCOUNT',
        'TASK', 'TASKPRED', 'TASKRSRC', 'TASKACTV',
        'UDFTYPE', 'UDFVALUE', 'MEMOTYPE'
    ]

    with open(output_path, 'w', encoding=encoding, newline='') as f:
        # Header
        header = tables.get('_header', ['21.00'])
        f.write('ERMHDR\t' + '\t'.join(header) + '\r')

        # Tables in dependency order
        for table_name in table_order:
            records = tables.get(table_name, [])
            if not records:
                continue

            fields = list(records[0].keys())
            f.write(f'%T\t{table_name}\r')
            f.write('%F\t' + '\t'.join(fields) + '\r')
            for record in records:
                values = [str(record.get(field, '')) for field in fields]
                f.write('%R\t' + '\t'.join(values) + '\r')
            f.write('%E\r')
```

### Step 6: Validate Before Delivery

Run validation on the generated file before handing it to the user. The schedule-xer-read-modify skill's validation function covers this, but here are the critical checks for generated files specifically:

1. **Every activity has a WBS assignment** — P6 requires it
2. **Logic completeness** — no activity without at least one predecessor or successor (except start/finish milestones)
3. **No circular logic** — check the relationship graph for cycles
4. **Calendar exists** — the calendar referenced by PROJECT and all TASKs must be in the CLNDR table
5. **Duration sanity** — no zero-duration tasks (except milestones), no absurdly large durations
6. **ID uniqueness** — no duplicate IDs within their scope
7. **Field alignment** — `%F` field count matches `%R` field count for every table

```python
def validate_generated_xer(tables):
    """Validate a newly generated XER before export."""
    issues = []

    tasks = tables.get('TASK', [])
    preds = tables.get('TASKPRED', [])
    task_ids = {t['task_id'] for t in tasks}

    # Check logic completeness
    # In TASKPRED: task_id = successor, pred_task_id = predecessor
    has_pred = {p['task_id'] for p in preds if p.get('task_id')}
    has_succ = {p['pred_task_id'] for p in preds if p.get('pred_task_id')}

    for task in tasks:
        tid = task['task_id']
        is_milestone = task.get('task_type', '') in ('TT_Mile', 'TT_FinMile')

        if tid not in has_pred and tid not in has_succ:
            issues.append(f"Activity {tid} '{task.get('task_name','')}' has no logic ties (open start AND open finish)")
        elif tid not in has_pred and not is_milestone:
            issues.append(f"Activity {tid} '{task.get('task_name','')}' has no predecessor (open start)")
        elif tid not in has_succ and not is_milestone:
            issues.append(f"Activity {tid} '{task.get('task_name','')}' has no successor (open finish)")

    # Check for cycles
    from collections import defaultdict, deque
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    for p in preds:
        pred_id = p.get('pred_task_id')
        succ_id = p.get('task_id')  # task_id = successor in TASKPRED
        if pred_id and succ_id:
            graph[pred_id].append(succ_id)
            in_degree[succ_id] += 1
            if pred_id not in in_degree:
                in_degree[pred_id] = in_degree.get(pred_id, 0)

    # Topological sort to detect cycles
    queue = deque([n for n in task_ids if in_degree.get(n, 0) == 0])
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited < len(task_ids):
        issues.append("Circular logic detected — schedule contains dependency loops")

    return issues
```

## Duration Calibration

When scaling durations from reference schedules to a new project, consider:

- **Building size** — square footage, number of floors, number of units
- **Complexity** — renovation vs. new construction, occupied vs. vacant, phased vs. single-phase
- **Location factors** — urban vs. rural, access constraints, permitting timelines
- **Season** — winter concrete work takes longer, roofing has weather windows

A simple scaling approach:

```python
def scale_duration(reference_duration_hrs, reference_sqft, new_sqft, complexity_factor=1.0):
    """Scale a reference duration based on relative project size."""
    size_ratio = new_sqft / reference_sqft
    # Use square root scaling — doubling size doesn't double duration
    scaled = reference_duration_hrs * (size_ratio ** 0.5) * complexity_factor
    # Round to nearest 8-hour day
    return round(scaled / 8) * 8
```

The square root scaling reflects that most construction activities don't scale linearly — a building twice the size doesn't take twice as long because crews can work in parallel and there are fixed setup/mobilization costs.

## Activity Naming Conventions

Follow patterns from the reference schedules when possible. If establishing new conventions:

- Lead with the discipline or area when using activity codes
- Activity name should describe the work: verb + object (e.g., "Install Roofing", "Pour Foundation Walls")
- Avoid abbreviations in activity names unless they're industry-standard (MEP, HVAC, GC)
- Milestones should clearly state what's being marked: "Substantial Completion", "Building Permit Received"

## Output Checklist

Before delivering the generated XER to the user, confirm:

- [ ] File parses without errors (re-read it with the parser)
- [ ] All validation checks pass
- [ ] WBS structure makes sense for the project scope
- [ ] Activity count is reasonable (not too granular, not too summary)
- [ ] Logic network is complete — no dangling activities
- [ ] Durations are reasonable for the project type and size
- [ ] Calendar is appropriate (5-day, 6-day, etc.)
- [ ] Project start date matches the proposal
- [ ] Known milestones are included with appropriate constraints
- [ ] The file is ready to import into P6 without modification

Tell the user: this is a starting point. After importing to P6, they should run the scheduler (F9), review the critical path, and adjust durations and logic as needed. The generated schedule gives them the structure and logic framework — not a finished product.

## Reference Files

For XER format details and table schemas, the schedule-xer-read-modify skill's reference file covers the full specification. This skill focuses on the generation workflow; refer to that skill for parsing and format details.
