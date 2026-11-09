"""段3(予測モデル)のテスト。段2までのパネル(make all)と、`make panel-model` の実行後に動かす。"""
import csv
import hashlib
import subprocess
from pathlib import Path

import duckdb
import numpy as np
import pytest

from nagplat.common import ROOT
from nagplat import panel_model as pm

WH = ROOT / "warehouse" / "nagasaki.duckdb"
OUT = ROOT / "outputs" / "public"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(WH), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def table(con):
    return pm.build_table(con, "main")


# ---- モデルの部品(小さな例) ----
def test_ridge_recovers_a_linear_relation_and_is_deterministic():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 3))
    r = 2.0 * X[:, 0] - 1.0 * X[:, 1] + 0.5 + rng.normal(scale=0.1, size=400)
    m = pm.fit_ridge(X, r, alpha=1.0)
    p = pm.predict_ridge(m, X)
    assert np.mean(np.abs(p - r)) < 0.2
    assert np.array_equal(p, pm.predict_ridge(pm.fit_ridge(X, r, alpha=1.0), X))


def test_ridge_huber_is_not_dragged_by_a_huge_outlier():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(300, 1))
    r = 1.0 * X[:, 0] + rng.normal(scale=0.1, size=300)
    r[0] = 5000.0                                              # 避難指示区域の町村のような外れ値
    m = pm.fit_ridge(X, r, alpha=1.0)
    assert abs(m["beta"][0] / m["sd"][0] - 1.0) < 0.3          # 傾きは約1のまま(二乗損失なら大きくずれる)


def test_gbdt_learns_a_step_and_is_reproducible():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(600, 2))
    r = np.where(X[:, 0] > 0, 3.0, -3.0)
    a = pm.fit_gbdt(X, r, depth=2, n_trees=60)
    b = pm.fit_gbdt(X, r, depth=2, n_trees=60)
    pa, pb = pm.predict_gbdt(a, X), pm.predict_gbdt(b, X)
    assert np.array_equal(pa, pb)                              # seed固定: 同じ結果
    assert np.mean(np.abs(pa - r)) < 0.5
    assert a["gain"][0] > 10 * a["gain"][1]                    # 効いている特徴量に利得が集まる


# ---- 特徴量の時点(リークの防止) ----
def test_census_features_use_2015_census_up_to_t2020_and_2020_census_after(con, table):
    for area in ("42201", "01100"):
        for t in (2016, 2019, 2020, 2021, 2023):
            census = 2015 if t <= 2020 else 2020
            want = con.execute("SELECT value FROM silver_panel_value WHERE area_code=? AND item_code='A1102' AND year=?",
                               [area, census]).fetchone()
            i = np.where((table.area == area) & (table.t == t))[0]
            if want and i.size:
                got = table.X[i[0], pm.FEATURE_NAMES.index("log_pop_japanese")]
                assert got == pytest.approx(np.log(want[0])), (area, t)


def test_annual_features_are_taken_from_year_t_minus_1(con, table):
    area, t = "42201", 2021
    b = con.execute("SELECT births, pop_japanese_asof FROM gold_panel_municipality_year WHERE area_code=? AND year=?",
                    [area, t - 1]).fetchone()
    pop = con.execute("SELECT pop_japanese_asof FROM gold_panel_municipality_year WHERE area_code=? AND year=?",
                      [area, t]).fetchone()[0]
    i = np.where((table.area == area) & (table.t == t))[0][0]
    assert table.X[i, pm.FEATURE_NAMES.index("births_per_1000")] == pytest.approx(b[0] / pop * 1000)


def test_lags_are_filled_with_the_b1_rule_and_employment_is_not_used(table):
    assert not any("employ" in n for n in pm.FEATURE_NAMES)
    j0, j1, j2 = (pm.FEATURE_NAMES.index(n) for n in ("y_t", "y_t_minus1", "y_t_minus2"))
    i = np.where(table.t == 2016)[0][0]                        # t=2016: y(2015), y(2014) がない
    assert table.X[i, j1] == pytest.approx(table.X[i, j0]) and table.X[i, j2] == pytest.approx(table.X[i, j0])
    assert table.b1[i] == pytest.approx(table.X[i, j0])


def test_future_labels_do_not_change_predictions(table):
    """評価年 T 以降の目的年のラベルを書き換えても、T の予測は変わらない(時間のリークがない)。"""
    T = 2021
    ok = pm._train_ok(table)
    train = ok & (table.target_year <= T - 1)
    test = table.ok & (table.target_year == T)
    a = pm.tune_and_fit(table, train, T)
    pa = pm.predict_ridge(a["ridge"], table.X[test]), pm.predict_gbdt(a["gbdt"], table.X[test])
    import copy
    tb2 = copy.copy(table)
    tb2.y = table.y.copy()
    tb2.y[table.target_year >= T] += 1000.0
    b = pm.tune_and_fit(tb2, train, T)
    pb = pm.predict_ridge(b["ridge"], tb2.X[test]), pm.predict_gbdt(b["gbdt"], tb2.X[test])
    assert np.array_equal(pa[0], pb[0]) and np.array_equal(pa[1], pb[1])
    assert a["n_train"] == b["n_train"] and table.target_year[train].max() == T - 1


