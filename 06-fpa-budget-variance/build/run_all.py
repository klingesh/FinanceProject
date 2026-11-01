"""Rebuild everything offline from data/ and source_data/: peers -> workbook -> Excel recalc + checks -> figures.

Run from the project folder:  python build/run_all.py
Needs Windows with Microsoft Excel for step 3 (COM recalculation, checks and the driver-change test).
Downloading the sources again is a separate, optional step: python build/fetch_source_data.py
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = ["peer_benchmarks.py", "build_fpa_model.py", "recalc_verify.py", "make_figures.py"]


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for step in STEPS:
        print(f"== {step}", flush=True)
        rc = subprocess.call([sys.executable, os.path.join(HERE, step)], cwd=HERE, env=env)
        if rc != 0:
            print(f"FAILED at {step} (exit {rc})")
            return rc
    print("ALL STEPS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
