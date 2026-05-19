"""
State-transition helpers for the schedule update email preview.

The preview tracks per-item status across weeks like a mini git diff:
    active   -> normal (checked; was in last week's email too)
    new      -> green  (just added this update)
    removed  -> red    (unchecked this update; was in last update)
    archived -> gray, collapsed (still unchecked after another update)

When generating THIS week's preview from LAST week's edited HTML, call
`transition_items()` with the parsed items to compute new statuses, then
pass the result to generate_email_preview_html.

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

    This is the main entry point for the skill when generating a new preview:
    given what Claude produced this week, and what was in last week's preview,
    compute the full item list (with statuses, previous_text for edits, and
    90-day-pruned archives) ready to pass to generate_preview_html.

    Args:
        last_week_items: list of dicts from parse_preview_html() of last
                         week's preview (e.g. result['red_flags_full']).
        this_week_texts: list of plain text strings Claude wrote for this
                         update's version of this field.
        today_iso: 'YYYY-MM-DD' for transitions & pruning. Defaults to today.
        similarity_threshold: difflib ratio cutoff for fuzzy-matching an item
                              across weeks. 0.6 ≈ shares ~60% of content.
        max_archived_days: prune archived items older than this.

    Returns:
        list of {text, previous_text, status, checked, date_archived} dicts.
        Pass directly as e.g. red_flags= kwarg to generate_preview_html.

    Semantics (matched cases):
        - this_week_text fuzzy-matches a last-week active/new item:
              status='active', previous_text=last_week_text if differs
              (renders with amber outline + inline diff when the text was
              tweaked).
        - this_week_text fuzzy-matches a last-week removed/archived item:
              status='new' (Claude pulled it back in — visually "new again").
        - this_week_text has no match:
              status='new' (truly new this update).

    Semantics (unmatched last-week items — Claude dropped them):
        - last status was active or new: status='removed' this week.
        - last status was removed (and not re-checked by user): status=
              'archived' this week with date_archived=today.
        - last status was archived: stays archived (original date preserved).
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_items = list(last_week_items or [])
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
            prev_text = (prev.get('text') or '').strip()
            prev_status = prev.get('status', 'active')
            # Resurrecting a removed/archived item counts as "new".
            if prev_status in ('removed', 'archived'):
                status = 'new'
                previous_text = ''
            else:
                status = 'active'
                previous_text = prev_text if prev_text != text else ''
            matched.append({
                'text': text,
                'previous_text': previous_text,
                'status': status,
                'checked': True,
                'date_archived': '',
            })
        else:
            matched.append({
                'text': text,
                'previous_text': '',
                'status': 'new',
                'checked': True,
                'date_archived': '',
            })

    # --- Drop phase: last-week items Claude didn't include ---------
    dropped = []
    for i, it in enumerate(last_items):
        if i in used:
            continue
        prev_text = (it.get('text') or '').strip()
        if not prev_text:
            continue
        prev_status = it.get('status', 'active')

        if prev_status in ('active', 'new'):
            new_status = 'removed'
            new_checked = False
            new_archived = ''
        elif prev_status == 'removed':
            new_status = 'archived'
            new_checked = False
            new_archived = today_iso
        elif prev_status == 'archived':
            new_status = 'archived'
            new_checked = False
            new_archived = it.get('date_archived', today_iso)
        else:
            new_status = 'active'
            new_checked = bool(it.get('checked', True))
            new_archived = ''

        # 90-day prune
        if (new_status == 'archived'
                and _too_old(new_archived, today, max_archived_days)):
            continue

        dropped.append({
            'text': prev_text,
            'previous_text': '',
            'status': new_status,
            'checked': new_checked,
            'date_archived': new_archived,
        })

    return matched + dropped


def transition_items(last_week_items, new_texts=None, today_iso=None,
                     max_archived_days=MAX_ARCHIVED_DAYS):
    """Apply week-over-week state transitions.

    Args:
        last_week_items: list of dicts {text, checked, status, date_archived}
                         from parse_preview_html() of last week's preview.
        new_texts: list of plain strings — items discovered this week that
                   were not in last week's list. Each gets status='new'.
        today_iso: 'YYYY-MM-DD'. Used as date_archived when transitioning
                   removed -> archived. Defaults to today.
        max_archived_days: archived items older than this many days are
                           pruned from the result (default 90).

    Returns:
        list of dicts ready for generate_preview_html's list kwargs.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    result = []
    for item in last_week_items or []:
        status = item.get('status', 'active')
        checked = bool(item.get('checked', True))
        new_item = {
            'text': item.get('text', ''),
            'checked': True,
            'status': 'active',
            'date_archived': '',
        }

        if status == 'new':
            new_item['status'] = 'active' if checked else 'removed'
            new_item['checked'] = bool(checked)
        elif status == 'active':
            new_item['status'] = 'active' if checked else 'removed'
            new_item['checked'] = bool(checked)
        elif status == 'removed':
            if checked:
                new_item['status'] = 'active'
                new_item['checked'] = True
            else:
                new_item['status'] = 'archived'
                new_item['checked'] = False
                new_item['date_archived'] = today_iso
        elif status == 'archived':
            if checked:
                new_item['status'] = 'active'
                new_item['checked'] = True
            else:
                new_item['status'] = 'archived'
                new_item['checked'] = False
                new_item['date_archived'] = item.get('date_archived', today_iso)
        else:
            new_item['status'] = 'active'
            new_item['checked'] = bool(checked)

        # 90-day prune: archived items past max age drop out entirely
        if (new_item['status'] == 'archived'
                and _too_old(new_item.get('date_archived'),
                             today, max_archived_days)):
            continue

        result.append(new_item)

    # Append newly discovered items
    existing_texts = {
        (r['text'] or '').strip().lower() for r in result if r.get('text')
    }
    for text in (new_texts or []):
        key = (text or '').strip().lower()
        if not key or key in existing_texts:
            continue
        result.append({
            'text': text,
            'checked': True,
            'status': 'new',
            'date_archived': '',
        })
        existing_texts.add(key)

    return result


