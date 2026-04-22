# Westland Construction — Scheduling Standards & Procedures

This document is the authoritative reference for Westland Construction scheduling standards. It replaces the Westland Scheduling Procedures Outline PDF and should be kept up to date as procedures change.

---

## Introduction

Westland is establishing a systematic approach to scheduling. Rather than start from scratch with each new project, we create detailed, accurate baseline template schedules for each standard project and building type. Schedules are then carefully adjusted and customized to fit the specific project. This is never a boilerplate process — the activities, logic, and durations for each schedule must be unique. However, the basic structure, organization, and workflow should be consistent across all Westland projects.

We must consult with the people who will actually do the work and ensure we have accurate sequencing, good durations, realistic time frames for shop drawings, review, fabrication, and shipping. Teams must resist the temptation to assume an initial schedule is accurate without real input from trade partners, suppliers, design teams, owners, etc.

---

## Schedule Development Lifecycle

### 1. Proposal Schedule Request
- Business Development / Directors request a proposal schedule from the Scheduling Department
- Request must be submitted to the Scheduling Department Manager **no less than 14 days** before the schedule is needed

### 2. Develop Conceptual Project Schedule
- Utilize a Westland template, or ensure organization and formatting adhere to Westland standards
- Obtain a detailed design & permitting schedule from the design team with sufficient detail to track progress
- Include the design process in Westland's conceptual schedule
- Coordinate with estimating / preconstruction for appropriate detail and durations for preconstruction deliverables, prequalification, buyout, etc.
- Include a procurement section for key materials — identify materials needing early release, expedited reviews, or careful monitoring due to market issues. Include all long lead items and materials identified as critical or likely to experience delays during the submittal or fabrication process. Include fabrication and shipping activities and secure valid durations.
- Develop a clear **Site Logistics & Workflow Plan** prior to creating the detailed schedule
- Ensure the level of detail corresponds to the amount of design information available
- Consult with team members and reference similar projects and construction types
- Use reasonable assumptions and historical data to compensate for incomplete design
- Include Westland standard responsibility codes and assign each task a responsible party

### 3. Update at Each Project Phase
- **Design** — As required by design progress and preconstruction agreement
- **Preconstruction** — As required by the preconstruction agreement
- **Construction** — Weekly
- **Closeout** — Produce a final record schedule documenting completion of all contract work, closeout items, and applicable owner occupancy activities

### 4. Develop Detailed Baseline Schedule
1. Meet with the Project Director and PMT to develop a graphic schedule detailing anticipated scope, identifying general areas, zoning, phasing, and flow for all site development and structures. **The Superintendent must be an integral part of this process.**
2. Project scheduler creates the tasks and logic in CPM software and issues a draft for PMT review
3. PMT provides in-depth review and feedback on the draft
4. PMT and scheduler work with trade partners and suppliers to perform pull planning to confirm scope, establish durations, and secure buy-in. Digital process is acceptable provided key team members are directly involved.
5. Run reports using **SmartPM Quality Checker** and the **P6 Check Schedule Report** to ensure all activities have sound logic, optimal sequencing, and appropriate predecessor and successor relationships. **This step is critical prior to establishing the baseline.**

### 5. Establish Baseline
- Submit baseline for Owner approval. Typically finalized and set once NTP is issued — usually required within 10 days of contract execution.
- In P6 Professional: assign the approved version as the Baseline Schedule and export an XER file as a record before commencing updates
- In Phoenix Project Manager: save a separate copy as the Baseline Version and establish the primary Storepoint
- Create a new project in SmartPM and upload the baseline schedule for performance tracking. For projects too short to warrant SmartPM, use the Quality Checker to ensure best practice compliance.

---

## Schedule Maintenance & Updates

### Update Cadence
- **Construction:** Weekly, or bi-monthly if warranted, but **no less than every other week**
- **Preconstruction:** At each design milestone (Schematic Design, DD, 70% CD, 100% CD, and as needed)
- The full Westland project team should participate in updates. Updates may also be performed with trades during weekly coordination meetings.

### Update Procedures
1. Before commencing an update, create a new dated schedule update folder on the shared drive
2. Preserve a record of the current version:
   - **Phoenix:** Create a copy of the last updated file, rename to current date
   - **P6:** Once update is complete, export an XER file and place in the same folder
3. Document all changes (altering relationships, adding/deleting/splitting activities). Done automatically when uploaded to SmartPM.
4. Store copies on G:Drive/Procore AND local hard drive (backup for network failures)
5. Issue a Weekly Update Report via email — copy the full PMT, Project Director, Estimator, and Scheduling Team. Follow the **Schedule Update Email Procedure** guidelines.

### Preconstruction Deliverables
- Updated Design Schedule
- Rolling Schedules extracted from the updated Baseline Schedule (attached to Preconstruction Reports)
- Any required filters (Trades, Critical Path, Specific Sections)

