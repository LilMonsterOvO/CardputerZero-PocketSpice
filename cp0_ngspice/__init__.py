"""PocketSpice (cp0-ngspice) package."""
from __future__ import annotations

import os
from pathlib import Path
import sys

if sys.platform.startswith("win"):
    _conda_bin = Path(sys.prefix) / "Library" / "bin"
    if _conda_bin.exists():
        os.add_dll_directory(str(_conda_bin))
        if str(_conda_bin) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(_conda_bin) + os.pathsep + os.environ.get("PATH", "")
