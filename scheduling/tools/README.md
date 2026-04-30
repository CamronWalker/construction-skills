# scheduling/tools/

Standalone tooling that wraps the schedule-toolbox engines into deliverables.

## build_gantt_html.py

Renders a self-contained Gantt review HTML (`schedule-review.html`) from
`schedule-activities.json`. The output opens locally from disk -- no server,
no CDN, no external assets -- and is the iteration surface for the proposal
schedule loop.

### Inputs

- `schedule-activities.json` -- emitted by `cpm_engine.build_activities_json()`
  after `schedule_forward_backward()`. Contains the project metadata, the full
  activity list with WBS hierarchy, and a `paths` block (critical, near-critical,
  driving paths to each end-state, parallel branches).

### Output

- `schedule-review.html` -- single file, ~100 KB. Inlines the vendored
  frappe-gantt UMD bundle, the Westland CSS overrides, the Westland logo as
  a base64 data URI, and the activity JSON.

### Usage

```bash
# default: writes <input-folder>/schedule-review.html
python scheduling/tools/build_gantt_html.py path/to/schedule-activities.json

# explicit output path
python scheduling/tools/build_gantt_html.py schedule-activities.json -o my-review.html

# override project name (otherwise pulled from project.name in the JSON)
python scheduling/tools/build_gantt_html.py schedule-activities.json --project "Murray Apex"
```

### From Python

```python
from build_gantt_html import build_gantt_html

build_gantt_html('schedule-activities.json',
                 output_path='schedule-review.html',
                 project_name_override='Murray Apex')
```

## End-to-end flow (proposal schedule iteration)

```
[XER]
  -> parse_xer()
  -> schedule_forward_backward()
  -> build_activities_json()       # cpm_engine.py
  -> write schedule-activities.json
  -> build_gantt_html.py           # this script
  -> schedule-review.html
```

### The Copy-for-Claude iteration loop

The HTML is the input surface, not just an output. Camron edits durations
inline, leaves notes on activity-ID chips, optionally toggles the
**Default view** checkbox, then clicks **Copy for Claude** to copy a
structured JSON payload to his clipboard. He pastes it into the agent
terminal. Claude applies the changes and regenerates everything.

1. Generator produces `<project>-vN.xer`, `schedule-activities.json`, and
   `schedule-review.html` together in the Proposal Schedule folder.
2. Camron opens `schedule-review.html` in Chrome.
3. Camron edits durations directly in the table column, clicks the
   activity-ID chip in front of any name to leave a note, optionally toggles
   "Default view" to bake the current zoom/scroll into the next render.
4. Camron clicks **Copy for Claude** and pastes the JSON into the terminal.
5. Claude reads the paste-back, opens the `paths` section in the current
   `schedule-activities.json`, states the second-order effect on critical /
   near-critical paths, then:
   - Applies each `duration_change` to the matching TASK row's
     `target_drtn_hr_cnt` (= `to_days * 8`); writes a new `-v{N+1}.xer`
     (Westland's immutability rule).
   - Addresses each `comment` -- sequence change, constraint, parent move,
     or clarifying question.
   - Re-runs CPM via `schedule_forward_backward()`.
   - Rebuilds the JSON with `build_activities_json(..., default_view=
     payload.get("default_view"))` so the HTML restores the same view if
     "Default view" was on.
   - Re-renders the HTML via `build_gantt_html.py`.
6. Camron refreshes the page. Loop.
7. Final XER is saved per the `-v{N}.xer` rule. The JSON and HTML are
   transient -- overwritten each iteration, never versioned.

For the full paste-back JSON schema and a worked example, see
`scheduling:schedule-create-proposal-schedule` § "Iteration loop."

## Repository layout

```
scheduling/
  assets/
    westland-logo.png        # embedded as data URI in the HTML
  lib/
    frappe-gantt/
      frappe-gantt.umd.js    # vendored from npm (MIT)
      frappe-gantt.css
      license.txt
  templates/
    gantt-review.html        # template with <<<TOKEN>>> placeholders
  tools/
    build_gantt_html.py      # this script
    README.md                # you are here
```