### Construction Deliverables at Each Update
- Updated Baseline Schedule
- Critical Path Schedule
- Longest Path Schedule
- 4-Week Rolling Schedule (extracted from updated Baseline — assists Superintendents with detailed 4-week schedules and trade coordination)
- Any required or beneficial filters (Trades/Responsible Parties, Procurement, Other Specific Sections)
- Any reports or filters required by project specifications
- Upload current update through Procore Drive

---

## Work Breakdown Structure (WBS)

### Standard Westland WBS Template

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
      [by AREA - LEVEL]
    BUILDING ENCLOSURE - WINDOWS - ENTRIES - FINISH SYSTEMS
      [by ELEVATION - AREA - LEVEL]
    INTERIOR ROUGH-IN & FINISHES
      [by AREA - LEVEL]

  COMMISSIONING & CLOSE-OUT
    [may be shown by Building, Area, or Floor]
```

### WBS Flexibility
The standard WBS is a starting point. Adapt it to the project:
- **Demo phase:** Demolition placement depends on phasing — before construction (greenfield), after construction (occupied rebuild), or interleaved (phased turnover). See `schedule-create-proposal-schedule/references/wbs-patterns.md` for the three patterns and decision table. The one-line rule "add DEMOLITION above CONSTRUCTION" covers only the greenfield case and is wrong for occupied rebuilds — post-demo sitework on the old footprint should nest under DEMOLITION, not under new-school SITEWORK.
- **Multiple buildings:** Repeat the Construction sub-structure for each building or use building-level WBS nodes
- **Phased turnover:** Add turnover milestones within the appropriate WBS sections
- **Additional phases:** Insert as needed while maintaining the overall Westland organizational structure

---

## Minimum Schedule Requirements

### Milestones
- **One milestone every 30 days** (Critical Path or Significant Event)
- Include all Westland standard required milestones
- Include any milestones required by project specifications

### Required Elements (Minimum Standard)
- Prequalification Process / Mock-Ups
- Design (if CM/GC or Design Build): Schematic Design, DD, 70% CD, 100% CD
- Submittals / Procurement / Mock-Ups
- Preconstruction Activities
- Construction: Sitework, Structure & Sub-Rough, Building Enclosure, Interior Rough-In & Finishes
- Closeout
- Progress Impacts: Weather Days, PR's/ASI's, Owner Delays, Contractor Delays

### Responsibility Codes
Every task must be assigned a responsible party using Westland standard responsibility codes.

---

## Managing & Documenting Schedule Impacts

### Impact Activities
- Any issue impacting or potentially impacting the project schedule must be properly documented
- Insert IMPACT activities that tie into existing schedule logic to clearly demonstrate the effect on current and subsequent activities and project completion
- Anticipated delays should be published and presented to the owner's rep and project team as soon as Westland's team is aware of an impact or potential impact. **Clear, honest, timely communication is vital.**

### Time Impact Analysis (TIA)
1. Enter delays as IMPACT Activities into the schedule to communicate the delay
2. If IMPACT activities drive the Critical Path, develop a TIA:
   - Create a **Fragnet** (fragment of the schedule logic network) within the updated baseline schedule
   - Tie the Fragnet to the activity the IMPACT is driving
   - Create an appropriate successor relationship to show the effect on the Critical Path
   - Use the standardized Impact Analysis Form to develop the TIA

### Extension of Time (EOT)
- EOTs should be submitted as a PCO on a monthly basis when possible
- Clearly indicate verbally and in writing when a delay is ongoing so the owner knows future claims will continue until the core issue is resolved

### Recovery Planning
- If a delay is caused by a trade contractor, do all in power to create a solid recovery plan
- Rather than surrendering float or giving up critical path days, work as a team to secure buy-in and hold partners accountable to recovery dates

---

## Schedule Formatting

Follow the established Westland branding and color guidelines. Reference the approved color key and sample layouts. If additional customizing is required for a specific client, **consult the Scheduling Department Manager** for approval of new color schemes and branding.

---

## SmartPM Integration

### Required SmartPM Usage
- **Quality Checker:** Run before baselining any schedule. Also used for projects too short to warrant a full SmartPM project.
- **Analytics Report:** Attached to schedule update emails. Referenced for specific schedule changes.
- **Change Log:** URL included in update emails so stakeholders can review specific changes.
- **View Trends:** Performance graphs (Activity Hit Rate, Window Start/Finish Accuracy, Schedule Compression Index, Monthly Activity Distribution, SPI Over Time) included in update emails.
- **Schedule Compliance Report:** Excel report distributed to the project team each week, reviewed in detail during OAC meetings. Include with meeting minutes and add language stating all parties reviewed the report.

### SmartPM Workflow
1. Create project in SmartPM after baseline is established
2. Upload each schedule update
3. Use SmartPM data for update emails (summary report, change log, performance graphs)
4. Reference SmartPM analytics in schedule discussions and owner communications
