"""段4: 前向き予測(2026年の転入超過率を、2025年までの情報で予測する)。設計: docs/段4_前向き予測_設計.md

段3のコード(panel_model)を、そのまま使う。段3との差(設計に事前に書いた):
  - 2025年の転入超過率 y(2025) は、e-Stat の住民基本台帳人口移動報告 2025年結果(表11-1・11-2)から作る。分母は2020年の日本人人口(段3と同じ)。
  - 年次項目の値が年 t−1 にない場合(出生・死亡・婚姻・離婚・病院・診療所・歯科診療所は2023年まで)は、得られる最新の年の値を使う。
  - 予測区間: 人口規模の階級ごとに、過去の評価年(2020〜2025年)の絶対誤差の95%点を、予測の±幅にする。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from . import panel_eval as pe
from . import panel_model as pm
from .common import ROOT, write_csv

IDOU_IN = ROOT / "raw" / "public" / "idou" / "idou2025_t11-1_transfers_in.xlsx"
IDOU_OUT = ROOT / "raw" / "public" / "idou" / "idou2025_t11-2_transfers_out.xlsx"
IDOU_NET = ROOT / "raw" / "public" / "idou" / "idou2025_t11-3_net.xlsx"
JP_MOVERS = 61000                     # 国籍コード: 日本人移動者
BACKTEST_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
FORECAST_YEAR = 2026
INTERVAL_Q = 0.95
METHODS = pm.ALL_METHODS
ANNUAL_COLS = ["births", "deaths", "marriages", "divorces", "kindergarten_pupils", "elementary_pupils",
               "junior_high_pupils", "high_school_students", "general_hospitals", "clinics", "dental_clinics",
               "area_total", "area_habitable"]
CENSUS_COLS = ["pop_total_asof", "pop_japanese_asof", "pop_under15_asof", "pop_65plus_asof", "pop_foreign_asof",
               "households_asof", "single_households_asof"]


def read_idou_table(path: Path) -> dict[str, float]:
    """e-Stat のExcel(表11-x)から、日本人移動者の地域コード(5桁) → 総数 を読む。"""
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    out: dict[str, float] = {}
    for r in ws.iter_rows(min_row=7, values_only=True):
        if r and r[1] == JP_MOVERS and r[5] is not None:
            out[str(r[5])] = float(r[7])
    return out


def load_2025_moves() -> dict[str, tuple[float, float]]:
    tin, tout, net = read_idou_table(IDOU_IN), read_idou_table(IDOU_OUT), read_idou_table(IDOU_NET)
    bad = [c for c in tin if c in tout and c in net and tin[c] - tout[c] != net[c]]
    assert not bad, f"転入−転出≠転入超過: {bad[:5]}"
    return {c: (tin[c], tout[c]) for c in tin if c in tout}


def build_forward_table(con, scope: str = "main", moves25: dict | None = None,
                        with_2025: bool = True) -> tuple[pm.Table, np.ndarray]:
    """panel_model.build_table と同じ特徴量(t = 2016〜2023)に、t = 2024(目的 = 2025年の e-Stat の値)と
    t = 2025(目的 = 2026年。未知)を加える。戻り値: (Table, 予測する行のマスク)。"""
    moves25 = moves25 if moves25 is not None else load_2025_moves()
    ex = "excluded_main" if scope == "main" else "excluded_sensitivity"
    cols = ANNUAL_COLS + CENSUS_COLS
    q = f"""SELECT area_code, pref_code, year, net_rate_permille, pop_jp_denominator, COALESCE({ex}, TRUE),
                   {", ".join(cols)} FROM gold_panel_municipality_year ORDER BY area_code, year"""
    data: dict[tuple[str, int], list] = {}
    pref_of: dict[str, str] = {}
    for r in con.execute(q).fetchall():
        data[(r[0], r[2])] = list(r)
        pref_of[r[0]] = r[1]
    ci = {c: 6 + i for i, c in enumerate(cols)}
    if with_2025:                                           # 2025年の行(率は e-Stat から。他の列は2024年の行を引き継ぐ)
        for area in list(pref_of):
            base = data.get((area, 2024))
            if base is None:
                continue
            row = list(base)
            row[2] = 2025
            pop = base[4]
            tin, tout = moves25.get(area, (None, None))
            row[3] = (round((tin - tout) / pop * 1000, 4) if tin is not None and pop and pop > 0 else None)
            for c in ANNUAL_COLS:
                row[ci[c]] = None                           # 2025年の年次項目は未公表
            data[(area, 2025)] = row
    last_year = 2025 if with_2025 else 2024

    def v(row, name):
        x = row[ci[name]]
        return np.nan if x is None else float(x)

    def annual(area, t):
        """年 t−1 の値。ない項目は、得られる最新の年(t−1 以前)の値。"""
        out = {}
        for k in ANNUAL_COLS:
            val = np.nan
            for y in range(t - 1, 2015, -1):
                row = data.get((area, y))
                if row is not None and row[ci[k]] is not None:
                    val = float(row[ci[k]])
                    break
            out[k] = val
        return out

    def rate(row):
        return np.nan if row is None or row[3] is None else float(row[3])

    keys = {k: [] for k in ("area", "pref", "t", "X", "y_t", "b1", "y", "pop_t", "pop_target", "ok", "pred")}
    for (area, year), r in data.items():
        t = year
        nxt = data.get((area, t + 1))
        is_pred = (t == last_year)                          # 目的年が未知の行
        if nxt is None and not is_pred:
            continue
        prev, prev2 = data.get((area, t - 1)), data.get((area, t - 2))
        y_t, y_1, y_2 = rate(r), rate(prev), rate(prev2)
        avail = [x for x in (y_t, y_1, y_2) if not np.isnan(x)]
        b1 = float(np.mean(avail)) if avail else np.nan
        y_1f = y_1 if not np.isnan(y_1) else b1
        y_2f = y_2 if not np.isnan(y_2) else b1
        pop_j, pop_tot, hh = v(r, "pop_japanese_asof"), v(r, "pop_total_asof"), v(r, "households_asof")
        ann = annual(area, t) if (t - 1) >= 2016 else {k: np.nan for k in ANNUAL_COLS}
        # t−1 の年次項目が全くない場合(t=2016)は段3と同じく欠損のまま
        if t == 2016:
            ann = {k: np.nan for k in ANNUAL_COLS}
        f = [
            y_t, y_1f, y_2f,
            np.log(pop_j) if pop_j > 0 else np.nan,
            pm._div(v(r, "pop_under15_asof"), pop_tot), pm._div(v(r, "pop_65plus_asof"), pop_tot),
            pm._div(v(r, "pop_foreign_asof"), pop_tot), pm._div(pop_tot, hh), pm._div(v(r, "single_households_asof"), hh),
            np.log(pop_j / ann["area_habitable"]) if pop_j > 0 and ann["area_habitable"] > 0 else np.nan,
            pm._div(ann["area_habitable"], ann["area_total"]),
            pm._div(ann["births"], pop_j) * 1000, pm._div(ann["deaths"], pop_j) * 1000,
            pm._div(ann["marriages"], pop_j) * 1000, pm._div(ann["divorces"], pop_j) * 1000,
            pm._div(ann["kindergarten_pupils"], pop_j) * 1000, pm._div(ann["elementary_pupils"], pop_j) * 1000,
            pm._div(ann["junior_high_pupils"], pop_j) * 1000, pm._div(ann["high_school_students"], pop_j) * 1000,
            pm._div(ann["general_hospitals"], pop_j) * 10000, pm._div(ann["clinics"], pop_j) * 10000,
            pm._div(ann["dental_clinics"], pop_j) * 10000,
        ]
        excl_t = bool(r[5])
        if is_pred:
            yv, pop_target, ok = np.nan, np.nan, False
            pred = (not excl_t) and not np.isnan(y_t)
        else:
            yv = rate(nxt)
            pop_target = float(nxt[4]) if nxt[4] is not None else np.nan
            ok = (not excl_t) and (not bool(nxt[5])) and not np.isnan(y_t) and not np.isnan(yv)
            pred = False
        keys["area"].append(area); keys["pref"].append(pref_of[area]); keys["t"].append(t)
        keys["X"].append(f); keys["y_t"].append(y_t); keys["b1"].append(b1); keys["y"].append(yv)
        keys["pop_t"].append(float(r[4]) if r[4] is not None else np.nan); keys["pop_target"].append(pop_target)
        keys["ok"].append(ok); keys["pred"].append(pred)
    tb = pm.Table(area=np.array(keys["area"]), pref=np.array(keys["pref"]), t=np.array(keys["t"]),
                  X=np.array(keys["X"], dtype=float), y_t=np.array(keys["y_t"]), b1=np.array(keys["b1"]),
                  y=np.array(keys["y"]), pop_t=np.array(keys["pop_t"]), pop_target=np.array(keys["pop_target"]),
                  ok=np.array(keys["ok"], dtype=bool))
    return tb, np.array(keys["pred"], dtype=bool)


def _size_classes(pop: np.ndarray) -> np.ndarray:
    return np.array([pe.size_class(p) if not np.isnan(p) else -1 for p in pop])


def run_scope(con, scope: str) -> dict:
    tb, pred_mask = build_forward_table(con, scope)
    ok_train = pm._train_ok(tb)
    cls = _size_classes(tb.pop_t)
    err: dict[str, dict[int, list]] = {m: {k: [] for k in range(len(pe.SIZE_LABELS))} for m in METHODS}
    backtest = []
    for T in BACKTEST_YEARS:
        train = ok_train & (tb.target_year <= T - 1)
        test = tb.ok & (tb.target_year == T)
        fit = pm.tune_and_fit(tb, train, T)
        preds = {"B0_previous_year": tb.y_t[test], "B1_mean_last3": tb.b1[test],
                 "M1_ridge": tb.b1[test] + pm.predict_ridge(fit["ridge"], tb.X[test]),
                 "M2_gbdt": tb.b1[test] + pm.predict_gbdt(fit["gbdt"], tb.X[test])}
        for m in METHODS:
            e = np.abs(preds[m] - tb.y[test])
            for k in range(len(pe.SIZE_LABELS)):
                err[m][k] += list(e[cls[test] == k])
            backtest.append(dict(scope=scope, method=m, eval_year=T, n=int(test.sum()), mae=float(e.mean()),
                                 alpha=fit["alpha"], gbdt_depth=fit["gbdt_depth"], gbdt_trees=fit["gbdt_trees"],
                                 n_train=fit["n_train"]))
    width = {m: {k: (float(np.quantile(err[m][k], INTERVAL_Q)) if err[m][k] else float("nan"))
                 for k in range(len(pe.SIZE_LABELS))} for m in METHODS}
    train = ok_train & (tb.target_year <= FORECAST_YEAR - 1)
    fit = pm.tune_and_fit(tb, train, FORECAST_YEAR)
    idx = np.where(pred_mask)[0]
    X = tb.X[idx]
    point = {"B0_previous_year": tb.y_t[idx], "B1_mean_last3": tb.b1[idx],
             "M1_ridge": tb.b1[idx] + pm.predict_ridge(fit["ridge"], X),
             "M2_gbdt": tb.b1[idx] + pm.predict_gbdt(fit["gbdt"], X)}
    return dict(tb=tb, idx=idx, point=point, width=width, cls=cls, backtest=backtest, fit_hyper=dict(
        scope=scope, alpha=fit["alpha"], gbdt_depth=fit["gbdt_depth"], gbdt_trees=fit["gbdt_trees"],
        n_train=fit["n_train"], n_folds=fit["n_folds"]))


def _r(x, k=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


def run(out_dir: Path | None = None) -> dict:
    import duckdb
    out = out_dir or ROOT / "outputs" / "public"
    con = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    names = {a: n for a, n in con.execute("SELECT area_code, area_name FROM silver_panel_area").fetchall()}
    pred_rows, bt_rows, w_rows, hp_rows = [], [], [], []
    for scope in ("main", "sensitivity"):
        res = run_scope(con, scope)
        tb, idx, cls = res["tb"], res["idx"], res["cls"]
        for j, i in enumerate(idx):
            row = dict(scope=scope, area_code=tb.area[i], area_name=names.get(tb.area[i], ""), pref_code=tb.pref[i],
                       size_class=pe.SIZE_LABELS[cls[i]] if cls[i] >= 0 else "", y_2025_permille=_r(tb.y_t[i], 4))
            for m in METHODS:
                p = float(res["point"][m][j])
                w = res["width"][m].get(int(cls[i]), float("nan"))
                row[f"pred_{m}"] = _r(p, 4)
                row[f"lo_{m}"] = _r(p - w, 4)
                row[f"hi_{m}"] = _r(p + w, 4)
            pred_rows.append(row)
        bt_rows += [{k: (_r(v, 4) if isinstance(v, float) else v) for k, v in b.items()} for b in res["backtest"]]
        for m in METHODS:
            for k, lab in enumerate(pe.SIZE_LABELS):
                w_rows.append(dict(scope=scope, method=m, size_class=lab, half_width_permille=_r(res["width"][m][k], 4)))
        hp_rows.append({k: (_r(v, 4) if isinstance(v, float) else v) for k, v in res["fit_hyper"].items()})
    con.close()
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "forecast_2026_predictions.csv", pred_rows)
    write_csv(out / "forecast_2026_backtest_2020_2025.csv", bt_rows)
    write_csv(out / "forecast_2026_interval_widths.csv", w_rows)
    write_csv(out / "forecast_2026_hyperparams.csv", hp_rows)
    return dict(n_pred={s: sum(1 for r in pred_rows if r["scope"] == s) for s in ("main", "sensitivity")})


def main() -> int:
    print("panel-forward:", run())
    return 0
