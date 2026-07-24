"""Layout detection + path resolution for proposal-schedule projects.

Two folder layouts are supported:

LEGACY (pre-v4.0.0):
    <project>/Proposal Schedule/
        Murray Apex Center -v1.xer ... -v{N}.xer       <- all versions live here
        schedule-activities.json                        <- current
        proposal-anchors.json
        Schedule Plan - <Project>.pdf
        iterations/paste-*.json
        feedback/postmortem-*.md
        .cpm-cache/

NEW (v4.0.0+):
    <project>/
        <Project Name>.xer                              <- current/final XER, no version suffix
        schedule-activities.json                        <- current
        Schedule Plan.pdf                               <- final plan (post-approval)
        proposal-anchors.json                           <- anchors metadata
        Old Iterations/
            <Project Name> -v1.xer ... -v{N-1}.xer     <- prior versions only
            paste-*.json
            postmortem-*.md
            scores/v{N}.json
            .cpm-cache/
            .iterate-debug.log

Detection rule: the new layout exists if `<project>/Old Iterations/`
exists. Otherwise we fall back to legacy. `propsched init` creates the
new layout; `propsched migrate` converts legacy to new (not implemented
in v4.0.0 -- legacy projects stay legacy unless manually moved).

This module is the single source of truth for "where does X live" so the
CLI scripts don't each implement their own path resolution.
"""

import re
from pathlib import Path


LAYOUT_NEW = 'new'
LAYOUT_LEGACY = 'legacy'

NEW_ITERATIONS_DIR = 'Old Iterations'
LEGACY_PROPOSAL_DIR = 'Proposal Schedule'


def detect_layout(project):
    """Return 'new' if Old Iterations/ exists, else 'legacy'."""
    project = Path(project)
    if (project / NEW_ITERATIONS_DIR).is_dir():
        return LAYOUT_NEW
    if (project / LEGACY_PROPOSAL_DIR).is_dir():
        return LAYOUT_LEGACY
    # Empty / brand-new project: prefer new layout
    return LAYOUT_NEW


def iterations_dir(project, layout=None):
    """Where prior -v{N}.xer + paste archives + scores live."""
    project = Path(project)
    layout = layout or detect_layout(project)
    if layout == LAYOUT_NEW:
        return project / NEW_ITERATIONS_DIR
    # Legacy: iterations/ subfolder under Proposal Schedule/
    return project / LEGACY_PROPOSAL_DIR / 'iterations'


def proposal_dir(project, layout=None):
    """Where the current/working schedule files live (XER, JSON, anchors).

    For new layout this is the project root itself; for legacy it's the
    Proposal Schedule subfolder. CLIs that need to read or write the
    current files use this.
    """
    project = Path(project)
    layout = layout or detect_layout(project)
    if layout == LAYOUT_NEW:
        return project
    return project / LEGACY_PROPOSAL_DIR


def cache_dir(project, layout=None):
    """Where .cpm-cache/ lives -- always under the iterations folder."""
    return iterations_dir(project, layout) / '.cpm-cache'


def scores_dir(project, layout=None):
    return iterations_dir(project, layout) / 'scores'


def feedback_dir(project, layout=None):
    """Where postmortem-*.md files live.

    New layout: directly inside Old Iterations/ (postmortems alongside
    paste archives keeps the iteration record together).
    Legacy: feedback/ subfolder under Proposal Schedule/ (preserved for
    back-compat with v3.x projects).
    """
    project = Path(project)
    layout = layout or detect_layout(project)
    if layout == LAYOUT_NEW:
        return project / NEW_ITERATIONS_DIR
    return project / LEGACY_PROPOSAL_DIR / 'feedback'


def reviewer_feedback_dir(project, layout=None):
    """Where parked reviewer-feedback JSONs live (per-reviewer artifacts)."""
    return iterations_dir(project, layout) / 'reviewer-feedback'


