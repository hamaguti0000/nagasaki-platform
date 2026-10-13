"""全国パネルでの、基準手法(4種)の評価。**機械学習モデルは含まない**。

目的変数: 日本人移動者の転入超過率(人口1,000人あたり。国内移動のみ)の、翌年の値 y(T)。
予測は、年 t = T-1 までの情報のみを使う。

基準手法(結果を見る前に固定した。変更しない):
  B0 前年値            : y(t)
  B1 直近3年の平均      : y(t), y(t-1), y(t-2) のうち、得られるものの平均
  B2 規模階級の平均      : 年 t の、同じ人口規模階級の市区町村の y(t) の平均
  B3 全国の中央値        : 年 t の、全市区町村の y(t) の中央値
  (B2・B3 は、年 t の横断面の統計。評価対象を含めない設定 b・c では、その都道府県を除いて計算する)

検証:
  (a) 時間で切る           : 評価年 T = 2020〜2024。全市区町村。B2・B3 の統計は、全市区町村から。
  (b) 都道府県ごとに外す    : 47分割。評価する都道府県を、B2・B3 の統計の計算から外す。
  (c) 長崎を外し、時間で切る : 長崎を B2・B3 の統計から外して、長崎の21市町を評価する(= (b) の長崎の行)。
注: 基準手法は学習するパラメータを持たないため、(b)・(c) は (a) と、B2・B3 の統計の計算対象だけが異なる。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

EVAL_YEARS = [2020, 2021, 2022, 2023, 2024]
SIZE_BINS = [5_000, 10_000, 30_000, 100_000]           # 人口(日本人、国勢調査)の階級の境界
SIZE_LABELS = ["<5千", "5千-1万", "1万-3万", "3万-10万", ">=10万"]
METHODS = ["B0_previous_year", "B1_mean_last3", "B2_size_class_mean", "B3_national_median"]
SEED = 20261013                                         # ブートストラップの乱数のseed(固定)
N_BOOT = 2000
NAGASAKI = "42"


def size_class(pop: float) -> int:
    for i, b in enumerate(SIZE_BINS):
        if pop < b:
            return i
    return len(SIZE_BINS)


@dataclass
class Row:
    area_code: str
    pref: str
    t: int
    y_t: float
    y_t1: float | None
    y_t2: float | None
    y: float            # 実績 y(T)
    pop_t: float
    pop_target: float


def load_rows(con, scope: str = "main") -> list[Row]:
    ex = "excluded_main" if scope == "main" else "excluded_sensitivity"
    q = f"""SELECT area_code, pref_code, t, y_t, y_t_minus1, y_t_minus2, y_target, pop_t, pop_target
            FROM gold_panel_forecast_table
            WHERE target_year BETWEEN 2020 AND 2024 AND NOT COALESCE({ex}, TRUE) AND NOT COALESCE({ex}_target, TRUE)
              AND y_t IS NOT NULL AND y_target IS NOT NULL
            ORDER BY target_year, area_code"""
    return [Row(a, p, t, y0, y1, y2, y, pt, pg) for a, p, t, y0, y1, y2, y, pt, pg in con.execute(q).fetchall()]


def all_cross_sections(con, scope: str) -> dict[int, list[Row]]:
    """B2・B3 の統計に使う、年 t の横断面(評価対象かどうかに関わらず、除外されていない市区町村)。"""
    ex = "excluded_main" if scope == "main" else "excluded_sensitivity"
    q = f"""SELECT area_code, pref_code, t, y_t, pop_t FROM gold_panel_forecast_table
            WHERE NOT COALESCE({ex}, TRUE) AND y_t IS NOT NULL ORDER BY t, area_code"""
    out: dict[int, list] = {}
    for a, p, t, y0, pt in con.execute(q).fetchall():
        out.setdefault(t, []).append((a, p, y0, pt))
    return out


def predict(rows: list[Row], xs: dict[int, list], setting: str, pref_out: str | None = None) -> dict[str, np.ndarray]:
    """各行の予測。setting: 'a' 全市区町村から統計 / 'b' 各行の都道府県を除いて統計。"""
    n = len(rows)
    out = {m: np.empty(n) for m in METHODS}
    # 統計の事前計算(年・除外する都道府県ごと)
    cache: dict[tuple, tuple[float, dict[int, float]]] = {}

    def stats(t: int, excl: str | None):
        key = (t, excl)
        if key not in cache:
            cs = [(p, y, pop) for _, p, y, pop in xs[t] if excl is None or p != excl]
            med = float(np.median([y for _, y, _ in cs]))
            by = {}
            for k in range(len(SIZE_LABELS)):
                v = [y for _, y, pop in cs if size_class(pop) == k]
                by[k] = float(np.mean(v)) if v else med
            cache[key] = (med, by)
        return cache[key]

    for i, r in enumerate(rows):
        ys = [v for v in (r.y_t, r.y_t1, r.y_t2) if v is not None]
        out["B0_previous_year"][i] = r.y_t
        out["B1_mean_last3"][i] = float(np.mean(ys))
        excl = r.pref if setting == "b" else None
        med, by = stats(r.t, excl)
        out["B2_size_class_mean"][i] = by[size_class(r.pop_t)]
        out["B3_national_median"][i] = med
    return out


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.ptp(b) == 0 or np.ptp(a) == 0:
        return float("nan")
    ra = np.argsort(np.argsort(a, kind="stable"), kind="stable").astype(float)
    rb = np.argsort(np.argsort(b, kind="stable"), kind="stable").astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def metrics(rows: list[Row], pred: np.ndarray, years: list[int] | None = None) -> dict:
    y = np.array([r.y for r in rows])
    w = np.array([r.pop_target for r in rows])
    e = pred - y
    ty = np.array([r.t + 1 for r in rows])
    sp = []
    for T in sorted(set(ty)):
        m = ty == T
        sp.append(_spearman(pred[m], y[m]))
    sp = [s for s in sp if not math.isnan(s)]
    return dict(n=len(rows), mae=float(np.mean(np.abs(e))), rmse=float(np.sqrt(np.mean(e ** 2))),
                wmae=float(np.sum(w * np.abs(e)) / np.sum(w)),
                sign_acc=float(np.mean((pred > 0) == (y > 0))),
                spearman_mean=float(np.mean(sp)) if sp else float("nan"))


def evaluate(con, scope: str = "main") -> dict:
    rows = load_rows(con, scope)
    xs = all_cross_sections(con, scope)
    res = {"rows": rows, "scope": scope}
    for setting in ("a", "b"):
        res[setting] = predict(rows, xs, setting)
    return res


def bootstrap_improvement(rows: list[Row], preds: dict[str, np.ndarray], codes: list[str]) -> dict:
    """長崎の市町をまとまりとして再標本化し、基準B0に対するMAEの改善率の区間を出す(seed固定)。"""
    rng = np.random.default_rng(SEED)
    idx_by = {c: [i for i, r in enumerate(rows) if r.area_code == c] for c in codes}
    y = np.array([r.y for r in rows])
    err = {m: np.abs(preds[m] - y) for m in METHODS}
    out = {}
    cs = list(idx_by)
    draws = rng.integers(0, len(cs), size=(N_BOOT, len(cs)))
    for m in METHODS[1:]:
        vals = []
        for d in draws:
            idx = [i for k in d for i in idx_by[cs[k]]]
            b0 = err["B0_previous_year"][idx].mean()
            vals.append(1 - err[m][idx].mean() / b0)
        out[m] = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))
    return out
