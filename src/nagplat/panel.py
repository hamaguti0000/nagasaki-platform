"""全国パネル(市区町村×年)の構築。取得元: SSDSE-A(教育用標準データセット 市区町村)の各年版(2018〜2026年版)。

SSDSE-A は、各版に「最新の年次」の値が入る(版の年 − 2 など、項目ごとに遅れが異なる)。
そのため、版を重ねて、(市区町村, 項目, 年度) の値を組み立てる。

  bronze_ssdse_a      : 版×市区町村×項目×年度 の値(原本の構造のまま)
  silver_ssdse_area_map: 地域コードの対応(版の間でコードが変わった市区町村を、最新のコードに寄せる)
  silver_panel_value  : 市区町村×項目×年度 の値(最新の版を採用。版の間の差を残す)
  gold_panel_municipality_year : 市区町村×年(2016〜2024)の指標とフラグ
  gold_panel_forecast_table    : 年 t の情報 → 年 t+1 の転入超過率(基準手法の評価用)

年度の対応・遅れは、各版のヘッダー(「年度」の行)から読む。コードに書き込まない。
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .common import ROOT, write_csv

VINTAGES = list(range(2018, 2027))
PANEL_YEARS = list(range(2016, 2025))      # 転入者数・転出者数が、版から組み立てられる年
TARGET_IN, TARGET_OUT, POP_JP = "A5101", "A5102", "A1102"

# 年次の項目(毎年。版ごとに別の年度の値が入る)
ANNUAL = {
    "A4101": "births", "A4200": "deaths", "A9101": "marriages", "A9201": "divorces",
    "E1101": "kindergartens", "E1501": "kindergarten_pupils", "E2101": "elementary_schools",
    "E2401": "elementary_teachers", "E2501": "elementary_pupils", "E3101": "junior_high_schools",
    "E3401": "junior_high_teachers", "E3501": "junior_high_pupils", "E4101": "high_schools",
    "E4501": "high_school_students", "B1101": "area_total", "B1103": "area_habitable",
    "I510120": "general_hospitals", "I5102": "clinics", "I5103": "dental_clinics",
}
# 5年周期の項目(国勢調査)。「直近の国勢調査」を使う
CENSUS = {
    "A1101": "pop_total", "A1102": "pop_japanese", "A1301": "pop_under15", "A1302": "pop_15_64",
    "A1303": "pop_65plus", "A1700": "pop_foreign", "A7101": "households", "A810105": "single_households",
    "F1102": "employed", "F1107": "unemployed",
}
# 避難指示区域の市町村(国・県の一覧との照合は未確認。名称は私の知識による候補)
EVAC_CANDIDATES = {"田村市", "南相馬市", "川俣町", "広野町", "楢葉町", "富岡町", "川内村", "大熊町", "双葉町", "浪江町", "葛尾村", "飯舘村"}
CONFIRMED_DISASTER_CODES = {"07546"}       # 双葉町: 「解説」に、2020年国勢調査の時点で常住者なしと明記


def vintage_path(v: int) -> Path:
    return ROOT / "raw" / "public" / "ssdse" / f"SSDSE-A-{v}.csv"


def read_vintage(v: int) -> dict:
    t = vintage_path(v).read_bytes().decode("cp932")
    r = list(csv.reader(io.StringIO(t)))
    code, yr, name = r[0], r[1], r[2]
    assert name[0] == "地域コード" and "A1101" in code and "A5101" in code, (v, code[0], name[0])
    return dict(vintage=v, item_code=code, ref_year=yr, item_name=name, rows=r[3:])


def long_csv(path: Path) -> dict:
    """全版を縦持ちのCSV(UTF-8)に書く。戻り値: 版ごとの市区町村コード集合と名称。"""
    areas: dict[int, dict[str, tuple[str, str]]] = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["vintage", "area_code", "pref_name", "area_name", "item_code", "item_name", "ref_year", "value"])
        for v in VINTAGES:
            d = read_vintage(v)
            ic, iy, inm = d["item_code"], d["ref_year"], d["item_name"]
            areas[v] = {}
            for row in d["rows"]:
                if not row or not row[0]:
                    continue
                areas[v][row[0]] = (row[1], row[2])
                for i in range(3, len(ic)):
                    x = row[i].strip()
                    w.writerow([v, row[0], row[1], row[2], ic[i], inm[i], int(iy[i]), float(x) if x != "" else ""])
    return areas


def code_map(areas: dict) -> list[dict]:
    """版の間でコードが入れ替わった市区町村を、最新の版のコードに対応づける。
    規則: 隣り合う版で、同じ都道府県の中で『消えたコード1件・増えたコード1件』のとき、同一の市区町村とみなす。
    それ以外の増減があれば、対応づけられないので異常終了する(手で確認する)。"""
    vs = sorted(areas)
    nxt: dict[str, tuple[str, int]] = {}
    changes = []
    for a, b in zip(vs, vs[1:]):
        rem = sorted(set(areas[a]) - set(areas[b]))
        add = sorted(set(areas[b]) - set(areas[a]))
        if not rem and not add:
            continue
        if len(rem) == 1 and len(add) == 1 and areas[a][rem[0]][0] == areas[b][add[0]][0]:
            nxt[rem[0]] = (add[0], b)
            changes.append(dict(from_code=rem[0], to_code=add[0], last_vintage_with_from=a, first_vintage_with_to=b,
                                old_name=areas[a][rem[0]][1], new_name=areas[b][add[0]][1],
                                prefecture=areas[a][rem[0]][0],
                                basis="隣り合う版で、同じ都道府県の消えたコードと増えたコードが各1件(推定。廃置分合等情報での確認は未確認)"))
        else:
            raise SystemExit(f"地域コードの増減を対応づけられない: {a}->{b} 消えた={rem} 増えた={add}")
    return changes


def canonical(code: str, nxt: dict[str, str]) -> str:
    seen = set()
    while code in nxt and code not in seen:
        seen.add(code)
        code = nxt[code]
    return code


def build_panel(con) -> dict:
    work = ROOT / "work"
    areas = long_csv(work / "ssdse_long.csv")
    changes = code_map(areas)
    nxt = {c["from_code"]: c["to_code"] for c in changes}
    write_csv(ROOT / "ledger" / "panel_code_changes.csv", changes,
              ["from_code", "to_code", "last_vintage_with_from", "first_vintage_with_to", "old_name", "new_name",
               "prefecture", "basis"])
    con.execute(f"""CREATE TABLE bronze_ssdse_a AS SELECT vintage::INTEGER AS vintage, area_code, pref_name, area_name,
        item_code, item_name, ref_year::INTEGER AS ref_year, value::DOUBLE AS value
        FROM read_csv('{work / 'ssdse_long.csv'}', header=true, all_varchar=true)""")
    # 地域コードの対応
    latest = areas[VINTAGES[-1]]
    con.execute("CREATE TABLE silver_ssdse_area_map (ssdse_code VARCHAR, canon_code VARCHAR, area_code VARCHAR, "
                "pref_code VARCHAR, pref_name VARCHAR, area_name VARCHAR, code_changed BOOLEAN)")
    rows = []
    allcodes = {c for v in areas for c in areas[v]}
    for c in sorted(allcodes):
        cc = canonical(c, nxt)
        pref, name = latest[cc]
        rows.append((c, cc, cc[1:], cc[1:3], pref, name, cc != c or cc in nxt.values()))
    con.executemany("INSERT INTO silver_ssdse_area_map VALUES (?,?,?,?,?,?,?)", rows)
    items = list(ANNUAL) + list(CENSUS) + [TARGET_IN, TARGET_OUT]
    inlist = ",".join(f"'{i}'" for i in items)
    con.execute(f"""CREATE TABLE silver_panel_value AS
        SELECT m.area_code, b.item_code, b.ref_year AS year,
               ARG_MAX(b.value, b.vintage) AS value, MAX(b.vintage) AS vintage_used,
               COUNT(DISTINCT b.vintage) AS n_vintages, MAX(b.value) - MIN(b.value) AS revision_range
        FROM bronze_ssdse_a b JOIN silver_ssdse_area_map m ON m.ssdse_code = b.area_code
        WHERE b.item_code IN ({inlist})
        GROUP BY m.area_code, b.item_code, b.ref_year""")
    # 地域の台帳(最新の名称・フラグ)
    con.execute("""CREATE TABLE silver_panel_area AS
        SELECT area_code, ANY_VALUE(pref_code) AS pref_code, ANY_VALUE(pref_name) AS pref_name,
               ANY_VALUE(area_name) AS area_name, BOOL_OR(code_changed) AS code_change
        FROM silver_ssdse_area_map GROUP BY area_code""")
    ev = ",".join(f"'{n}'" for n in sorted(EVAC_CANDIDATES))
    cd = ",".join(f"'{n}'" for n in sorted(CONFIRMED_DISASTER_CODES))
    ann = ",\n".join(f"MAX(v.value) FILTER (WHERE v.item_code='{c}') AS {n}" for c, n in ANNUAL.items())
    cen = ",\n".join(
        f"MAX(c.value) FILTER (WHERE c.item_code='{c}') AS {n}_asof" for c, n in CENSUS.items())
    con.execute(f"""CREATE TABLE gold_panel_municipality_year AS
        WITH y AS (SELECT area_code, year,
                   MAX(value) FILTER (WHERE item_code='{TARGET_IN}')  AS transfers_in_jp,
                   MAX(value) FILTER (WHERE item_code='{TARGET_OUT}') AS transfers_out_jp,
                   {ann}
                   FROM silver_panel_value v WHERE year BETWEEN {PANEL_YEARS[0]} AND {PANEL_YEARS[-1]} GROUP BY 1, 2),
        base AS (SELECT a.area_code, a.pref_code, a.pref_name, a.area_name, a.code_change, yrs.year
                 FROM silver_panel_area a, (SELECT UNNEST(RANGE({PANEL_YEARS[0]}, {PANEL_YEARS[-1] + 1})) AS year) yrs),
        den AS (SELECT area_code, year AS census_year, value AS pop_jp FROM silver_panel_value WHERE item_code='{POP_JP}'),
        cenf AS (SELECT area_code, year AS census_year, item_code, value FROM silver_panel_value
                 WHERE item_code IN ({",".join(f"'{c}'" for c in CENSUS)}))
        SELECT b.area_code, b.pref_code, b.pref_name, b.area_name, b.year,
               y.transfers_in_jp, y.transfers_out_jp,
               y.transfers_in_jp - y.transfers_out_jp AS net_transfers_jp,
               CASE WHEN b.year >= 2020 THEN 2020 ELSE 2015 END AS census_year_denominator,
               d.pop_jp AS pop_jp_denominator,
               CASE WHEN d.pop_jp > 0 THEN ROUND((y.transfers_in_jp - y.transfers_out_jp) / d.pop_jp * 1000, 4) END
                   AS net_rate_permille,
               CASE WHEN b.year >= 2021 THEN 2020 ELSE 2015 END AS census_year_asof,
               {", ".join(f"y.{n}" for n in ANNUAL.values())},
               {", ".join(f"(SELECT value FROM cenf c WHERE c.area_code=b.area_code AND c.item_code='{c}' AND c.census_year = (CASE WHEN b.year >= 2021 THEN 2020 ELSE 2015 END)) AS {n}_asof" for c, n in CENSUS.items())},
               b.code_change,
               (d.pop_jp = 0) AS pop_zero,
               (b.area_code IN ({cd})) AS disaster_confirmed,
               (b.pref_code = '07' AND b.area_name IN ({ev})) AS evac_candidate
        FROM base b
        LEFT JOIN y ON y.area_code = b.area_code AND y.year = b.year
        LEFT JOIN den d ON d.area_code = b.area_code AND d.census_year = (CASE WHEN b.year >= 2020 THEN 2020 ELSE 2015 END)""")
    con.execute("""ALTER TABLE gold_panel_municipality_year ADD COLUMN excluded_main BOOLEAN""")
    con.execute("""ALTER TABLE gold_panel_municipality_year ADD COLUMN excluded_sensitivity BOOLEAN""")
    con.execute("""UPDATE gold_panel_municipality_year SET
        excluded_main = (code_change OR COALESCE(pop_zero, TRUE) OR disaster_confirmed OR net_rate_permille IS NULL),
        excluded_sensitivity = (code_change OR COALESCE(pop_zero, TRUE) OR disaster_confirmed OR evac_candidate
                                OR net_rate_permille IS NULL)""")
    con.execute("""CREATE TABLE gold_panel_forecast_table AS
        SELECT area_code, pref_code, area_name, year AS t, year + 1 AS target_year,
               net_rate_permille AS y_t,
               LAG(net_rate_permille, 1) OVER w AS y_t_minus1,
               LAG(net_rate_permille, 2) OVER w AS y_t_minus2,
               LEAD(net_rate_permille, 1) OVER w AS y_target,
               LEAD(pop_jp_denominator, 1) OVER w AS pop_target,
               pop_jp_denominator AS pop_t,
               excluded_main, LEAD(excluded_main, 1) OVER w AS excluded_main_target,
               excluded_sensitivity, LEAD(excluded_sensitivity, 1) OVER w AS excluded_sensitivity_target
        FROM gold_panel_municipality_year
        WINDOW w AS (PARTITION BY area_code ORDER BY year)""")
    con.execute("DELETE FROM gold_panel_forecast_table WHERE target_year > 2024")
    write_item_ledger(con)
    return dict(changes=changes, n_items=len(items))


def write_item_ledger(con) -> None:
    """項目の台帳(資料源・周期・版ごとの年度・名称の変更)を ledger/panel_items.csv に書く。"""
    import openpyxl
    src = {}
    p = ROOT / "raw" / "reference" / "ssds_kiso_shi.xlsx"
    if p.exists():
        ws = openpyxl.load_workbook(p, data_only=True)["基礎データ項目一覧"]
        for r in ws.iter_rows(min_row=5, values_only=True):
            if r[0] and r[1]:
                src[str(r[1])] = (r[3], r[4], r[5])
    roles = {TARGET_IN: "target_component", TARGET_OUT: "target_component"}
    roles.update({c: "feature_annual" for c in ANNUAL})
    roles.update({c: "feature_census" for c in CENSUS})
    rows = []
    for code, role in sorted(roles.items()):
        per = con.execute("""SELECT vintage, ANY_VALUE(ref_year), ANY_VALUE(item_name) FROM bronze_ssdse_a
                             WHERE item_code = ? GROUP BY vintage ORDER BY vintage""", [code]).fetchall()
        names = sorted({n for _, _, n in per})
        lags = [v - y for v, y, _ in per]
        pat = "一定(版−%d)" % lags[0] if len(set(lags)) == 1 else "版により異なる"
        dept, srcname, cycle = src.get(code, ("", "", ""))
        rows.append(dict(item_code=code, item_name=names[-1], role=role, n_vintages=len(per),
                         ref_year_by_vintage=";".join(f"{v}:{y}" for v, y, _ in per), lag_pattern=pat,
                         name_variants=" / ".join(names) if len(names) > 1 else "",
                         source_dept=dept or "", source_survey=srcname or "", cycle=cycle or ""))
    write_csv(ROOT / "ledger" / "panel_items.csv", rows)
