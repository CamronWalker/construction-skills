"""
Parse an edited email preview HTML file back into a dict of email fields.

Reads the file written by generate_email_preview_html.py after the human has
edited it in a browser. Handles:
    - scalar fields, numeric metrics, narrative blocks
    - per-item lists: each LI has text, checked, status, date_archived
    - custom_paragraphs: [{label, text, checked}]
    - attachments: [{filename, checked, status, date_archived}]
    - summary / graph screenshot paths

Two shapes returned for lists (and attachments):
    red_flags         -> list of markdown strings (checked & non-archived only)
                         ready to pass to generate_email_msg.py
    red_flags_full    -> list of dicts {text, checked, status, date_archived}
                         pass this into next week's generate_email_preview_html
                         along with transition_items()

HTML -> markdown:
    <b>/<strong>                     -> **...**
    <span class="priority">          -> ==...==
    <span style="color:#C94444..">   -> ==...==

Stdlib only.
"""

import html as html_mod
import os
import re


PROJECT_INFO_FIELDS = {
    'project_name', 'job_number',
    'contractual_completion', 'projected_completion',
}

# --- HTML -> markdown --------------------------------------------------

_RE_PRIORITY_CLASS = re.compile(
    r'<span\b[^>]*class="[^"]*\bpriority\b[^"]*"[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
_RE_PRIORITY_STYLE = re.compile(
    r'<span\b[^>]*style="[^"]*color:\s*#c94444[^"]*"[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
_RE_BOLD = re.compile(r'<(b|strong)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
_RE_ITALIC = re.compile(r'<(i|em)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
_RE_BR = re.compile(r'<br\s*/?>', re.IGNORECASE)
# Diff markup (from generate_email_preview_html.diff_words_html):
#   <del class="diff-del">X</del>  -> removed text, drop entirely
#   <ins class="diff-ins">X</ins>  -> new text, unwrap (keep content)
_RE_DIFF_DEL = re.compile(r'<del\b[^>]*>[\s\S]*?</del>', re.IGNORECASE)
_RE_DIFF_INS = re.compile(r'<ins\b[^>]*>([\s\S]*?)</ins>', re.IGNORECASE)
_RE_ANY_TAG = re.compile(r'<[^>]+>')


def html_to_markdown(inner_html):
    if not inner_html:
        return ''
    s = inner_html
    # Diff markup: drop <del> content (phantom), keep <ins> content.
    s = _RE_DIFF_DEL.sub('', s)
    s = _RE_DIFF_INS.sub(r'\1', s)
    s = _RE_PRIORITY_CLASS.sub(r'==\1==', s)
    s = _RE_PRIORITY_STYLE.sub(r'==\1==', s)
    s = _RE_BOLD.sub(r'**\2**', s)
    s = _RE_ITALIC.sub(r'*\2*', s)
    s = _RE_BR.sub('\n', s)
    s = _RE_ANY_TAG.sub('', s)
    s = html_mod.unescape(s)
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in s.splitlines()]
    return '\n'.join(l for l in lines if l is not None).strip()


# --- Element iteration ------------------------------------------------

VOID_ELEMENTS = {'img', 'br', 'hr', 'input', 'meta', 'link', 'area',
                 'base', 'col', 'embed', 'source', 'track', 'wbr'}

_RE_ATTR = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')


def _parse_attrs(attr_str):
    d = {m.group(1).lower(): m.group(2) for m in _RE_ATTR.finditer(attr_str)}
    # Also capture valueless boolean attrs (e.g. `checked`)
    for m in re.finditer(r'(?:^|\s)([a-zA-Z][-a-zA-Z0-9_:.]*)(?=\s|/>|>|$)', attr_str):
        k = m.group(1).lower()
        if k not in d:
            d[k] = ''
    return d


def _find_matching_close(html, start_idx, tag):
    tag = tag.lower()
    depth = 1
    pos = start_idx
    open_re = re.compile(rf'<{tag}\b[^>]*>', re.IGNORECASE)
    close_re = re.compile(rf'</{tag}\s*>', re.IGNORECASE)
    while pos < len(html):
        m_open = open_re.search(html, pos)
        m_close = close_re.search(html, pos)
        if not m_close:
            return None
        if m_open and m_open.start() < m_close.start():
            depth += 1
            pos = m_open.end()
            continue
        depth -= 1
        if depth == 0:
            return (start_idx, m_close.start(), m_close.end())
        pos = m_close.end()
    return None


def _iter_elements(html, tag_name, attr_filter=None):
    pos = 0
    tag_lc = tag_name.lower()
    is_void = tag_lc in VOID_ELEMENTS
    open_re = re.compile(rf'<{tag_lc}\b([^>]*)>', re.IGNORECASE)
    while pos < len(html):
        m = open_re.search(html, pos)
        if not m:
            return
        attrs = _parse_attrs(m.group(1))
        if is_void:
            if attr_filter is None or attr_filter(attrs):
                yield attrs, '', (m.start(), m.end())
            pos = m.end()
            continue
        inner_start = m.end()
        match = _find_matching_close(html, inner_start, tag_lc)
        if not match:
            return
        _, inner_end, after_close = match
        inner_html = html[inner_start:inner_end]
        if attr_filter is None or attr_filter(attrs):
            yield attrs, inner_html, (m.start(), after_close)
        pos = m.end()


def _has_contenteditable(attrs):
    ce = (attrs.get('contenteditable') or '').lower()
    return ce == 'true' or ce == ''


def _is_checked(attrs):
    """Treat `checked` / `checked=""` / `checked="checked"` as true."""
    return 'checked' in attrs


# --- Main parse --------------------------------------------------------

_RE_SCRIPT = re.compile(r'<script\b[^>]*>[\s\S]*?</script>', re.IGNORECASE)
_RE_STYLE = re.compile(r'<style\b[^>]*>[\s\S]*?</style>', re.IGNORECASE)


def parse_preview_html(path):
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()

    # Strip scripts/styles so template literals don't leak into parsing
    raw = _RE_SCRIPT.sub('', raw)
    raw = _RE_STYLE.sub('', raw)

    html_dir = os.path.dirname(os.path.abspath(path))

    # --- Metrics ------------------------------------------------------
    metrics = {}
    for m in re.finditer(
        r'data-metric="([^"]+)"[^>]*?data-value="(-?\d+)"', raw
    ):
        try:
            metrics[m.group(1)] = int(m.group(2))
        except ValueError:
            pass

    # --- Scalar editable spans/divs/p/a ------------------------------
    scalars = {}
    for tag_name in ('span', 'div', 'p'):
        for attrs, inner, _ in _iter_elements(raw, tag_name):
            if 'data-field' not in attrs:
                continue
            classes = (attrs.get('class') or '').split()
            # Skip custom-paragraph and attachment markers — handled separately
            if ({'paragraph_label', 'paragraph_text', 'attachment_name',
                 'li-content'} & {attrs['data-field']}):
                # These are inside items; we handle item containers
                # separately. Also skip if the element is inside a list item
                # or custom paragraph structure.
                pass
            if not _has_contenteditable(attrs) and tag_name != 'p':
                continue
            if tag_name == 'div' and 'block' not in classes:
                continue
            if (_has_contenteditable(attrs)
                    and attrs['data-field'] not in
                    {'paragraph_label', 'paragraph_text', 'attachment_name'}):
                scalars[attrs['data-field']] = html_to_markdown(inner)
    # Anchors (e.g. changelog URL)
    for attrs, inner, _ in _iter_elements(raw, 'a'):
        if 'data-field' in attrs:
            scalars.setdefault(attrs['data-field'], html_to_markdown(inner))

    # --- Lists (full items with status/checked) -----------------------
    # Main lists live in <ol/ul data-field="red_flags">; archived items live
    # in a sibling <ol/ul data-field="red_flags_archived">. Merge both under
    # the base field name so callers see a single {field}_full list.
    lists_full = {}
    for tag in ('ol', 'ul'):
        for attrs, inner, _ in _iter_elements(raw, tag):
            if 'data-field' not in attrs:
                continue
            if 'editable-list' not in (attrs.get('class') or '').split():
                continue
            field = attrs['data-field']
            base_field = (field[:-len('_archived')]
                          if field.endswith('_archived') else field)
            items = []
            for li_attrs, li_inner, _r in _iter_elements(inner, 'li'):
                item = _extract_list_item(li_attrs, li_inner)
                if item is not None:
                    items.append(item)
            if base_field in lists_full:
                lists_full[base_field].extend(items)
            else:
                lists_full[base_field] = items

    # Derived: string-only lists (checked & non-archived) for email gen
    lists_strings = {}
    for field, items in lists_full.items():
        lists_strings[field] = [
            i['text'] for i in items
            if i.get('checked') and i.get('status') != 'archived'
            and i.get('text', '').strip()
        ]

    # --- Custom paragraphs --------------------------------------------
    custom_paragraphs = []
    # Scope to the container so we don't pick up JS template literals.
    for container_attrs, container_inner, _ in _iter_elements(raw, 'div'):
        if container_attrs.get('data-field') != 'custom_paragraphs':
            continue
        for attrs, inner, _ in _iter_elements(container_inner, 'div'):
            if 'custom-paragraph' not in (attrs.get('class') or '').split():
                continue
            if 'custom-paragraphs' in (attrs.get('class') or '').split():
                continue
            label = ''
            text = ''
            checked = False
            for iattrs, _i, _r in _iter_elements(inner, 'input'):
                t = (iattrs.get('type') or '').lower()
                if t == 'checkbox':
                    checked = _is_checked(iattrs)
                    break
            for sattrs, sinner, _s in _iter_elements(inner, 'span'):
                if sattrs.get('data-field') == 'paragraph_label':
                    label = html_to_markdown(sinner)
                    break
            for dattrs, dinner, _d in _iter_elements(inner, 'div'):
                if dattrs.get('data-field') == 'paragraph_text':
                    text = html_to_markdown(dinner)
                    break
            custom_paragraphs.append(
                {'label': label, 'text': text, 'checked': checked}
            )
        break  # only one container

    # --- Attachments --------------------------------------------------
    attachments_full = []
    for container_attrs, container_inner, _ in _iter_elements(raw, 'div'):
        if 'attachments-section' not in (container_attrs.get('class') or '').split():
            continue
        for attrs, inner, _ in _iter_elements(container_inner, 'li'):
            if 'attachment-item' not in (attrs.get('class') or '').split():
                continue
            att = _extract_attachment_item(attrs, inner)
            if att is not None:
                attachments_full.append(att)
        break

    # Derived: list of filenames to attach (checked & non-archived)
    attachment_names = [
        a['filename'] for a in attachments_full
        if a.get('checked') and a.get('status') != 'archived'
        and a.get('filename', '').strip()
    ]

    # --- Changes-report option -----------------------------------------
    # Picked up from <input data-field="include_changes_report"> + the sibling
    # <input data-field="changes_report_filename"> inside the attachments card.
    changes_report = {'include': False, 'filename': ''}
    m_cr_cb = re.search(
        r'<input\b[^>]*data-field="include_changes_report"[^>]*>', raw,
        re.IGNORECASE,
    )
    if m_cr_cb:
        changes_report['include'] = bool(
            re.search(r'\s+checked(\s|=|>|/)', m_cr_cb.group(0), re.IGNORECASE)
        )
    m_cr_fn = re.search(
        r'<input\b[^>]*data-field="changes_report_filename"[^>]*>', raw,
        re.IGNORECASE,
    )
    if m_cr_fn:
        m_val = re.search(r'value="([^"]*)"', m_cr_fn.group(0), re.IGNORECASE)
        if m_val:
            changes_report['filename'] = html_mod.unescape(m_val.group(1))
    attachment_paths = [
        (fn if os.path.isabs(fn) else os.path.normpath(os.path.join(html_dir, fn)))
        for fn in attachment_names
    ]

    # --- Images -------------------------------------------------------
    summary_rel = ''
    for attrs, _inner, _ in _iter_elements(raw, 'img'):
        if attrs.get('data-field') == 'summary_screenshot_rel':
            summary_rel = attrs.get('data-src') or attrs.get('src') or ''
            break

    graph_rels = []
    for attrs, inner, _ in _iter_elements(raw, 'div'):
        classes = (attrs.get('class') or '').split()
        if ('graph-list' not in classes
                or attrs.get('data-field') != 'graph_screenshot_rels'):
            continue
        for iattrs, _iinner, _r in _iter_elements(inner, 'img'):
            src = iattrs.get('data-src') or iattrs.get('src') or ''
            if src:
                graph_rels.append(src)
        break

    def _rel_to_abs(rel):
        if not rel:
            return ''
        if os.path.isabs(rel):
            return rel
        return os.path.normpath(os.path.join(html_dir, rel))

    project_info = {k: scalars.get(k, '') for k in PROJECT_INFO_FIELDS}

    result = {
        'project_info': project_info,
        'days_behind': metrics.get('days_behind', 0),
        'gain_loss': metrics.get('gain_loss', 0),
        # Email-gen shape (strings)
        'successes': lists_strings.get('successes', []),
        'red_flags': lists_strings.get('red_flags', []),
        'stalled_tasks': lists_strings.get('stalled_tasks', []),
        'key_items': lists_strings.get('key_items', []),
        # Carry-forward shape (full dicts)
        'successes_full': lists_full.get('successes', []),
        'red_flags_full': lists_full.get('red_flags', []),
        'stalled_tasks_full': lists_full.get('stalled_tasks', []),
        'key_items_full': lists_full.get('key_items', []),
        'gain_loss_narrative': scalars.get('gain_loss_narrative', ''),
        'eot_recovery': scalars.get('eot_recovery', ''),
        'logic_changes': scalars.get('logic_changes', ''),
        'smartpm_changelog_url': scalars.get('smartpm_changelog_url', ''),
        'custom_paragraphs': custom_paragraphs,
        'attachments': attachments_full,
        'attachment_names': attachment_names,
        'attachment_paths': attachment_paths,
        'changes_report': changes_report,
        'summary_screenshot_path': _rel_to_abs(summary_rel),
        'summary_screenshot_rel': summary_rel,
        'graph_screenshot_paths': [_rel_to_abs(r) for r in graph_rels],
        'graph_screenshot_rels': graph_rels,
        'signer_name': scalars.get('signer_name', ''),
        'signer_title': scalars.get('signer_title', ''),
        'signer_mobile': scalars.get('signer_mobile', ''),
    }

    # Fallback metric extraction from visible text
    if 'days_behind' not in metrics:
        m = re.search(r'(-?\d+)', scalars.get('days_line_value', ''))
        if m:
            val = int(m.group(1))
            if 'Ahead' in scalars.get('days_line_label', ''):
                val = -val
            result['days_behind'] = val
    if 'gain_loss' not in metrics:
        m = re.search(r'(-?\d+)', scalars.get('gain_loss_value', ''))
        if m:
            val = int(m.group(1))
            if 'Loss' in scalars.get('gain_loss_value', ''):
                val = -val
            result['gain_loss'] = val

    # Back-compat: derive include_* flags from custom paragraphs
    result['include_compliance_report'] = any(
        p['checked'] and 'compliance' in p['label'].lower()
        for p in custom_paragraphs
    )
    result['include_procurement_sheets'] = any(
        p['checked'] and ('procurement' in p['label'].lower()
                          or 'progress update' in p['label'].lower())
        for p in custom_paragraphs
    )

    return result


def _extract_list_item(li_attrs, li_inner):
    """Extract {text, checked, status, date_archived} from a list-item LI.

    Handles both the new per-item card structure and the older flat
    `<li contenteditable>...</li>` structure from earlier previews.
    """
    classes = (li_attrs.get('class') or '').split()
    status = li_attrs.get('data-status', 'active')
    date_archived = li_attrs.get('data-archived', '')

    # Prefer data-checked attribute; fall back to checkbox state inside
    dc = li_attrs.get('data-checked')
    if dc is not None:
        checked = dc.lower() == 'true'
    else:
        checked = True
        for iattrs, _i, _r in _iter_elements(li_inner, 'input'):
            if (iattrs.get('type') or '').lower() == 'checkbox':
                checked = _is_checked(iattrs)
                break

    # Find the content. New structure: <div class="li-content">.
    # Old structure: LI itself is contenteditable, text is directly inside.
    text = ''
    content_found = False
    for dattrs, dinner, _r in _iter_elements(li_inner, 'div'):
        if 'li-content' in (dattrs.get('class') or '').split():
            text = html_to_markdown(dinner)
            content_found = True
            break
    if not content_found:
        # Legacy: LI directly contains the text (strip any nested controls)
        # We approximate by taking everything before the first control div.
        m = re.search(
            r'<div\b[^>]*class="[^"]*li-controls[^"]*"', li_inner,
            flags=re.IGNORECASE,
        )
        candidate = li_inner[:m.start()] if m else li_inner
        text = html_to_markdown(candidate)

    if not text.strip() and not content_found:
        return None
    return {
        'text': text,
        'checked': checked,
        'status': status,
        'date_archived': date_archived,
    }


def _extract_attachment_item(attrs, inner):
    classes = (attrs.get('class') or '').split()
    status = attrs.get('data-status', 'active')
    date_archived = attrs.get('data-archived', '')
    dc = attrs.get('data-checked')
    if dc is not None:
        checked = dc.lower() == 'true'
    else:
        checked = True
        for iattrs, _i, _r in _iter_elements(inner, 'input'):
            if (iattrs.get('type') or '').lower() == 'checkbox':
                checked = _is_checked(iattrs)
                break
    filename = ''
    for sattrs, sinner, _ in _iter_elements(inner, 'span'):
        if (sattrs.get('data-field') == 'attachment_name'
                or 'attachment-name' in (sattrs.get('class') or '').split()):
            filename = html_to_markdown(sinner).strip()
            break
    if not filename:
        return None
    return {
        'filename': filename,
        'checked': checked,
        'status': status,
        'date_archived': date_archived,
    }


if __name__ == '__main__':
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument('html_path')
    args = ap.parse_args()
    fields = parse_preview_html(args.html_path)
    print(json.dumps(fields, indent=2, default=str))
