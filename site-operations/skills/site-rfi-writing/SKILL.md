---
name: site-rfi-writing
description: >
  Guide RFI writing through an interactive Q&A process that produces clear, actionable Requests for
  Information. Use this skill whenever the user asks to "write an RFI", "draft an RFI", "submit an RFI",
  "create an RFI", "I have a question for the architect", "I need clarification on the drawings",
  "the specs are unclear", "conflicting details", "missing information on the plans", or mentions
  "RFI" in the context of construction document clarification. Also trigger when the user says
  "I can't figure out what the detail is showing", "the plans and specs don't match", "there's a
  conflict between drawings", "what does the architect mean by this", or "I need a design clarification".
  Before writing the RFI, the skill searches local project files and optionally Procore documents to
  see if the answer already exists — the best RFI is the one you don't have to send. If no answer is
  found, the skill walks through structured questions to build a complete RFI with proper spec references,
  drawing references, suggested resolution, and impact assessment. Output as formatted markdown or push
  directly to Procore via Zapier MCP integration (if configured).
---

# RFI Writing Assistant

This skill guides users through writing effective Requests for Information (RFIs) for construction projects. It follows the principle that **no RFI is the best RFI** — before drafting anything, it first attempts to find the answer in existing project documents. Only when the information genuinely cannot be found does it proceed to build a well-crafted, actionable RFI through interactive Q&A.

## Philosophy: No RFI Is the Best RFI

RFIs take time to write, route, and answer. Every unnecessary RFI slows down the project. Before creating an RFI:

1. **Search the contract documents first.** The answer is often already in the plans or specs — just in a different location than expected.
2. **Check related details and cross-references.** Architectural details reference structural, MEP references architectural — the answer may live in another discipline's drawings.
3. **Read the spec section carefully.** Specification language is precise. The answer may be in a paragraph the user hasn't read yet.
4. **Only write the RFI if the information is genuinely missing, conflicting, or ambiguous** in the contract documents.

---

## Workflow Overview

1. **Understand the question** — Ask what the user is confused about
2. **Search for the answer first** — Check local files, suggest where to look, optionally search Procore
3. **If answer found** — Present it, confirm the RFI is no longer needed
4. **If RFI needed** — Interactive Q&A to build out all RFI fields
5. **Draft and review** — Present the formatted RFI, iterate with the user
6. **Output** — Formatted markdown OR push to Procore as a draft (if MCP configured)

---

## Phase 1: Understand the Question

Start by asking the user to describe what they need clarification on. Ask these questions one or two at a time — do not dump them all at once.

### Opening prompt:

```
What do you need clarification on? Describe the issue in your own words — what are you
trying to build or install, and what's unclear about the contract documents?
```

### Follow-up questions (as needed):

- **What trade/discipline does this relate to?** (structural, architectural, mechanical, electrical, plumbing, fire protection, civil, landscape, etc.)
- **What area or location on the project?** (building, floor, room, grid lines, elevation)
- **Do you have a specific drawing or spec section where you noticed the issue?** (e.g., "Detail 3 on A5.01" or "Spec Section 07 92 00, paragraph 2.1.A")
- **What type of issue is this?**
  - Missing information — something not shown or specified
  - Conflicting information — two documents say different things
  - Ambiguous information — could be interpreted multiple ways
  - Design clarification — need the designer to confirm intent

---

## Phase 2: Search for the Answer First

Before writing the RFI, attempt to find the answer in available project documents. Use two search strategies in parallel.

### Strategy A: Search the Project Folder

This skill is typically used from within a Claude Code session with a local project folder selected. Search the conversation's project folder for plans, specs, and contract documents that might contain the answer.

**Glob patterns to search:**

```
**/*.pdf
**/*.PDF
**/Specifications/**
**/Specs/**
**/Plans/**
**/Drawings/**
**/Contract Documents/**
**/Project Documents/**
**/Submittals/**
**/Addenda/**
```

If PDF files are found that match the relevant discipline or spec section, read them and search for the answer to the user's question. For example, if the user asks about joint sealants, search for files containing "sealant", "07 92 00", or "joint" in their names or content.

If no project documents are available in the folder, skip to Strategy B and suggest where to look based on domain knowledge.

### Strategy B: Common Document Locations

Even if no local files are available, suggest where the answer might be found based on the type of question. Use this knowledge base of common locations:

