"""
State-transition helpers for the schedule update email seed.

The seed tracks per-item status across weeks like a mini git diff:
    active   -> normal (checked; was in last week's email too)
    new      -> green  (just added this update)
    removed  -> red    (unchecked this update; was in last update)
    archived -> gray, collapsed (still unchecked after another update)

When generating THIS week's seed from LAST week's {YYYY-MM-DD}-email.json,
call `reconcile_items()` with the parsed lists to compute new statuses and
prev_idx pointers — the cloud editor's diff overlays consume the result.

The rules:

    last status  |  last checked  |  new status
    -----------  |  ------------  |  -----------
    new          |  True          |  active       (settled after one week)
    new          |  False         |  removed      (added then cancelled)
    active       |  True          |  active
    active       |  False         |  removed
    removed      |  True          |  active       (user re-added)
    removed      |  False         |  archived     (set date_archived)
    archived     |  True          |  active       (user un-archived)
    archived     |  False         |  archived     (stays collapsed)

Truly new items (discovered from the XER/transcript this week that weren't
in last week's list) get status='new'.
"""

import difflib
import re
from datetime import date, timedelta

# Items stay archived for at most this many days before being pruned entirely.
# Applies to list items (red_flags, successes, etc.) and to attachments.
# Custom closing paragraphs are NOT age-pruned — they have no date_archived
# and they're explicitly curated by the user.
MAX_ARCHIVED_DAYS = 90

# Pattern-based bootstrap for share_to_procore. New attachments matching
# these patterns default to True (publicly shareable in the Procore Documents
# folder); everything else defaults to False (the folder is public, so
# unfamiliar files require an explicit opt-in via the preview checkbox).
_PROCORE_BOOTSTRAP_PATTERNS = [
    re.compile(r'view', re.IGNORECASE),
    re.compile(r'update[-_ ]request.*\.xlsm$', re.IGNORECASE),
]


def _bootstrap_share_to_procore(filename):
    """Return True if a brand-new attachment with this filename should
    default to share_to_procore=True."""
    if not filename:
        return False
    return any(p.search(filename) for p in _PROCORE_BOOTSTRAP_PATTERNS)


def _parse_iso(s):
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _too_old(date_archived, today, max_days):
    d = _parse_iso(date_archived)
    if d is None:
        return False
    return (today - d).days > max_days


_WORD_PATTERN = re.compile(r'\w+')

# Date patterns commonly found in Westland attachment filenames. We strip
# these before comparing so "Report 01 - ... 2026-04-08.pdf" matches the
# same template with next week's date. Order matters: the longer ISO form
# is tried before the shorter US form so we don't split across dashes.
_FILENAME_DATE_PATTERNS = [
    re.compile(r'\b\d{4}[-_./]\d{2}[-_./]\d{2}\b'),   # YYYY-MM-DD / YYYY_MM_DD / etc.
    re.compile(r'\b\d{2}[-_./]\d{2}[-_./]\d{4}\b'),   # MM-DD-YYYY
    re.compile(r'\b\d{4}\d{2}\d{2}\b'),                # YYYYMMDD
]


def _normalize_attachment_name(filename):
    """Strip date tokens from a filename and lowercase/squeeze whitespace.

    Used to compare attachments across weeks. "Report 01 - Neiafu Tonga
    Temple Master Schedule 2026-04-08.pdf" and the same with 2026-04-15
    both normalize to the same key, so week-over-week re-globbing doesn't
    flag every file as new.
    """
    if not filename:
        return ''
    s = filename
    for pat in _FILENAME_DATE_PATTERNS:
        s = pat.sub('', s)
    s = re.sub(r'[-_\s]+', ' ', s)
    return s.lower().strip()


def _similarity(a, b):
    """Similarity between two strings, robust to one being a prefix/expansion
    of the other.

    Returns max of:
        - difflib SequenceMatcher ratio() (rewards shared substrings)
        - word-overlap ratio (shared words / words in shorter) * 0.9
          — catches the case where Claude added a clause to an existing item.
    """
    al, bl = a.lower(), b.lower()
    seq_ratio = difflib.SequenceMatcher(
        a=al, b=bl, autojunk=False,
    ).ratio()
    a_words = set(_WORD_PATTERN.findall(al))
    b_words = set(_WORD_PATTERN.findall(bl))
    if not a_words or not b_words:
        return seq_ratio
    shorter = a_words if len(a_words) < len(b_words) else b_words
    overlap = len(a_words & b_words) / len(shorter)
    return max(seq_ratio, overlap * 0.9)


