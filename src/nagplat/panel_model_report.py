"""全国パネルの予測モデル(段3)の評価結果を、表(CSV)にする。出力先: outputs/public/panel_model_*.csv

主の集計(scope=main)と感度分析(scope=sensitivity: 避難指示区域の候補12町村も除く)は、別の行に分けて出す(混ぜない)。
setting: a = 時間で切る(全市区町村)、b = 評価する都道府県を学習から外し、時間で切る(長崎の行 = 段2の (c))。
"""
from __future__ import annotations

import duckdb
import numpy as np

from .common import ROOT, AREAS, write_csv
from . import panel_eval as pe
from . import panel_model as pm

OUT = ROOT / "outputs" / "public"
NAG_CODES = [c for c, _ in AREAS]
NAG_NAMES = {c: n for c, n in AREAS}
PAIRS = [(m, b) for m in ("B1_mean_last3", "M1_ridge", "M2_gbdt") for b in ("B0_previous_year",)] + \
        [(m, "B1_mean_last3") for m in ("M1_ridge", "M2_gbdt")]


def _r(x, k=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


def _fmt(m: dict) -> dict:
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in m.items()}


def _imp(mae_m: float, mae_b: float) -> float:
    return 1 - mae_m / mae_b


def run(workers: int = 6) -> dict:
    con = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    overall, by_year, nag, nag_by_year, nag_by_city, by_pref, importance, hyper = [], [], [], [], [], [], [], []
    summary = {}
    for scope in ("main", "sensitivity"):
        res = pm.evaluate_models(con, scope, workers=workers, keep_models=True)
        rows = res["rows"]
        years = np.array([r.t + 1 for r in rows])
        prefs = np.array([r.pref for r in rows])
        areas = np.array([r.area_code for r in rows])
        hyper += res["hyper"]
        for setting in ("a", "b"):
            preds = res[setting]
            ci = pm.cluster_bootstrap(rows, preds, PAIRS, areas)       # 市区町村をまとまりとして再標本化
            mae = {m: pe.metrics(rows, preds[m])["mae"] for m in pm.ALL_METHODS}
            for m in pm.ALL_METHODS:
                mt = pe.metrics(rows, preds[m])
                row = dict(scope=scope, setting=setting, method=m, **_fmt(mt),
                           improvement_vs_B0=_r(_imp(mae[m], mae["B0_previous_year"])),
                           improvement_vs_B1=_r(_imp(mae[m], mae["B1_mean_last3"])))
                for b, tag in (("B0_previous_year", "B0"), ("B1_mean_last3", "B1")):
                    lo, hi = ci.get((m, b), (None, None))
                    row[f"improvement_vs_{tag}_ci95_low"] = _r(lo)
                    row[f"improvement_vs_{tag}_ci95_high"] = _r(hi)
                overall.append(row)
            if setting == "a":
                for m in pm.ALL_METHODS:
                    for T in pe.EVAL_YEARS:
                        mk = years == T
                        sub = [r for r, k in zip(rows, mk) if k]
                        mm = pe.metrics(sub, preds[m][mk])
                        b0 = pe.metrics(sub, preds["B0_previous_year"][mk])["mae"]
                        b1 = pe.metrics(sub, preds["B1_mean_last3"][mk])["mae"]
                        by_year.append(dict(scope=scope, setting=setting, method=m, eval_year=T, **_fmt(mm),
                                            improvement_vs_B0=_r(_imp(mm["mae"], b0)),
                                            improvement_vs_B1=_r(_imp(mm["mae"], b1))))
        # 長崎(設定 b の長崎の行 = 長崎を学習から外し、評価年より前の年のデータだけで学習する)
        pb = res["b"]
        mk = prefs == pe.NAGASAKI
        nrows = [r for r, k in zip(rows, mk) if k]
        npred = {m: pb[m][mk] for m in pm.ALL_METHODS}
        nareas = areas[mk]
        nci = pm.cluster_bootstrap(nrows, npred, PAIRS, nareas)
        nmae = {m: pe.metrics(nrows, npred[m])["mae"] for m in pm.ALL_METHODS}
        # 都道府県ごとのMAE(設定 b)。長崎の位置を見る
        for p in sorted(set(prefs)):
            pm_ = prefs == p
            sub = [r for r, k in zip(rows, pm_) if k]
            row = dict(scope=scope, pref_code=p, n=len(sub))
            for m in pm.ALL_METHODS:
                row[f"mae_{m}"] = _r(pe.metrics(sub, pb[m][pm_])["mae"])
            by_pref.append(row)
        for m in pm.ALL_METHODS:
            mt = pe.metrics(nrows, npred[m])
            row = dict(scope=scope, method=m, **_fmt(mt),
                       improvement_vs_B0=_r(_imp(nmae[m], nmae["B0_previous_year"])),
                       improvement_vs_B1=_r(_imp(nmae[m], nmae["B1_mean_last3"])))
            for b, tag in (("B0_previous_year", "B0"), ("B1_mean_last3", "B1")):
                lo, hi = nci.get((m, b), (None, None))
                row[f"improvement_vs_{tag}_ci95_low"] = _r(lo)
                row[f"improvement_vs_{tag}_ci95_high"] = _r(hi)
            nag.append(row)
            for T in pe.EVAL_YEARS:
                k2 = np.array([r.t + 1 == T for r in nrows])
                sub = [r for r, k in zip(nrows, k2) if k]
                if sub:
                    nag_by_year.append(dict(scope=scope, method=m, eval_year=T, **_fmt(pe.metrics(sub, npred[m][k2]))))
            if scope == "main":
                for c in NAG_CODES:
                    ci_idx = nareas == c
                    if ci_idx.sum():
                        sub = [r for r, k in zip(nrows, ci_idx) if k]
                        mm = pe.metrics(sub, npred[m][ci_idx])
                        nag_by_city.append(dict(area_code=c, area_name=NAG_NAMES[c], method=m, n=mm["n"],
                                                mae=_r(mm["mae"]), mean_pred=_r(float(np.mean(npred[m][ci_idx]))),
                                                mean_actual=_r(float(np.mean([r.y for r in sub])))))
        # 重要度(設定 a のモデル。相関で、因果ではない)
        tb, ridx = res["table"], res["ridx"]
        for T, fit in res["fits"].items():
            test_idx = ridx[years == T]
            perm = {d["feature"]: d for d in pm.permutation_importance(fit, tb, test_idx)}
            gain = fit["gbdt"]["gain"]
            gshare = gain / gain.sum() if gain.sum() > 0 else gain
            beta = fit["ridge"]["beta"][:-1]
            for j, name in enumerate(pm.FEATURE_NAMES):
                importance.append(dict(scope=scope, eval_year=T, feature=name,
                                       ridge_coef_standardized=_r(float(beta[j])),
                                       gbdt_gain_share=_r(float(gshare[j])),
                                       perm_mae_increase_ridge=_r(perm[name]["perm_mae_increase_ridge"]),
                                       perm_mae_increase_gbdt=_r(perm[name]["perm_mae_increase_gbdt"])))
        summary[scope] = dict(n_national=len(rows), n_nagasaki=len(nrows), n_features=res["n_features"],
                              n_train_rows_last=res["fits"][2024]["n_train"])
    con.close()
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "panel_model_overall.csv", overall)
    write_csv(OUT / "panel_model_by_year.csv", by_year)
    write_csv(OUT / "panel_model_nagasaki.csv", nag)
    write_csv(OUT / "panel_model_nagasaki_by_year.csv", nag_by_year)
    write_csv(OUT / "panel_model_nagasaki_by_municipality.csv", nag_by_city)
    write_csv(OUT / "panel_model_by_prefecture.csv", by_pref)
    write_csv(OUT / "panel_model_importance.csv", importance)
    hp = [dict(scope=h["scope"], setting=h["setting"], eval_year=h["eval_year"], held_out_pref=h["held_out_pref"],
               n_train=h["n_train"], n_val_folds=h["n_folds"], ridge_alpha=h["alpha"],
               gbdt_depth=h["gbdt_depth"], gbdt_trees=h["gbdt_trees"],
               cv_mae_ridge=_r(h["cv_mae_ridge"]), cv_mae_gbdt=_r(h["cv_mae_gbdt"])) for h in hyper]
    write_csv(OUT / "panel_model_hyperparams.csv", hp)
    pm.write_leak_register()
    return summary


def main() -> int:
    s = run()
    print("panel-model:", s)
    return 0
