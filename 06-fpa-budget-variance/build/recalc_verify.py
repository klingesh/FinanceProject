"""Recalculate the workbook in Excel, verify it, run a driver-change test, export CSV outputs.

Steps
1. Excel (COM, own instance): CalculateFull, save, close, so cached values exist.
2. openpyxl data_only=True: scan every sheet for error values; read every check.
3. Compare Excel results with the independent Python model (reference_model.py).
4. Driver-change test on a temporary copy: change an actual price driver, then an actual volume
   driver, then the forecast case; recalculate after each; confirm the variance sheets and bridges
   move exactly as the Python model predicts and all checks still PASS. The copy is deleted afterwards.
5. Export key tables to outputs/*.csv and write outputs/verification_log.txt.
"""
from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import sys
import tempfile
import time

import openpyxl
import pythoncom
import win32com.client

import inputs as I
import reference_model as RM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(ROOT, "Vriddhi_Foods_FPA_FY2027.xlsx")
OUTD = os.path.join(ROOT, "outputs")
TMP = os.path.join(tempfile.gettempdir(), "vriddhi_fpa_driver_test_copy.xlsx")
LOG: list[str] = []
ERRS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")

with open(os.path.join(HERE, "layout.json"), encoding="utf-8") as fh:
    LAY = json.load(fh)
R, A, AD, FD = LAY["R"], LAY["A"], LAY["AD"], LAY["FD"]

PL_MAP = [("vol_tot", "volume"), ("gs_tot", "gross_sales"), ("ts_tot", "trade_spend"), ("nr_tot", "net_revenue"),
          ("mat", "material"), ("pack", "packaging"), ("conv", "conversion"), ("gp", "gross_profit"),
          ("freight", "freight"), ("ap", "ap"), ("emp", "employee"), ("oth", "other_oh"), ("ebitda", "ebitda"),
          ("da", "da"), ("int", "interest"), ("pbt", "pbt"), ("tax", "tax"), ("pat", "pat")]
EB_KEYS = ["vol", "mix", "lp", "tsr", "mrate", "pcrate", "freight", "ap", "emp", "oth"]


def log(msg=""):
    print(msg)
    LOG.append(str(msg))


def excel_app():
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    return app


def recalc_and_save(path):
    app = excel_app()
    wb = None
    try:
        wb = app.Workbooks.Open(path)
        app.CalculateFull()
        wb.Save()
        wb.Close(SaveChanges=False)
        wb = None
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        app.Quit()
        del app
        pythoncom.CoUninitialize()


def scan_errors(wb):
    found = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.strip() in ERRS:
                    found.append(f"{ws.title}!{c.coordinate}={c.value}")
    return found


def read_checks(wb):
    ws = wb["Checks"]
    rows = []
    r = 11
    while ws[f"A{r}"].value is not None:
        rows.append((ws[f"A{r}"].value, ws[f"B{r}"].value, ws[f"C{r}"].value, ws[f"D{r}"].value, ws[f"F{r}"].value))
        r += 1
    return rows, ws["D8"].value


def compare(label, got, exp, tol=1e-6):
    d = abs(got - exp)
    flag = "OK" if d <= tol else "MISMATCH"
    log(f"  {label:<44} excel {got:>12.4f}  python {exp:>12.4f}  diff {d:.2e}  {flag}")
    return d <= tol