**Architectural:**
- Wall types and assemblies → A2.xx series (wall sections), A5.xx (wall details)
- Door and window details → A4.xx series, door/window schedules on A1.xx or A6.xx
- Finish details → A6.xx series, finish schedule
- Roof details → A5.xx series (typically A5.01-A5.03)
- Waterproofing/flashing → Details often on A5.xx, but spec in Division 07

**Structural:**
- Connection details → S5.xx series
- Reinforcement → S2.xx (foundation), S3.xx (framing), S4.xx (details)
- Embed plates → S4.xx or S5.xx details, referenced from plans

**MEP:**
- Equipment schedules → Usually on first or last sheet of each discipline
- Riser diagrams → P1.01 (plumbing), M1.01 (mechanical), E1.01 (electrical)
- Control sequences → Spec Division 23 (HVAC), often Section 23 09 00

**Specifications by common question type:**

| Topic | Spec Section |
|-------|-------------|
| Joint sealants | 07 92 00 |
| Waterproofing | 07 10 00 – 07 19 00 |
| Concrete (cast-in-place) | 03 30 00 |
| Concrete (precast) | 03 40 00 |
| Masonry | 04 20 00 |
| Structural steel | 05 12 00 |
| Miscellaneous metals | 05 50 00 |
| Roofing | 07 50 00 series |
| Doors/frames/hardware | 08 11 00, 08 14 00, 08 71 00 |
| Drywall/framing | 09 21 16 (framing), 09 29 00 (gypsum board) |
| Painting | 09 91 00 or 09 91 23 |
| Fire protection | 21 00 00 series |
| Plumbing | 22 00 00 series |
| HVAC | 23 00 00 series |
| Electrical | 26 00 00 series |

Present these suggestions to the user:

```
Before we write an RFI, let's make sure the answer isn't already in the contract
documents. Based on your question about [topic], here are the most likely places
to find the answer:

- **Drawing:** [suggested sheet numbers and detail references]
- **Specification:** [suggested spec section and paragraph]
- **Also check:** [cross-references to other disciplines]

Have you already checked these locations? If you have the project documents
available locally, I can search them for you.
```

### Phase 2 Resolution

If the answer is found in any of these searches, present it clearly:

```
I found what appears to be the answer to your question:

[Present the relevant information with document reference]

**Source:** [Drawing number, spec section, or document name]

Does this resolve your question, or do you still need to submit an RFI?
```

If the user confirms the answer is sufficient, the workflow ends here. No RFI needed.

---

## Phase 3: Build the RFI Through Q&A

If the answer was not found or the user confirms the RFI is still needed, proceed with structured Q&A to gather all necessary information. Ask these questions progressively — not all at once.

### 3.0 Check for Duplicate RFIs

Before drafting, confirm this question hasn't already been asked:

```
Before we write this RFI, have you checked your project's RFI log to make
sure this question hasn't already been submitted? Duplicate RFIs waste
everyone's time and make the team look disorganized.

Check for:
- Similar subject matter in the same area/location
- RFIs referencing the same drawing or spec section
- RFIs from other trades that may have already asked this question
```

If the user confirms a similar RFI already exists, help them determine whether the existing RFI covers their question or if a new one is still needed (e.g., different location, different aspect of the same detail).

### 3.1 Subject Line

Help the user craft a clear, specific subject line. A good subject line includes the **location/area** and the **topic**:

```
Let's start with the subject line. A good RFI subject includes WHERE and WHAT.

Examples:
- "Bldg A, Level 2 — Wall Type W4 Head Detail at Curtain Wall Intersection"
- "Parking Garage Grid B-3 — Conflicting Slab Edge Reinforcement Details"
- "Roof Level — Flashing Detail at Parapet Cap, Detail 5/A5.02"

Based on what you've told me, here's a draft subject:
  "[Generated subject based on earlier conversation]"

Does this work, or would you like to adjust it?
```

### 3.2 Question Body

Guide the user to write a single, specific, unambiguous question. Enforce the **one question per RFI** rule:

```
Now the actual question. The best RFI questions are:
- ONE question only (if you have multiple, we'll create separate RFIs)
- Specific enough that the designer knows exactly what to look at
- References the exact document, sheet, detail, and paragraph

Draft the question starting with something like:
  "Please clarify..." or "Please confirm..." or "Please provide..."

What is the specific question you need answered?
```

If the user provides multiple questions, split them:

```
I see two distinct questions here. Best practice is one question per RFI —
it's easier to track, assign, and close. Let's create this RFI for the first
question, and I'll help you draft a second RFI for the other.
```

### 3.3 Contract Document References

Ask for specific references to anchor the RFI to the contract documents:

