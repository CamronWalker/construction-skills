"""Locate and load the cpm_engine helper module from the schedule-toolbox skill.

The CLI tools live alongside cpm_engine.py in the scheduling plugin tree, so
the import path is deterministic. We avoid making cpm_engine a real package
(it isn't structured as one) and use importlib to load it from its
canonical references/ folder.
"""

from pathlib import Path
import importlib.util


_THIS = Path(__file__).resolve()
_PLUGIN_ROOT = _THIS.parent.parent  # construction-skills/scheduling/
_REF_DIR = _PLUGIN_ROOT / 'skills' / 'schedule-toolbox' / 'references'


def load_cpm():
    """Return the loaded cpm_engine module."""
    spec = importlib.util.spec_from_file_location(
        'cpm_engine', _REF_DIR / 'cpm_engine.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reference_dir():
    return _REF_DIR


def plugin_root():
    return _PLUGIN_ROOT
