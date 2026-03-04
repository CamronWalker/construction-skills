---
name: pm-change-event
description: >
  Analyze incoming change events and distribute scope to affected subcontractors through an
  interactive workflow. Use this skill whenever the user asks to "process a change event",
  "distribute a change", "break down a PR", "break down a CCD", "analyze a change order",
  "who does this change affect", "which subs need to price this", "send this change to subs",
  "route a bulletin", "ASI distribution", "owner change", "design change breakdown", or mentions
  "change event", "proposal request", "contract change directive", "ASI", or "bulletin" in
  the context of distributing scope to subcontractors. Also trigger when the user says
  "I got a change from the owner", "the architect issued a revision", "we need to price this
  change", "break this down by trade", "figure out who's affected by this change", or
  "send this out for pricing". The skill reads the source document, identifies affected trades,
  maps scope per subcontractor, and outputs a formatted change event distribution summary.
  Output as formatted markdown or push directly to Procore via Zapier MCP integration
  (if configured).
---

# Change Event Distribution Assistant

This skill helps general contractor project managers analyze incoming change events — proposal requests (PRs), contract change directives (CCDs), architect's supplemental instructions (ASIs), bulletins, and owner-directed changes — and determine which subcontractors are affected, what scope each sub is taking on, and how to distribute the change for pricing or execution.

## Philosophy: Know Your Subs' Scopes Before You Route the Change

A change event sent to the wrong subcontractor wastes time. A change event sent without clear scope descriptions generates confusion, phone calls, and inflated pricing. Before distributing any change:

1. **Read the full change document.** Understand exactly what is changing — new scope, deleted scope, revised scope, or clarification of existing scope.
2. **Map every change item to a trade.** Use the spec sections, drawing disciplines, and scope breakdown to identify every subcontractor who touches the affected work.
3. **Write clear scope descriptions per sub.** Each subcontractor should receive only the portions of the change relevant to their contract — not the entire document with "figure out what's yours."
4. **Flag overlaps and gaps.** Where scope could belong to multiple trades, call it out explicitly rather than leaving it ambiguous.

---

## Workflow Overview

1. **Receive the change document** — User provides the source document (email, PR, CCD, ASI, bulletin, or pasted text)
2. **Analyze the change** — Read and categorize every scope item in the change
3. **Identify affected subcontractors** — Map scope items to trades using project context
4. **Draft scope descriptions per sub** — Write what each sub is responsible for from this change
5. **Review and refine** — Present the distribution, iterate with the user
6. **Output** — Formatted markdown summary OR push to Procore as a change event

---

## Phase 1: Receive the Change Document

Start by collecting the source material. Ask these questions progressively — not all at once.

### Opening prompt:

```
What change document do you need to process? You can:

- Paste the text of a PR, CCD, ASI, bulletin, or email
- Upload a PDF or image of the change document
- Describe the change verbally and I'll help structure it

What type of change is this?
- **PR (Proposal Request)** — Owner/architect asking the GC to price a potential change
- **CCD (Contract Change Directive)** — Direction to proceed with the change, pricing to follow
- **ASI (Architect's Supplemental Instruction)** — Design clarification or minor change,
  may or may not have cost impact
- **Bulletin / Revision** — Revised drawings or specs issued during construction
- **Owner-directed change** — Direct instruction from the owner
- **Field condition** — Unforeseen condition discovered during construction
- **Code/regulatory change** — Required change due to code official or AHJ direction
```

### Follow-up questions (as needed):

- **What is the project?** (name, number — needed for context and Procore integration)
- **What is the change event number or reference?** (PR-XXX, CCD-XXX, ASI-XXX, Bulletin XX, etc.)
- **Date received?**
- **Who issued it?** (architect, owner, engineer, etc.)
- **Do you have a project subcontractor list or scope breakdown I can reference?** (CSV, list, or description of who has what scope)
- **Is there a response deadline?** (date by which pricing or acknowledgment is needed)

---

## Phase 2: Analyze the Change

Read the entire change document and extract every discrete scope item. For each item, identify:

1. **What is changing** — New work, deleted work, revised work, or clarification
2. **Which discipline/trade area** — Architectural, structural, mechanical, electrical, plumbing, fire protection, civil, etc.
3. **Which spec sections are affected** — Map to CSI divisions
4. **Which drawings are affected** — Sheet numbers, detail references
5. **Location on the project** — Building, floor, area, grid lines

