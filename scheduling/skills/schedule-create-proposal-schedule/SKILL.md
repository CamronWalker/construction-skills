---
name: schedule-create-proposal-schedule
description: >
  Create a construction proposal schedule plan through a structured interview process. Use this skill
  whenever the user wants to "plan a proposal schedule", "create a schedule plan", "build a bid
  schedule", "proposal schedule questionnaire", "schedule planning session", or wants to analyze
  sample schedules and bid documents to develop a schedule basis before generating a XER file.
  Also trigger when the user says "I have some similar schedules and a bid package" or "help me
  plan out this schedule" or "schedule basis document" or "schedule plan from bid docs". This skill
  produces a comprehensive schedule plan document — if the user wants to go straight to XER
  generation without the planning interview, use schedule-xer-generate instead. This skill's
  output feeds directly into schedule-xer-generate as the scope input.
---

# Proposal Schedule Planning Session

This skill orchestrates a multi-phase interview process that takes sample XER files and bid documents as inputs, walks the user through approximately 20 context-aware questions across four topic areas, collects free-form notes, and produces a comprehensive schedule plan document. The plan document serves as the scope input for the `schedule-xer-generate` skill. The entire process is guided by the `schedule-best-practices` skill — all schedule decisions (logic network, relationship types, constraint usage, float targets, etc.) must conform to DCMA 14-Point, GAO, and AACE best practice standards. After XER generation, the `schedule-quality-score` skill scores the schedule and the process iterates until the schedule achieves an A grade.

## Workflow Overview

1. **Gather Inputs** — Collect sample XER files and bid documents from the project folder
2. **Auto-Parse & Analysis** — Parse all XER files using schedule-xer-read-modify patterns; read bid documents; extract key data
3. **Structured Q&A** — Walk through ~20 questions across 4 topic areas, using parsed data to provide context and options. All recommendations follow `schedule-best-practices` standards.
4. **Targeted Free-Write** — Collect detailed notes on 5 specific topics
5. **Summary & Review** — Present all decisions for user confirmation and revision
6. **Plan Document** — Generate the complete schedule plan document (built to `schedule-best-practices` standards)
7. **XER Generation** — Generate the XER file via `schedule-xer-generate`
8. **Quality Scoring & Iteration** — Score the generated XER using `schedule-quality-score`. If the schedule does not achieve an A grade, identify the failing metrics, ask the user targeted follow-up questions if needed, fix the issues, and regenerate. Repeat until the schedule scores an A.

---

## Phase 1: Gather Inputs

### Expected Folder Structure

The skill expects a **project folder path** with this structure:

```
<project-folder>/
├── Bid Documents/              ← bid proposal, specs, plans, contract docs
└── Proposal Schedule/
    ├── Sample Schedules/       ← sample XER files from similar projects
    └── [outputs go here]
```

### How to Prompt the User

Ask the user for the project folder path:

```
To start the proposal schedule planning session, I need the path to your project folder.

The folder should contain:

1. **Bid Documents/** — The bid package materials: bid proposal, plans/specifications,
   contract documents, schedule requirements, and any other bid docs.

2. **Proposal Schedule/Sample Schedules/** — 1-5 XER files from similar completed projects.
   These will be analyzed to extract WBS patterns, activity sequences, durations, and logic
   that can inform the new schedule.

   What makes a good sample: same building type, similar size/complexity, similar delivery method.

What is the project folder path?
```

### After Receiving the Path

1. List all files found in `Bid Documents/` and `Proposal Schedule/Sample Schedules/`
2. Confirm with the user before proceeding: "I found X XER files and Y bid documents. Ready to proceed?"

---

## Phase 2: Auto-Parse & Analysis

### Parsing Sample XER Files

For each XER file, parse using the approach from the `schedule-xer-read-modify` skill and extract a schedule profile:

