"""CPM result cache keyed by content hash of the modified task graph.

Free win during dev iterations where the agent re-runs `proposal_iterate.py`
without changing the schedule (e.g. to regenerate HTML, smoke a new flag,
re-archive a paste-back). The cache hits when the post-mutation task graph
is byte-identical to a prior run.

Cache layout: `<project>/Proposal Schedule/.cpm-cache/<sha256>.json`

Key inputs feed the hash:
  - tasks (relevant fields only; CPM-affecting columns)
  - preds (TASKPRED)
  - data_date

Calendars and project rows are deliberately omitted from the key -- they
change rarely and are heavy to hash. If you change a calendar mid-iteration
the cache will return stale results; clear the .cpm-cache/ folder.
"""

import hashlib
import json
from pathlib import Path


# Fields that change CPM output. Limit the hash key to these to keep the
# digest stable across noise (display fields, IDs, etc.).
_TASK_HASH_FIELDS = (
    'task_id', 'task_code', 'task_type', 'status_code',
    'target_drtn_hr_cnt', 'remain_drtn_hr_cnt',
    'cstr_type', 'cstr_date', 'cstr_type2', 'cstr_date2',
    'clndr_id',
)
_PRED_HASH_FIELDS = (
    'task_id', 'pred_task_id', 'pred_type', 'lag_hr_cnt',
)


def hash_inputs(tasks, preds, data_date):
    """Stable sha256 over the CPM-affecting subset of TASK + TASKPRED."""
    h = hashlib.sha256()
    h.update(b'data_date:')
    h.update(str(data_date).encode('utf-8'))
    h.update(b'\n')

    # Sort tasks by task_id so order doesn't affect the digest
    h.update(b'tasks:\n')
    for t in sorted(tasks, key=lambda r: r.get('task_id', '')):
        for f in _TASK_HASH_FIELDS:
            h.update(f.encode('ascii'))
            h.update(b'=')
            h.update((t.get(f) or '').encode('utf-8'))
            h.update(b'\t')
        h.update(b'\n')

    h.update(b'preds:\n')
    for r in sorted(
        preds,
        key=lambda r: (r.get('task_id', ''), r.get('pred_task_id', '')),
    ):
        for f in _PRED_HASH_FIELDS:
            h.update(f.encode('ascii'))
            h.update(b'=')
            h.update((r.get(f) or '').encode('utf-8'))
            h.update(b'\t')
        h.update(b'\n')

    return h.hexdigest()


def cache_dir(proposal_dir):
    return Path(proposal_dir) / '.cpm-cache'


def load(proposal_dir, key):
    """Return (results, metadata) if cached, else None."""
    p = cache_dir(proposal_dir) / f'{key}.json'
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
        return d.get('results', []), d.get('metadata', {})
    except (json.JSONDecodeError, OSError):
        return None


def store(proposal_dir, key, results, metadata):
    """Write results+metadata to the cache."""
    d = cache_dir(proposal_dir)
    d.mkdir(exist_ok=True)
    p = d / f'{key}.json'
    p.write_text(
        json.dumps({'results': results, 'metadata': metadata},
                   ensure_ascii=False, default=str),
        encoding='utf-8',
    )
