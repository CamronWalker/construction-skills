"""
Parse an edited project-context.html back into a Python dict.

Returns:
    project_name, job_number, contractual_completion,
    smartpm_url, smartpm_trends_url, smartpm_changelog_url,
    smartpm_project_name,  # SmartPM v2 card title (falls back to project_name)
    signer_name, signer_title, signer_mobile,
    procore_company_id, procore_project_id,
    graph_screenshots: list[str],
    project_log: list[{date, body}],
    to_recipients: list[{name, email}],
    cc_recipients: list[{name, email}],
    # Compat forms for generate_email_msg which expects the semicolon form:
    to_recipients_str: "Name <email>; email; ...",
    cc_recipients_str: "...",

No external deps — stdlib regex.
"""

import html as html_mod
import os
import re


# Strip scripts/styles — their template literals would otherwise leak
_RE_SCRIPT = re.compile(r'<script\b[^>]*>[\s\S]*?</script>', re.IGNORECASE)
_RE_STYLE = re.compile(r'<style\b[^>]*>[\s\S]*?</style>', re.IGNORECASE)
_RE_COMMENT = re.compile(r'<!--[\s\S]*?-->')

_RE_ATTR = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
VOID_ELEMENTS = {'img', 'br', 'hr', 'input', 'meta', 'link', 'area',
                 'base', 'col', 'embed', 'source', 'track', 'wbr'}


def _parse_attrs(s):
    # html.unescape on every attribute value -- the generator escapes user
    # text via html.escape on write, so the parser must decode entities on
    # read or values containing &, <, >, ", ' come back encoded.
    d = {
        m.group(1).lower(): html_mod.unescape(m.group(2))
        for m in _RE_ATTR.finditer(s or '')
    }
    # Capture valueless attrs (e.g. `readonly`)
    for m in re.finditer(r'(?:^|\s)([a-zA-Z][-a-zA-Z0-9_:.]*)(?=\s|/>|>|$)', s or ''):
        k = m.group(1).lower()
        if k not in d:
            d[k] = ''
    return d


def _find_matching_close(raw, start_idx, tag):
    tag = tag.lower()
    depth = 1
    pos = start_idx
    open_re = re.compile(rf'<{tag}\b[^>]*>', re.IGNORECASE)
    close_re = re.compile(rf'</{tag}\s*>', re.IGNORECASE)
    while pos < len(raw):
        m_open = open_re.search(raw, pos)
        m_close = close_re.search(raw, pos)
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


def _iter_elements(raw, tag_name):
    pos = 0
    tag_lc = tag_name.lower()
    is_void = tag_lc in VOID_ELEMENTS
    open_re = re.compile(rf'<{tag_lc}\b([^>]*)>', re.IGNORECASE)
    while pos < len(raw):
        m = open_re.search(raw, pos)
        if not m:
            return
        attrs = _parse_attrs(m.group(1))
        if is_void:
            yield attrs, '', (m.start(), m.end())
            pos = m.end()
            continue
        match = _find_matching_close(raw, m.end(), tag_lc)
        if not match:
            return
        _, inner_end, after_close = match
        inner = raw[m.end():inner_end]
        yield attrs, inner, (m.start(), after_close)
        pos = m.end()


def _strip_tags(s):
    if not s:
        return ''
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', '', s)
    return html_mod.unescape(s)