```python
def extract_schedule_profile(tables, file_name):
    """Extract a schedule profile from parsed XER tables for comparison."""
    tasks = tables.get('TASK', [])
    wbs = tables.get('PROJWBS', [])
    preds = tables.get('TASKPRED', [])
    project = tables.get('PROJECT', [{}])[0]
    calendars = tables.get('CALENDAR', tables.get('CLNDR', []))

    # Filter to non-summary, non-LOE activities
    real_tasks = [t for t in tasks if t.get('task_type', '') not in ('TT_WBS', 'TT_LOE')]

    # Duration stats — XER stores hours internally, convert to days (÷ 8) for display
    durations_hrs = [float(t.get('target_drtn_hr_cnt', 0)) for t in real_tasks
                     if t.get('task_type', '') not in ('TT_Mile', 'TT_FinMile')]
    durations = [d / 8 for d in durations_hrs]  # Convert to working days

    # Relationship type distribution
    rel_types = {}
    for p in preds:
        rt = p.get('pred_type', 'PR_FS').replace('PR_', '')
        rel_types[rt] = rel_types.get(rt, 0) + 1

    # Milestone list
    milestones = [
        {'name': t.get('task_name', ''), 'type': t.get('task_type', ''),
         'date': t.get('cstr_date', t.get('early_end_date', ''))}
        for t in tasks if t.get('task_type', '') in ('TT_Mile', 'TT_FinMile')
    ]

    # Activity naming patterns — sample first 15 activity names per WBS node
    naming_samples = {}
    for t in real_tasks[:50]:
        wbs_id = t.get('wbs_id', 'unknown')
        if wbs_id not in naming_samples:
            naming_samples[wbs_id] = []
        if len(naming_samples[wbs_id]) < 5:
            naming_samples[wbs_id].append(t.get('task_name', ''))

    profile = {
        'file_name': file_name,
        'project_name': project.get('project_name', 'Unknown'),
        'start_date': project.get('start_date', ''),
        'end_date': project.get('end_date', ''),

        # WBS structure
        'wbs_tree': build_wbs_tree(wbs),
        'wbs_depth': max_wbs_depth(wbs),
        'wbs_node_count': len(wbs),

        # Activity patterns
        'total_activities': len(real_tasks),
        'activity_types': count_by_field(real_tasks, 'task_type'),
        'naming_samples': naming_samples,

        # Duration statistics (working days)
        'duration_min_days': min(durations) if durations else 0,
        'duration_max_days': max(durations) if durations else 0,
        'duration_median_days': sorted(durations)[len(durations)//2] if durations else 0,
        'duration_avg_days': sum(durations) / len(durations) if durations else 0,

        # Logic network
        'relationship_count': len(preds),
        'relationship_ratio': round(len(preds) / max(len(real_tasks), 1), 2),
        'rel_type_distribution': rel_types,

        # Milestones
        'milestones': milestones,

        # Calendars
        'calendars': [(c.get('clndr_name', ''), c.get('clndr_id', ''))
                      for c in calendars],
    }
    return profile


def build_wbs_tree(wbs_records):
    """Reconstruct WBS hierarchy as an indented list."""
    nodes = {w.get('wbs_id'): w for w in wbs_records}
    children = {}
    root = None
    for w in wbs_records:
        parent = w.get('parent_wbs_id', '')
        if parent and parent in nodes:
            children.setdefault(parent, []).append(w.get('wbs_id'))
        elif not parent:
            root = w.get('wbs_id')

    def render(node_id, depth=0):
        node = nodes.get(node_id, {})
        lines = ['  ' * depth + node.get('wbs_name', node_id)]
        for child_id in children.get(node_id, []):
            lines.extend(render(child_id, depth + 1))
        return lines

    if root:
        return '\n'.join(render(root))
    return '\n'.join(w.get('wbs_name', '') for w in wbs_records)


def max_wbs_depth(wbs_records):
    """Calculate maximum depth of WBS hierarchy."""
    nodes = {w.get('wbs_id'): w for w in wbs_records}
    def depth(node_id, d=0):
        node = nodes.get(node_id, {})
        parent = node.get('parent_wbs_id', '')
        if parent and parent in nodes:
            return depth(parent, d + 1)
        return d
    return max((depth(w.get('wbs_id')) for w in wbs_records), default=0)


def count_by_field(records, field):
    """Count records by a field value."""
    counts = {}
    for r in records:
        val = r.get(field, 'unknown')
        counts[val] = counts.get(val, 0) + 1
    return counts
```

### Extracting Bid Document Information

Read the bid documents and extract into structured categories:

- **Project name, location, and type**
- **Contract duration / substantial completion date**
- **Required milestones and interim deadlines**
- **Phasing requirements** from specs or contract
- **Liquidated damages** amounts and triggers
- **Schedule specification requirements** (update frequency, format, detail level, software)
- **Scope summary** by major division or area
- **Special conditions** (occupied building, phased turnover, seasonal restrictions)

### Presenting the Analysis Summary

Present findings to the user before beginning the Q&A:

```
## Analysis Summary

### Sample Schedule Profiles

**Schedule A: [Project Name] ([file_name])**
- Duration: [X] months | Activities: [N] | Relationship Ratio: [X.X]:1
- WBS Structure ([depth] levels, [node_count] nodes):
  [indented WBS tree]
- Milestones: [list]
- Activity Naming Pattern: [observed pattern with examples]
- Duration Range: [min]–[max] days (median [med] days, avg [avg] days)
- Relationship Types: FS [X]%, SS [Y]%, FF [Z]%
- Calendar: [calendar names]
- Sample Activities:
  - [5-10 representative activity names grouped by WBS area]

**Schedule B: [Project Name] ([file_name])**
[Same structure]

### Bid Document Findings

- **Project:** [Name and type]
- **Location:** [location]
- **Contract Duration:** [X months / specific date]
- **Required Milestones:** [list]
- **Phasing:** [requirements found or "none specified"]
- **LD/Incentives:** [amounts and triggers]
- **Schedule Specification:** [requirements from specs]
- **Major Scope Areas:** [list]
- **Special Conditions:** [list]

I'll now begin the planning questionnaire. Each question will reference what I found
in these schedules and bid documents.
```

### Best Practices Compliance (schedule-best-practices)

Throughout the entire Q&A and plan generation process, apply the `schedule-best-practices` skill as a guardrail. Every recommendation and default must conform to DCMA 14-Point, GAO, and AACE standards:

- **Logic completeness:** Every activity must have at least one predecessor and one successor (except project start/finish milestones). Target missing logic < 5%. Flag this during Q&A if sample schedules show gaps.
- **Relationship types:** Default to Finish-to-Start (FS). Target FS >= 90%, SS <= 5%, FF <= 5%, SF < 1%. When suggesting SS or FF relationships (e.g., for MEP overlap in Q9), note the impact on relationship distribution.
- **Constraints:** Minimize hard constraints. Target total constraints <= 5%. Only use constraints for contract-mandated dates. ALAP is a directive, not a constraint — it is acceptable.
- **High float:** Target < 5% of activities with total float > 44 days. Ensure the logic network is tight enough to prevent excessive float.
- **Relationship ratio:** Target >= 1.5:1 (relationships to activities). Recommend this during Q&A when discussing logic density.
- **Leads:** Zero leads (no negative lag). Always use positive lag or adjust relationship type instead.
- **Lags:** Target < 5% of relationships with positive lag. Prefer logic-driven sequencing over lag.
- **High duration:** Target < 5% of activities with duration > 25 working days. Procurement activities (submittals, fabrication, delivery) are exempt from this threshold — long lead times are expected. If user proposes long-duration non-procurement activities, recommend breaking them down.
- **Negative float:** Zero negative float in the generated schedule. If the contract duration is tight (identified in Q1), flag this risk.

When presenting recommendations during Q&A, reference these thresholds. For example, in Q13 (Activity Granularity), if the user wants very few activities, warn that this may push relationship ratio below 1.5:1 or create high-float activities.

---

