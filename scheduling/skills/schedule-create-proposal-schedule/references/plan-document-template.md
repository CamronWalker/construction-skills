# Proposal Schedule Plan Document Template

Generate this document and save to `<project-folder>/Proposal Schedule/Schedule Plan - [Project Name].md`. Fill in all sections from the analysis results and user responses.

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

### 2.2 Bid Documents Analyzed
- [list of documents reviewed with key findings from each]

### 2.3 Schedule Assumptions
[All assumptions, formatted as a numbered list]

---

## 3. Work Breakdown Structure

### 3.1 WBS Structure
[The chosen WBS tree, fully indented, based on Westland standard adapted to this project]

### 3.2 WBS Rationale
[Why this structure was chosen — references to sample schedules and scope]

---

## 4. Proposed Activity List by WBS Node

**All activity names follow Verb + Noun convention** with allowed industry acronyms
(HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB) and & in place of "and".
Always spell out Notice to Proceed, Substantial Completion & Final Completion.

**All durations are in working days.** (XER files store durations in hours — multiply days x 8 for XER.)

### [WBS Node 1: e.g., Preconstruction]
| Activity Name | Duration (days) | Type | Duration Basis |
|--------------|----------------|------|---------------|
| Submit Shop Drawings | [days] | Task | [e.g., "Schedule A: 10 days for similar scope"] |
| Receive Building Permit | [days] | Milestone | [e.g., "Contract requirement"] |

### [WBS Node 2: e.g., Site Work]
| Activity Name | Duration (days) | Type | Duration Basis |
|--------------|----------------|------|---------------|
| Install Erosion Control | [days] | Task | [basis] |

[Continue for each WBS node...]

**Target Total Activities:** [number]

---

## 5. Logic Network Description

### 5.1 Phase-to-Phase Sequencing
[Major phase transitions and their relationship types]
- Preconstruction -> Site Work: [FS / SS with lag]
- Site Work -> Foundation: [relationship]
- Foundation -> Structure: [relationship]
- etc.

### 5.2 Within-Phase Logic Chains
Key sequences within each phase:

**Site Work:**
- Mobilize -> Erosion Control -> Clear & Grub -> Excavate -> Utilities -> Backfill -> Grade

**Foundation:**
- Excavate Footings -> Form -> Rebar -> Pour -> Strip -> Form Walls -> Rebar -> Pour -> Strip -> Waterproof -> Backfill

**Structure:**
[Sequences based on project scope]

**MEP:**
[Sequences based on project scope]

**Finishes:**
[Typical finish sequence]

**Closeout:**
[Sequence]

### 5.3 Cross-Phase Ties
[Key relationships that span phases]

### 5.4 Relationship Standards
- Default relationship type: FS
- Where SS is used: [list]
- Where FF is used: [if any]
- Target relationship ratio: [X.X]:1
- Lag usage: [guidelines]

---

## 6. Construction Sequence / Flow Plan

### 6.1 Overall Approach
[Overall construction flow narrative]

### 6.2 Phase-by-Phase Narrative
**Mobilization & Site Work** — [narrative]
**Foundation & Structure** — [narrative]
**Building Envelope** — [narrative]
**MEP Rough-In** — [narrative]
**Interior Finishes** — [narrative]
**Commissioning & Closeout** — [narrative]

---

## 7. Milestone Schedule

| Milestone | Target Timing | Type | Constraint | Source |
|-----------|--------------|------|------------|--------|
| NTP | [date] | Start Mile | SNET | Contract |
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
**Work Hours:** [start time - end time]
**Weather Allowances:** [if applicable]
**Holidays:** [if known]
**Overtime Provisions:** [if applicable]

---

## 11. Scope & Subcontractor Summary

| Scope Item | Self-Perform / Sub | Subcontractor | Lead Time | Notes |
|------------|-------------------|---------------|-----------|-------|
| [scope] | [SP/Sub] | [name or TBD] | [if applicable] | [notes] |

---

## 12. Owner Requirements & Communication

[Owner requirements and communication plan]

---

## 13. Activity Naming & Detail Standards

**Naming Convention:** Verb + Noun with allowed acronyms (HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB) & shorthand.
Always spell out Notice to Proceed, Substantial Completion & Final Completion.
**Target Activity Count:** [estimated]

---

## 14. Decision Log

[Record of key decisions made during planning, including user responses to guidance questions and any deviations from Westland defaults]

---

*This schedule plan document serves as the basis for XER generation.
It should be reviewed and approved before proceeding to schedule creation.*
```