Present the analysis as a numbered list:

```
Based on my review of [document reference], here are the scope items I've identified:

1. [Scope item description] — [Discipline] — [Drawing/spec reference]
2. [Scope item description] — [Discipline] — [Drawing/spec reference]
3. [Scope item description] — [Discipline] — [Drawing/spec reference]
...

Did I capture everything? Are there any items I missed or mischaracterized?
```

**Important**: Ask the user to confirm the scope item list before proceeding. Changes are frequently more complex than they appear — a single ASI can affect 5-10 trades across dozens of scope items.

---

## Phase 3: Identify Affected Subcontractors

### 3.1 Use Project Context First

If the user has provided a subcontractor list, scope breakdown, or buyout log, use it as the primary source for mapping scope items to specific companies. Every project's scope splits are different — one project may have the GC self-performing drywall while another has it subcontracted.

If project context has not been provided, ask:

```
To map these changes to the right subcontractors, I need to know who has what
scope on this project. Can you provide any of the following?

- A subcontractor list with their scope descriptions
- A buyout log or commitment list
- A cost code / scope breakdown
- Or just tell me which trades are subcontracted vs. self-performed
```

### 3.2 Trade Mapping Reference

Use this reference table when project-specific information is not available, or to validate and supplement the project subcontractor list.

| CSI Division | Typical Trade | Common Scope Items in Changes |
|---|---|---|
| 01 | General Conditions (GC) | Temporary facilities, cleanup, general requirements |
| 02 | Existing Conditions | Demolition, abatement, earthwork (sometimes) |
| 03 | Concrete | Foundations, SOG, elevated slabs, formwork, rebar, finishing |
| 04 | Masonry | CMU, brick veneer, stone, mortar, grout, reinforcement |
| 05 | Metals | Structural steel, misc metals, railings, stairs, embeds, lintels |
| 06 | Wood/Plastics/Composites | Rough carpentry, finish carpentry, millwork, casework |
| 07 | Thermal/Moisture Protection | Roofing, waterproofing, insulation, sealants, fireproofing |
| 08 | Openings | Doors/frames/hardware, windows, glazing/curtain wall, storefronts |
| 09 | Finishes | Drywall/ACT, flooring, tile, painting, wall coverings |
| 10 | Specialties | Toilet accessories, signage, lockers, fire extinguishers |
| 11 | Equipment | Kitchen equipment, lab equipment, athletic equipment |
| 12 | Furnishings | Furniture, window treatments, manufactured casework |
| 13 | Special Construction | Pre-engineered structures, pools, clean rooms |
| 14 | Conveying | Elevators, escalators, dumbwaiters |
| 21 | Fire Suppression | Sprinkler systems, standpipes, fire pumps |
| 22 | Plumbing | Piping, fixtures, water heaters, med gas |
| 23 | HVAC | Ductwork, piping, equipment, controls, TAB |
| 25 | Integrated Automation | BAS/BMS, controls integration |
| 26 | Electrical | Power distribution, lighting, branch wiring, generators |
| 27 | Communications | Low voltage, data/telecom, AV, security, fire alarm |
| 28 | Electronic Safety/Security | Access control, CCTV, intrusion detection |
| 31 | Earthwork | Grading, excavation, fill, compaction |
| 32 | Exterior Improvements | Paving, curbs, sidewalks, landscaping, irrigation |
| 33 | Utilities | Site utilities, storm, sanitary, water, gas |

### 3.3 Flag Scope Overlaps

These are the most commonly ambiguous areas where a change item could belong to multiple subcontractors. Flag any that apply:

| Change Item | Could Belong To | Resolution Approach |
|---|---|---|
| Blocking/backing in walls | Drywall or Carpentry | Check who carries Division 06 vs 09 |
| Firestopping / firecaulk | Fire protection, drywall, or each penetrating trade | Check spec section 07 84 00 assignment |
| Painting of exposed structure | Painting or Steel | Check if 09 91 00 includes structural steel |
| Seismic bracing of MEP | Each MEP trade or a specialty sub | Check individual MEP contracts |
| Roof penetrations / flashing | Roofing or the penetrating trade | Check Division 07 scope split |
| Electrical for mechanical equip | Electrical or HVAC sub | Check "power wiring to mechanical equipment" in Division 26 |
| Controls / BAS | HVAC, electrical, or controls sub | Check Division 25 assignment |
| Excavation for utilities | Sitework or each utility trade | Check Division 31 vs 33 scope split |
| Insulation on piping/ductwork | Insulation sub, plumbing, or HVAC | Check Division 07 21 00 vs 22/23 |
| Temporary protection | GC or each trade | Check general conditions scope |
| Caulking / sealants | Each trade at their work or a sealant sub | Check Division 07 92 00 assignment |
| Rough-in for owner equipment | Plumbing, electrical, or GC | Check Division 11 coordination requirements |