## Phase 3: Structured Q&A Session

### How Context-Aware Questions Work

Every question follows this pattern:

1. **State the question clearly**
2. **Present relevant context** from the parsed XER files and bid docs
3. **Compare how sample schedules handled it**: "Schedule A did X, Schedule B did Y — which approach fits this project?"
4. **Suggest a default or recommendation** based on the analysis
5. **Show an example of what a good answer looks like**

Questions should be asked **one at a time** or in small groups of 2-3 related questions. Do not dump all 20 questions at once. Pace the session to keep the user engaged and allow each answer to inform follow-up context.

---

### Topic Area 1: Contract & Bid Requirements (Questions 1–5)

**Question 1: Contract Duration / Substantial Completion Date**

```
Context to pull: From bid docs — contract duration, substantial completion date, NTP
date if specified. From sample XERs — each schedule's total duration (start to SC milestone).

Present: "The bid documents specify [X]. For reference:
- Schedule A ([project name]) ran [Y months] from NTP to Substantial Completion
- Schedule B ([project name]) ran [Z months]
Does the contract duration match what you'd expect for this scope, or do you have
concerns about the timeline?"

Example good answer: "The contract says 18 months from NTP. That feels tight — the
elementary school we did in Provo took 16 months and this one is 20% larger. I'd plan
for 18 months but flag it as a risk."
```

**Question 2: Required Milestones and Interim Deadlines**

```
Context to pull: From bid docs — any milestones mentioned in contract, specs, or bid
forms. From sample XERs — list all milestones (TT_Mile, TT_FinMile) from each schedule.

Present: "I found these milestones in the bid documents: [list].
The sample schedules used these milestone structures:
- Schedule A: [milestone list with approximate timing relative to NTP]
- Schedule B: [milestone list with approximate timing]
Are there additional interim milestones the owner expects, or contractual deadlines
not captured in the bid docs?"

Example good answer: "The contract requires Building Dry-In by month 8 — that's not in
the docs you found but it's in the pre-bid meeting notes. Also add a milestone for
elevator inspection at month 12."
```

**Question 3: Phasing Requirements / Sequencing Mandates**

```
Context to pull: From bid docs — Division 01 General Requirements, phasing plans,
sequencing requirements from specs. From sample XERs — overall sequencing approach
(single phase vs. multi-phase, identified by WBS structure and milestone patterns).

Present: "The specs [indicate phasing requirements / don't specify phasing]. The sample
schedules handled phasing as follows:
- Schedule A: [single phase / 2 phases / building-by-building]
- Schedule B: [approach]
Does the owner require specific phasing, or is the sequencing at your discretion?"

Example good answer: "The owner wants the east wing turned over 3 months early so they
can start moving staff. That means we need a two-phase approach — east wing first,
then west wing."
```

**Question 4: Liquidated Damages / Incentive Structures**

```
Context to pull: From bid docs — LD amounts, LD triggers, incentive provisions,
bonus/penalty clauses.

Present: "The contract includes [LD amount per day / no LD provision found]. LDs are
triggered by [milestone / SC date / final completion]. Are there incentive bonuses
for early completion, or other financial implications tied to schedule dates?"

Example good answer: "$2,500/day LDs after Substantial Completion, plus $1,000/day
after Final Completion. No incentive bonus. We need to build in at least 2 weeks of
float before SC."
```

**Question 5: Owner-Required Schedule Format / Reporting**

```
Context to pull: From bid docs — schedule specification section (usually Section 01 32 00
or similar), update frequency, required software, level of detail requirements,
narrative requirements.

Present: "The schedule specification requires: [list findings — P6 format, monthly
updates, narrative, etc.]. For items not specified, the sample schedules used:
[X-level WBS, monthly updates, etc.]. Any additional reporting or format requirements
from the owner that aren't in the specs?"

Example good answer: "Monthly updates with a 3-week lookahead. Owner wants the schedule
in P6 native format plus a PDF Gantt. They also want a separate milestone summary
for their board reports."
```

---

### Topic Area 2: Construction Sequencing (Questions 6–10)

**Question 6: Overall Construction Flow**

```
Context to pull: From sample XERs — reconstruct the high-level sequencing from each
schedule's WBS and logic network. Identify whether the schedule is organized
building-by-building, floor-by-floor, trade-by-trade, or area-by-area. Show the
top-level activity flow.

Present: "Looking at how the sample schedules organized construction flow:
- Schedule A organized by [building/floor/area]: [high-level sequence]
- Schedule B organized by [trade/phase]: [high-level sequence]
For this project, which approach fits best? Consider: [number of buildings, floors,
distinct areas, whether trades need to cycle through areas]."

Example good answer: "This is a single building, 3 floors. I want to go floor-by-floor
for structure, then area-by-area for finishes. The mechanical room is a separate
sequence from the classroom wings."
```

**Question 7: Site Mobilization and Logistics**

```
Context to pull: From sample XERs — early activities in each schedule (first 10-15
activities by early start date). From bid docs — site access requirements, mobilization
provisions.

Present: "The sample schedules started with these mobilization sequences:
- Schedule A: [list first 8-10 activities with durations]
- Schedule B: [list first 8-10 activities with durations]
What does mobilization look like for this project? Consider: site access, temporary
facilities, utilities connections, erosion control, existing conditions."

Example good answer: "Tight urban site — we need to set up traffic control and
pedestrian barriers first. Temporary power from the street, temporary water from
the adjacent building. Two-week mobilization before any earthwork."
```

**Question 8: Foundation / Structural Sequence Strategy**

```
Context to pull: From sample XERs — activities under foundation/structure WBS nodes,
their sequences and durations. From bid docs — structural system type, foundation type
if identifiable from scope.

Present: "The structural sequences in the sample schedules:
- Schedule A: [foundation type] → [structural system] — [sequence summary, key durations]
- Schedule B: [foundation type] → [structural system] — [sequence summary, key durations]
What structural system is this project using, and how do you want to sequence it?"

Example good answer: "Spread footings, CMU bearing walls with steel bar joists.
Foundation is straightforward — 6 weeks. Structure goes floor-by-floor: CMU walls,
set joists, pour deck, repeat. About 4 weeks per floor."
```

