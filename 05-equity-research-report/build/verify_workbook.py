"""Recalculate AsianPaints_Ratio_Analysis.xlsx in Excel, then verify it and export the results to outputs/.

1. Excel (COM, own DispatchEx instance): CalculateFull, save, close, quit, so cached values exist.
2. openpyxl data_only=True: no error values anywhere; every Checks row = PASS; every ratio, DuPont factor, rank
   and scorecard value equals the independent pandas calculation in ratio_engine.py.
3. Export what the report uses: outputs/ratios_fy2022_fy2026.csv, outputs/dupont_fy2022_fy2026.csv,
   outputs/peer_comparison_fy2026.csv, outputs/peer_comparison_5yr.csv, outputs/scorecard.csv,
   outputs/workbook_checks.csv. Log: outputs/verification_log.txt.

Run:  python build/verify_workbook.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ratio_engine as RE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "AsianPaints_Ratio_Analysis.xlsx"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")
COLS = {"FY2022": "E", "FY2023": "F", "FY2024": "G", "FY2025": "H", "FY2026": "I", "AVG5": "J"}
log: list[str] = []


def say(msg: str) -> None:
    print(msg)
    log.append(msg)


def recalc_in_excel(path: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    xl = None
    wb = None
    try:
        xl = win32com.client.DispatchEx("Excel.Application")
        xl.Visible = False
        xl.DisplayAlerts = False
        wb = xl.Workbooks.Open(str(path))
        xl.CalculateFull()
        wb.Save()
        wb.Close(SaveChanges=False)
        wb = None
        say(f"Excel recalculation done: {path.name}")
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:  # noqa: BLE001
                pass
        if xl is not None:
            xl.Quit()
        pythoncom.CoUninitialize()


def main() -> None:
    t0 = time.time()
    recalc_in_excel(XLSX)
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    cmap = pd.read_csv(ROOT / "build" / "_cell_map.csv")
    rowof = {(r.sheet, r.company if isinstance(r.company, str) else "", r.code): int(r.row) for r in cmap.itertuples()}

    # 1. error values and empty formula results
    n_err, n_cells = 0, 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                n_cells += 1
                if isinstance(c.value, str) and c.value.strip() in ERRORS:
                    n_err += 1
                    say(f"ERROR VALUE {ws.title}!{c.coordinate}: {c.value}")
    say(f"Scanned {n_cells} non-empty cells on {len(wb.worksheets)} sheets: {n_err} error values")

    # 2. checks sheet
    ws = wb["Checks"]
    checks = []
    overall = None
    for r in range(5, ws.max_row + 1):
        res = ws.cell(r, 10).value
        name = ws.cell(r, 2).value
        if name == "OVERALL":
            overall = res
            continue
        if res in ("PASS", "FAIL"):
            checks.append({"check_no": ws.cell(r, 1).value, "check": name, "company": ws.cell(r, 3).value,
                           "result": res, "tolerance": ws.cell(r, 11).value})
    ck = pd.DataFrame(checks)
    ck.to_csv(OUT / "workbook_checks.csv", index=False)
    n_fail = int((ck.result == "FAIL").sum())
    say(f"Checks sheet: {len(ck)} checks, {n_fail} FAIL, OVERALL = {overall}")
    for _, x in ck[ck.result == "FAIL"].iterrows():
        say(f"   FAIL: {x.check} | {x.company}")

    # 3. compare with the pandas engine
    inp = RE.load_inputs()
    res = RE.compute_all(inp)
    wr, wd = wb["Ratios"], wb["DuPont"]
    worst, n_cmp = 0.0, 0
    rows_out, dup_out = [], []
    for sym in RE.COMPANIES:
        for code, lab, grp, fmt, better in RE.RATIOS:
            r = rowof[("Ratios", sym, code)]
            rec = {"company": RE.NAMES[sym], "code": code, "ratio": lab, "group": grp, "unit": fmt}
            for fy, col in COLS.items():
                xv = wr[f"{col}{r}"].value
                ev = float(res[sym].loc[code, fy])
                rec[fy] = xv
                d = abs(float(xv) - ev) / max(1.0, abs(ev))
                worst = max(worst, d)
                n_cmp += 1
                if d > 1e-9:
                    say(f"MISMATCH Ratios {sym} {code} {fy}: excel {xv} engine {ev}")
            rows_out.append(rec)
        for code in ["D3_NPM", "D3_AT", "D3_EM", "D3_ROE", "D5_TB", "D5_IB", "D5_EBITM", "D5_AT", "D5_EM", "D5_ROE"]:
            r = rowof[("DuPont", sym, code)]
            rec = {"company": RE.NAMES[sym], "code": code}
            for fy, col in COLS.items():
                xv = wd[f"{col}{r}"].value
                ev = float(res[sym].loc[code, fy])
                rec[fy] = xv
                d = abs(float(xv) - ev) / max(1.0, abs(ev))
                worst = max(worst, d)
                n_cmp += 1
                if d > 1e-9:
                    say(f"MISMATCH DuPont {sym} {code} {fy}: excel {xv} engine {ev}")
            dup_out.append(rec)
    say(f"Ratios + DuPont: {n_cmp} cells compared with ratio_engine.py, worst relative gap {worst:.2e}")
    pd.DataFrame(rows_out).to_csv(OUT / "ratios_fy2022_fy2026.csv", index=False)
    pd.DataFrame(dup_out).to_csv(OUT / "dupont_fy2022_fy2026.csv", index=False)

    # peer tables and scorecard
    wp = wb["Peer_Comparison"]
    names = [RE.NAMES[s] for s in RE.COMPANIES]
    rank_bad = 0
    for basis, col_key in [("FY2026", "FY2026"), ("AVG5", "AVG5")]:
        pt = RE.peer_table(res, col_key, inp if basis == "AVG5" else None).set_index("code")
        recs = []
        for code, lab, grp, fmt, better in RE.RATIOS:
            r = rowof[("Peer_Comparison", basis, code)]
            rec = {"code": code, "ratio": wp.cell(r, 2).value, "better": better, "unit": fmt}
            for i, n in enumerate(names):
                xv = wp.cell(r, 4 + i).value
                rec[n] = xv
                if abs(float(xv) - float(pt.loc[code, n])) > 1e-9 * max(1, abs(float(pt.loc[code, n]))):
                    say(f"MISMATCH peer value {basis} {code} {n}: {xv} vs {pt.loc[code, n]}")
                    rank_bad += 1
                if better:
                    xr = wp.cell(r, 11 + i).value
                    rec[f"rank_{n}"] = xr
                    if int(xr) != int(pt.loc[code, f"rank_{n}"]):
                        say(f"MISMATCH rank {basis} {code} {n}: {xr} vs {pt.loc[code, f'rank_{n}']}")
                        rank_bad += 1
            rec["peer_median"] = wp.cell(r, 9).value
            rec["ap_minus_median"] = wp.cell(r, 10).value
            recs.append(rec)
        pd.DataFrame(recs).to_csv(OUT / ("peer_comparison_fy2026.csv" if basis == "FY2026" else
                                         "peer_comparison_5yr.csv"), index=False)
    sr, posr = rowof[("Peer_Comparison", "", "score_r")], rowof[("Peer_Comparison", "", "pos_r")]
    comp26 = RE.composite(RE.peer_table(res, "FY2026"))
    comp5 = RE.composite(RE.peer_table(res, "AVG5", inp))
    sc = []
    for i, n in enumerate(names):
        x26, x5 = wp.cell(sr, 4 + i).value, wp.cell(sr, 9 + i).value
        p26, p5 = wp.cell(posr, 4 + i).value, wp.cell(posr, 9 + i).value
        if abs(x26 - comp26[n]) > 1e-9 or abs(x5 - comp5[n]) > 1e-9:
            say(f"MISMATCH scorecard {n}: excel {x26:.4f}/{x5:.4f} engine {comp26[n]:.4f}/{comp5[n]:.4f}")
            rank_bad += 1
        sc.append({"company": n, "weighted_rank_fy2026": x26, "position_fy2026": p26,
                   "weighted_rank_5yr": x5, "position_5yr": p5})
    pd.DataFrame(sc).to_csv(OUT / "scorecard.csv", index=False)
    say(f"Peer tables, ranks and scorecard: {rank_bad} mismatches")
    for s in sc:
        say(f"   {s['company']:<15} FY2026 weighted rank {s['weighted_rank_fy2026']:.3f} (#{s['position_fy2026']}), "
            f"5-yr {s['weighted_rank_5yr']:.3f} (#{s['position_5yr']})")
    cov = wb["Cover"]
    say("Cover: " + " | ".join(str(cov.cell(r, 4).value) for r in range(14, 18)))
    con = wb["Conclusion"]
    say("Conclusion verdict: " + str(con["A3"].value))
    for r in range(1, con.max_row + 1):
        v = con.cell(r, 1).value
        if isinstance(v, str) and len(v) > 120:
            say("   " + v[:400])

    # key numbers for the notes
    ap = res["ASIANPAINT"]
    say("Asian Paints FY2026: " + ", ".join(f"{k} {ap.loc[k, 'FY2026']:.4f}" for k in
                                             ["GM", "EBITDAM", "NPM", "ROE", "ROE_ADJ", "ROCE", "AT", "CCC", "FCFM"]))
    ok = n_err == 0 and n_fail == 0 and overall == "PASS" and worst < 1e-9 and rank_bad == 0
    say(f"VERIFICATION {'PASSED' if ok else 'FAILED'} in {time.time() - t0:.1f} s")
    (OUT / "verification_log.txt").write_text("\n".join(log), encoding="utf-8")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
