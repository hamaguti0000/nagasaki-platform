"""段1のテスト。原本の取得(make fetch)と build/validate/map の実行後に動かす。"""
import csv
import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from nagplat.common import AREAS, ROOT, YEARS
from nagplat.fetch import all_sources, verify_local
from nagplat.parse_jma import parse_value

WH = ROOT / "warehouse" / "nagasaki.duckdb"


def q(sql):
    con = duckdb.connect(str(WH), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- 取得物のハッシュ ----
def test_raw_files_match_recorded_hashes():
    assert verify_local() == []


def test_prefecture_files_match_independent_earlier_hashes():
    pref = [s for s in all_sources() if s["license_class"] == "restricted_pref"]
    assert len(pref) == 1 + 11 + 11  # 集約表1 + 本文11 + 年間集計11
    for s in pref:
        assert s["expected_sha256"], s["source_id"]
        assert sha(ROOT / s["dest"]) == s["expected_sha256"], s["source_id"]


# ---- 行数 ----
def test_row_counts_match_expected():
    with open(ROOT / "config" / "expected_counts.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            n = q(f"SELECT COUNT(*) FROM {r['id']}")[0][0]
            assert n == int(r["expected"]), r["id"]


# ---- 年×市町の網羅 ----
def test_year_by_municipality_grid_is_complete():
    got = set(q("SELECT year, area_code FROM gold_municipality_year"))
    assert got == {(y, c) for y in YEARS for c, _ in AREAS}
    for col in ("population_jan1", "tourists_total", "tourists_per_capita", "pop_change_rate_pct"):
        assert q(f"SELECT COUNT(*) FROM gold_municipality_year WHERE {col} IS NULL")[0][0] == 0


# ---- 恒等式 ----
def test_tourism_identity_total_equals_day_plus_stay():
    bad = q("SELECT year, area_name FROM silver_tourism_year "
            "WHERE ABS(tourists_total - (day_visitors + stay_person_days)) > 0.5")
    assert bad == []


def test_population_identities():
    assert q("SELECT year, area_name FROM silver_population_year "
             "WHERE ABS(pop_change - (social_change + natural_change)) > 0.5") == []
    assert q("SELECT year, area_name FROM silver_population_year "
             "WHERE ABS(social_change - (in_total - out_total)) > 0.5 OR ABS(natural_change - (births - deaths)) > 0.5") == []


def test_prefecture_total_equals_sum_of_municipalities():
    for col in ("tourists_total", "day_visitors", "stay_person_days"):
        bad = q(f"""SELECT t.year FROM silver_tourism_year t WHERE t.area_name='県計' AND ABS(t.{col} -
                    (SELECT SUM({col}) FROM silver_tourism_year u WHERE u.year=t.year AND u.area_name<>'県計')) > 0.5""")
        assert bad == [], col


# ---- 再算定・基準変更の注記との整合(validate の結果)----
def test_validation_has_no_failures():
    with open(ROOT / "ledger" / "validation_results.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "make validate を先に実行する"
    assert [r["check_id"] for r in rows if r["status"] == "FAIL"] == []
    ids = {r["check_id"] for r in rows}
    assert {"V50", "V51", "V52", "V53"} <= ids


def test_every_red_cell_is_explained_by_a_note():
    rows = q("SELECT year, area_name FROM silver_tourism_year WHERE tourists_total_recalc AND year BETWEEN 2014 AND 2024 "
             "AND area_name <> '県計'")
    with open(ROOT / "ledger" / "revision_notes.csv", encoding="utf-8-sig") as f:
        notes = {(int(r["recalculated_year"]), r["area_name"]) for r in csv.DictReader(f)}
    assert [r for r in rows if r not in notes] == []


# ---- パーサー(原本の目視で確認した値)----
def test_known_values_from_source_workbooks():
    r = q("SELECT tourists_total FROM silver_tourism_year WHERE year=2025 AND area_name='長崎市'")
    assert r == [(10052499.0,)]
    r = q("SELECT tourists_total FROM silver_tourism_year WHERE year=2014 AND area_name='長崎市'")
    assert r == [(6306800.0,)]
    r = q("SELECT pop_start FROM silver_population_year WHERE year=2025 AND area_name='長崎市'")
    assert r == [(387395.0,)]
    r = q("SELECT temp_mean_c, precip_total_mm, sunshine_total_h FROM silver_weather_month "
          "WHERE station_name='長崎' AND year=2020 AND month=1")
    assert r == [(9.7, 116.0, 91.7)]


def test_jma_value_flags():
    assert parse_value("470.0 )") == (470.0, "quasi_normal")
    assert parse_value("7.6 ]") == (7.6, "insufficient")
    assert parse_value("--") == (None, "no_phenomenon")
    assert parse_value("9.7") == (9.7, "ok")


# ---- 公開区分の守り ----
def test_public_outputs_contain_no_prefecture_statistics_columns():
    forbidden = {"tourists_total", "tourists_per_capita", "pop_start", "pop_end", "births", "deaths", "day_visitors"}
    panel_ok = {"births", "deaths"}  # 全国パネル(SSDSE-A。国のデータ)の出生数・死亡数。県の異動人口調査の列ではない
    for p in (ROOT / "data" / "public").rglob("*.csv"):
        header = set(p.read_text(encoding="utf-8-sig").splitlines()[0].replace('"', "").split(","))
        is_panel = p.name.startswith(("gold_panel_", "silver_panel_", "silver_ssdse_"))
        bad = header & (forbidden - panel_ok if is_panel else forbidden)
        assert not bad, (p, bad)


def test_gitignore_excludes_raw_and_restricted():
    txt = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for line in ("raw/", "data/restricted/", "outputs/restricted/"):
        assert line in txt.splitlines()


# ---- 再実行で同じ結果 ----
def test_rebuild_is_deterministic():
    from nagplat.build import build_all
    from nagplat.mapmaker import make_maps
    def snapshot():
        out = {}
        for base in ("data", "outputs"):
            for p in sorted((ROOT / base).rglob("*")):
                if p.suffix in (".csv", ".geojson", ".png", ".json"):
                    out[str(p.relative_to(ROOT))] = sha(p)
        return out
    a = snapshot()
    build_all()
    make_maps()
    b = snapshot()
    assert a == b


# ---- 外部アクセスのルール ----
def test_user_agent_is_neutral_and_network_code_is_confined():
    import re
    from nagplat import fetch
    assert "@" not in fetch.UA and "/home/" not in fetch.UA
    fetch._check_ua(fetch.UA)
    with pytest.raises(SystemExit):
        fetch._check_ua("tool (contact: someone@example.org)")
    # ネットワークを使うコードは fetch.py のみ
    users = [p.name for p in (ROOT / "src" / "nagplat").glob("*.py")
             if re.search(r"^\s*(import|from)\s+(requests|urllib|http\.client|socket)\b", p.read_text(encoding="utf-8"), re.M)]
    assert users == ["fetch.py"]
    src = (ROOT / "src" / "nagplat" / "fetch.py").read_text(encoding="utf-8")
    assert "trust_env = False" in src


def test_no_personal_identifiers_in_publishable_files():
    from nagplat.privacy_scan import scan
    res = scan()
    # スキャナー自身の正規表現・規約の引用中の語は除く
    assert res["hits"] == []


# ---- 公開版の修正(要確認2件の反映)----
def test_public_revision_notes_has_no_prefecture_numeric_column():
    header = (ROOT / "ledger" / "revision_notes.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert "visitors_total_change_persons" not in header


def test_public_output_hashes_exclude_restricted_files():
    rows = (ROOT / "manifest" / "output_hashes.csv").read_text(encoding="utf-8").splitlines()[1:]
    assert rows and not any("restricted" in r for r in rows)


def test_gitignore_excludes_restricted_ledger_and_manifest():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "ledger/restricted/" in lines and "manifest/restricted/" in lines


# ---- 全国パネル(段2)----
def _raw_vintage_value(v: int, code: str, item: str) -> float:
    import io
    rows = list(csv.reader(io.StringIO((ROOT / "raw" / "public" / "ssdse" / f"SSDSE-A-{v}.csv").read_bytes().decode("cp932"))))
    j = rows[0].index(item)
    return float(next(r for r in rows[3:] if r[0] == code)[j])


def test_panel_shape_and_nagasaki_complete():
    assert q("SELECT COUNT(*), COUNT(DISTINCT area_code), MIN(year), MAX(year) FROM gold_panel_municipality_year") == [(15669, 1741, 2016, 2024)]
    n = q("SELECT COUNT(*) FROM gold_panel_municipality_year WHERE pref_code='42' AND net_rate_permille IS NOT NULL")[0][0]
    assert n == 21 * 9
    got = {c for (c,) in q("SELECT DISTINCT area_code FROM gold_panel_municipality_year WHERE pref_code='42'")}
    assert got == {c for c, _ in AREAS}


def test_panel_values_match_independent_parse_of_raw():
    # 長崎市(R42201): 2026年版 → 2024年の転入者数・転出者数。別の読み方(csv直読み)と一致する
    r = q("SELECT transfers_in_jp, transfers_out_jp FROM gold_panel_municipality_year WHERE area_code='42201' AND year=2024")
    assert r == [(_raw_vintage_value(2026, "R42201", "A5101"), _raw_vintage_value(2026, "R42201", "A5102"))]
    r = q("SELECT transfers_in_jp FROM gold_panel_municipality_year WHERE area_code='42201' AND year=2016")
    assert r == [(_raw_vintage_value(2018, "R42201", "A5101"),)]


def test_panel_code_change_is_the_single_known_case():
    with open(ROOT / "ledger" / "panel_code_changes.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(r["from_code"], r["to_code"]) for r in rows] == [("R40305", "R40231")]
    assert q("SELECT COUNT(DISTINCT area_code) FROM gold_panel_municipality_year WHERE code_change") == [(1,)]


def test_baseline_definitions_on_toy_rows():
    import numpy as np
    from nagplat.panel_eval import Row, predict
    rows = [Row("01001", "01", 2020, 3.0, 1.0, 2.0, 0.0, 20000, 20000),
            Row("01002", "01", 2020, -3.0, None, None, 0.0, 20000, 20000),
            Row("02001", "02", 2020, 9.0, 9.0, 9.0, 0.0, 200000, 200000)]
    xs = {2020: [(r.area_code, r.pref, r.y_t, r.pop_t) for r in rows]}
    p = predict(rows, xs, "a")
    assert list(p["B0_previous_year"]) == [3.0, -3.0, 9.0]
    assert list(p["B1_mean_last3"]) == [2.0, -3.0, 9.0]
    assert list(p["B2_size_class_mean"]) == [0.0, 0.0, 9.0]       # 同じ階級(1万-3万)の平均 = (3 + -3)/2
    assert list(p["B3_national_median"]) == [3.0, 3.0, 3.0]       # 中央値
    pb = predict(rows, xs, "b")                                    # 自分の都道府県を除く統計
    assert list(pb["B3_national_median"]) == [9.0, 9.0, 0.0]      # 都道府県01の行は、02の値(9.0)。02の行は、01の2値の中央値(0.0)


def test_bootstrap_is_reproducible():
    import numpy as np
    from nagplat.panel_eval import METHODS, Row, bootstrap_improvement
    rng = np.random.default_rng(1)
    rows = [Row(f"4220{i % 3}", "42", 2020, float(i), None, None, float(i) + 1, 1000, 1000) for i in range(30)]
    preds = {m: np.array([r.y_t + k for r in rows]) for k, m in enumerate(METHODS)}
    a = bootstrap_improvement(rows, preds, ["42200", "42201", "42202"])
    b = bootstrap_improvement(rows, preds, ["42200", "42201", "42202"])
    assert a == b


def test_panel_validation_items_present_and_not_failed():
    with open(ROOT / "ledger" / "validation_results.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = {r["check_id"] for r in rows}
    assert {f"P{i:02d}" for i in range(1, 17)} <= ids
    assert [r["check_id"] for r in rows if r["check_id"].startswith("P") and r["status"] == "FAIL"] == []


def test_panel_evaluation_tables_are_reproducible():
    from nagplat import panel_report
    out = ROOT / "outputs" / "public"
    names = sorted(p.name for p in out.glob("panel_baseline_*.csv"))
    assert len(names) == 6
    before = {n: sha(out / n) for n in names}
    panel_report.run()
    assert {n: sha(out / n) for n in names} == before


# ---- 出典の表記と、結果の文言 ----
def test_ssdse_credit_is_in_readme_and_notice():
    required = ["SSDSE-A-2018〜SSDSE-A-2026", "https://www.nstac.go.jp/use/literacy/SSDSE/", "を加工して作成",
                "元の出典: 総務省統計局「統計でみる都道府県・市区町村のすがた(社会・人口統計体系)」"]
    for name in ("README.md", "NOTICE"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for r in required:
            assert r in text, (name, r)


def test_results_wording_keeps_the_caveats():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "全国パネル_段2_結果.md").read_text(encoding="utf-8")
    for must in ("−1.3%", "勝てなかった", "+0.6%", "勝ったとは言い切れない", "双葉町", "事後の補助的な分析", "分母"):
        assert must in doc, must
    for must in ("−1.3%", "+0.6%", "双葉町", "勝ったとは言い切れない", "分母の限界"):
        assert must in readme, must