**Question 9: MEP Rough-In Coordination Approach**

```
Context to pull: From sample XERs — MEP-related activities, their sequencing and
overlap patterns (look for SS relationships between plumbing/electrical/HVAC rough-in).

Present: "The sample schedules handled MEP rough-in as follows:
- Schedule A: [sequential/overlapping approach, key durations, relationship types used]
- Schedule B: [sequential/overlapping approach, key durations, relationship types used]
How do you want to sequence mechanical, electrical, and plumbing rough-in? Sequential
by trade, overlapping by area, or fully parallel?"

Example good answer: "Plumbing underground first, then overhead rough-in by area.
Electrical and HVAC can overlap with plumbing overhead — use SS with a 1-week lag.
Fire sprinkler goes in with HVAC."
```

**Question 10: Commissioning and Closeout Sequence**

```
Context to pull: From sample XERs — activities in the closeout/commissioning phase,
their durations and sequences. From bid docs — commissioning requirements,
closeout provisions, time between SC and Final Completion.

Present: "The sample schedules allocated these durations for closeout:
- Schedule A: [X weeks] commissioning, [Y weeks] punchlist, [Z weeks] to final completion
- Schedule B: [different breakdown]
The bid docs [specify commissioning requirements / don't mention commissioning].
How much time do you want to allocate for commissioning, punchlist, and closeout?"

Example good answer: "Full commissioning required — 6 weeks for MEP commissioning,
2 weeks for punchlist, 4 weeks from SC to Final Completion. Budget 3 months total
from substantial systems completion to Final."
```

---

### Topic Area 3: WBS & Detail Level (Questions 11–15)

**Question 11: WBS Depth Preference**

```
Context to pull: From sample XERs — reconstruct each schedule's WBS tree with
indentation showing depth. Count nodes at each level. Also generate a PROPOSED WBS
based on the bid scope document.

Present: "Here are the WBS structures from the sample schedules:

Schedule A ([depth]-level, [node_count] nodes):
  [full indented WBS tree]

Schedule B ([depth]-level, [node_count] nodes):
  [full indented WBS tree]

Based on the bid scope, here is a proposed WBS for this project:
  [generated WBS tree based on scope items identified in Phase 2]

Which depth level works for you? Do you want to match one of the samples,
use the proposed structure, or customize?"

Example good answer: "Go with 3 levels like Schedule A, but add a 4th level under
MEP to break out plumbing, electrical, and HVAC separately. The proposed WBS
looks good — add a 'Site Utilities' node under Site Work."
```

**Question 12: Activity Naming Conventions**

The standard naming convention is **Verb + Noun** with **no acronyms** — always spell out full words. This is non-negotiable. All activity names generated by this skill must follow this pattern. Never use acronyms like MEP, HVAC, GC, CMU, etc. — always write "Mechanical Electrical Plumbing", "Heating Ventilation and Air Conditioning", "General Conditions", "Concrete Masonry Unit", etc. The question is about modifiers — area suffixes, floor prefixes — not whether to use verb-noun or acronyms.

```
Context to pull: From sample XERs — extract 10-15 representative activity names from
each schedule. Identify which ones follow verb-noun and which deviate. Flag any acronyms
found in sample schedules — these will be spelled out in the new schedule.

Present: "The standard for activity naming is Verb + Noun with no acronyms:
  - Tie Rebar
  - Pour Concrete
  - Erect Structural Steel
  - Install Roofing Membrane
  - Frame Interior Walls
  - Set Bar Joists
  - Hang Drywall
  - Install Underground Plumbing
  - Rough In Heating Ventilation and Air Conditioning  (never 'HVAC')
  - Install Fire Sprinkler System  (never 'Install FS')

The sample schedules used:
Schedule A: [show examples — note any acronyms that will be spelled out]
Schedule B: [show examples]

For modifiers, do you want:
- Area/floor suffix when needed? (e.g., 'Frame Interior Walls - 2nd Floor')
- Building prefix for multi-building? (e.g., 'Building A - Frame Walls')"

Example good answer: "Verb + noun, no area prefix since it's one building.
Use the floor as a suffix when needed: 'Frame Interior Walls - 2nd Floor'."
```

**Question 13: Activity Granularity**

```
Context to pull: From sample XERs — count activities per WBS node to show density.
Calculate overall ratio of activities to WBS nodes. Show total activity counts.

Present: "Activity density in the sample schedules:
- Schedule A: [N] total activities across [M] WBS nodes ([ratio] activities/node avg)
  - Foundation: [X] activities
  - Structure: [Y] activities
  - MEP: [Z] activities
  - Finishes: [W] activities
- Schedule B: [different density breakdown]
How granular do you want this schedule? More detail = better tracking but more
maintenance. For a proposal schedule, [X-Y] activities per WBS node is typical."

Example good answer: "Keep it at proposal level — 5-8 activities per major WBS node.
We'll add detail after we win the job. Total should be around 200-300 activities
for a project this size."
```

**Question 14: Organization Method (CSI / Area / Phase / Hybrid)**

```
Context to pull: From sample XERs — determine whether each schedule is organized by
CSI division, by area/building, by construction phase, or a hybrid. From bid docs —
whether the bid form or specs reference CSI divisions.

Present: "The sample schedules are organized as:
- Schedule A: [by phase — Site, Foundation, Structure, Envelope, Interior, Closeout]
- Schedule B: [hybrid — by building, then by trade within each building]
The bid documents [reference CSI divisions / organize by area / don't specify].
How do you want to organize: by CSI division, by area/building, by phase, or hybrid?"

Example good answer: "Phase-based at the top level (Preconstruction, Site, Building,
Closeout), then by floor within Building, then by trade within each floor.
Don't use CSI divisions — they don't match how we manage the work."
```

