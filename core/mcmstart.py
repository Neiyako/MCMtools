#!/usr/bin/env python3
"""Launcher shim so `./start` works under any Python without installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcmcore.launcher import main

raise SystemExit(main())
