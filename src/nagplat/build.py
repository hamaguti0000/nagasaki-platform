"""蓄積: 原本 → bronze(原本の構造のまま) → silver(市町コード・年・単位を揃える) → gold(指標)。

DuckDB(warehouse/nagasaki.duckdb)で処理し、Parquet と CSV を data/ に書く。
利用条件の区分でディレクトリを分ける: data/public(出典を付けて公開してよい) と data/restricted(県統計由来。GitHubに上げない)。
全て決定的(並び順を指定。乱数は使わない)。
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from .common import (AREAS, JMA_VIEWS, NAME_TO_CODE, PREF_TOTAL, ROOT, STATIONS, TOURISM_YEARS, YEARS,
                     jma_dest, read_csv, write_csv)
from .fetch import all_sources, verify_local
from .parse_boundary import dissolve_by_city, read_small_areas, to_geojson
from .parse_jinko import parse_nenkan
from .parse_jma import parse_monthly
from .parse_kanko import SHEETS, parse_aggregate

WAREHOUSE = ROOT / "warehouse" / "nagasaki.duckdb"
DATA = ROOT / "data"

# 出力先の区分(table -> class)
PUBLIC_TABLES = {"bronze_jma_monthly", "bronze_boundary_small_area", "silver_station", "silver_weather_month",
                 "silver_area", "gold_station_year", "gold_municipality_pop2020",
                 # 全国パネル(SSDSE-A。国のデータのみ)
                 "silver_panel_area", "silver_ssdse_area_map", "gold_panel_municipality_year",
                 "gold_panel_forecast_table"}
RESTRICTED_TABLES = {"bronze_kanko_aggregate", "bronze_jinko_nenkan", "silver_tourism_year",
                     "silver_population_year", "gold_municipality_year"}


def _src_hash(source_id: str) -> str:
    from .fetch import _last_logged_hashes
    return _last_logged_hashes().get(source_id, "")


def _layer(table: str) -> str:
    return table.split("_", 1)[0]


def _export(con: duckdb.DuckDBPyConnection, table: str, order_by: str) -> None:
    cls = "public" if table in PUBLIC_TABLES else "restricted"
    d = DATA / cls / _layer(table)
    d.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM {table} ORDER BY {order_by}) TO '{d / (table + '.parquet')}' (FORMAT parquet)")
    con.execute(f"COPY (SELECT * FROM {table} ORDER BY {order_by}) TO '{d / (table + '.csv')}' "
                f"(FORMAT csv, HEADER, FORCE_QUOTE *)")


def _insert(con, table: str, rows: list[dict], ddl: str) -> None:
    con.execute(f"CREATE TABLE {table} ({ddl})")
    if rows:
        cols = list(rows[0])
        con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(cols))})",
                        [[r[c] for c in cols] for r in rows])


def build_all() -> None:
    problems = verify_local()
    if problems:
        raise SystemExit(f"原本の検証に失敗: {problems[:5]} ... `make fetch` を実行してください")
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    if WAREHOUSE.exists():
        WAREHOUSE.unlink()
    con = duckdb.connect(str(WAREHOUSE))
    con.execute("SET threads TO 1")  # 浮動小数の集計順を固定し、再実行で同じ結果にする

    # ---- bronze: 県観光統計 集約表 ----
    kid = "kanko_agg_visitors"
    kpath = ROOT / next(s["dest"] for s in all_sources() if s["source_id"] == kid)
    krows = parse_aggregate(kpath)
    metrics = list(SHEETS.values())
    ddl = "year INTEGER, area_name VARCHAR, " + ", ".join(f"{m} DOUBLE, {m}__recalc BOOLEAN" for m in metrics) + \
          ", source_id VARCHAR, source_sha256 VARCHAR"
    out = []
    for r in krows:
        d = {"year": r["year"], "area_name": r["area_name"]}
        for m in metrics:
            d[m] = r.get(m)
            d[f"{m}__recalc"] = bool(r.get(f"{m}__recalc"))
        d["source_id"] = kid
        d["source_sha256"] = _src_hash(kid)
        out.append(d)
    _insert(con, "bronze_kanko_aggregate", out, ddl)

    # ---- bronze: 県異動人口調査 年間集計 ----
    nrows = []
    for y in YEARS:
        sid = f"jinko_nenkan_{y}"
        p = ROOT / next(s["dest"] for s in all_sources() if s["source_id"] == sid)
        for r in parse_nenkan(p, y):
            r["source_id"], r["source_sha256"] = sid, _src_hash(sid)
            nrows.append(r)
    pcols = ["pop_start", "in_pref", "in_out", "in_total", "out_pref", "out_out", "out_total", "social_change",
             "births", "deaths", "natural_change", "pop_change", "pop_end"]
    ddl = "year INTEGER, area_name VARCHAR, source_row INTEGER, source_sheet VARCHAR, " + \
          ", ".join(f"{c} DOUBLE" for c in pcols) + ", source_id VARCHAR, source_sha256 VARCHAR"
    order = ["year", "area_name", "source_row", "source_sheet"] + pcols + ["source_id", "source_sha256"]
    _insert(con, "bronze_jinko_nenkan", [{k: r[k] for k in order} for r in nrows], ddl)

    # ---- bronze: 気象庁 月ごとの値 ----
    jrows = []
    for block, _n, _a in STATIONS:
        for y in YEARS:
            for v in JMA_VIEWS:
                sid = f"jma_{block}_{y}_{v}"
                for r in parse_monthly(ROOT / jma_dest(block, y, v), block, y, v):
                    r["source_id"], r["source_sha256"] = sid, _src_hash(sid)
                    jrows.append(r)
    _insert(con, "bronze_jma_monthly", jrows,
            "block_no VARCHAR, year INTEGER, month INTEGER, variable VARCHAR, raw VARCHAR, value DOUBLE, "
            "flag VARCHAR, source_id VARCHAR, source_sha256 VARCHAR")

    # ---- bronze: 境界データ(小地域の属性) と市町への集約 ----
    bpath = ROOT / next(s["dest"] for s in all_sources() if s["source_id"] == "boundary_koku2020_42")
    small = read_small_areas(bpath)
    _insert(con, "bronze_boundary_small_area",
            [{k: s[k] for k in ("key_code", "city_code", "city_name", "s_area", "hcode", "area_m2", "jinko", "setai")}
             for s in small],
            "key_code VARCHAR, city_code VARCHAR, city_name VARCHAR, s_area VARCHAR, hcode INTEGER, "
            "area_m2 DOUBLE, jinko BIGINT, setai BIGINT")
    cities = dissolve_by_city(small)
    gj = to_geojson(cities)
    gdir = DATA / "public" / "gold"
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "municipality_boundary.geojson").write_text(
        json.dumps(gj, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    # ---- silver ----
    con.execute("CREATE TABLE silver_area (area_code VARCHAR, area_name VARCHAR, kind VARCHAR, in_scope BOOLEAN)")
    con.executemany("INSERT INTO silver_area VALUES (?,?,?,?)",
                    [(c, n, "市" if n.endswith("市") else "町", True) for c, n in AREAS] +
                    [("42000", PREF_TOTAL, "県", False)])
    # 観光
    sel = ", ".join(f"b.{m} AS {m}, b.{m}__recalc AS {m}_recalc" for m in metrics)
    con.execute(f"""CREATE TABLE silver_tourism_year AS
        SELECT b.year, a.area_code, b.area_name, {sel}, b.source_id, b.source_sha256
        FROM bronze_kanko_aggregate b JOIN silver_area a USING (area_name)
        WHERE b.year BETWEEN {TOURISM_YEARS[0]} AND {TOURISM_YEARS[-1]}""")
    # 人口(期末 - (期首 + 増減) = 国勢調査等による基準更新の補正)
    con.execute("""CREATE TABLE silver_population_year AS
        SELECT b.year, a.area_code, b.area_name, b.pop_start, b.in_total, b.out_total, b.social_change, b.births,
               b.deaths, b.natural_change, b.pop_change, b.pop_end,
               b.pop_end - (b.pop_start + b.pop_change) AS census_adjustment, b.source_id, b.source_sha256
        FROM bronze_jinko_nenkan b JOIN silver_area a USING (area_name)""")
    # 観測点
    import json as _json
    tbl = _json.loads((ROOT / "raw/public/jma/amedastable.json").read_text(encoding="utf-8"))
    con.execute("CREATE TABLE silver_station (block_no VARCHAR, station_name VARCHAR, amedas_id VARCHAR, "
                "lat DOUBLE, lon DOUBLE, alt_m DOUBLE)")
    for block, name, amd in STATIONS:
        t = tbl[amd]
        assert t["kjName"] == name, (amd, t["kjName"], name)
        con.execute("INSERT INTO silver_station VALUES (?,?,?,?,?,?)",
                    [block, name, amd, t["lat"][0] + t["lat"][1] / 60, t["lon"][0] + t["lon"][1] / 60, t["alt"]])
    con.execute("""CREATE TABLE silver_weather_month AS
        SELECT s.block_no, s.station_name, w.year, w.month,
               MAX(CASE WHEN variable='temp_mean_c' THEN value END) AS temp_mean_c,
               MAX(CASE WHEN variable='temp_max_c' THEN value END) AS temp_max_c,
               MAX(CASE WHEN variable='temp_min_c' THEN value END) AS temp_min_c,
               MAX(CASE WHEN variable='precip_total_mm' THEN value END) AS precip_total_mm,
               MAX(CASE WHEN variable='sunshine_total_h' THEN value END) AS sunshine_total_h,
               BOOL_AND(flag IN ('ok')) AS all_ok,
               STRING_AGG(DISTINCT CASE WHEN flag <> 'ok' THEN variable || ':' || flag END, ';' ORDER BY CASE WHEN flag <> 'ok' THEN variable || ':' || flag END) AS flags
        FROM bronze_jma_monthly w JOIN silver_station s ON s.block_no = w.block_no
        GROUP BY s.block_no, s.station_name, w.year, w.month""")

    # ---- ledger: 再算定の注記 → 比較不可フラグ(観光客延べ数) ----
    notes = read_csv(ROOT / "ledger" / "revision_notes.csv")
    flags = []
    for n in notes:
        if n["category"] == "method_change" and n["indicator_scope"] in ("visitors", "both"):
            ed = int(n["edition_year"])
            flags.append(dict(area_name=n["area_name"], area_code=NAME_TO_CODE[n["area_name"]],
                              indicator="tourists_total", year_before=ed - 2, year_after=ed - 1,
                              basis=f"{ed}年版の注記(算定方法の見直し)", note_source_id=n["source_id"]))
    flags.sort(key=lambda d: (d["area_code"], d["year_after"]))
    write_csv(ROOT / "ledger" / "comparability_flags.csv", flags)
    con.execute("CREATE TABLE ledger_comparability_flags (area_name VARCHAR, area_code VARCHAR, indicator VARCHAR, "
                "year_before INTEGER, year_after INTEGER, basis VARCHAR, note_source_id VARCHAR)")
    if flags:
        con.executemany("INSERT INTO ledger_comparability_flags VALUES (?,?,?,?,?,?,?)",
                        [[f[k] for k in ("area_name", "area_code", "indicator", "year_before", "year_after",
                                         "basis", "note_source_id")] for f in flags])

    # ---- gold ----
    yrs = f"{YEARS[0]} AND {YEARS[-1]}"
    con.execute(f"""CREATE TABLE gold_municipality_year AS
        SELECT t.year, t.area_code, t.area_name,
               p.pop_start AS population_jan1,
               t.tourists_total AS tourists_total,
               ROUND(t.tourists_total / p.pop_start, 3) AS tourists_per_capita,
               ROUND(100.0 * p.pop_change / p.pop_start, 3) AS pop_change_rate_pct,
               t.tourists_total_recalc AS tourists_recalculated_by_prefecture,
               EXISTS (SELECT 1 FROM ledger_comparability_flags f
                       WHERE f.area_code = t.area_code AND f.year_after = t.year) AS tourists_basis_changed_vs_prev_year
        FROM silver_tourism_year t
        JOIN silver_population_year p ON p.area_code = t.area_code AND p.year = t.year
        WHERE t.year BETWEEN {yrs} AND t.area_name <> '{PREF_TOTAL}'""")
    # 年の値の方針(気象庁の記号): 正常値と準正常値(')': 資料数が基準の80%以上)は使い、記号の件数を残す。
    # 資料不足値(']')・欠測・疑問値を含む変数の年の値は、空欄にする(月の値は silver に残す)。月を除いた平均は季節で偏るため使わない。
    con.execute("""CREATE TABLE gold_station_year AS
        WITH w AS (SELECT * FROM bronze_jma_monthly WHERE variable IN ('temp_mean_c','precip_total_mm','sunshine_total_h'))
        SELECT s.block_no, s.station_name, w.year,
               COUNT(DISTINCT w.month) AS n_months,
               CASE WHEN COUNT(*) FILTER (WHERE variable='temp_mean_c' AND flag IN ('ok','quasi_normal')) = 12
                    THEN ROUND(AVG(value) FILTER (WHERE variable='temp_mean_c'), 2) END AS temp_mean_c,
               CASE WHEN COUNT(*) FILTER (WHERE variable='precip_total_mm' AND flag IN ('ok','quasi_normal')) = 12
                    THEN ROUND(SUM(value) FILTER (WHERE variable='precip_total_mm'), 1) END AS precip_total_mm,
               CASE WHEN COUNT(*) FILTER (WHERE variable='sunshine_total_h' AND flag IN ('ok','quasi_normal')) = 12
                    THEN ROUND(SUM(value) FILTER (WHERE variable='sunshine_total_h'), 1) END AS sunshine_total_h,
               COUNT(*) FILTER (WHERE flag = 'quasi_normal') AS n_quasi_normal_values,
               COUNT(*) FILTER (WHERE flag NOT IN ('ok','quasi_normal')) AS n_excluded_values
        FROM w JOIN silver_station s ON s.block_no = w.block_no
        GROUP BY s.block_no, s.station_name, w.year""")
    con.execute("""CREATE TABLE gold_municipality_pop2020 AS
        SELECT city_code AS area_code, ANY_VALUE(city_name) AS area_name, SUM(jinko) AS population_2020_census,
               COUNT(*) AS n_small_areas
        FROM bronze_boundary_small_area GROUP BY city_code""")

    # ---- 全国パネル(SSDSE-A の各年版) ----
    from .panel import build_panel
    build_panel(con)

    # ---- export ----
    orders = {
        "bronze_kanko_aggregate": "year, area_name", "bronze_jinko_nenkan": "year, source_row",
        "bronze_jma_monthly": "block_no, year, month, variable",
        "bronze_boundary_small_area": "key_code, s_area, hcode, area_m2",
        "silver_area": "area_code", "silver_tourism_year": "year, area_code",
        "silver_population_year": "year, area_code", "silver_station": "block_no",
        "silver_weather_month": "block_no, year, month", "gold_municipality_year": "year, area_code",
        "gold_station_year": "block_no, year", "gold_municipality_pop2020": "area_code",
        "silver_panel_area": "area_code", "silver_ssdse_area_map": "ssdse_code",
        "gold_panel_municipality_year": "area_code, year", "gold_panel_forecast_table": "area_code, t",
    }
    for t, o in orders.items():
        _export(con, t, o)
    con.close()
    from .ledger import measure_sources, verify_terms_quotes
    verify_terms_quotes()
    measure_sources()
    _write_output_hashes()
    print("build: OK")


def _write_output_hashes() -> None:
    """出力のSHA256。公開用(manifest/output_hashes.csv)と、非公開のファイル名を含む分(manifest/restricted/)に分ける。"""
    from .common import sha256_file
    pub, priv = [], []
    for p in sorted(DATA.rglob("*")):
        if p.suffix in (".csv", ".geojson"):
            row = dict(path=str(p.relative_to(ROOT)), sha256=sha256_file(p), bytes=p.stat().st_size)
            (priv if "/restricted/" in row["path"] else pub).append(row)
    write_csv(ROOT / "manifest" / "output_hashes.csv", pub, ["path", "sha256", "bytes"])
    write_csv(ROOT / "manifest" / "restricted" / "output_hashes_restricted.csv", priv, ["path", "sha256", "bytes"])
