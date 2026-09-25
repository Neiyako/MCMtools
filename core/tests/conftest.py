"""Make `mcmcore` importable from the tests without installation."""

import pathlib
import sys

_CORE = pathlib.Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
