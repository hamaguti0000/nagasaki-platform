"""段4(前向き予測)のテスト。`make fetch`(idou2025)、`make all`、`python -m nagplat.cli panel-forward` の実行後に動かす。"""
import copy
import csv
import hashlib
from pathlib import Path

import duckdb
import numpy as np
import pytest

from nagplat import panel_forward as pf
from nagplat import panel_model as pm
from nagplat.common import ROOT

OUT = ROOT / "outputs" / "public"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def forward(con):
    return pf.build_forward_table(con, "main")


def test_2025_moves_satisfy_identity_and_cover_the_panel(con):
    mv = pf.load_2025_moves()                                   # 内部で 転入−転出=転入超過 を assert
    codes = {r[0] for r in con.execute("SELECT DISTINCT area_code FROM gold_panel_municipality_year").fetchall()}
    assert codes <= set(mv)
    assert mv["42201"] == (9733.0, 11060.0)                     # 長崎市(表11-1・11-2の値)


def test_forward_features_equal_stage3_features_for_the_same_rows(con):
    a = pm.build_table(con, "main")
    b, _ = pf.build_forward_table(con, "main", with_2025=False)
    ka = {(x, int(t)): i for i, (x, t) in enumerate(zip(a.area, a.t))}
    kb = {(x, int(t)): i for i, (x, t) in enumerate(zip(b.area, b.t))}
    common = [k for k in ka if k in kb]
    ia, ib = np.array([ka[k] for k in common]), np.array([kb[k] for k in common])
    assert len(common) == len(a.t)
    assert np.allclose(a.X[ia], b.X[ib], equal_nan=True) and np.allclose(a.y[ia], b.y[ib], equal_nan=True)


def test_2025_rate_uses_2020_census_denominator_and_estat_values(con, forward):
    tb, pred = forward
    i = np.where((tb.area == "42201") & (tb.t == 2024))[0][0]    # t=2024 の目的 = 2025年
    pop = con.execute("SELECT pop_jp_denominator FROM gold_panel_municipality_year WHERE area_code='42201' AND year=2024").fetchone()[0]
    assert tb.y[i] == pytest.approx(round((9733 - 11060) / pop * 1000, 4))
    j = np.where((tb.area == "42201") & (tb.t == 2025))[0][0]    # t=2025 は予測する行(目的は未知)
    assert pred[j] and np.isnan(tb.y[j]) and not tb.ok[j] and tb.y_t[j] == pytest.approx(tb.y[i])


def test_latest_available_value_is_used_for_missing_annual_items(forward):
    tb, pred = forward
    names = pm.FEATURE_NAMES
    assert not np.isnan(tb.X[pred]).any()                        # 予測する行に欠損はない
    i = np.where((tb.area == "42201") & (tb.t == 2024))[0][0]
    j = np.where((tb.area == "42201") & (tb.t == 2025))[0][0]
    for n in ("births_per_1000", "hospitals_per_10000"):         # 2024年がない項目: 2023年の値(分母は年tの国勢調査人口)
        assert tb.X[i, names.index(n)] == pytest.approx(tb.X[j, names.index(n)])


def test_labels_of_the_evaluation_year_do_not_change_backtest_predictions(forward):
    tb, _ = forward
    T = 2025
    train = pm._train_ok(tb) & (tb.target_year <= T - 1)
    test = tb.ok & (tb.target_year == T)
    a = pm.tune_and_fit(tb, train, T)
    tb2 = copy.copy(tb)
    tb2.y = tb.y.copy()
    tb2.y[tb.target_year >= T] += 1000.0
    b = pm.tune_and_fit(tb2, train, T)
    assert np.array_equal(pm.predict_ridge(a["ridge"], tb.X[test]), pm.predict_ridge(b["ridge"], tb.X[test]))
    assert np.array_equal(pm.predict_gbdt(a["gbdt"], tb.X[test]), pm.predict_gbdt(b["gbdt"], tb.X[test]))


def test_prediction_table_shape_and_intervals():
    rows = list(csv.DictReader(open(OUT / "forecast_2026_predictions.csv", encoding="utf-8")))
    by = {s: [r for r in rows if r["scope"] == s] for s in ("main", "sensitivity")}
    assert len(by["main"]) == 1739 and len(by["sensitivity"]) == 1728
    nag = [r for r in by["main"] if r["pref_code"] == "42"]
    assert len(nag) == 21
    for r in rows:
        for m in pf.METHODS:
            lo, p, hi = (float(r[f"{k}_{m}"]) for k in ("lo", "pred", "hi"))
            assert lo <= p <= hi
    cands = {"田村市", "南相馬市", "川俣町", "広野町", "楢葉町", "富岡町", "川内村", "大熊町", "浪江町", "葛尾村", "飯舘村"}
    assert not [r for r in by["sensitivity"] if r["pref_code"] == "07" and r["area_name"] in cands]


def test_backtest_years_2020_to_2024_match_stage3_tables():
    s3 = {(r["scope"], r["method"], r["eval_year"]): float(r["mae"])
          for r in csv.DictReader(open(OUT / "panel_model_by_year.csv", encoding="utf-8")) if r["setting"] == "a"}
    for r in csv.DictReader(open(OUT / "forecast_2026_backtest_2020_2025.csv", encoding="utf-8")):
        k = (r["scope"], r["method"], r["eval_year"])
        if k in s3:
            assert float(r["mae"]) == pytest.approx(s3[k], abs=1e-3), k


def test_forecast_is_reproducible(tmp_path):
    names = ["forecast_2026_predictions.csv", "forecast_2026_backtest_2020_2025.csv",
             "forecast_2026_interval_widths.csv", "forecast_2026_hyperparams.csv"]
    pf.run(out_dir=tmp_path)
    for n in names:
        assert sha(tmp_path / n) == sha(OUT / n), n


def test_manifest_matches_files_if_frozen():
    p = ROOT / "ledger" / "forecast_2026_manifest.csv"
    if not p.exists():
        pytest.skip("まだ固定していない")
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if r["kind"] == "file":
            assert sha(ROOT / r["path"]) == r["sha256"], r["path"]