**Question 15: Milestone Strategy**

```
Context to pull: From sample XERs — list all milestones from each schedule with their
names, types (TT_Mile vs TT_FinMile), and relative timing. From bid docs — contractually
required milestones.

Present: "Milestones in the sample schedules:
- Schedule A ([N] milestones): [list with relative timing in months from start]
- Schedule B ([M] milestones): [list with relative timing]
Contract-required milestones: [list from bid docs]

How many milestones do you want? What naming convention? Should milestones mark
the START of a phase, the END, or both?"

Example good answer: "End-of-phase milestones only: NTP, Building Permit,
Foundation Complete, Building Dried-In, MEP Rough-In Complete, Substantial
Completion, Final Completion. Name them exactly that way — no abbreviations."
```

---

### Topic Area 4: Risk & Procurement (Questions 16–20)

**Question 16: Long-Lead Procurement Items**

```
Context to pull: From bid docs — specified equipment, specialty items mentioned in specs.
From sample XERs — procurement/submittal activities and their durations.

Present: "From the bid documents, these items may be long-lead:
- [list items identified from specs — switchgear, elevator, specialty finishes, etc.]
The sample schedules included these procurement activities:
- Schedule A: [list with lead times in weeks]
- Schedule B: [list with lead times in weeks]
Which items need procurement activities in this schedule? What lead times should we use?"

Example good answer: "Elevator is 16 weeks from order. Switchgear is 12 weeks.
Custom curtain wall is 20 weeks — that's the longest lead. Also add 8 weeks for
kitchen equipment and 6 weeks for HVAC units."
```

**Question 17: Weather / Seasonal Considerations**

```
Context to pull: From bid docs — project location, any seasonal restrictions in specs.
From the proposed start date — calculate which months each major phase will fall in.

Present: "Based on a [start date] start, here's approximately when major phases fall:
- Earthwork/Foundation: [months] — [weather note for that season/location]
- Structure: [months]
- Roofing/Exterior: [months] — [weather note]
- Interior Finishes: [months]
- Closeout: [months]
Are there seasonal impacts to account for? Winter concrete restrictions,
rainy season impacts, extreme heat limitations?"

Example good answer: "We're starting in November — earthwork will hit winter.
Budget 2 weeks of weather delays for December-January. No concrete below 40 degrees
without hotwater/blankets. Roofing needs to be done before monsoon season starts in July."
```

**Question 18: Permit and Inspection Timeline**

```
Context to pull: From bid docs — permitting requirements, inspection milestones.
From sample XERs — permit-related activities and their durations.

Present: "The sample schedules allocated these durations for permitting:
- Schedule A: [building permit X weeks, inspections Y days each]
- Schedule B: [different approach]
What permit and inspection timelines should we plan for? Consider: building permit
review time, fire marshal review, health department, elevator inspections,
final occupancy certificate."

Example good answer: "Building permit already in hand. Plan 3 days for each
rough-in inspection, 5 days for fire marshal review, 10 days for final inspection
and CO. Elevator inspection is a 3-week lead time — schedule it early."
```

**Question 19: Subcontractor Availability / Self-Perform Scope**

```
Context to pull: From bid docs — scope items by division. Present a list of
major trade packages.

Present: "Major trade packages for this project based on the scope:
[list: earthwork, concrete, structural steel, roofing, mechanical, electrical,
plumbing, fire protection, drywall, finishes, etc.]
Which scopes are you self-performing vs. subcontracting? Any concerns about
subcontractor availability or capacity that should affect the schedule?"

Example good answer: "Self-perform: concrete, rough carpentry, drywall, painting.
Everything else is subbed. The mechanical sub is booked tight — we might not get
them on site until month 4. Electrical is fine. Steel fabricator has a 10-week
shop drawing / fabrication cycle."
```

**Question 20: Known Risk Items / Schedule Threats**

```
Context to pull: From bid docs — any risk items, unusual conditions, or red flags
identified during document review. From sample XERs — any pattern of delays visible
in the completed schedule data (activities with very high float, negative float,
or out-of-sequence progress).

Present: "Based on my review, potential schedule risks include:
- [list items identified from bid docs: phased occupied building, unusual site
  conditions, complex coordination requirements, etc.]
- [list patterns from sample schedules: phases that consistently took longer than
  planned, areas with logic density issues]
What other risks or schedule threats do you see?"

Example good answer: "The existing underground utilities aren't well documented —
budget 2 weeks for exploratory excavation before we commit to the site utility
route. Also, the owner's design team is slow on RFI responses — plan 14-day
turnaround for all RFIs instead of the standard 7."
```

---

## Phase 4: Targeted Free-Write Prompts

After all 20 questions, present 5 structured free-write prompts. Each has a brief intro explaining what kind of information is valuable.

### 1. Site Conditions & Logistics

```
Describe the site conditions and logistics approach in your own words.
Consider: site access points, staging areas, material storage, crane placement,
temporary facilities, adjacent building/road impacts, traffic management,
parking, temporary utilities, erosion control, and any environmental restrictions.
```

Example response: "Single access point off Main Street — need a flagman during deliveries. Staging area in the south parking lot until we need it for paving. Tower crane on the east side, mobile crane for steel on the west. Temporary power from transformer on 3rd Ave."

### 2. Owner Relationship & Communication

```
Describe how you'll interact with the owner and their team during this project.
Consider: meeting frequency, reporting format, decision turnaround expectations,
key owner representatives, design team responsiveness, and any relationship
dynamics that affect scheduling.
```

Example response: "Weekly OAC meetings, biweekly schedule review with the PM. Owner's rep is hands-on — wants daily photo logs. Design team is responsive on structural but slow on MEP coordination. Expect 3-week RFI turnaround on mechanical questions."

### 3. Self-Perform vs. Subcontractor Scope Breakdown