```
What contract document references should we include?

- **Drawing number:** (e.g., A5.01, S3.02)
- **Detail or section call:** (e.g., Detail 3/A5.01, Section A/S3.02)
- **Spec section:** (e.g., Section 07 92 00, paragraph 2.1.A)
- **Addenda:** (e.g., Addendum No. 3, Bulletin 12)

These references are critical — they tell the designer exactly where to look.
```

### 3.4 Background and Context

Gather enough context to make the RFI self-contained:

```
Provide any additional context that would help the designer understand
the question:

- What triggered this question? (e.g., "We're about to install this
  component and need to know before we proceed")
- What have you already checked? (e.g., "We reviewed sheets A5.01
  and A5.02 but neither shows this condition")
- Is there a conflict? If so, describe both conflicting items with
  their document references.
```

### 3.5 Suggested Resolution

This is one of the most important fields — an RFI with a suggested resolution gets answered faster:

```
What do you think the answer SHOULD be? Providing a suggested resolution
significantly speeds up response time — the designer can simply agree
or correct your suggestion rather than drafting a response from scratch.

For example:
- "We suggest using Detail 5/A5.01 at this condition, modified to
   accommodate the 6" CMU wall instead of the 4" shown."
- "Based on similar conditions on sheets S3.01-S3.03, we believe the
   intent is #5 @ 12" o.c. each way."
- "We recommend extending the waterproof membrane 6" past the face
   of the wall per manufacturer's recommendations."

What is your suggested resolution?
```

### 3.6 Impact Assessment

Determine cost and schedule impact:

```
What is the impact if this question is not answered promptly?

**Schedule impact:**
- Is this on or near the critical path?
- How many days of delay could result?
- What work is being held pending this answer?

**Cost impact:**
- Could the answer change the cost of the work?
- Is there a more/less expensive option depending on the answer?
- Are there remobilization costs if work is stopped?
```

Map the responses to these values:
- `cost_impact_status`: `"Yes"`, `"No"`, `"TBD"`, or `"N/A"`
- `schedule_impact_status`: `"Yes"`, `"No"`, `"TBD"`, or `"N/A"`

### 3.7 Assignment and Due Date

```
Who should respond to this RFI?

- **Responsible contractor:** Which company is responsible for this
  scope of work? (e.g., "ABC Concrete, Inc.")
- **Assignee(s):** Who specifically should answer? (e.g., the architect,
  structural engineer, MEP engineer, owner)
- **Due date:** When do you need the answer? Consider:
  - When does the affected work start?
  - Allow reasonable review time (typically 7-14 days per contract)
  - What does your contract say about RFI response time?
```

---

## Phase 4: Draft and Review

Compile all gathered information into a formatted RFI draft and present it for review.

### Draft Format

```markdown
## RFI: [Subject Line]

**Drawing Reference:** [Drawing number(s)]
**Detail/Section:** [Detail references]
**Specification Section:** [Spec section and paragraph]
**Location:** [Building/floor/area/grid lines]

---

### Background

[Context paragraph — what triggered the question, what has been checked,
what the conflict or ambiguity is]

### Question

[Single, specific, unambiguous question]

### Contract Document References

[List each referenced document with the specific paragraph, detail, or
note that is relevant to the question]

### Suggested Resolution

[What the contractor believes the answer should be, with justification]

### Impact

**Schedule Impact:** [Status] — [Description of affected work and days at risk]
**Cost Impact:** [Status] — [Description of potential cost change]

---

**Requested Response By:** [Due date]
**Responsible Contractor:** [Company name]
**Assigned To:** [Person/firm who should answer]
```

### Review Checklist

Before finalizing, verify with the user:

- Subject line includes location AND topic
- Question is a single, specific question
- At least one contract document is referenced (drawing or spec section)
- Suggested resolution is included
- Impact is stated factually (no emotional language)
- Due date is reasonable per contract requirements
- The right person/firm is assigned to respond

```
Here's the drafted RFI. Please review:

[Present the draft]

Anything you'd like to change? I can adjust the subject, question,
references, suggested resolution, impact statement, or assignment.
```

Iterate until the user is satisfied.

---

## Phase 5: Output

The default output is formatted markdown that can be copied into any project management system.

### Formatted Markdown (Default)

Output the final RFI using the draft format from Phase 4. This is the standard output that works with any workflow — copy it into Procore, PlanGrid, Submittal Exchange, email, or any other system.

### Push to Procore (If Zapier MCP Configured)