---

## Phase 4: Draft Scope Descriptions Per Sub

For each affected subcontractor, write a clear scope description that includes:

1. **What they need to do** — Add, delete, or revise specific scope items
2. **Where** — Location on the project
3. **Reference documents** — Which drawings, specs, or change document pages apply to them
4. **Action required** — Price the change, proceed with the work, or both

### Distribution Template

```markdown
## Change Event Distribution: [CE Number] — [Title]

**Source Document:** [PR-XXX / CCD-XXX / ASI-XXX / Bulletin XX]
**Date Received:** [date]
**Issued By:** [architect / owner / engineer]
**Change Type:** [PR / CCD / ASI / Bulletin / Field Condition / Code Change]
**Response Due:** [date, if applicable]

---

### Affected Subcontractors

| # | Subcontractor | Trade | Scope Description | Reference | Action Required |
|---|---|---|---|---|---|
| 1 | [Company Name] | [Trade] | [What they need to add/delete/revise] | [Drawing/spec refs] | [Price / Proceed / Both] |
| 2 | [Company Name] | [Trade] | [What they need to add/delete/revise] | [Drawing/spec refs] | [Price / Proceed / Both] |
| 3 | [Company Name] | [Trade] | [What they need to add/delete/revise] | [Drawing/spec refs] | [Price / Proceed / Both] |

### Items Retained by GC
[Any scope items the GC is self-performing, or "None — all items distributed to subcontractors"]

### Scope Overlaps / Items Requiring Clarification
[Any items where trade assignment is ambiguous — flag for PM to resolve with the affected subs]

### Estimated Impact Summary

| Category | Detail |
|---|---|
| Schedule Impact | [Description or TBD — which activities are affected, critical path impact] |
| Estimated Cost Range | [If known, or "Pending sub pricing"] |
| Critical Path Affected? | [Yes / No / TBD] |
| Response Deadline | [Date subs need to return pricing or acknowledge] |
```

### Review with User

Present the draft and ask for confirmation:

```
Here's the change event distribution. Please review:

[Present the draft]

Things to verify:
- Are the subcontractor names/companies correct?
- Is the scope split accurate for your project's contracts?
- Are there any trades I missed?
- Do the drawing/spec references look right?
- Is the action required (price vs. proceed) correct for each sub?
- Is the response deadline reasonable?

What would you like to adjust?
```

Iterate until the user is satisfied.

---

## Phase 5: Output

The default output is formatted markdown that can be copied into any project management system or emailed to subcontractors.

### Formatted Markdown (Default)

Output the final distribution summary using the template from Phase 4. This is the standard output that works with any workflow — copy it into Procore, email it to subs, or save it to the project folder.

### Push to Procore (If Zapier MCP Configured)

If the `mcp__claude_ai_Zapier__procore_create_change_event` tool is available, offer to push directly:

```
Would you also like me to create this as a change event in Procore?
I can push it directly — you'll be able to review and update it from there.
```

**Before calling the tool, ask for:**
- Procore project name or ID
- Confirm status (default: Open)

**Field mapping:**

| Distribution Field | Procore Parameter | Notes |
|---|---|---|
| CE title | `title` | From the change document title/subject |
| Full distribution summary | `description` | The complete distribution breakdown as formatted text |
| Change type / reason | `change_order_change_reason` | Maps to: "Owner Change", "Design Change", "Field Condition", "Regulatory Change", etc. |
| Status | `change_event_status` | Default: "Open" |
| Source document type | `event_type` | PR, CCD, ASI, Bulletin, etc. |
| Scope summary | `event_scope` | Summary of overall scope of the change |
| Estimated cost | `estimated_cost_amount` | If available from sub pricing or estimate |
| Project | `project` | Procore project name or ID |