def transition_attachments(last_week_attachments, fresh_filenames=None,
                           today_iso=None,
                           max_archived_days=MAX_ARCHIVED_DAYS):
    """Match this week's freshly-globbed filenames against last week's
    tracked attachments by DATE-STRIPPED name. Files that are just
    last week's template with an updated date carry forward as
    `status='active'` (the filename is UPDATED to the current week's
    version). Only attachments that normalize to a brand-new key become
    `status='new'`.

    Unmatched last-week items (Claude/globs dropped them) transition:
        active/new -> removed
        removed    -> archived (date_archived = today)
        archived   -> archived (original date preserved, 90-day prune)

    Args:
        last_week_attachments: list of dicts from last week's preview parse.
        fresh_filenames: this week's freshly-resolved filenames (from
            project-context.md globs matched against the dated folder).
        today_iso: 'YYYY-MM-DD' for transitions & pruning (defaults to today).
        max_archived_days: drop archives older than this (default 90).

    Returns:
        list of {filename, checked, status, date_archived} dicts ready to
        pass to generate_email_preview_html as the `attachments` kwarg.
    """
    if today_iso is None:
        today_iso = date.today().isoformat()
    today = date.fromisoformat(today_iso)

    last_items = list(last_week_attachments or [])
    # Normalized-name index into last_items. First occurrence wins.
    norm_index = {}
    for i, a in enumerate(last_items):
        norm = _normalize_attachment_name(a.get('filename', ''))
        if norm:
            norm_index.setdefault(norm, i)

    used = set()
    result = []

    # --- Match phase: fresh ↔ last-week via normalized names -----------
    for fn in (fresh_filenames or []):
        if not fn:
            continue
        norm = _normalize_attachment_name(fn)
        if norm and norm in norm_index and norm_index[norm] not in used:
            i = norm_index[norm]
            used.add(i)
            last_a = last_items[i]
            last_status = last_a.get('status', 'active')
            last_checked = bool(last_a.get('checked', True))

            if last_status in ('active', 'new'):
                status = 'active'
                checked = True
            elif last_status == 'removed':
                # It's back in the fresh glob set — treat as restored.
                # If the user had it checked = True last week too (a revert),
                # keep it active; if unchecked, they explicitly removed it
                # and the glob re-adding it looks odd, but active is safer.
                status = 'active'
                checked = True
            elif last_status == 'archived':
                # Coming back from the archive — call it new so the user
                # sees it as a fresh addition this update.
                status = 'new'
                checked = True
            else:
                status = 'active'
                checked = True

            # NEW — share_to_procore preserved from last week
            share_to_procore = bool(last_a.get('share_to_procore', False))

            result.append({
                'filename': fn,  # fresh filename — carries this week's date
                'checked': checked,
                'status': status,
                'date_archived': '',
                'share_to_procore': share_to_procore,   # NEW
            })
        else:
            # No match → genuinely new attachment; bootstrap from filename
            result.append({
                'filename': fn,
                'checked': True,
                'status': 'new',
                'date_archived': '',
                'share_to_procore': _bootstrap_share_to_procore(fn),   # NEW
            })

    # --- Drop phase: last-week items not matched this week -------------
    for i, a in enumerate(last_items):
        if i in used:
            continue
        last_status = a.get('status', 'active')
        last_checked = bool(a.get('checked', True))
        # NEW — preserve share_to_procore on dropped items too
        share_to_procore = bool(a.get('share_to_procore', False))

        if last_status in ('active', 'new'):
            new_status = 'removed'
            new_checked = False
            new_archived = ''
        elif last_status == 'removed':
            new_status = 'archived'
            new_checked = False
            new_archived = today_iso
        elif last_status == 'archived':
            new_status = 'archived'
            new_checked = False
            new_archived = a.get('date_archived', today_iso)
        else:
            new_status = 'active'
            new_checked = last_checked
            new_archived = ''

        if (new_status == 'archived'
                and _too_old(new_archived, today, max_archived_days)):
            continue

        result.append({
            'filename': a.get('filename', ''),
            'checked': new_checked,
            'status': new_status,
            'date_archived': new_archived,
            'share_to_procore': share_to_procore,   # NEW
        })

    return result
