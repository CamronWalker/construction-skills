---
name: construction-observations-import
description: >
  Batch-create Procore observations from an architect's, engineer's, or commissioning report —
  one observation per report item, with a reasoned type and location per item and a dedupe pass
  against existing observations, all previewed before any write. Use when someone says "add these
  observations", "import the architect's/engineer's observation report", "batch add to the
  observations tracker", "turn this field report into observations", "log the design/punch/
  commissioning report items", "add the report items to Procore", or hands over a report whose
  line items each need tracking to closure. Every write is confirmed first; duplicates are skipped.
---

# Construction Observations Import

Take a field/observation report — an architect's site-visit report, an engineer's punch, a commissioning report — and turn each line item into a tracked Procore observation, so nothing falls through. The work is in getting each item's **type**, **location**, and **dedupe** right, then writing only after the user approves the batch.

> Writes through the Procore MCP. See `construction-procore-toolbox` for project resolution and the two-stage write contract — every create here follows it.

## Reason the type — don't blanket-default

`create_observation` accepts five standard type categories: `commissioning`, `quality`, `safety`, `warranty`, `work_to_complete`. Pick per item by reasoning about the report and the line:

- **Architect / engineer field or design-review report** → most items are `work_to_complete` (a deficiency to fix) or `quality` (workmanship not to spec). Read each item and choose — don't stamp them all identically.
- **Commissioning report** → items are `commissioning`.
- **Safety walk** → `safety`. **Warranty inspection** → `warranty`.

**Honor a project's configured types when possible.** Some projects configure named observation types (e.g. an "Architect Report" type). Try to discover them at runtime via the raw escape hatch (`procore_describe_endpoint` then `procore_get` on the observations types endpoint — see `construction-procore-toolbox`). If a configured type matches the report kind, create via `procore_post` using that type; otherwise fall back to the best-fit standard category above. If you can't confidently determine the type, ask rather than guess.

## Dedupe is mandatory

Before creating anything, `list_observations` for the project (**paginate to the end**) and compare each report item against what already exists — by title, description, and location similarity. Likely duplicates are **skipped**, not silently re-created. Show them in the review table as "already exists (#id)" so the user sees you checked. When a match is uncertain, flag it for the user rather than auto-skipping or auto-creating.

## Reason the locations

`list_locations` (the level/area/room tree) and map each report item to the best-matching `locationId` by reasoning over the location the report states against what the project actually has (e.g. report says "Level 2 corridor" → match the project's "Level 02 › Corridor" node). If there's no confident match, **leave the location unset and flag it** — never invent a location that isn't in the project's list.

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId`.
2. **Read the report.** PDF (use the pdf skill) or pasted text. Extract each discrete item — its description, stated location, any responsible party/trade, and any due date.
3. **Load the project's vocabulary:** observation types (configured + standard fallback), `list_locations`, and `list_project_users` (for `assigneeId`) / `find_company_vendor` (for `tradeId`/vendor) as needed.
4. **Build each observation:** reasoned `type`, reasoned `locationId`, `assigneeId`, `dueDate`, `priority`, and a clear `name` + `description` drawn from the report item.
5. **Dedupe** against `list_observations` (see above).
6. **Present the full batch as a review table** — item → type → location → assignee → due → dup? — so the user can eyeball the reasoning before anything is written.
7. **Dry-run then write.** Create each **non-duplicate** with `confirm` omitted first (preview), and only after the user's yes, re-call with `confirm: true`. Skip the flagged duplicates.
8. **Report** created observations with IDs/links, list what was skipped as duplicate, and flag any item left without a location/type for the user to resolve.

## Quick reference

| Step | Tool |
|------|------|
| Resolve project | `find_project` |
| Existing observations (dedupe) | `list_observations` (paginate) |
| Location tree | `list_locations` |
| Assignees | `list_project_users` |
| Configured observation types | raw `procore_get` (see toolbox) |
| Create | `create_observation` (dry-run → confirm), or `procore_post` for a configured type |

## Common mistakes

- **One blanket type for every item.** Reason per item; a mixed architect report can be part `quality`, part `work_to_complete`.
- **Skipping the dedupe pass.** Always read existing observations first — a second copy of every punch item helps no one.
- **Inventing locations.** Only use `locationId`s that exist on the project; leave unset and flag when unsure.
- **Writing before the batch is reviewed.** Show the whole table, dry-run, then confirm.

**Voice:** see `westland-house-style` — observation names/descriptions concrete and specific, drawn straight from the report.