```
List each major scope item and whether it's self-performed or subcontracted.
For subcontracted work, note any known lead times, mobilization requirements,
or sequencing constraints.
```

Example response:
- Self-perform: Concrete (foundation + flatwork), framing, drywall, paint
- Sub — Earthwork: ABC Excavation, available start month 1
- Sub — Steel: XYZ Steel, 10-week fab cycle from approved shops
- Sub — Mechanical: TBD, need 4-week mobilization notice
- Sub — Electrical: Sparks Electric, concurrent with mechanical
- Sub — Roofing: Need to bid, 6-week lead on materials

### 4. Schedule Narrative Assumptions

```
List the key assumptions you're making for this schedule. These become the
'schedule basis' and protect you if conditions change. Consider: crew sizes,
work hours, weather allowances, owner-furnished items, design completion status,
and any conditions precedent.
```

Example response:
- Standard 5-day, 8-hour work week. No overtime unless noted.
- Owner furnishes all kitchen equipment by month 10.
- Design is 100% complete at NTP — no allowance for design changes.
- Weather: 10 weather days built into earthwork, 5 into roofing.
- Crew: 2 concrete crews for foundation, 1 crew for elevated slabs.
- Building permit in hand at NTP.

### 5. Catch-All

```
Is there anything else that should be captured in the schedule plan that wasn't
covered by the questions above? Any unique project conditions, owner quirks,
lessons learned from similar projects, or scheduling approaches you want to use?
```

Example response: "The spec requires LEED commissioning — add a separate commissioning consultant coordination track. Also, this owner always adds scope during the project — build in 2 weeks of management reserve before SC. Lesson from the Provo school: get the elevator contract signed in month 1 or it will be the critical path."

---

## Phase 5: Summary & Review

After all questions and free-write prompts are complete, present a structured summary:

```
## Schedule Plan Summary — [Project Name]

### Contract & Bid Requirements
1. **Duration:** [answer from Q1]
2. **Milestones:** [answer from Q2]
3. **Phasing:** [answer from Q3]
4. **LDs/Incentives:** [answer from Q4]
5. **Format/Reporting:** [answer from Q5]

### Construction Sequencing
6. **Overall Flow:** [answer from Q6]
7. **Mobilization:** [answer from Q7]
8. **Foundation/Structure:** [answer from Q8]
9. **MEP Coordination:** [answer from Q9]
10. **Commissioning/Closeout:** [answer from Q10]

### WBS & Detail Level
11. **WBS Depth:** [answer from Q11]
12. **Naming Convention:** [answer from Q12]
13. **Activity Granularity:** [answer from Q13]
14. **Organization Method:** [answer from Q14]
15. **Milestone Strategy:** [answer from Q15]

### Risk & Procurement
16. **Long-Lead Items:** [answer from Q16]
17. **Weather/Seasonal:** [answer from Q17]
18. **Permits/Inspections:** [answer from Q18]
19. **Sub Availability / Self-Perform:** [answer from Q19]
20. **Known Risks:** [answer from Q20]

### Free-Write Notes
- **Site Conditions:** [summary]
- **Owner Relationship:** [summary]
- **Self-Perform Breakdown:** [summary]
- **Schedule Assumptions:** [summary]
- **Additional Notes:** [summary]

---

**Review this summary.** Do you want to change any answers before I generate
the schedule plan document? Reference questions by number (e.g., "Change Q6 to...").
```

Accept revisions by number and update the summary until the user confirms they are satisfied.

---

## Phase 6: Generate Schedule Plan Document

Output the plan document as a markdown file to `<project-folder>/Proposal Schedule/Schedule Plan - [Project Name].md`.

### Plan Document Template

