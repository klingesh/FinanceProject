"""Finalise Castrol_India_LBO_Model.xlsx in Microsoft Excel (COM) and verify it.

1. Opens the openpyxl-built workbook in a private Excel instance (DispatchEx, hidden).
2. Creates the live What-If data tables on the Sensitivities sheet ({=TABLE()}).
3. Calculates, then switches the scenario selector 1 -> 2 -> 3 -> 1 and logs key outputs and
   every check for each case. Saves with the Base case selected, so cached values exist.
4. Re-opens the file with openpyxl (data_only=True): no Excel error values anywhere, every
   formula has a cached value, every check says PASS. Writes build/verification_log.txt.
5. Exports CSVs to outputs/ (used by build/make_figures.py and the README).

Run:  python build/finalise_with_excel.py   (Windows + Microsoft Excel required)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "Castrol_India_LBO_Model.xlsx"
LAYOUT = json.loads((ROOT / "build" / "layout.json").read_text(encoding="utf-8"))
POS = LAYOUT["pos"]
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
LOG: list[str] = []
ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!")
SCEN_NAMES = {1: "Base", 2: "Upside", 3: "Downside"}
YEARS = {"C": "CY2026E", "D": "CY2027E", "E": "CY2028E", "F": "CY2029E", "G": "CY2030E", "H": "CY2031E"}


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


def addr(key: str, col: str = "C") -> tuple[str, str]:
    sheet, row = POS[key]
    return sheet, f"{col}{row}"


# Key outputs read for every scenario: (label, key, column)
SUMMARY = [
    ("offer_price_rs", "offer", "C"), ("premium_to_close", "su_prem_close", "C"),
    ("equity_purchase_price_cr", "su_eq", "C"), ("cash_at_close_cr", "cash_close", "C"),
    ("entry_ev_cr", "ev", "C"), ("ev_cy2026e_ebitda_x", "m_26", "C"), ("ev_ltm_ebitda_x", "m_ltm", "C"),
    ("market_ev_ltm_x", "mkt_m", "C"), ("cy2026e_ebitda_cr", "o_ebitda", "C"), ("ltm_ebitda_cr", "e_ltm", "C"),
    ("total_debt_cr", "debt_amt", "C"), ("debt_x_ebitda", "debt_x", "C"), ("pf_interest_cover_x", "pf_icr", "C"),
    ("transaction_fees_cr", "u_txn", "C"), ("financing_fees_cr", "u_fin", "C"), ("excess_cash_used_cr", "s_cash", "C"),
    ("sponsor_equity_cr", "s_eq", "C"), ("equity_pct_cap", "eq_pct", "C"), ("cy2031e_revenue_cr", "o_rev", "H"),
    ("cy2031e_ebitda_cr", "o_ebitda", "H"), ("cy2031e_ebitda_margin", "o_em", "H"), ("exit_multiple_x", "x_mult", "C"),
    ("exit_ev_cr", "x_ev", "C"), ("net_debt_exit_cr", "nd_exit", "C"), ("exit_equity_cr", "x_eq", "C"),
    ("mip_cr", "r_mip", "C"), ("sponsor_proceeds_cr", "r_proc", "C"), ("irr", "r_irr", "C"), ("moic", "r_moic", "C"),
    ("unlevered_irr", "u_irr", "C"), ("after_tax_cost_of_debt", "u_dcost", "C"),
    ("net_debt_ebitda_exit_x", "d_lev_net", "H"), ("icr_cy2027e_x", "d_icr", "D"),
    ("attr_ebitda_growth_cr", "a_ebitda", "C"), ("attr_multiple_cr", "a_mult", "C"), ("attr_debt_paydown_cr", "a_debt", "C"),
    ("attr_fees_cr", "a_fees", "C"), ("attr_mip_cr", "a_mip", "C"), ("covenants", "d_cov_all", "C"),
    ("checks_core", "chk_core", "E"), ("checks_state", "chk_state", "E"), ("checks_overall", "chk_overall", "E"),
]
# Debt_Schedule rows exported for every scenario (outputs/scenario_credit_stats.csv, used by make_figures.py)
CREDIT_ROWS = [
    ("total_debt_cr", "d_tot"), ("cash_cr", "d_cash"), ("net_debt_cr", "d_nd"), ("ebitda_cr", "d_ebitda"),
    ("total_debt_ebitda_x", "d_lev_tot"), ("net_debt_ebitda_x", "d_lev_net"), ("ebitda_cash_interest_x", "d_icr"),
    ("covenant_max_net_leverage_x", "d_cov_lev"), ("covenant_min_icr_x", "d_cov_icr"),
    ("leverage_covenant_ebitda_headroom", "d_headroom"),
]
CREDIT: list[list] = []


def com_phase() -> list[dict]:
    import pythoncom
    import win32com.client as win32

    pythoncom.CoInitialize()
    app = None
    wb = None
    results: list[dict] = []
    try:
        app = win32.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        try:
            app.ScreenUpdating = False
        except Exception:  # noqa: BLE001
            pass
        wb = app.Workbooks.Open(str(XLSX), 0, False)
        app.Calculation = -4105  # xlCalculationAutomatic (data tables included)
        ws = wb.Worksheets("Sensitivities")
        for t in LAYOUT["sens"]["tables"]:
            rng = ws.Range(t["range"])
            col_in = ws.Range(t["col_input"])
            rng.Table(ws.Range(t["row_input"]), col_in)
            first_body = t["body"].split(":")[0]
            log(f"data table {t['id']} {t['range']}: {ws.Range(first_body).Formula}")
        app.CalculateFull()
        for name in ["Cover", "Historical", "Assumptions", "Sources_Uses", "Operating_Model", "Debt_Schedule",
                     "Returns", "Sensitivities", "Checks", "Real_Deal_Context"]:
            circ = wb.Worksheets(name).CircularReference
            if circ is not None:
                log(f"CIRCULAR REFERENCE on {name}: {circ.Address}")
        wa = wb.Worksheets("Assumptions")
        scen_cell = LAYOUT["scen_cell"]
        for scen in (1, 2, 3):
            wa.Range(scen_cell).Value = scen
            app.CalculateFull()
            row = {"scenario": SCEN_NAMES[scen]}
            for label, key, col in SUMMARY:
                sh, a = addr(key, col)
                row[label] = wb.Worksheets(sh).Range(a).Value
            row["min_icr_x"] = min(wb.Worksheets("Debt_Schedule").Range(addr("d_icr", c)[1]).Value for c in "DEFGH")
            for label, key in CREDIT_ROWS:
                sh, rr = POS[key]
                CREDIT.append([SCEN_NAMES[scen], label] + [wb.Worksheets(sh).Range(f"{c}{rr}").Value for c in "CDEFGH"])
            # every check row
            fails = []
            ch = wb.Worksheets("Checks")
            rows = list(range(LAYOUT["checks"]["first_core"], LAYOUT["checks"]["last_core"] + 1)) + \
                list(range(LAYOUT["checks"]["first_state"], LAYOUT["checks"]["last_state"] + 1))
            for rr in rows:
                if ch.Range(f"E{rr}").Value != "PASS":
                    fails.append(f"#{ch.Range(f'A{rr}').Value} {ch.Range(f'B{rr}').Value} = {ch.Range(f'C{rr}').Value}")
            row["failed_checks"] = "; ".join(fails) if fails else ""
            results.append(row)
            log(f"scenario {scen} {SCEN_NAMES[scen]}: IRR {row['irr']:.4f}, MOIC {row['moic']:.3f}, "
                f"entry {row['ev_cy2026e_ebitda_x']:.2f}x, exit equity {row['exit_equity_cr']:,.0f}, "
                f"checks {row['checks_overall']}, covenants {row['covenants']}"
                + (f", FAILED: {row['failed_checks']}" if fails else ""))
        wa.Range(scen_cell).Value = 1
        app.CalculateFull()
        # live scenario table on Sensitivities (computed by Excel's data table)
        for i in range(3):
            rr = POS[f"t5_{i + 1}"][1]
            vals = [ws.Range(f"{c}{rr}").Value for c in "DEFGHIJKLM"]
            log(f"live scenario table row {i + 1}: {vals}")
        wb.Save()
        log(f"saved with Excel at {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        if app is not None:
            app.Quit()
        pythoncom.CoUninitialize()
    return results


def verify_and_export(results: list[dict]) -> bool:
    from openpyxl import load_workbook

    wf = load_workbook(XLSX)                  # formulas
    wv = load_workbook(XLSX, data_only=True)  # cached values from Excel
    n_formula = n_err = n_none = 0
    for ws in wf.worksheets:
        vs = wv[ws.title]
        for row in ws.iter_rows():
            for c in row:
                v = vs[c.coordinate].value
                is_f = (isinstance(c.value, str) and c.value.startswith("=")) or type(c.value).__name__ in (
                    "ArrayFormula", "DataTableFormula")
                if isinstance(v, str) and v.strip() in ERRORS:
                    n_err += 1
                    log(f"ERROR VALUE {ws.title}!{c.coordinate} = {v} formula {c.value}")
                if is_f:
                    n_formula += 1
                    if v is None:
                        n_none += 1
                        log(f"NO CACHED VALUE {ws.title}!{c.coordinate} formula {c.value}")
    # data-table bodies (Excel stores values; check they are all filled)
    sv = wv["Sensitivities"]
    n_dt_cells = n_dt_empty = 0
    for t in LAYOUT["sens"]["tables"]:
        for row in sv[t["body"]]:
            for c in row:
                n_dt_cells += 1
                if c.value is None or (isinstance(c.value, str) and c.value in ERRORS):
                    n_dt_empty += 1
    log(f"formula cells: {n_formula}; error values: {n_err}; formulas without cached value: {n_none}; "
        f"data-table cells: {n_dt_cells}, empty/error: {n_dt_empty}")

    def val(key: str, col: str = "C"):
        sh, a = addr(key, col)
        return wv[sh][a].value

    ok_checks = all(r["checks_overall"] == "ALL PASS" for r in results)
    base_ok = val("chk_overall", "E") == "ALL PASS"
    log(f"checks ALL PASS in all three scenarios: {ok_checks}; saved file (Base) overall: {val('chk_overall', 'E')}")
    sane = (-0.5 < val("r_irr") < 0.6) and (0 < val("r_moic") < 6) and (8 < val("m_26") < 25) and \
        abs(val("su_diff")) < 0.01
    log(f"sanity of key outputs (IRR, MOIC, entry multiple, sources = uses): {sane}")

    # ---------------------------------------------------------------- exports
    keys = list(results[0].keys())
    with open(OUT / "scenario_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in results:
            w.writerow(r)

    write_csv(OUT / "scenario_credit_stats.csv", [["scenario", "item"] + [YEARS[c] for c in "CDEFGH"]] + CREDIT)

    def table_rows(spec: list[tuple[str, str]], cols: list[str]) -> list[list]:
        out = [["item"] + [YEARS[c] for c in cols]]
        for label, key in spec:
            out.append([label] + [val(key, c) for c in cols])
        return out

    om = [("revenue_cr", "o_rev"), ("revenue_growth", "o_g"), ("gross_margin", "o_gm"), ("ebitda_cr", "o_ebitda"),
          ("ebitda_margin", "o_em"), ("da_cr", "o_da"), ("ebit_cr", "o_ebit"), ("net_finance_costs_cr", "o_netfin"),
          ("pbt_cr", "o_pbt"), ("tax_cr", "o_tax"), ("net_income_cr", "o_ni"), ("trade_nwc_cr", "o_nwc"),
          ("capex_cr", "o_capex")]
    rows = table_rows(om, list("CDEFGH"))
    rows += table_rows([("increase_in_nwc_cr", "o_dnwc"), ("unlevered_fcf_cr", "o_ufcf"), ("levered_fcf_cr", "o_lfcf")],
                       list("DEFGH"))[1:]
    write_csv(OUT / "base_operating_model.csv", rows)
    ds = [("term_loan_a_cr", "tla_close"), ("term_loan_b_cr", "tlb_close"), ("holdco_pik_notes_cr", "mz_close"),
          ("revolver_cr", "rcf_close"), ("total_debt_cr", "d_tot"), ("lease_liabilities_cr", "d_lease"),
          ("cash_cr", "d_cash"), ("net_debt_cr", "d_nd"), ("ebitda_cr", "d_ebitda"), ("total_debt_ebitda_x", "d_lev_tot"),
          ("net_debt_ebitda_x", "d_lev_net")]
    rows = table_rows(ds, list("CDEFGH"))
    rows += table_rows([("scheduled_repayment_tla_cr", "d_m_tla"), ("scheduled_repayment_tlb_cr", "d_m_tlb"),
                        ("sweep_tlb_cr", "d_s_tlb"), ("sweep_tla_cr", "d_s_tla"), ("pik_accrued_cr", "mz_pik"),
                        ("cash_interest_cr", "d_cint"), ("ebitda_cash_interest_x", "d_icr"),
                        ("covenant_max_net_leverage_x", "d_cov_lev"), ("covenant_min_icr_x", "d_cov_icr"),
                        ("senior_debt_repaid_pct", "d_paydown")], list("DEFGH"))[1:]
    write_csv(OUT / "base_debt_schedule.csv", rows)
    su = [["item", "rs_crore", "pct_of_total", "x_cy2026e_ebitda"]]
    for lab, key in [("Purchase of equity", "u_eq"), ("Refinance existing borrowings", "u_refi"),
                     ("Transaction fees", "u_txn"), ("Financing fees", "u_fin"), ("Total uses", "u_tot")]:
        su.append([lab, val(key), val(key, "D"), None])
    for lab, key in [("Revolver drawn", "s_rcf"), ("Term loan A", "s_tla"), ("Term loan B", "s_tlb"),
                     ("Holdco PIK notes", "s_mz"), ("Excess balance-sheet cash", "s_cash"),
                     ("Sponsor equity", "s_eq"), ("Total sources", "s_tot")]:
        su.append([lab, val(key), val(key, "D"), val(key, "E")])
    write_csv(OUT / "sources_and_uses.csv", su)
    at = [["driver", "rs_crore"]]
    for lab, key in [("Sponsor equity invested", "r_inv"), ("EBITDA growth", "a_ebitda"), ("Multiple change", "a_mult"),
                     ("Debt paydown and cash build", "a_debt"), ("Fees at close", "a_fees"),
                     ("Management incentive pool", "a_mip"), ("Sponsor exit proceeds", "r_proc")]:
        at.append([lab, val(key)])
    write_csv(OUT / "returns_attribution.csv", at)
    hist = [["item", "CY2021", "CY2022", "CY2023", "CY2024", "CY2025", "LTM Sep-2026"]]
    for lab, key in [("revenue_cr", "h_rev"), ("ebitda_cr", "h_ebitda"), ("ebitda_margin", "h_em"),
                     ("gross_margin", "h_gm"), ("pat_cr", "h_pat_rep")]:
        hist.append([lab] + [val(key, c) for c in "CDEFGJ"])
    for lab, key in [("cfo_cr", "h_cfo"), ("capex_cr", "h_capex"), ("fcf_cr", "h_fcf"), ("dividends_cr", "h_div"),
                     ("capex_pct_revenue", "h_capexp"), ("fcf_to_ebitda", "h_fcfconv")]:
        hist.append([lab] + [val(key, c) for c in "CDEFG"] + [None])
    write_csv(OUT / "historical_summary.csv", hist)
    sw = wv["Sensitivities"]
    for t in LAYOUT["sens"]["tables"]:
        if t["id"] == "t5":
            continue
        rows = [[t["title"]] + list(t["top"])]
        r0, c0 = t["body"].split(":")
        first_row = int("".join(ch for ch in r0 if ch.isdigit()))
        for i, lv in enumerate(t["left"]):
            rr = first_row + i
            rows.append([lv] + [sw.cell(rr, 4 + j).value for j in range(len(t["top"]))])
        write_csv(OUT / f"sensitivity_{t['id']}.csv", rows)
    (ROOT / "build" / "verification_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    return ok_checks and base_ok and n_err == 0 and n_none == 0 and n_dt_empty == 0 and sane


def write_csv(path: Path, rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def main() -> None:
    t0 = time.time()
    log(f"verification run {dt.datetime.now():%Y-%m-%d %H:%M:%S} on {XLSX.name}")
    results = com_phase()
    ok = verify_and_export(results)
    log(f"RESULT: {'VERIFIED' if ok else 'PROBLEMS FOUND'} in {time.time() - t0:.1f}s")
    (ROOT / "build" / "verification_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    print("EXIT_OK" if ok else "EXIT_PROBLEMS")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