def verify_values(wb, S):
    ok = True
    bud, act, fc = wb["Budget_PL"], wb["Actuals_H1"], wb["Forecast_6plus6"]
    for title_, ws, colx, ref in (("Budget H1", bud, "P", S["bud_h1"]), ("Actual H1", act, "J", S["act_h1"]),
                                  ("Budget FY", bud, "R", S["bud_fy"]), ("Forecast FY", fc, "R", S["fc_fy"])):
        log(f"{title_}:")
        for k, rk in PL_MAP:
            ok &= compare(k, ws[f"{colx}{R[k]}"].value, ref[rk])
    pv = wb["PVM_Bridge"]
    eb = LAY["pvm_summ"]["eb"]
    br = RM.bridges(S["act_h1"], S["bud_h1"])
    log("H1 EBITDA bridge items:")
    for (lab, val), k in zip(br["ebitda_bridge"], EB_KEYS):
        ok &= compare(lab, pv[f"C{eb[k]}"].value, val)
    rev = LAY["pvm_summ"]["rev"]
    log("H1 revenue PVM:")
    ok &= compare("volume", pv[f"C{rev['vol']}"].value, br["vol"])
    ok &= compare("mix", pv[f"C{rev['mix']}"].value, br["mix"])
    ok &= compare("list price", pv[f"C{rev['lp']}"].value, br["lp"])
    ok &= compare("trade spend rate & channel mix", pv[f"C{rev['tsr']}"].value, br["tsr"])
    t5 = LAY["pvm_det"]["rt5"]
    ok &= compare("material rate: edible oil", pv[f"C{t5}"].value, br["mr_rm"]["OIL"])
    fo = wb["FY_Outlook"]
    ebf = LAY["fy_summ"]["eb"]
    brf = RM.bridges(S["fc_fy"], S["bud_fy"])
    log("FY EBITDA bridge items (forecast vs budget):")
    for (lab, val), k in zip(brf["ebitda_bridge"], EB_KEYS):
        ok &= compare(lab, fo[f"C{ebf[k]}"].value, val)
    return ok


def com_read(ws, addr):
    return ws.Range(addr).Value