def reconcile_items(last_week_items, this_week_texts, today_iso=None,
                    similarity_threshold=0.6,
                    max_archived_days=MAX_ARCHIVED_DAYS):
    """Reconcile this week's generated texts with last week's tracked items.

    Returns (this_week_rows, last_week_rows_as_baseline):
        - `this_week_rows`: dicts shaped {text, checked, status, date_archived,
          prev_idx} where `prev_idx` is the index into `last_week_rows_as_baseline`
          (the second element of the tuple). `prev_idx` is None when status='new'.
        - `last_week_rows_as_baseline`: a normalized echo of `last_week_items`
          shaped {text, checked, status, date_archived}. Pass-through copy so
          callers can write it into the seed's `last_week.<list>` slot without
          re-normalizing.

    Diff overlays in the cloud editor and "strikethrough-previous-metric"
    badges in the .eml builder are computed by walking from
    `this_week.<list>[i]` → `last_week.<list>[this_week.<list>[i].prev_idx]`.
    The denormalized `previous_text` field that the legacy flow used is gone —
    callers walk `last_week.<list>[prev_idx]` for the prior text.

    Args:
        last_week_items: list of dicts from last week's `email-draft.json`
                         (e.g. `last_week_draft['this_week']['red_flags']`).
                         Each dict should have at minimum a `text` field.
        this_week_texts: list of HTML strings Claude wrote for this update's
                         version of this field. Pass through verbatim — items
                         are HTML now, not markdown (see scheduling/CLAUDE.md).
        today_iso: 'YYYY-MM-DD' for transitions & pruning. Defaults to today.
        similarity_threshold: difflib ratio cutoff for fuzzy-matching an item
                              across weeks. 0.6 ≈ shares ~60% of content.
        max_archived_days: prune archived items older than this.

    Semantics (matched cases):
        - this_week_text fuzzy-matches a last-week active/new item:
              status='active', prev_idx=index into last_week_rows_as_baseline.
        - this_week_text fuzzy-matches a last-week removed/archived item:
              status='new', prev_idx=None
              (Claude pulled it back in — visually "new again").
        - this_week_text has no match:
              status='new', prev_idx=None (truly new this update).

    Semantics (unmatched last-week items — Claude dropped them):
        - last status was active or new: status='removed' this week
          (carried into this_week_rows so the editor can show the strike-out).
          prev_idx points to its slot in last_week_rows_as_baseline.
        - last status was removed (and not re-checked by user): status=
              'archived' this week with date_archived=today.
        - last status was archived: stays archived (original date preserved).
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_items = list(last_week_items or [])

    # Normalized echo of last week — pass-through copy preserving each row's
    # text/checked/status. This is what gets written to
    # this week's seed under `last_week.<list>`.
    last_week_baseline = [
        {
            'text': (it.get('text') or ''),
            'checked': bool(it.get('checked', True)),
            'status': it.get('status', 'active'),
        }
        for it in last_items
    ]

    used = set()

    # --- Match phase: this week's texts ↔ last week's items --------
    matched = []
    for raw in (this_week_texts or []):
        text = (raw or '').strip()
        if not text:
            continue
        best_idx = -1
        best_ratio = 0.0
        for i, it in enumerate(last_items):
            if i in used:
                continue
            prev_text = (it.get('text') or '').strip()
            if not prev_text:
                continue
            if prev_text == text:
                best_idx, best_ratio = i, 1.0
                break
            r = _similarity(prev_text, text)
            if r > best_ratio:
                best_ratio, best_idx = r, i

        if best_idx >= 0 and best_ratio >= similarity_threshold:
            used.add(best_idx)
            prev = last_items[best_idx]
            prev_status = prev.get('status', 'active')
            # Resurrecting a removed/archived item counts as "new" — no prev_idx
            # so the editor renders it without a diff overlay.
            if prev_status in ('removed', 'archived'):
                matched.append({
                    'text': text,
                    'checked': True,
                    'status': 'new',
                    'prev_idx': None,
                })
            else:
                row = {
                    'text': text,
                    'checked': True,
                    'status': 'active',
                    'prev_idx': best_idx,
                }
                prev_text = (last_items[best_idx].get('text') or '').strip()
                if text != prev_text:
                    row['edited'] = True
                matched.append(row)
        else:
            matched.append({
                'text': text,
                'checked': True,
                'status': 'new',
                'prev_idx': None,
            })

    # --- Drop phase: last-week items Claude didn't include (v2 lifecycle) ---
    dropped = []
    for i, it in enumerate(last_items):
        if i in used:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        prev_status = it.get('status', 'active')

        # v2: only 'active' or 'new' last week → 'removed' this week. Anything
        # already 'removed' last week drops entirely (no archived pile for
        # the four primary lists). 'archived' shouldn't appear here (it's
        # isolated to key_items_archived in v2) — treat defensively as drop.
        if prev_status in ('active', 'new'):
            dropped.append({
                'text': prev_text,
                'checked': False,
                'status': 'removed',
                'prev_idx': i,
            })
        # else: drop. Do not append.

    this_week_rows = matched + dropped
    return this_week_rows, last_week_baseline


def reconcile_key_items(last_week_key_items, last_week_key_items_archived,
                        this_week_texts, today_iso=None,
                        similarity_threshold=0.6,
                        max_archived_days=MAX_ARCHIVED_DAYS):
    """v2 key_items reconciliation — splits output into active + archived.

    Unlike `reconcile_items`, key_items maintains an archived pile in a
    separate sibling list (`key_items_archived`) for delay-claim evidence.
    Archived rows older than `max_archived_days` drop entirely.

    Args:
        last_week_key_items: prior week's `this_week.key_items` rows
            (active/new/removed status).
        last_week_key_items_archived: prior week's
            `this_week.key_items_archived` rows (archived status,
            with `date_archived`).
        this_week_texts: HTML strings Claude wrote for this update's
            key items.
        today_iso: 'YYYY-MM-DD' for transitions & pruning.
        similarity_threshold: fuzzy-match cutoff.
        max_archived_days: prune archived items older than this.

    Returns:
        (this_week_rows, this_week_archived_rows, last_week_baseline):
            - this_week_rows: active/new/removed for seed.this_week.key_items.
              Carries `prev_idx`, optional `edited`.
            - this_week_archived_rows: archived for
              seed.this_week.key_items_archived. Each row has
              `date_archived` set.
            - last_week_baseline: pass-through copy of last_week_key_items
              (active key_items only) for seed.last_week.key_items.

    Lifecycle:
        active/new in last_week.key_items → matched this week: active.
                                          → unmatched this week: removed.
        removed in last_week.key_items   → unmatched: archived (date_archived=today).
        archived in last_week.key_items_archived
                                        → matched this week: new (resurrection).
                                        → unmatched: stays archived (original date).
                                        → past max_archived_days: dropped.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_active = list(last_week_key_items or [])
    last_archived = list(last_week_key_items_archived or [])

    last_week_baseline = [
        {
            'text': (it.get('text') or ''),
            'checked': bool(it.get('checked', True)),
            'status': it.get('status', 'active'),
        }
        for it in last_active
    ]

    # Build combined search space for fuzzy matching: active items first,
    # then archived. Track which list each index belongs to.
    search = [(i, 'active', it) for i, it in enumerate(last_active)] + \
             [(i, 'archived', it) for i, it in enumerate(last_archived)]
    used_active = set()
    used_archived = set()

    matched = []
    for raw in (this_week_texts or []):
        text = (raw or '').strip()
        if not text:
            continue
        best = None  # (ratio, idx_in_search)
        for s_idx, (orig_idx, kind, it) in enumerate(search):
            if kind == 'active' and orig_idx in used_active:
                continue
            if kind == 'archived' and orig_idx in used_archived:
                continue
            prev_text = (it.get('text') or '').strip()
            if not prev_text:
                continue
            if prev_text == text:
                best = (1.0, s_idx)
                break
            r = _similarity(prev_text, text)
            if best is None or r > best[0]:
                best = (r, s_idx)

        if best is not None and best[0] >= similarity_threshold:
            orig_idx, kind, it = search[best[1]]
            prev_text = (it.get('text') or '').strip()
            if kind == 'active':
                used_active.add(orig_idx)
                prev_status = it.get('status', 'active')
                if prev_status in ('removed',):
                    matched.append({
                        'text': text,
                        'checked': True,
                        'status': 'new',
                        'prev_idx': None,
                    })
                else:
                    row = {
                        'text': text,
                        'checked': True,
                        'status': 'active',
                        'prev_idx': orig_idx,
                    }
                    if text != prev_text:
                        row['edited'] = True
                    matched.append(row)
            else:  # kind == 'archived' — resurrection
                used_archived.add(orig_idx)
                matched.append({
                    'text': text,
                    'checked': True,
                    'status': 'new',
                    'prev_idx': None,
                })
        else:
            matched.append({
                'text': text,
                'checked': True,
                'status': 'new',
                'prev_idx': None,
            })

    # Drop phase for active items: unmatched last-week active/new → 'removed' this week.
    dropped_active = []
    new_archived = []
    for i, it in enumerate(last_active):
        if i in used_active:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        prev_status = it.get('status', 'active')
        if prev_status in ('active', 'new'):
            dropped_active.append({
                'text': prev_text,
                'checked': False,
                'status': 'removed',
                'prev_idx': i,
            })
        elif prev_status == 'removed':
            # removed last week, still gone this week → archive now
            new_archived.append({
                'text': prev_text,
                'checked': False,
                'status': 'archived',
                'date_archived': today_iso,
                'prev_idx': i,
            })

    # Drop phase for archived items: unmatched archives stay archived
    # (original date), prune anything older than max_archived_days.
    for i, it in enumerate(last_archived):
        if i in used_archived:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        date_archived = it.get('date_archived', today_iso) or today_iso
        if _too_old(date_archived, today, max_archived_days):
            continue
        new_archived.append({
            'text': prev_text,
            'checked': False,
            'status': 'archived',
            'date_archived': date_archived,
            # prev_idx for archived rows references the archived baseline,
            # which is its own list — leave None to avoid ambiguity. The
            # editor uses date_archived to render the row, not prev_idx.
            'prev_idx': None,
        })

    this_week_rows = matched + dropped_active
    return this_week_rows, new_archived, last_week_baseline


