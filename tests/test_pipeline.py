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
    for p in (ROOT / "data" / "public").rglob("*.csv"):
        header = set(p.read_text(encoding="utf-8-sig").splitlines()[0].replace('"', "").split(","))
        assert not (header & forbidden), (p, header & forbidden)


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