```markdown
# Proposal Schedule Plan — [Project Name]

**Prepared:** [Date]
**Prepared By:** [User / Company]
**Status:** Draft — Schedule Basis Document

---

## 1. Project Overview

**Project Name:** [name]
**Project Type:** [type extracted from bid docs]
**Location:** [location]
**Contract Duration:** [duration]
**Anticipated NTP:** [date]
**Substantial Completion:** [date]
**Final Completion:** [date]
**Liquidated Damages:** [amount and triggers]

---

## 2. Schedule Basis

### 2.1 Reference Schedules Analyzed
| # | Project Name | File | Activities | Duration | Rel. Ratio | Key Takeaway |
|---|-------------|------|-----------|----------|------------|--------------|
| 1 | [name] | [file] | [count] | [months] | [ratio] | [what we borrowed] |
| 2 | [name] | [file] | [count] | [months] | [ratio] | [what we borrowed] |

### 2.2 Bid Documents Analyzed
- [list of documents reviewed with key findings from each]

### 2.3 Schedule Assumptions
[All assumptions from the free-write section, formatted as a numbered list]

---

## 3. Work Breakdown Structure

### 3.1 WBS Structure
[The chosen WBS tree, fully indented, with WBS codes]

### 3.2 WBS Rationale
[Why this structure was chosen — references to sample schedules and scope]

---

## 4. Proposed Activity List by WBS Node

For each WBS node, list the proposed activities. This section provides the detail
needed for XER generation via the schedule-xer-generate skill.

**All activity names must follow Verb + Noun convention with no acronyms** — always spell
out full words (e.g., Tie Rebar, Pour Concrete, Erect Structural Steel, Install Roofing
Membrane, Frame Interior Walls, Rough In Heating Ventilation and Air Conditioning).

**All durations are in working days.** (XER files store durations in hours internally —
multiply days by 8 when writing to XER.)

### [WBS Node 1: e.g., Preconstruction]
| Activity Name | Duration (days) | Type | Duration Basis |
|--------------|----------------|------|---------------|
| Submit Shop Drawings | [days] | Task | [e.g., "Schedule A: 10 days for similar scope"] |
| Receive Building Permit | [days] | Milestone | [e.g., "Contract requirement"] |

### [WBS Node 2: e.g., Site Work]
| Activity Name | Duration (days) | Type | Duration Basis |
|--------------|----------------|------|---------------|
| Install Erosion Control | [days] | Task | [basis] |
| Excavate Building Pad | [days] | Task | [basis] |

[Continue for each WBS node...]

**Target Total Activities:** [number from Q13]

---

## 5. Logic Network Description

### 5.1 Phase-to-Phase Sequencing
[Major phase transitions and their relationship types]
- Preconstruction → Site Work: [FS / SS with lag]
- Site Work → Foundation: [relationship]
- Foundation → Structure: [relationship]
- Structure → Envelope: [relationship]
- Structure → MEP Rough-In: [relationship, e.g., SS with 2-week lag]
- MEP Rough-In → Finishes: [relationship]
- Finishes → Closeout: [relationship]

### 5.2 Within-Phase Logic Chains
Key sequences within each phase:

**Site Work:**
- Mobilize → Erosion Control → Clear & Grub → Excavate → Utilities → Backfill → Grade

**Foundation:**
- Excavate Footings → Form Footings → Rebar Footings → Pour Footings → Strip Footings → Form Walls → Rebar Walls → Pour Walls → Strip Walls → Waterproof → Backfill

**Structure:**
[Sequences based on Q8 answer]

**MEP:**
[Sequences based on Q9 answer]

**Finishes:**
[Typical finish sequence]

**Closeout:**
[Sequence based on Q10 answer]

### 5.3 Cross-Phase Ties
[Key relationships that span phases]
- e.g., "Roof Dry-In (Envelope) → MEP Rough-In Start (MEP): FS"
- e.g., "Underground Plumbing (MEP) SS to Foundation with 1-week lag"

### 5.4 Relationship Standards
- Default relationship type: FS
- Where SS is used: [list from Q9 and sequencing answers]
- Where FF is used: [if any]
- Target relationship ratio: [X.X]:1
- Lag usage: [guidelines from user responses]

---

## 6. Construction Sequence / Flow Plan

### 6.1 Overall Approach
[From Q6 — the overall construction flow narrative]

### 6.2 Phase-by-Phase Narrative

**Mobilization & Site Work**
[From Q7 — mobilization approach, site work sequence]

**Foundation & Structure**
[From Q8 — structural sequence, foundation approach]

**Building Envelope**
[Roofing, exterior walls, windows — based on sequencing discussion]

**MEP Rough-In**
[From Q9 — MEP coordination approach]

**Interior Finishes**
[Finishing sequence — based on flow discussion]

**Commissioning & Closeout**
[From Q10 — commissioning approach, punchlist, closeout]

---

## 7. Milestone Schedule

| Milestone | Target Timing | Type | Constraint | Source |
|-----------|--------------|------|------------|--------|
| NTP | [date] | Start Mile | SNET | Contract |
| [milestone] | Month [X] | Finish Mile | [if contract] | [Contract/Internal] |
| Substantial Completion | [date] | Finish Mile | FNET | Contract |
| Final Completion | [date] | Finish Mile | FNET | Contract |

---

## 8. Procurement & Long-Lead Items

| Item | Lead Time | Submittal By | Order By | Need On Site | Notes |
|------|-----------|-------------|----------|-------------|-------|
| [item] | [weeks] | Month [X] | Month [Y] | Month [Z] | [notes] |

---

## 9. Risk Register

| # | Risk Item | Impact | Likelihood | Mitigation | Schedule Impact |
|---|-----------|--------|-----------|------------|----------------|
| 1 | [risk] | [H/M/L] | [H/M/L] | [strategy] | [days/weeks] |

---

## 10. Calendar & Work Hours

**Standard Calendar:** [5-day / 6-day / 7-day]
**Work Hours:** [start time – end time]
**Weather Allowances:** [from Q17]
**Holidays:** [if known]
**Overtime Provisions:** [if applicable]

---

## 11. Scope & Subcontractor Summary

| Scope Item | Self-Perform / Sub | Subcontractor | Lead Time | Notes |
|------------|-------------------|---------------|-----------|-------|
| [scope] | [SP/Sub] | [name or TBD] | [if applicable] | [notes] |

---

## 12. Owner Requirements & Communication

[From free-write section 2 — formatted as a bulleted list]

---

## 13. Activity Naming & Detail Standards

**Naming Convention:** Verb + Noun, no acronyms — always spell out full words (e.g., Tie Rebar, Pour Concrete, Erect Structural Steel, Rough In Heating Ventilation and Air Conditioning). [Modifier preferences from Q12: area suffix, floor prefix]
**Activity Granularity:** [from Q13]
**Organization Method:** [from Q14]
**Target Activity Count:** [estimated from Q13]

---

## 14. Q&A Decision Log

[Complete log of all 20 questions and answers, preserved for reference]

---

*This schedule plan document serves as the basis for XER generation.
It should be reviewed and approved before proceeding to schedule creation.*
```

---

## Phase 7: XER Generation

After presenting the plan document, prompt the user:

```
The schedule plan document is complete and saved to:
  [project-folder]/Proposal Schedule/Schedule Plan - [Project Name].md

Would you like to proceed to generate the actual XER file using this plan?

If yes, I'll use the schedule-xer-generate skill with this plan document as the
scope input, along with the sample XER files as reference schedules. The generated
XER will be saved to:
  [project-folder]/Proposal Schedule/[Project Name].xer

The generated XER will implement the WBS structure, activity list, construction
sequence, milestones, and logic network described in this plan. All activities
will follow the Verb + Noun naming convention with no acronyms — always spelled
out (e.g., Tie Rebar, Pour Concrete, Erect Structural Steel). All durations in
the plan are in working days (converted to hours for XER storage).

After generation, I'll score the schedule using the schedule-quality-score skill
and iterate until it achieves an A grade.
```