def driver_change_test(S_base):
    """Change actual drivers and the forecast case on a temporary copy; recalc in Excel after each change.

    Test A: Aug-26 actual edible-oil price 126 -> 140 Rs/kg (Actuals_H1 ERP block).
    Test B: Aug-26 actual Beverages General Trade volume -100 t (a late ERP posting correction).
    Test C: forecast case switch on the Cover (2 = Downside, 3 = Upside, back to 1 = Base).
    Each Excel result is compared with the independent Python model given the same change, and every
    check must still PASS. The copy is closed without saving and deleted.
    """
    shutil.copyfile(XLSX, TMP)
    app = excel_app()
    wb = None
    ok = True
    try:
        wb = app.Workbooks.Open(TMP)
        app.CalculateFull()
        ck = wb.Worksheets("Checks")
        sa = wb.Worksheets("Actuals_H1")
        sf = wb.Worksheets("Forecast_6plus6")
        pv = wb.Worksheets("PVM_Bridge")
        vm = wb.Worksheets("Variance_Monthly")
        vy = wb.Worksheets("Variance_YTD")
        cov = wb.Worksheets("Cover")
        eb = LAY["pvm_summ"]["eb"]
        rev = LAY["pvm_summ"]["rev"]
        t5 = LAY["pvm_det"]["rt5"]
        VR, YR = LAY["VR"], LAY["YR"]
        aug = 4  # month index of Aug-26 (column H)

        # Test A: actual price driver
        log("Test A: Aug-26 actual edible-oil price 126 -> 140 Rs/kg")
        oil_cell = f"H{AD['rm_OIL']}"
        before = dict(ebitda=com_read(sa, f"J{R['ebitda']}"), oil=com_read(pv, f"C{t5}"),
                      status=com_read(ck, "D8"), oilprice=com_read(sa, oil_cell),
                      ytd_eb=com_read(vy, f"L{YR['ebitda']}"), aug_eb=com_read(vm, f"H{VR['ebitda']}"))
        log(f"Before: Actuals_H1!{oil_cell} = {before['oilprice']}, H1 actual EBITDA = {before['ebitda']:.4f}, "
            f"YTD EBITDA variance = {before['ytd_eb']:.4f}, Aug EBITDA variance = {before['aug_eb']:.4f}, "
            f"oil rate effect = {before['oil']:.4f}, checks = {before['status']}")
        sa.Range(oil_cell).Value = 140.0
        app.CalculateFull()
        after = dict(ebitda=com_read(sa, f"J{R['ebitda']}"), oil=com_read(pv, f"C{t5}"),
                     status=com_read(ck, "D8"), fails=com_read(ck, "D7"),
                     ytd_eb=com_read(vy, f"L{YR['ebitda']}"), aug_eb=com_read(vm, f"H{VR['ebitda']}"),
                     fc_h1=com_read(sf, f"P{R['ebitda']}"), bridge_end=com_read(pv, f"C{eb['end']}"))
        # Python prediction with the same change
        saved = copy.deepcopy(I.ACTUAL["rm_price"]["OIL"])
        I.ACTUAL["rm_price"]["OIL"][aug] = 140.0
        try:
            S_new = RM.summary(1)
        finally:
            I.ACTUAL["rm_price"]["OIL"] = saved
        br_new = RM.bridges(S_new["act_h1"], S_new["bud_h1"])
        log(f"After:  Actuals_H1!{oil_cell} = 140, H1 actual EBITDA = {after['ebitda']:.4f}, YTD EBITDA variance = "
            f"{after['ytd_eb']:.4f}, Aug EBITDA variance = {after['aug_eb']:.4f}, oil rate effect = {after['oil']:.4f}, "
            f"forecast H1 EBITDA = {after['fc_h1']:.4f}, bridge end = {after['bridge_end']:.4f}, "
            f"checks = {after['status']} ({after['fails']:.0f} failed)")
        ok &= compare("A: H1 actual EBITDA", after["ebitda"], S_new["act_h1"]["ebitda"])
        ok &= compare("A: Variance_YTD EBITDA variance", after["ytd_eb"],
                      S_new["act_h1"]["ebitda"] - S_new["bud_h1"]["ebitda"])
        ok &= compare("A: Variance_Monthly Aug-26 EBITDA variance", after["aug_eb"],
                      float(S_new["actual"]["ebitda"][aug] - S_new["budget"]["ebitda"][aug]))
        ok &= compare("A: PVM_Bridge edible-oil rate effect", after["oil"], br_new["mr_rm"]["OIL"])
        ok &= compare("A: PVM_Bridge EBITDA bridge end", after["bridge_end"], S_new["act_h1"]["ebitda"])
        ok &= compare("A: Forecast_6plus6 H1 EBITDA", after["fc_h1"], S_new["act_h1"]["ebitda"])
        ok &= after["status"] == "ALL PASS"
        sa.Range(oil_cell).Value = before["oilprice"]
        app.CalculateFull()
        ok &= compare("A: restored H1 actual EBITDA", com_read(sa, f"J{R['ebitda']}"), before["ebitda"], 1e-9)

        # Test B: actual volume driver
        log("Test B: Aug-26 actual Beverages General Trade volume -100 t")
        vol_cell = f"H{AD['vol_BEV_GT']}"
        def rd():
            return dict(vol_var=com_read(vy, f"L{YR['vol_BEV']}"), nr_var=com_read(vy, f"L{YR['nr_tot']}"),
                        vol=com_read(pv, f"C{rev['vol']}"), mix=com_read(pv, f"C{rev['mix']}"),
                        lp=com_read(pv, f"C{rev['lp']}"), tsr=com_read(pv, f"C{rev['tsr']}"),
                        rev_end=com_read(pv, f"C{rev['end']}"), eb_end=com_read(pv, f"C{eb['end']}"),
                        ebitda=com_read(sa, f"J{R['ebitda']}"), status=com_read(ck, "D8"),
                        fails=com_read(ck, "D7"))

        v0 = com_read(sa, vol_cell)
        b0 = rd()
        log(f"Before: Actuals_H1!{vol_cell} = {v0:.1f} t, beverages H1 volume variance = {b0['vol_var']:.1f} t, "
            f"net revenue variance = {b0['nr_var']:.4f}, PVM volume / mix / list price / trade spend = "
            f"{b0['vol']:.4f} / {b0['mix']:.4f} / {b0['lp']:.4f} / {b0['tsr']:.4f}, checks = {b0['status']}")
        v1 = round(v0 - 100.0, 1)
        sa.Range(vol_cell).Value = v1
        app.CalculateFull()
        b1 = rd()
        orig_av = I.actual_volumes
        av = orig_av()
        av[("BEV", "GT")][aug] = v1
        I.actual_volumes = lambda: copy.deepcopy(av)
        try:
            S_b = RM.summary(1)
        finally:
            I.actual_volumes = orig_av
        br_b = RM.bridges(S_b["act_h1"], S_b["bud_h1"])
        log(f"After:  Actuals_H1!{vol_cell} = {v1:.1f} t, beverages H1 volume variance = {b1['vol_var']:.1f} t, "
            f"net revenue variance = {b1['nr_var']:.4f}, PVM volume / mix / list price / trade spend = "
            f"{b1['vol']:.4f} / {b1['mix']:.4f} / {b1['lp']:.4f} / {b1['tsr']:.4f}, H1 EBITDA = {b1['ebitda']:.4f}, "
            f"checks = {b1['status']} ({b1['fails']:.0f} failed)")
        ok &= compare("B: Variance_YTD beverages volume variance (t)", b1["vol_var"],
                      S_b["act_h1"]["vol_l"]["BEV"] - S_b["bud_h1"]["vol_l"]["BEV"])
        ok &= compare("B: Variance_YTD net revenue variance", b1["nr_var"], br_b["nr_var"])
        ok &= compare("B: PVM_Bridge volume effect", b1["vol"], br_b["vol"])
        ok &= compare("B: PVM_Bridge mix effect", b1["mix"], br_b["mix"])
        ok &= compare("B: PVM_Bridge list price effect", b1["lp"], br_b["lp"])
        ok &= compare("B: PVM_Bridge trade-spend effect", b1["tsr"], br_b["tsr"])
        ok &= compare("B: PVM_Bridge revenue bridge end", b1["rev_end"], S_b["act_h1"]["net_revenue"])
        ok &= compare("B: PVM_Bridge EBITDA bridge end", b1["eb_end"], S_b["act_h1"]["ebitda"])
        ok &= abs(b1["vol_var"] - b0["vol_var"] + 100.0) < 1e-6 and b1["status"] == "ALL PASS"
        sa.Range(vol_cell).Value = v0
        app.CalculateFull()
        ok &= compare("B: restored H1 actual EBITDA", com_read(sa, f"J{R['ebitda']}"), b0["ebitda"], 1e-9)

        # Test C: forecast case switch
        log("Test C: forecast case switch on Cover!D10")
        for case in (2, 3, 1):
            cov.Range("D10").Value = case
            app.CalculateFull()
            fy = com_read(sf, f"R{R['ebitda']}")
            exp = RM.summary(case)["fc_fy"]["ebitda"]
            st = com_read(ck, "D8")
            log(f"Case {case}: FY forecast EBITDA excel {fy:.4f} python {exp:.4f}, checks = {st}")
            ok &= abs(fy - exp) < 1e-6 and st == "ALL PASS"
        wb.Close(SaveChanges=False)
        wb = None
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        app.Quit()
        del app
        pythoncom.CoUninitialize()
        time.sleep(1)
        if os.path.exists(TMP):
            os.remove(TMP)
    log(f"Temporary copy deleted: {not os.path.exists(TMP)}")
    return ok


