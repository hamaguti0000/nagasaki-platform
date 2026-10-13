"""全国パネルの基準手法の評価結果を、表(CSV)にする。出力先: outputs/public/panel_baseline_*.csv"""
from __future__ import annotations

import duckdb
import numpy as np

from .common import ROOT, AREAS, write_csv
from . import panel_eval as pe

OUT = ROOT / "outputs" / "public"
NAG_CODES = [c for c, _ in AREAS]
NAG_NAMES = {c: n for c, n in AREAS}


def _r(x, k=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


def _fmt(m: dict) -> dict:
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in m.items()}


def run() -> dict:
    con = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    overall, by_year, nag, nag_by_year, nag_by_city, by_pref = [], [], [], [], [], []
    summary = {}
    for scope in ("main", "sensitivity"):
        res = pe.evaluate(con, scope)
        rows = res["rows"]
        years = np.array([r.t + 1 for r in rows])
        prefs = np.array([r.pref for r in rows])
        for setting in ("a", "b"):
            preds = res[setting]
            base_mae = pe.metrics(rows, preds["B0_previous_year"])["mae"]
            for m in pe.METHODS:
                mt = pe.metrics(rows, preds[m])
                overall.append(dict(scope=scope, setting=setting, method=m, **_fmt(mt),
                                    improvement_vs_B0=_r(1 - mt["mae"] / base_mae)))
                if setting == "a":
                    for T in pe.EVAL_YEARS:
                        mk = years == T
                        sub = [r for r, k in zip(rows, mk) if k]
                        mm = pe.metrics(sub, preds[m][mk])
                        b0 = pe.metrics(sub, preds["B0_previous_year"][mk])["mae"]
                        by_year.append(dict(scope=scope, setting=setting, method=m, eval_year=T, **_fmt(mm),
                                            improvement_vs_B0=_r(1 - mm["mae"] / b0)))
        # 長崎(設定 c = 長崎を統計から外し、評価年より前の情報のみ)
        pb = res["b"]
        mk = np.array([r.pref == pe.NAGASAKI for r in rows])
        nrows = [r for r, k in zip(rows, mk) if k]
        npred = {m: pb[m][mk] for m in pe.METHODS}
        b0 = pe.metrics(nrows, npred["B0_previous_year"])["mae"]
        ci = pe.bootstrap_improvement(nrows, npred, NAG_CODES)
        # 都道府県ごとの MAE(設定 b)。長崎の位置を見る
        pref_mae = {}
        for p in sorted(set(prefs)):
            pm = prefs == p
            if pm.sum() == 0:
                continue
            sub = [r for r, k in zip(rows, pm) if k]
            row = dict(scope=scope, pref_code=p, n=len(sub))
            for m in pe.METHODS:
                row[f"mae_{m}"] = _r(pe.metrics(sub, pb[m][pm])["mae"])
            by_pref.append(row)
            pref_mae[p] = row["mae_B0_previous_year"]
        order = sorted(pref_mae.values())
        pct = float(np.mean([v <= pref_mae[pe.NAGASAKI] for v in order]))
        for m in pe.METHODS:
            mt = pe.metrics(nrows, npred[m])
            lo, hi = ci.get(m, (None, None))
            nag.append(dict(scope=scope, method=m, **_fmt(mt), improvement_vs_B0=_r(1 - mt["mae"] / b0),
                            improvement_ci95_low=_r(lo), improvement_ci95_high=_r(hi),
                            pref_rank_pct_B0_mae=_r(pct, 3) if m == "B0_previous_year" else None))
            for T in pe.EVAL_YEARS:
                k2 = np.array([r.t + 1 == T for r in nrows])
                sub = [r for r, k in zip(nrows, k2) if k]
                if sub:
                    mm = pe.metrics(sub, npred[m][k2])
                    nag_by_year.append(dict(scope=scope, method=m, eval_year=T, **_fmt(mm)))
            if scope == "main":
                for c in NAG_CODES:
                    ci_idx = np.array([r.area_code == c for r in nrows])
                    if ci_idx.sum():
                        sub = [r for r, k in zip(nrows, ci_idx) if k]
                        mm = pe.metrics(sub, npred[m][ci_idx])
                        nag_by_city.append(dict(area_code=c, area_name=NAG_NAMES[c], method=m, n=mm["n"],
                                                mae=_r(mm["mae"]),
                                                mean_pred=_r(float(np.mean(npred[m][ci_idx]))),
                                                mean_actual=_r(float(np.mean([r.y for r in sub])))))
        summary[scope] = dict(n_national=len(rows), n_nagasaki=len(nrows))
    con.close()
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "panel_baseline_overall.csv", overall)
    write_csv(OUT / "panel_baseline_by_year.csv", by_year)
    write_csv(OUT / "panel_baseline_nagasaki.csv", nag)
    write_csv(OUT / "panel_baseline_nagasaki_by_year.csv", nag_by_year)
    write_csv(OUT / "panel_baseline_nagasaki_by_municipality.csv", nag_by_city)
    write_csv(OUT / "panel_baseline_by_prefecture.csv", by_pref)
    return summary


def main() -> int:
    s = run()
    print("panel-eval:", s)
    return 0
