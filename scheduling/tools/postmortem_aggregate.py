"""postmortem_aggregate.py -- scan the proposal-schedule postmortem corpus
and emit a recency-weighted ruleset block for Phase 1 of the next proposal
draft.

A postmortem captures one proposal cycle's "what I missed" + numbered
hypotheses (see `phases/02-iterate.md` § "Postmortem on final approval").
This CLI walks the configured root, parses each postmortem's frontmatter
+ Hypotheses section, weights by recency, and prints a markdown block
ready for the agent to inject into Phase 1 recommendations.

Three postmortem layouts are supported (in priority order):

  1. Tier 7+ folder:
       <project>/Old Iterations/postmortems/{date}-{slug}/postmortem.md
     plus optional siblings: project-metadata.json, durations-captured.json,
     reviewer-feedback/*.json. Folder scope = full context.

  2. v4.x single-file (new layout):
       <project>/Old Iterations/postmortem-{date}-{slug}.md

  3. v3.x single-file (legacy):
       <project>/Proposal Schedule/feedback/postmortem-{date}-{slug}.md

Filtering supports any project_metadata field (project_type, region,
square_footage range, building_systems, ...). With --show-durations,
matched postmortems' durations-captured.json entries are surfaced for
Phase-1 reuse.

With zero postmortems in the corpus, prints a friendly skip message; the
draft just proceeds with default Westland standards. With a small corpus,
prints what's there as observations -- aggregation across many is what
turns hypotheses into rules, but every postmortem still carries useful
signal on its own.

Usage:
    python postmortem_aggregate.py
    python postmortem_aggregate.py --root "<dir>"
    python postmortem_aggregate.py --project-type "office-tenant-improvement"
    python postmortem_aggregate.py --region "Utah Valley"
    python postmortem_aggregate.py --system structural-masonry
    python postmortem_aggregate.py --show-durations
    python postmortem_aggregate.py --top 5
    python postmortem_aggregate.py --json     # machine-readable output
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# Default scan root: the folder where Westland keeps active proposal projects
DEFAULT_ROOTS = [
    Path.home() / 'OneDrive - Westland Construction' / '01 Projects' / '~Proposal Schedules',
    Path.home() / 'Westland Construction' / 'Proposal Schedules',
]

# Half-life for recency weighting in days. A postmortem 365 days old is
# weighted at 0.5 of a brand-new one. Tunable via --half-life.
DEFAULT_HALF_LIFE_DAYS = 365


def _resolve_root(arg_root):
    if arg_root:
        return Path(arg_root)
    for c in DEFAULT_ROOTS:
        if c.exists():
            return c
    return None


def _parse_frontmatter(text):
    """Pull YAML-ish frontmatter into a dict. Stops at the first '---' fence."""
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        fm[k.strip()] = v.strip().strip('"\'')
    return fm, parts[2]


def _section(text, heading):
    """Return the body of `## {heading}` up to the next H2."""
    pattern = re.compile(rf'^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s+|\Z)',
                         re.MULTILINE | re.DOTALL)
    m = pattern.search(text)
    return m.group(1).strip() if m else ''


def _extract_hypotheses(body):
    """Pull the numbered hypotheses out of '## Hypotheses for next time'.

    Accepts either '1. text', '1) text', or '- text' style. Returns list
    of stripped hypothesis strings.
    """
    sec = _section(body, 'Hypotheses for next time')
    if not sec:
        return []
    items = []
    for line in sec.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r'^(?:\d+[.)]|\-|\*)\s+(.+)$', s)
        if m:
            items.append(m.group(1).strip())
    return items


def _recency_weight(postmortem_date_str, today, half_life_days):
    try:
        d = datetime.strptime(postmortem_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return 0.5  # unknown date -> neutral weight
    age_days = max(0, (today - d).days)
    # Exponential decay with half-life
    return math.pow(0.5, age_days / half_life_days)


def _scan_legacy_files(root):
    """Yield (path, kind) tuples for legacy single-file postmortems.

    Kinds:
      - 'legacy-v3'   : <project>/Proposal Schedule/feedback/postmortem-*.md
      - 'legacy-v4'   : <project>/Old Iterations/postmortem-*.md
    """
    for p in root.rglob('feedback/postmortem-*.md'):
        if p.is_file() and not p.name.startswith('.'):
            yield p, 'legacy-v3'
    for p in root.rglob('Old Iterations/postmortem-*.md'):
        if p.is_file() and not p.name.startswith('.'):
            yield p, 'legacy-v4'


def _scan_folder_postmortems(root):
    """Yield (folder_path, postmortem_md_path) for Tier 7 folder postmortems."""
    for p in root.rglob('postmortems/*/postmortem.md'):
        if p.is_file():
            yield p.parent, p


def _slug_from_filename(name):
    # postmortem-2026-04-30-murray-apex-center.md -> murray-apex-center
    m = re.match(r'^postmortem-\d{4}-\d{2}-\d{2}-(.+)\.md$', name)
    return m.group(1) if m else name


def _slug_from_folder(folder_name):
    # 2026-04-30-murray-apex-center -> murray-apex-center
    m = re.match(r'^\d{4}-\d{2}-\d{2}-(.+)$', folder_name)
    return m.group(1) if m else folder_name


def _read_json_safe(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _matches_metadata(metadata_dict, args):
    """Return True if the metadata dict satisfies all the metadata filter args."""
    if args.project_type:
        ptype = metadata_dict.get('project_type', '') or ''
        if args.project_type.lower() not in str(ptype).lower():
            return False
    if args.region:
        r = metadata_dict.get('region', '') or ''
        if args.region.lower() not in str(r).lower():
            return False
    if args.system:
        systems = metadata_dict.get('building_systems') or []
        if isinstance(systems, str):
            systems = [s.strip() for s in systems.split(',') if s.strip()]
        if args.system.lower() not in [s.lower() for s in systems]:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=None,
                    help='Folder to scan recursively for postmortems')
    ap.add_argument('--project-type', default=None,
                    help='Filter postmortems whose project_type contains this substring')
    ap.add_argument('--region', default=None,
                    help='Filter postmortems whose project metadata region contains this substring')
    ap.add_argument('--system', default=None,
                    help='Filter postmortems whose building_systems contains this entry '
                         '(e.g. structural-masonry)')
    ap.add_argument('--show-durations', action='store_true',
                    help='Surface durations-captured.json entries from matched postmortems')
    ap.add_argument('--top', type=int, default=10,
                    help='Limit the ruleset to the top N hypotheses by weight (default 10)')
    ap.add_argument('--half-life', type=int, default=DEFAULT_HALF_LIFE_DAYS,
                    help=f'Recency-weight half-life in days (default {DEFAULT_HALF_LIFE_DAYS})')
    ap.add_argument('--json', action='store_true',
                    help='Emit machine-readable JSON instead of markdown')
    args = ap.parse_args()

    root = _resolve_root(args.root)
    if root is None or not root.exists():
        msg = ('No postmortem root found. Pass --root or place projects under '
               'a Westland Proposal Schedules folder.')
        if args.json:
            print(json.dumps({'status': 'no-root', 'message': msg}))
        else:
            print(msg)
        return 1

    today = datetime.now().date()
    postmortems = []
    seen_paths = set()  # de-dup if a folder postmortem also has a legacy file

    # Pass 1: Tier 7 folder postmortems (richer metadata)
    for folder, md_path in _scan_folder_postmortems(root):
        if str(md_path) in seen_paths:
            continue
        try:
            text = md_path.read_text(encoding='utf-8')
        except OSError:
            continue
        fm, body = _parse_frontmatter(text)
        # Folder may carry project-metadata.json snapshot -- merge into the
        # filter context; frontmatter wins for 'project'/'project_type', but
        # region / building_systems usually live in the metadata file.
        meta_snapshot = _read_json_safe(folder / 'project-metadata.json') or {}
        merged_meta = dict(meta_snapshot)
        for k, v in fm.items():
            if v not in (None, ''):
                merged_meta[k] = v
        if not _matches_metadata(merged_meta, args):
            continue
        weight = _recency_weight(fm.get('postmortem_date', ''), today,
                                 args.half_life)
        hypotheses = _extract_hypotheses(body)
        durations_data = None
        if args.show_durations:
            d = _read_json_safe(folder / 'durations-captured.json')
            if d and (d.get('entries') or []):
                durations_data = d['entries']
        postmortems.append({
            'path': str(md_path),
            'folder': str(folder),
            'kind': 'folder',
            'project': fm.get('project',
                              merged_meta.get('project_name')
                              or _slug_from_folder(folder.name)),
            'project_type': merged_meta.get('project_type', ''),
            'project_metadata': meta_snapshot,
            'postmortem_date': fm.get('postmortem_date', ''),
            'weight': round(weight, 3),
            'hypotheses': hypotheses,
            'durations': durations_data,
        })
        seen_paths.add(str(md_path))

    # Pass 2: legacy single-file postmortems (v3.x + v4.x). Skip if we already
    # captured a folder version of the same project+date.
    for path, kind in _scan_legacy_files(root):
        if str(path) in seen_paths:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            continue
        fm, body = _parse_frontmatter(text)
        if not _matches_metadata(fm, args):
            continue
        weight = _recency_weight(fm.get('postmortem_date', ''), today,
                                 args.half_life)
        hypotheses = _extract_hypotheses(body)
        postmortems.append({
            'path': str(path),
            'kind': kind,
            'project': fm.get('project', _slug_from_filename(path.name)),
            'project_type': fm.get('project_type', ''),
            'project_metadata': {},
            'postmortem_date': fm.get('postmortem_date', ''),
            'weight': round(weight, 3),
            'hypotheses': hypotheses,
            'durations': None,
        })
        seen_paths.add(str(path))

    if not postmortems:
        if args.json:
            print(json.dumps({
                'status': 'empty',
                'root': str(root),
                'message': 'No postmortems available; proceed with default Westland standards.',
            }, indent=2))
        else:
            print(f'No postmortems found under {root}.')
            print()
            print('Proceed with default Westland standards. As proposal cycles')
            print('complete and feedback/postmortem-*.md files accumulate, this')
            print('CLI will surface recency-weighted hypotheses for the next draft.')
        return 0

    # Flatten + weight every hypothesis individually
    weighted = []
    for pm in postmortems:
        for h in pm['hypotheses']:
            weighted.append({
                'hypothesis': h,
                'weight': pm['weight'],
                'source_project': pm['project'],
                'source_date': pm['postmortem_date'],
                'source_type': pm['project_type'],
            })

    weighted.sort(key=lambda x: -x['weight'])
    top = weighted[:args.top]

    if args.json:
        print(json.dumps({
            'status': 'ok',
            'root': str(root),
            'corpus_size': len(postmortems),
            'hypothesis_count': len(weighted),
            'top': top,
            'all_postmortems': postmortems,
        }, indent=2))
        return 0

    # Markdown ruleset block ready to inject into a Phase 1 recommendation
    filters = []
    if args.project_type:
        filters.append(f'project_type ~= {args.project_type}')
    if args.region:
        filters.append(f'region ~= {args.region}')
    if args.system:
        filters.append(f'building_system has {args.system}')
    filt_str = f' ({", ".join(filters)})' if filters else ''
    print(f'# Hypotheses from prior postmortems{filt_str}')
    print(f'# Corpus: {len(postmortems)} postmortem(s) under {root}')
    print(f'# Recency half-life: {args.half_life}d. Top {len(top)} by weight.')
    print('# These are observations from past cycles, not crowned rules. Cite')
    print('# the source if you act on one ("postmortem 2026-04 from Spanish')
    print('# Fork flagged X; using Y here").')
    print()
    for i, h in enumerate(top, 1):
        meta = f"[{h['source_project']}, {h['source_date']}, weight {h['weight']}]"
        print(f'{i}. {h["hypothesis"]}  {meta}')

    if args.show_durations:
        rows = []
        for pm in postmortems:
            if not pm.get('durations'):
                continue
            for e in pm['durations']:
                rows.append((pm, e))
        if rows:
            print()
            print('# Duration knowledge from matched postmortems')
            print(f'# {len(rows)} entr{"y" if len(rows) == 1 else "ies"} '
                  f'across {sum(1 for pm in postmortems if pm.get("durations"))} '
                  f'postmortem(s).')
            print()
            for pm, e in rows:
                code = e.get('task_code') or '?'
                name = e.get('task_name') or ''
                dur = e.get('final_duration_days')
                src = e.get('source') or '?'
                rationale = (e.get('rationale') or '').replace('\n', ' ').strip()
                if len(rationale) > 100:
                    rationale = rationale[:97] + '...'
                tail = f' -- {rationale}' if rationale else ''
                print(f'- [{code}] {name} = {dur}d  [{src}, '
                      f'{pm["source_project"] if "source_project" in pm else pm["project"]}, '
                      f'{pm["postmortem_date"]}]{tail}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
