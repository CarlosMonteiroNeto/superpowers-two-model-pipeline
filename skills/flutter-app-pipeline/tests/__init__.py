"""Test package bootstrap for the Flutter pipeline's script modules.

The production scripts live beside their shell wrappers rather than in an
installable Python package. Register that directory once for unittest
discovery so tests do not depend on import order or an external PYTHONPATH.
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