def postmortems_dir(project, layout=None):
    """Where postmortem folders live (Tier 7+ folder-style postmortems).

    Legacy single-file postmortem-{date}-{slug}.md still works for older
    projects; new postmortems are folders under this directory.
    """
    return iterations_dir(project, layout) / 'postmortems'


def metadata_path(project, layout=None):
    """project-metadata.json at the project root (both layouts)."""
    return Path(project) / 'project-metadata.json'


def durations_path(project, layout=None):
    """durations.json accumulating per-activity duration knowledge."""
    return iterations_dir(project, layout) / 'durations.json'


def anchors_path(project, layout=None):
    return proposal_dir(project, layout) / 'proposal-anchors.json'


def activities_json_path(project, layout=None):
    return proposal_dir(project, layout) / 'schedule-activities.json'


def debug_log_path(project, layout=None):
    project = Path(project)
    layout = layout or detect_layout(project)
    if layout == LAYOUT_NEW:
        return iterations_dir(project, layout) / '.iterate-debug.log'
    return proposal_dir(project, layout) / '.iterate-debug.log'


_VERSION_RE = re.compile(r'-v(\d+)\.xer$', re.IGNORECASE)


def find_current_xer(project, layout=None):
    """Return the path to the CURRENT/working XER.

    New layout: the unversioned `<name>.xer` at the project root.
    Legacy: the highest -v{N}.xer under Proposal Schedule/.

    Returns None if no XER is found.
    """
    project = Path(project)
    layout = layout or detect_layout(project)
    if layout == LAYOUT_LEGACY:
        return _find_highest_versioned_xer(proposal_dir(project, layout))
    # New layout: any unversioned .xer at project root
    candidates = [p for p in project.glob('*.xer') if not _VERSION_RE.search(p.name)]
    if not candidates:
        # Fall back: maybe the root has versioned XERs (init not yet run)
        return _find_highest_versioned_xer(project)
    # If multiple, prefer the one whose stem matches the project folder name
    by_name = {p.stem.lower(): p for p in candidates}
    preferred = by_name.get(project.name.lower())
    if preferred:
        return preferred
    # Else the most recently modified
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _find_highest_versioned_xer(folder):
    folder = Path(folder)
    if not folder.is_dir():
        return None
    best = None
    for p in folder.glob('*.xer'):
        m = _VERSION_RE.search(p.name)
        if not m:
            continue
        v = int(m.group(1))
        if best is None or v > best[1]:
            best = (p, v)
    return best[0] if best else None


def latest_archived_version(project, layout=None):
    """In the new layout, return the highest -v{N} found under Old Iterations/.
    In the legacy layout, return the highest -v{N} under Proposal Schedule/.

    Returns 0 if none are present.
    """
    project = Path(project)
    layout = layout or detect_layout(project)
    folder = iterations_dir(project, layout) if layout == LAYOUT_NEW else proposal_dir(project, layout)
    best = 0
    if folder.is_dir():
        for p in folder.glob('*.xer'):
            m = _VERSION_RE.search(p.name)
            if m:
                v = int(m.group(1))
                if v > best:
                    best = v
    return best


def project_name_from_xer(xer_path):
    """Strip the -v{N}.xer suffix to recover the unversioned project-stem."""
    p = Path(xer_path)
    stem = p.stem
    m = re.search(r'^(.*?)\s*-v\d+$', stem, re.IGNORECASE)
    return m.group(1) if m else stem


def archived_xer_path(project, version, project_name=None, layout=None):
    """Return the path where -v{version}.xer should live in the iterations folder."""
    project = Path(project)
    layout = layout or detect_layout(project)
    if project_name is None:
        # Derive from current XER, else fall back to project folder name
        cur = find_current_xer(project, layout)
        project_name = project_name_from_xer(cur) if cur else project.name
    return iterations_dir(project, layout) / f'{project_name} -v{version}.xer'
