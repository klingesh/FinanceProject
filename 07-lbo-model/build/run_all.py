"""Rebuild everything offline: workbook -> Excel recalculation and checks -> outputs/*.csv -> figures/*.png.

Steps
  1. build/build_lbo_model.py      writes Castrol_India_LBO_Model.xlsx from data/ (openpyxl, live formulas)
  2. build/finalise_with_excel.py  Microsoft Excel via COM: creates the data tables, recalculates, runs the
                                   Base / Upside / Downside cases, checks every cell, writes
                                   build/verification_log.txt and outputs/*.csv
  3. build/make_figures.py         figures/*.png from outputs/*.csv

Step 2 needs Windows with Microsoft Excel. Refreshing the raw data is a separate, online step
(build/fetch_screener_standalone.py and build/fetch_market_data.py) and changes the snapshot in source_data/.

Run:  python build/run_all.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = ["build_lbo_model.py", "finalise_with_excel.py", "make_figures.py"]


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    for step in STEPS:
        print(f"=== {step}", flush=True)
        res = subprocess.run([sys.executable, str(ROOT / "build" / step)], cwd=ROOT, env=env, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        print(res.stdout, end="", flush=True)
        if res.stderr.strip():
            print(res.stderr, end="", file=sys.stderr, flush=True)
        if res.returncode != 0 or "EXIT_OK" not in res.stdout:
            print(f"FAILED at {step} (exit code {res.returncode})")
            return 1
    print(f"ALL STEPS OK in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