def transition_attachments(last_week_attachments, fresh_filenames=None,
                           today_iso=None):
    """v2 attachment reconciliation.

    Match fresh-globbed filenames against last week's attachments by
    date-stripped fuzzy name. Files that re-appear week-over-week
    (only the date token changed) carry forward as `status='active'`
    with the FRESH filename. Files only in fresh become `status='new'`.

    Unmatched last-week items (Claude/glob dropped them) transition:
        active/new → removed
        removed   → drop entirely (no archived pile for attachments)

    Args:
        last_week_attachments: list of dicts from last week's
            email-draft.json (`last_draft['this_week']['attachments']`).
            Expected v2 fields: name, ext (optional), checked, procore,
            status, prev_idx.
        fresh_filenames: this week's freshly-resolved basename strings.
        today_iso: 'YYYY-MM-DD' for transitions (defaults to today).

    Returns:
        list of {name, ext, checked, procore, status, prev_idx} dicts
        ready for seed.this_week.attachments.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()

    last_items = list(last_week_attachments or [])
    norm_index = {}
    for i, a in enumerate(last_items):
        norm = _normalize_attachment_name(a.get('name', '') or a.get('filename', ''))
        if norm:
            norm_index.setdefault(norm, i)

    used = set()
    result = []

    # --- Match phase: fresh ↔ last-week via normalized names -----------
    for fn in (fresh_filenames or []):
        if not fn:
            continue
        norm = _normalize_attachment_name(fn)
        ext = _ext_of(fn)
        if norm and norm in norm_index and norm_index[norm] not in used:
            i = norm_index[norm]
            used.add(i)
            last_a = last_items[i]
            last_status = last_a.get('status', 'active')

            if last_status in ('active', 'new', 'removed'):
                # Restoration / continuation — call it active.
                row = {
                    'name': fn,
                    'checked': True,
                    'status': 'active',
                    'procore': bool(last_a.get('procore',
                                                last_a.get('share_to_procore', False))),
                    'prev_idx': i,
                }
                if ext:
                    row['ext'] = ext
                result.append(row)
            else:
                # Defensive: unknown status, treat as new.
                row = {
                    'name': fn,
                    'checked': True,
                    'status': 'new',
                    'procore': _bootstrap_share_to_procore(fn),
                    'prev_idx': None,
                }
                if ext:
                    row['ext'] = ext
                result.append(row)
        else:
            row = {
                'name': fn,
                'checked': True,
                'status': 'new',
                'procore': _bootstrap_share_to_procore(fn),
                'prev_idx': None,
            }
            if ext:
                row['ext'] = ext
            result.append(row)

    # --- Drop phase: last-week items not matched this week -------------
    for i, a in enumerate(last_items):
        if i in used:
            continue
        last_status = a.get('status', 'active')
        name = a.get('name', '') or a.get('filename', '')
        if not name:
            continue
        ext = a.get('ext') or _ext_of(name)

        if last_status in ('active', 'new'):
            row = {
                'name': name,
                'checked': False,
                'status': 'removed',
                'procore': bool(a.get('procore',
                                       a.get('share_to_procore', False))),
                'prev_idx': i,
            }
            if ext:
                row['ext'] = ext
            result.append(row)
        # else: drop entirely (no archived pile for attachments in v2).

    return result


def _ext_of(filename):
    """Return lowercase extension without dot, or '' if no extension."""
    if not filename:
        return ''
    base = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    if '.' not in base:
        return ''
    return base.rsplit('.', 1)[-1].lower()