def parse_project_context_html(path):
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    raw = _RE_SCRIPT.sub('', raw)
    raw = _RE_STYLE.sub('', raw)
    raw = _RE_COMMENT.sub('', raw)

    result = {
        'project_name': '',
        'job_number': '',
        'contractual_completion': '',
        'smartpm_url': '',
        'smartpm_trends_url': '',
        'smartpm_changelog_url': '',
        'smartpm_project_name': '',
        'signer_name': '',
        'signer_title': '',
        'signer_mobile': '',
        'procore_company_id': '',
        'procore_project_id': '',
        'graph_screenshots': [],
        'project_log': [],
        'to_recipients': [],
        'cc_recipients': [],
    }

    # Scalar text inputs
    scalar_fields = set(result.keys()) - {
        'graph_screenshots', 'project_log', 'to_recipients', 'cc_recipients',
    }
    for attrs, _inner, _span in _iter_elements(raw, 'input'):
        field = attrs.get('data-field')
        if not field:
            continue
        t = (attrs.get('type') or '').lower()
        # Only scalar text inputs here — recipient_* / item_value / log_body
        # are nested inside their own containers and handled below.
        if field in scalar_fields and t in ('text', ''):
            # The <input> is nested; make sure we don't grab nested inputs
            result[field] = attrs.get('value', '')

    # Recipients
    for attrs, inner, _span in _iter_elements(raw, 'div'):
        classes = (attrs.get('class') or '').split()
        if 'recipient-group' not in classes:
            continue
        field = attrs.get('data-field')
        if field not in ('to_recipients', 'cc_recipients'):
            continue
        recips = []
        for row_attrs, row_inner, _r in _iter_elements(inner, 'div'):
            row_cls = (row_attrs.get('class') or '').split()
            if 'recipient-row' not in row_cls:
                continue
            name = ''
            email = ''
            for ia, _i, _s in _iter_elements(row_inner, 'input'):
                f = ia.get('data-field')
                if f == 'recipient_name':
                    name = ia.get('value', '').strip()
                elif f == 'recipient_email':
                    email = ia.get('value', '').strip()
            if email:
                recips.append({'name': name, 'email': email})
        result[field] = recips

    # String lists (graph_screenshots)
    for attrs, inner, _span in _iter_elements(raw, 'div'):
        classes = (attrs.get('class') or '').split()
        if 'string-list' not in classes:
            continue
        field = attrs.get('data-field')
        if not field or field not in ('graph_screenshots',):
            continue
        items = []
        for row_attrs, row_inner, _r in _iter_elements(inner, 'div'):
            row_cls = (row_attrs.get('class') or '').split()
            if 'string-list-row' not in row_cls:
                continue
            for ia, _i, _s in _iter_elements(row_inner, 'input'):
                if ia.get('data-field') == 'item_value':
                    val = ia.get('value', '').strip()
                    if val:
                        items.append(val)
                    break
        result[field] = items

    # Project log
    for attrs, inner, _span in _iter_elements(raw, 'div'):
        classes = (attrs.get('class') or '').split()
        if 'project-log' not in classes:
            continue
        entries = []
        # Scope: only direct .log-entry descendants of .log-entries
        entries_container_match = None
        for ea, einner, _esp in _iter_elements(inner, 'div'):
            if 'log-entries' in (ea.get('class') or '').split():
                entries_container_match = einner
                break
        if entries_container_match is None:
            continue
        for row_attrs, row_inner, _r in _iter_elements(
            entries_container_match, 'div'
        ):
            row_cls = (row_attrs.get('class') or '').split()
            if 'log-entry' not in row_cls:
                continue
            date = row_attrs.get('data-date', '').strip()
            body = ''
            for ba, binner, _bs in _iter_elements(row_inner, 'div'):
                if ('log-body' in (ba.get('class') or '').split()
                        and ba.get('data-field') == 'log_body'):
                    body = _strip_tags(binner).strip()
                    break
            if date:
                entries.append({'date': date, 'body': body})
        result['project_log'] = entries
        break

    # --- Derived compat strings for legacy skill code -----------------
    result['to_recipients_str'] = _recipients_to_string(result['to_recipients'])
    result['cc_recipients_str'] = _recipients_to_string(result['cc_recipients'])

    return result


def _recipients_to_string(recipients):
    parts = []
    for r in recipients or []:
        email = (r.get('email') or '').strip()
        if not email:
            continue
        name = (r.get('name') or '').strip()
        parts.append(f'{name} <{email}>' if name else email)
    return '; '.join(parts)


def load_project_context(schedules_root):
    """Load project-context.html from schedules_root.

    Returns: (parsed_dict, html_path) or (None, None) if the file doesn't
    exist. If missing, the caller should prompt the user to run the
    `schedule-project-init` skill.
    """
    html_path = os.path.join(schedules_root, 'project-context.html')
    if not os.path.isfile(html_path):
        return (None, None)
    return (parse_project_context_html(html_path), html_path)


if __name__ == '__main__':
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    args = ap.parse_args()
    print(json.dumps(parse_project_context_html(args.path), indent=2, default=str))
