"""Verify UltraTech_3Statement_Model.xlsx in Excel (COM) and export results.

1. Opens the workbook in a private Excel instance (DispatchEx), creates the one-variable data table on the Cover
   sheet (row input cell C6 = scenario), and recalculates.
2. Switches the scenario to 1, 2 and 3, recalculates, and records every check and the key outputs.
3. Restores the Base case, saves (so cached values exist) and closes.
4. Re-opens the file with openpyxl (data_only=True): no error values anywhere, all checks PASS, data table filled.

Writes outputs/scenario_summary.csv, outputs/checks_log.csv, outputs/model_outputs_by_scenario.csv and
outputs/verification_log.txt.

Run:  python build/05_verify_model.py
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import pythoncom
import win32com.client
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "UltraTech_3Statement_Model.xlsx"
MAP = json.loads((ROOT / "build" / "model_map.json").read_text(encoding="utf-8"))
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
NAMES = {1: "Base", 2: "Bull", 3: "Bear"}
COLS = ["C", "D", "E", "F", "G", "H"]
YEARS = ["FY2026A", "FY2027E", "FY2028E", "FY2029E", "FY2030E", "FY2031E"]
ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")
EXPORT = {  # sheet -> keys exported per scenario
    "Income_Statement": ["cap_close", "adds", "vol", "util", "real", "rm_t", "pf_t", "fr_t", "oth_t", "ebitda_t", "ns",
                         "rev", "opex", "ebitda", "ebitda_m", "da", "ebit", "oi", "fin", "pbt", "tax", "pat", "nci",
                         "own", "eps"],
    "Balance_Sheet": ["capex_exp", "capex_mnt", "capex", "capz", "cwip_close", "nfa_close", "inv", "rec", "pay", "nwc",
                      "a_cash", "ta", "te", "l_debt", "tel", "bal", "oe_div", "dps", "nd", "nd_e", "ce", "roce"],
    "Cash_Flow": ["pat", "da", "d_inv", "d_rec", "d_pay", "cfo", "capex", "cfi", "new", "rep", "rev", "div", "cff",
                  "net", "close", "fcf"],
    "Debt_Schedule": ["t_close", "t_int", "r_draw", "r_close", "r_int", "fin_total", "debt_total", "icov"],
}


def num(v):
    return round(float(v), 4) if isinstance(v, (int, float)) else v


def main() -> None:
    log: list[str] = [f"verify run {time.strftime('%Y-%m-%d %H:%M')} file={XLSX.name}"]
    rows = MAP["rows"]
    dt_first, dt_last = MAP["cover"]["dt_first"], MAP["cover"]["dt_last"]
    k_first, k_last = rows["Checks"]["first"], rows["Checks"]["last"]
    check_rows, out_rows, dt_values = [], [], {}
    pythoncom.CoInitialize()
    xl = win32com.client.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    wb = None
    try:
        wb = xl.Workbooks.Open(str(XLSX))
        xl.Calculation = -4105  # xlCalculationAutomatic (includes data tables)
        cover = wb.Worksheets("Cover")
        cover.Range(MAP["datatable"]).Table(cover.Range(MAP["scenario_cell"]))  # row input cell = C6
        log.append(f"data table created on Cover!{MAP['datatable']} (row input cell {MAP['scenario_cell']})")
        chk = wb.Worksheets("Checks")
        for s in (1, 2, 3):
            cover.Range("C6").Value = s
            xl.CalculateFull()
            overall = chk.Range("C3").Value
            log.append(f"scenario {s} ({NAMES[s]}): overall checks = {overall}")
            for r in range(k_first, k_last + 1):
                rec = [chk.Range(f"{c}{r}").Value for c in "ABCDE"]
                check_rows.append({"scenario": NAMES[s], "check_no": int(rec[0]), "check": rec[1],
                                   "value": num(rec[2]), "tolerance": rec[3], "result": rec[4]})
                if rec[4] != "PASS":
                    log.append(f"   FAIL #{int(rec[0])} {rec[1]}: value={rec[2]}")
            for sheet, keys in EXPORT.items():
                ws = wb.Worksheets(sheet)
                for key in keys:
                    r = rows[sheet][key]
                    vals = ws.Range(f"C{r}:H{r}").Value[0]
                    out_rows.append({"scenario": NAMES[s], "sheet": sheet, "line": key,
                                     "label": ws.Range(f"A{r}").Value, "unit": ws.Range(f"B{r}").Value,
                                     **{y: num(v) for y, v in zip(YEARS, vals)}})
            live = [c[0] for c in cover.Range(f"B{dt_first}:B{dt_last}").Value]
            table = cover.Range(f"C{dt_first}:E{dt_last}").Value
            diff = max(abs(float(l) - float(t[s - 1])) for l, t in zip(live, table))
            log.append(f"   data table column {s} vs live model: max abs difference {diff:.6f}")
        dt_values = {i: row for i, row in enumerate(cover.Range(f"C{dt_first}:E{dt_last}").Value)}
        cover.Range("C6").Value = 1
        xl.CalculateFull()
        log.append(f"restored scenario 1 (Base); overall checks = {chk.Range('C3').Value}")
        wb.Save()
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        xl.Quit()
        pythoncom.CoUninitialize()
    # ---- exports
    with open(OUT / "checks_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(check_rows[0]))
        w.writeheader()
        w.writerows(check_rows)
    with open(OUT / "model_outputs_by_scenario.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    summ = []
    eng = MAP["engine"]
    for key, label, unit in MAP["metrics"]:
        for s in (1, 2, 3):
            vals = {y: num(dt_values[eng[f"{key}|{y}"] - dt_first][s - 1]) for y in YEARS[1:]}
            summ.append({"scenario": NAMES[s], "metric": label, "unit": unit, **vals})
    with open(OUT / "scenario_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)
    log.append(f"wrote outputs: checks_log.csv ({len(check_rows)} rows), model_outputs_by_scenario.csv "
               f"({len(out_rows)} rows), scenario_summary.csv ({len(summ)} rows)")
    verify_openpyxl(log, rows)
    n_fail = sum(1 for c in check_rows if c["result"] != "PASS")
    log.append(f"RESULT: {len(check_rows) - n_fail} of {len(check_rows)} checks PASS across 3 scenarios")
    (OUT / "verification_log.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    print("EXIT_OK" if n_fail == 0 else "EXIT_FAIL")


def verify_openpyxl(log: list[str], rows: dict) -> None:
    """Re-open the saved file: cached values present, no error values, checks PASS, sensible Base outputs."""
    wf = load_workbook(XLSX)  # formulas
    wv = load_workbook(XLSX, data_only=True)  # cached values written by Excel
    n_form = n_missing = 0
    errors = []
    for ws in wv.worksheets:
        wsf = wf[ws.title]
        for row in ws.iter_rows():
            for c in row:
                fv = wsf[c.coordinate].value
                is_formula = (isinstance(fv, str) and fv.startswith("=")) or \
                    type(fv).__name__ in ("ArrayFormula", "DataTableFormula")
                if is_formula:
                    n_form += 1
                    if c.value is None:
                        n_missing += 1
                if isinstance(c.value, str) and c.value.strip() in ERRORS:
                    errors.append(f"{ws.title}!{c.coordinate}={c.value}")
    log.append(f"openpyxl: {n_form} formula cells, {n_missing} without a cached value, {len(errors)} error values")
    for e in errors[:20]:
        log.append(f"   ERROR {e}")
    k = wv["Checks"]
    res = [k[f"E{r}"].value for r in range(rows["Checks"]["first"], rows["Checks"]["last"] + 1)]
    log.append(f"openpyxl: Checks!C3 = {k['C3'].value}; {res.count('PASS')} of {len(res)} checks PASS (Base saved)")
    cv = wv["Cover"]
    first, last = MAP["cover"]["dt_first"], MAP["cover"]["dt_last"]
    filled = sum(isinstance(cv[f"{c}{r}"].value, (int, float)) for r in range(first, last + 1) for c in "CDE")
    log.append(f"openpyxl: data table cells with numbers = {filled} of {3 * (last - first + 1)}")
    # sensible-output checks on the saved Base case
    g = lambda sh, key: [wv[sh][f"{c}{rows[sh][key]}"].value for c in COLS]  # noqa: E731
    base = {"rev": g("Income_Statement", "rev"), "ebitda": g("Income_Statement", "ebitda"),
            "ebitda_t": g("Income_Statement", "ebitda_t"), "own": g("Income_Statement", "own"),
            "eps": g("Income_Statement", "eps"), "capex": g("Balance_Sheet", "capex"),
            "fcf": g("Cash_Flow", "fcf"), "nd": g("Balance_Sheet", "nd"), "nd_e": g("Balance_Sheet", "nd_e"),
            "roce": g("Balance_Sheet", "roce"), "util": g("Income_Statement", "util"),
            "bal": g("Balance_Sheet", "bal")}
    for kk, vals in base.items():
        log.append(f"   Base {kk:8s} " + "  ".join(f"{y}={v:,.2f}" for y, v in zip(YEARS, vals)))
    sane = [("utilisation <= 100%", all(v <= 1 for v in base["util"])),
            ("EBITDA per tonne within Rs 600-2,000", all(600 <= v <= 2000 for v in base["ebitda_t"])),
            ("profit to owners positive", all(v > 0 for v in base["own"])),
            ("net debt / EBITDA below 3x", all(v < 3 for v in base["nd_e"])),
            ("balance check zero every year", all(abs(v) < 0.5 for v in base["bal"])),
            ("FY2026A revenue = 88,511.53", abs(base["rev"][0] - 88511.53) < 0.01)]
    for name, ok in sane:
        log.append(f"   sanity {'PASS' if ok else 'FAIL'}: {name}")


if __name__ == "__main__":
    main()