If the `mcp__claude_ai_Zapier__procore_create_rfi` tool is available, offer to push directly:

```
Would you also like me to create this RFI as a draft in Procore?
I can push it directly — you'll be able to review and send it from there.
```

**Before calling the tool, ask for:**
- Procore project name or ID
- Confirm saving as **draft** (default: yes)

**Field mapping:**

| RFI Field | Procore Parameter |
|-----------|-------------------|
| Subject line | `subject` |
| Background + question | `question_body` |
| Drawing number | `drawing_number` |
| Spec section | `specification_section` |
| Suggested resolution | `reference` |
| Cost impact status | `cost_impact_status` |
| Cost impact amount | `cost_impact_value` |
| Schedule impact status | `schedule_impact_status` |
| Schedule impact days | `schedule_impact_value` |
| Assigned reviewer(s) | `assignees` |
| Responsible contractor | `responsible_contractor` |
| Due date | `due_date` |
| Draft mode | `draft` (always `"true"` by default) |
| Project | `project` |

**Required Zapier fields:**
- `instructions`: `"Create a new RFI in the specified Procore project with the provided details. Save as draft so the user can review before sending."`
- `output_hint`: `"Return the RFI number, subject, status, and URL so the user can find it in Procore"`

After the tool returns, confirm success:

```
Your RFI has been created as a draft in Procore:

- **RFI Number:** [from response]
- **Subject:** [subject]
- **Status:** Draft

Log into Procore to review the RFI, attach any markups or photos,
and send it when ready.
```

---

## RFI Best Practices Reference

### Writing Quality

1. **One question per RFI.** Multiple questions in a single RFI lead to partial answers, confusion about closure status, and difficulty tracking. If there are related questions, create separate RFIs and reference each other.

2. **Reference specific contract documents.** Never write "per the plans" or "per the specs." Instead: "Per Detail 3/A5.01" or "Per Section 07 92 00, paragraph 2.1.A." Include the specific paragraph, note number, or detail callout.

3. **Always include a suggested resolution.** This speeds up response time dramatically. The designer can confirm, modify, or reject the suggestion rather than composing an answer from scratch. Frame it as: "We suggest..." or "Based on similar conditions, we believe the intent is..."

4. **State impact factually.** "Level 2 framing cannot proceed until this is resolved. Framing is scheduled to start March 15 and is on the critical path. A 5-day delay to this response would push the drywall milestone by 5 days." Do not write: "This is URGENT and we NEED an answer IMMEDIATELY or the whole project will be delayed!!!"

5. **Be factual, not emotional.** RFIs become part of the project record and may be referenced in claims or disputes. Keep the tone professional, factual, and neutral.

6. **Include markups and photos when available.** If the user has a photo of the field condition or a markup showing the conflict, mention that these should be attached.

7. **Clear subject line format.** Include the location/area AND the topic. Good: "Bldg A Level 2 Grid C — W4 Head Detail at Curtain Wall." Bad: "Question about wall detail."

### Timing and Process

8. **Submit early.** Don't wait until work is about to start. Review drawings and specs during pre-construction and submit RFIs as soon as questions arise.

9. **Allow contractual response time.** Most contracts specify 7-14 days for RFI responses. Set the due date accordingly, and note in the impact section if the work will be delayed.

10. **Track open RFIs.** An RFI without a response is a risk. Flag overdue RFIs and escalate per the contract.

### Common RFI Pitfalls to Avoid

- **Asking questions already answered in the documents.** This is why Phase 2 exists — search first.
- **Asking multiple questions in one RFI.** Split them.
- **Vague references.** "The drawings show..." — which drawing? Which detail?
- **No suggested resolution.** Forces the designer to start from scratch.
- **Emotional language.** Keep it professional.
- **Using RFIs to document scope changes.** That's a change order, not an RFI.
- **Using RFIs for scheduling or coordination issues.** Those belong in meeting minutes or correspondence.

---

## Procore Integration — Learn More

This skill supports optional direct integration with Procore via the Zapier MCP. When configured, you can push drafted RFIs directly into Procore as drafts — no copy-pasting required.

**What you get with Procore integration:**
- Create RFI drafts directly in your Procore project
- All fields (subject, question, references, impact, assignments) are mapped automatically
- RFIs are saved as drafts so you can review, attach markups/photos, and send from Procore

**Interested in setting this up?** The integration uses Anthropic's MCP (Model Context Protocol) with a Zapier connector for Procore. Contact Camron Walker for setup guidance and configuration help.
