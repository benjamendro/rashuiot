"""Bridge to the repo's eshkol-matching module (folder name has a hyphen)."""

import importlib.util
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_ROOT, 'eshkol-matching', 'eshkol_matcher.py')

_spec = importlib.util.spec_from_file_location('eshkol_matcher', _PATH)
eshkol_matcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eshkol_matcher)

EshkolMatcher = eshkol_matcher.EshkolMatcher
sanitize = eshkol_matcher.sanitize
