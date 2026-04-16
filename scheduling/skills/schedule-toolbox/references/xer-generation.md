# XER Generation

==============================================================================
ALWAYS WRITE TO A NEW FILE. NEVER OVERWRITE AN EXISTING XER.
CONFIRM OUTPUT PATH WITH USER BEFORE WRITING.
==============================================================================

## Always Template-Based

Never build from scratch. Too many implicit rules silently break P6 import.

## Six-Step Pattern

1. Read template as raw bytes, decode cp1252
2. Parse into sections — preserve `%T` and `%F` lines exactly
3. Clone PROJECT/SCHEDOPTIONS from template, override needed fields
4. Build new data rows with `make_r_line()` helper (exact field count required)
5. Reassemble — skip ACTVTYPE/ACTVCODE/TASKACTV tables
6. Write with CRLF line endings, cp1252 encoding

See `references/build_from_raw_template.py` for a working 96-task example.

## ID Strategy (avoid P6 collisions)

```python
PROJECT_ID = '99501'
wbs_counter = 30000
task_counter = 40000
pred_counter = 50000
```

## Calendar Data

The nested parenthetical format is fragile — copy `clndr_data` strings from `build_from_raw_template.py` (has working 5-day, 6-day, 7-day definitions). Never write calendar data programmatically.

## Westland Defaults

- WBS structure from `westland-standards.md`
- Milestones every 30 days
- Verb + Noun activity naming (allowed acronyms: HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB)
- All durations: working days × 8 = hours for XER storage

## Quality Check After Generation

```bash
python references/score_schedule.py <new_xer_path>
```

Target: B+ or higher initial generation, iterate to A grade.
