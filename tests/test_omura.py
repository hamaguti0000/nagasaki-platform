"""大村市の調査: 設計の固定(ハッシュ)・比較群の規則・判定の規則のテスト。"""
import csv
import hashlib

import numpy as np

from nagplat import omura
from nagplat.common import ROOT


def test_design_and_events_hash_match_manifest():
    rows = list(csv.DictReader(open(ROOT / "ledger" / "omura_design_manifest.csv", encoding="utf-8")))
    assert [r["id"] for r in rows] == ["D1", "E1"]
    for r in rows:
        assert hashlib.sha256((ROOT / r["file"]).read_bytes()).hexdigest() == r["sha256"], r["file"]


def test_rankdata_ties_and_spearman():
    assert list(omura.rankdata(np.array([3.0, 1.0, 3.0, 2.0]))) == [3.5, 1.0, 3.5, 2.0]
    x = np.arange(10.0)
    assert abs(omura.spearman(x, x ** 3) - 1.0) < 1e-12
    assert abs(omura.spearman(x, -x) + 1.0) < 1e-12


def test_comparison_group_rules():
    p = omura.load_panel()
    g = omura.groups(p)
    o = g["omura"][0]
    pop0 = omura.pop2020(p, o)
    assert p[o][2020]["area_name"] == "大村市" and p[o][2020]["pref_code"] == "42"
    for k in ("C1", "C2", "S1", "S2", "S3", "S4", "S5"):
        assert o not in g[k]
    assert all(p[c][2020]["pref_code"] == "42" and p[c][2020]["area_name"].endswith("市") for c in g["C1"])
    for c in g["C2"]:
        assert p[c][2020]["pref_code"] not in omura.METRO
        assert p[c][2020]["area_name"].endswith("市")
        assert omura.BAND[0] * pop0 <= omura.pop2020(p, c) <= omura.BAND[1] * pop0
    assert set(g["C2"]) <= set(g["S1"]) and set(g["C2"]) <= set(g["S2"]) and len(g["S4"]) == 20


def test_census_items_use_the_2020_census_row():
    """2020年調査の値は2021年の行(census_year_asof=2020)。2020年の行は2015年調査の値(取り違えの再発防止)。"""
    p = omura.load_panel()
    ss = omura.load_ssdse_single()
    o = omura.groups(p)["omura"][0]
    assert p[o][2021]["census_year_asof"] == "2020" and p[o][2020]["census_year_asof"] == "2015"
    ind = omura.indicators_for(p, ss, o)
    hh15, hh20 = float(p[o][2016]["households_asof"]), float(p[o][2021]["households_asof"])
    assert abs(ind["I1a"] - hh20 / hh15) < 1e-12


def test_classify_rules():
    codes = [f"c{i}" for i in range(40)]
    vals = {c: float(i) for i, c in enumerate(codes)}
    net = {c: float(i) for i, c in enumerate(codes)}          # 指標と純移動が同じ順序 → 相関が強い
    c1 = {c: vals[c] for c in codes[:10]}
    hi = omura.classify("X", +1, 100.0, vals, {**c1, "z": 50.0}, net, [])
    assert hi["verdict"] == "データが支持する"
    lo = omura.classify("X", +1, -5.0, vals, c1, net, [])
    assert lo["verdict"] == "データと合わない"
    assert omura.classify("X", +1, None, vals, c1, net, [])["verdict"] == "データでは判断できない"