def test_tune_and_fit_refuses_rows_from_the_evaluation_year(table):
    ok = pm._train_ok(table)
    with pytest.raises(AssertionError):
        pm.tune_and_fit(table, ok & (table.target_year <= 2021), 2021)


# ---- 評価の枠組みと結果の表 ----
def test_nagasaki_is_held_out_in_setting_b():
    rows = list(csv.DictReader(open(OUT / "panel_model_hyperparams.csv", encoding="utf-8")))
    for scope in ("main", "sensitivity"):
        for T in range(2020, 2025):
            a = [r for r in rows if r["scope"] == scope and r["setting"] == "a" and int(r["eval_year"]) == T]
            b = [r for r in rows if r["scope"] == scope and r["setting"] == "b" and int(r["eval_year"]) == T
                 and r["held_out_pref"] == "42"]
            assert len(a) == 1 and len(b) == 1
            assert int(b[0]["n_train"]) < int(a[0]["n_train"])


def test_model_tables_cover_the_fixed_methods_and_both_scopes():
    rows = list(csv.DictReader(open(OUT / "panel_model_overall.csv", encoding="utf-8")))
    assert {r["method"] for r in rows} == {"B0_previous_year", "B1_mean_last3", "M1_ridge", "M2_gbdt"}
    assert {r["scope"] for r in rows} == {"main", "sensitivity"}
    n = {(r["scope"], r["setting"]): int(r["n"]) for r in rows}
    assert n[("main", "a")] == 8692 and n[("sensitivity", "a")] == 8640   # 段2と同じ評価行
    nag = list(csv.DictReader(open(OUT / "panel_model_nagasaki.csv", encoding="utf-8")))
    assert {int(r["n"]) for r in nag if r["scope"] == "main"} == {105}


def test_baseline_rows_in_model_tables_match_stage2():
    s2 = {(r["scope"], r["setting"], r["method"]): r["mae"]
          for r in csv.DictReader(open(OUT / "panel_baseline_overall.csv", encoding="utf-8"))}
    s3 = {(r["scope"], r["setting"], r["method"]): r["mae"]
          for r in csv.DictReader(open(OUT / "panel_model_overall.csv", encoding="utf-8"))}
    for k, v in s3.items():
        if k[2] in ("B0_previous_year", "B1_mean_last3"):
            assert float(v) == pytest.approx(float(s2[k]), abs=1e-4), k


def test_leakage_register_and_feature_list_are_complete():
    reg = list(csv.DictReader(open(ROOT / "ledger" / "panel_leakage_register.csv", encoding="utf-8")))
    assert len(reg) >= 10 and all(r["countermeasure"] and r["status"] for r in reg)
    feats = [r["feature"] for r in csv.DictReader(open(ROOT / "ledger" / "panel_model_features.csv", encoding="utf-8"))
             if r["kind"] != "excluded"]
    assert feats == pm.FEATURE_NAMES


def test_importance_table_is_labeled_as_association():
    doc = (ROOT / "docs" / "全国パネル_段3_結果.md").read_text(encoding="utf-8")
    assert "因果ではない" in doc and "相関" in doc


def test_new_outputs_are_public_candidates_and_not_in_ignored_paths():
    from nagplat.publish_list import classify
    for p in sorted(OUT.glob("panel_model_*.csv")):
        rel = str(p.relative_to(ROOT))
        assert classify(rel)[0] == "public", rel
    for rel in ("ledger/panel_leakage_register.csv", "ledger/panel_model_features.csv",
                "docs/全国パネル_段3_結果.md", "src/nagplat/panel_model.py"):
        assert classify(rel)[0] == "public", rel
    if (ROOT / ".git").exists():
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.splitlines()
        private = ("raw/", "warehouse/", "work/", ".pylibs/", "local/", "data/restricted/", "outputs/restricted/",
                   "ledger/restricted/", "manifest/restricted/")
        assert [t for t in tracked if t.startswith(private)] == []


def test_model_tables_are_reproducible():
    """seed固定: 同じ入力で、再実行しても全ての表が一致する。"""
    from nagplat import panel_model_report
    names = sorted(p.name for p in OUT.glob("panel_model_*.csv"))
    assert len(names) == 8
    before = {n: sha(OUT / n) for n in names}
    panel_model_report.run()
    assert {n: sha(OUT / n) for n in names} == before
