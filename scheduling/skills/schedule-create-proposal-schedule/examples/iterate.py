"""Advanced custom-flow example for the proposal-schedule iteration loop.

For the standard agent-driven flow, run:

    python scheduling/tools/proposal_iterate.py --project "<project>" --paste paste.json

This file exists for cases where you need to step outside the CLI -- e.g.
prototyping a new check, instrumenting the loop, or running a what-if from
a notebook. Most agents should NOT read this file; the CLI is the canonical
entry point and this is a copy-and-adapt template only.

The pattern below is what `proposal_iterate.py` does internally, expanded
so you can see each step. It is not maintained in lockstep with the CLI --
treat it as a starting point.
"""

import json
import os
import importlib.util

# Update these to match your environment
REF = r'<plugin>/scheduling/skills/schedule-toolbox/lib'
PROJECT_FOLDER = r'<project-folder>'
LATEST_XER = r'<project-folder>/Proposal Schedule/Project -vN.xer'
NEXT_V_PATH = r'<project-folder>/Proposal Schedule/Project -v(N+1).xer'


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REF, f'{name}.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cpm = load('cpm_engine')


def parse_xer(path):
    for enc in ('cp1252', 'utf-8-sig', 'utf-8', 'latin-1'):
        try:
            text = open(path, 'rb').read().decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    tables, current, fields = {}, None, []
    for line in text.split('\r\n'):
        if line.startswith('%T'):
            current = line.split('\t')[1].strip()
            tables[current] = []
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
        elif line.startswith('%R') and current:
            tables[current].append(dict(zip(fields, line.split('\t')[1:])))
    return tables


def main(paste_text):
    payload = json.loads(paste_text)
    anchors = json.load(open(
        f'{PROJECT_FOLDER}/Proposal Schedule/proposal-anchors.json',
        encoding='utf-8',
    ))['anchors']

    # 1. Load latest XER and apply duration_changes IN MEMORY
    tables = parse_xer(LATEST_XER)
    tasks_by_id = {t['task_id']: t for t in tables['TASK']}
    for a in payload.get('activities', []):
        dc = a.get('duration_change')
        if dc and a['id'] in tasks_by_id:
            new_hr = int(round(float(dc['to_days']) * 8))
            tasks_by_id[a['id']]['target_drtn_hr_cnt'] = str(new_hr)

    # 2. What-if CPM, then check anchors BEFORE writing the new XER
    results, metadata = cpm.schedule_forward_backward(
        tables['TASK'], tables['TASKPRED'],
        tables.get('CALENDAR', tables.get('CLNDR', [])),
        payload['data_date'],
        tables.get('SCHEDOPTIONS', []),
        tables.get('PROJECT', []),
    )
    slips = cpm.check_anchor_dates(results, anchors)
    if slips:
        # Surface absorption suggestions, wait for confirmation, then re-run.
        for s in slips:
            cands = cpm.suggest_anchor_absorption(results, tables['TASKPRED'], s)
            print(s, cands)
        return

    # 3. Anchors hold -- write the new XER (Westland -v{N+1}.xer rule)
    # See `scheduling/tools/_xer_io.py` for the table-tracking write-back.
    # ...

    # 4. Build JSON; pass default_view through if present
    data = cpm.build_activities_json(
        results, metadata, tables['TASKPRED'],
        project_name=payload.get('project'),
        data_date=payload['data_date'],
        wbs_rows=tables.get('PROJWBS', []),
        default_view=payload.get('default_view'),
    )
    json_path = f'{PROJECT_FOLDER}/Proposal Schedule/schedule-activities.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        main(open(sys.argv[1]).read())
    else:
        print('Usage: python iterate.py <paste-back.json>')