def export_outputs(wb):
    os.makedirs(OUTD, exist_ok=True)
    bud, act, fc = wb["Budget_PL"], wb["Actuals_H1"], wb["Forecast_6plus6"]
    months = [m.strftime("%b-%y") for m in I.MONTHS]
    mcols = [chr(ord("D") + i) for i in range(12)]
    with open(os.path.join(OUTD, "monthly_pl_budget_actual_forecast.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "line_item_rs_crore"] + months + ["H1", "H2", "FY"])
        for name, ws, cols, aggs in (("Budget", bud, mcols, ["P", "Q", "R"]), ("Actual", act, mcols[:6], ["J"]),
                                     ("Forecast 6+6", fc, mcols, ["P", "Q", "R"])):
            for k, _ in PL_MAP:
                vals = [round(ws[f"{c}{R[k]}"].value, 4) for c in cols]
                vals += [""] * (12 - len(cols))
                agg = [round(ws[f"{c}{R[k]}"].value, 4) for c in aggs]
                if name == "Actual":
                    agg = agg + ["", ""]
                w.writerow([name, k] + vals + agg)
    vy = wb["Variance_YTD"]
    with open(os.path.join(OUTD, "h1_variance_ytd.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["line_item", "unit", "budget_h1", "actual_h1", "variance", "variance_pct", "fav_unfav"])
        for k, (r) in LAY["YR"].items():
            if k.startswith("h_"):
                continue
            row = [vy[f"B{r}"].value, vy[f"C{r}"].value, vy[f"J{r}"].value, vy[f"K{r}"].value, vy[f"L{r}"].value,
                   vy[f"M{r}"].value, vy[f"N{r}"].value]
            w.writerow([x if not isinstance(x, float) else round(x, 6) for x in row])
    pv, fo = wb["PVM_Bridge"], wb["FY_Outlook"]
    with open(os.path.join(OUTD, "bridges_h1_and_fy.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bridge", "step", "rs_crore"])
        for nm, ws, sm in (("H1 actual vs budget", pv, LAY["pvm_summ"]), ("FY forecast vs budget", fo, LAY["fy_summ"])):
            for part in ("rev", "gp", "eb"):
                for key, r in sm[part].items():
                    if key in ("diff", "pl"):
                        continue
                    w.writerow([f"{nm}: {part}", ws[f"B{r}"].value, round(ws[f"C{r}"].value, 6)])


def main():
    t0 = time.time()
    log(f"Workbook: {XLSX}")
    log("Step 1: Excel CalculateFull + save")
    recalc_and_save(XLSX)
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    log("Step 2: error scan and checks")
    errs = scan_errors(wb)
    log(f"  Error values found: {len(errs)}" + (f" -> {errs[:20]}" if errs else ""))
    rows, status = read_checks(wb)
    n_fail = sum(1 for r in rows if r[4] != "PASS")
    for num, area, desc, val, res in rows:
        log(f"  {num:>2} {res:<4} {area:<17} {desc} (value {val:.2e})" if isinstance(val, (int, float))
            else f"  {num:>2} {res} {area} {desc} (value {val})")
    log(f"  Checks: {len(rows)} total, {len(rows) - n_fail} PASS, {n_fail} FAIL; overall = {status}")
    log("Step 3: Excel vs independent Python model")
    S = RM.summary(1)
    vals_ok = verify_values(wb, S)
    log(f"  Values match: {vals_ok}")
    log("Step 4: driver-change test on a copy")
    drv_ok = driver_change_test(S)
    log(f"  Driver-change test passed: {drv_ok}")
    log("Step 5: export outputs")
    export_outputs(wb)
    cov = wb["Cover"]
    log("Cover KPI block (H1 budget, H1 actual, FY budget, FY forecast):")
    for r in range(15, 21):
        log(f"  {cov[f'B{r}'].value:<32} {cov[f'C{r}'].value:>10.4f} {cov[f'D{r}'].value:>10.4f} "
            f"{cov[f'H{r}'].value:>10.4f} {cov[f'I{r}'].value:>10.4f}")
    log(f"  Cover status: {cov['D11'].value} | {cov['E11'].value}")
    overall = (not errs) and n_fail == 0 and vals_ok and drv_ok
    log(f"OVERALL VERIFICATION: {'PASS' if overall else 'FAIL'} ({time.time() - t0:.0f}s)")
    os.makedirs(OUTD, exist_ok=True)
    with open(os.path.join(OUTD, "verification_log.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(LOG) + "\n")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