**Required Zapier fields:**
- `instructions`: `"Create a new change event in the specified Procore project. Include the full distribution summary in the description so the PM can see which subs are affected and what scope each has. Set status to Open."`
- `output_hint`: `"Return the change event number, title, status, and URL so the user can find it in Procore"`

After the tool returns, confirm success:

```
Your change event has been created in Procore:

- **Change Event Number:** [from response]
- **Title:** [title]
- **Status:** Open

Log into Procore to:
- Attach the original change document (PR/CCD/ASI/bulletin)
- Create individual change order requests (CORs) for each affected sub
- Link to the relevant commitment contracts
```

**Note:** The Zapier MCP tool creates the top-level change event in Procore. Individual Change Order Requests (CORs) for each subcontractor need to be created within Procore under that change event — the distribution summary in the description tells you exactly which CORs to create and what scope to include in each.

---

## Change Event Best Practices Reference

### Distribution Quality

1. **One scope description per sub.** Each subcontractor should receive a clear, self-contained description of their portion of the change — not the entire document with "see what applies to you."

2. **Reference specific contract documents.** Always cite the specific drawing sheets, detail numbers, and spec sections that are changing. "Revised per ASI-05" is not enough — "Revised head detail at curtain wall per Detail 3/A5.01 Rev 2 (ASI-05)" gives the sub what they need.

3. **Flag scope overlaps explicitly.** If a change item could belong to drywall or carpentry, say so. Don't silently assign it to one and create a gap or overlap.

4. **Distinguish between "price" and "proceed."** A PR requires pricing — the sub should not start work. A CCD directs work to proceed while pricing is resolved. Make the action required crystal clear.

5. **Include schedule context.** If the change affects critical path work or has a deadline for pricing, say so. "Please return pricing by [date] — this work area is scheduled to start [date]."

6. **Track responses.** Every sub on the distribution list needs to respond — even if their answer is "no impact to our scope." A non-response is not a confirmation.

7. **Link back to the source.** Every change event distribution should reference the originating PR, CCD, ASI, or bulletin number for traceability.

### Change Event Types Quick Reference

| Type | Abbreviation | Meaning | Sub Action |
|---|---|---|---|
| Proposal Request | PR | Owner/architect asking GC to price a potential change | Price only — do NOT proceed with work |
| Contract Change Directive | CCD | Direction to proceed, pricing negotiated after | Proceed with work, submit pricing |
| Architect's Supplemental Instruction | ASI | Design clarification or minor revision | Evaluate — may or may not have cost impact |
| Bulletin / Revision | Bulletin | Revised drawings or specs | Evaluate scope and cost impact |
| Owner Directive | OD | Direct owner instruction | Proceed per direction, document cost impact |
| Field Condition | FC | Unforeseen condition discovered in the field | Document, notify owner, price impact |
| Code/Regulatory Change | Code | Required by code official or AHJ | Proceed as required, document cost impact |

### Common Pitfalls

- **Sending the entire change document to all subs.** This creates confusion and results in subs ignoring changes that affect them or pricing work that isn't theirs.
- **Not tracking which subs have responded.** Every sub on the distribution list needs to respond — even if their answer is "no impact to our scope."
- **Ignoring schedule impact.** Cost gets all the attention, but schedule impact from changes is often more expensive than the direct cost.
- **Not linking back to the source document.** Every change event should reference the originating PR, CCD, ASI, or bulletin number for traceability.
- **Pricing CCDs late.** CCDs direct the work to proceed — but the pricing still needs to happen. Don't let CCD pricing slip because the work is already underway.
- **Missing the response deadline.** If the owner gave you 10 days to price a PR, your subs need their portion with enough lead time to respond. Don't send the distribution on day 9.
- **Not separating add/deduct items.** If a change adds some scope and deletes other scope, make sure each sub understands what they're adding and what they're crediting back.

---

## Procore Integration — Learn More

This skill supports optional direct integration with Procore via the Zapier MCP. When configured, you can push change events directly into Procore — no copy-pasting required.

**What you get with Procore integration:**
- Create change events directly in your Procore project
- All fields (title, description, status, scope) are mapped automatically
- Change events are created with the full distribution summary so you can create CORs per sub from there

**Interested in setting this up?** The integration uses Anthropic's MCP (Model Context Protocol) with a Zapier connector for Procore. Contact Camron Walker for setup guidance and configuration help.