If the user confirms:
1. Pass the plan document as the scope input to `schedule-xer-generate`
2. Pass the sample XER files as the reference schedules
3. Ensure all generated activity names follow Verb + Noun convention with no acronyms (spell out all words)
4. Convert all durations from working days (in plan document) to hours (days × 8) for XER storage
5. Apply `schedule-best-practices` guidance during generation:
   - Complete logic network (every activity has predecessor + successor)
   - FS >= 90% of relationships
   - Zero leads, minimal lags
   - No unnecessary hard constraints
   - Target relationship ratio >= 1.5:1
   - No non-procurement activities > 25 working days without justification (procurement activities are exempt)
5. Output the generated XER to `<project-folder>/Proposal Schedule/`
6. Proceed immediately to Phase 8

---

## Phase 8: Quality Scoring & Iteration

After XER generation, score the schedule using the `schedule-quality-score` skill and iterate until it achieves an **A grade** (90+ points).

### Step 1: Score the Generated Schedule

Run the `schedule-quality-score` skill on the generated XER file. This produces:
- A letter grade (A+ through D-)
- A numeric score (out of 100)
- Scored metric results (relationship types, float, critical path %, missing logic, relationship ratio, constraints)
- Informational metric results (convergence/divergence, dangling activities, high duration, lag, etc.)

### Step 2: Evaluate the Score

**If the schedule scores an A (90+):** Present the quality report to the user and confirm the schedule is complete.

```
The generated schedule scored [grade] ([score]/100). Here's the quality report:

[Full quality report from schedule-quality-score]

The schedule meets best practice standards. The XER file is saved to:
  [project-folder]/Proposal Schedule/[Project Name].xer
```

**If the schedule scores below an A:** Identify the specific metrics causing deductions and fix them.

### Step 3: Fix Identified Issues

For each metric with deductions, apply targeted fixes:

| Failing Metric | Automatic Fix | Ask User If... |
|---------------|--------------|----------------|
| **Missing Logic** (> 5%) | Add predecessor/successor relationships to dangling activities using logic patterns from plan document | Activities are ambiguous about where they belong in the sequence |
| **Relationship Types** (FS < 90%) | Convert non-FS relationships to FS where the SS/FF/SF isn't required by the construction sequence | Converting would break a sequencing decision from Q9 (MEP overlap) |
| **Constraints** (> 5%) | Remove non-contractual constraints, let logic drive dates | A constraint was added for a reason the user specified |
| **High Float** (> 5% with float > 44d) | Tighten logic network — add missing cross-phase ties, reduce excessive parallel paths | High float is intentional (management reserve, long-lead buffer) |
| **Relationship Ratio** (< 1.5:1) | Add missing relationships — cross-phase ties, inter-area dependencies | Schedule needs more activities (too coarse) rather than more relationships |
| **High Duration** (> 5% non-procurement activities with duration > 25 days) | Break long activities into sub-activities. Procurement activities (submittals, fabrication, delivery) are exempt — do not count them. | User intentionally wanted coarse granularity for certain phases |
| **Lags** (> 5%) | Replace lag with explicit activities (e.g., replace "cure time lag" with a "Cure Concrete" activity) | Lag represents a real waiting period that's better as lag than an activity |
| **Leads** (any) | Convert leads to positive lag or restructure the relationship | N/A — leads are always removed |
| **Negative Float** (any) | Adjust durations or logic to resolve; check if contract duration from Q1 is infeasible | The contract duration is genuinely too short — user needs to know |

### Step 4: Ask Follow-Up Questions When Needed

If a fix requires user input (see "Ask User If..." column above), ask targeted follow-up questions:

```
The schedule scored [grade] ([score]/100). To reach an A, I need to address:

1. [Metric]: [specific issue]. [Question for user]
2. [Metric]: [specific issue]. [Question for user]

Example:
"The schedule scored B+ (88/100). To reach an A, I need to address:

1. **Missing Logic (7%):** 12 activities have no successor. Most are in the Finishes
   phase — should 'Install Ceiling Grid' connect to 'Install Ceiling Tile', or are
   these parallel by area?

2. **High Float (8%):** 15 activities in Preconstruction have float > 44 days. This
   is because procurement activities start early but installation is months away.
   Should I add a tighter constraint on when submittals start, or is the float
   intentional buffer?"
```

### Step 5: Regenerate and Re-Score

After applying fixes (automatic + user-directed):
1. Regenerate the XER file with the corrections
2. Re-score using `schedule-quality-score`
3. If still below A, repeat Steps 3-5
4. Present the final quality report when A is achieved

### Iteration Guardrails

- **Maximum 3 iterations.** If the schedule cannot reach an A after 3 rounds, present the best score achieved, explain the remaining issues, and ask the user if they want to accept the current grade or continue manually.
- **Never sacrifice schedule accuracy for score.** If a best-practice violation exists because the construction sequence genuinely requires it (e.g., an SS relationship for overlapping MEP trades), document it as an accepted deviation rather than forcing a change that misrepresents the plan.
- **Track changes between iterations.** Show the user what changed in each round:

```
## Iteration [N] Results

**Previous Score:** [grade] ([score]/100)
**Current Score:** [grade] ([score]/100)

**Changes Made:**
- Added [X] successor relationships to resolve missing logic (7% → 3%)
- Converted [Y] SS relationships to FS in non-critical areas (FS 85% → 92%)
- Split [Z] high-duration activities into sub-activities (high duration 8% → 3%)

**Remaining Deductions:**
- [metric]: [value] — [reason it remains / accepted deviation]
```

### Final Deliverables

When the schedule achieves an A grade (or the user accepts the current grade after 3 iterations):

1. **XER file** saved to `<project-folder>/Proposal Schedule/[Project Name].xer`
2. **Schedule Plan document** saved to `<project-folder>/Proposal Schedule/Schedule Plan - [Project Name].md`
3. **Quality Report** presented to the user showing the final grade, all metric scores, and any accepted deviations
4. Summary of what was borrowed from each sample schedule and how the bid docs shaped the plan
