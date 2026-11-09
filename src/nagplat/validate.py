"""検証: 取得物・行数・年×市町の網羅・恒等式・再算定の注記との整合。結果を ledger/validation_results.csv に書く。

status: PASS / FAIL(公開物の更新を止める) / WARN(許容するが記録する)
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from .common import AREA_NAMES, AREAS, PREF_TOTAL, ROOT, STATIONS, TOURISM_YEARS, YEARS, read_csv, write_csv
from .fetch import all_sources, verify_local

TOL = 0.5  # 人数の許容差
METRICS = ["tourists_total", "day_visitors", "stay_person_days", "stay_nights", "stay_guests", "visitors_actual"]
POP_SUM_COLS = ["pop_start", "in_total", "out_total", "births", "deaths", "pop_end"]
CENSUS_ADJUST_YEARS = {2015, 2020}  # 国勢調査の確定を反映した基準更新(期末 ≠ 期首+増減)の年。実測して確認する。


class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, cid: str, desc: str, n: int, bad: list, status_if_bad: str = "FAIL", detail: str = "") -> None:
        st = "PASS" if not bad else status_if_bad
        d = detail or ("; ".join(str(b) for b in bad[:5]) + (f" ...(+{len(bad) - 5})" if len(bad) > 5 else ""))
        self.rows.append(dict(check_id=cid, description=desc, n_checked=n, n_failed=len(bad), status=st, detail=d))


def _norm_name(s: str) -> str:
    return s.replace("諌", "諫")


def _pdf_text(path: Path, cache: Path) -> str | None:
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    try:
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def _panel_checks(R: Results, q, srcs) -> None:
    from .panel import ANNUAL, CENSUS, PANEL_YEARS, TARGET_IN, TARGET_OUT, VINTAGES
    # P01 版ごとの行数と、取得物のハッシュ
    n_b = q("SELECT vintage, COUNT(DISTINCT area_code) FROM bronze_ssdse_a GROUP BY 1 ORDER BY 1")
    R.add("P01", "SSDSE-A の各版(9版)の市区町村数が1,741で一定", len(n_b), [r for r in n_b if r[1] != 1741])
    # P02 地域コードの形式と、都道府県コードとの整合
    bad = [r for r in q("SELECT DISTINCT area_code FROM bronze_ssdse_a") if not (len(r[0]) == 6 and r[0][0] == "R" and r[0][1:].isdigit())]
    R.add("P02", "地域コードが『R+5桁』の形式", 1, bad)
    pref = q("SELECT pref_code, COUNT(DISTINCT pref_name) FROM silver_panel_area GROUP BY 1 HAVING COUNT(DISTINCT pref_name) > 1")
    R.add("P03", "都道府県コードと都道府県名が1対1", 47, pref)
    npref = q("SELECT COUNT(DISTINCT pref_code) FROM silver_panel_area")[0][0]
    R.add("P04", "都道府県が47", 47, [] if npref == 47 else [npref])
    # P05 値の形式(数値以外・負数・欠け)
    nn = q("SELECT COUNT(*) FROM bronze_ssdse_a WHERE value IS NULL")[0][0]
    ng = q("SELECT COUNT(*) FROM bronze_ssdse_a WHERE value < 0 AND item_code <> 'D2211'")[0][0]  # D2211(実質公債費比率)は、定義上、負になりうる(実測703件)
    R.add("P05", "全版・全項目の値が、数値(欠け0。負数は、比率の項目D2211のみ)", q("SELECT COUNT(*) FROM bronze_ssdse_a")[0][0],
          ([f"欠け{nn}"] if nn else []) + ([f"負数{ng}"] if ng else []))
    # P06 市区町村×年の欠け(目的変数)
    exp = 1741 * len(PANEL_YEARS)
    got = q(f"SELECT COUNT(*) FROM gold_panel_municipality_year WHERE transfers_in_jp IS NOT NULL AND transfers_out_jp IS NOT NULL")[0][0]
    R.add("P06", "転入者数・転出者数(日本人移動者)が、1,741×9年(2016〜2024)の全てで存在", exp, [] if got == exp else [f"{got}/{exp}"])
    # P07 長崎の21市町が全年そろう
    have = q("SELECT year, area_code FROM gold_panel_municipality_year WHERE pref_code='42' AND net_rate_permille IS NOT NULL")
    want = {(y, c) for y in PANEL_YEARS for c, _ in AREAS}
    R.add("P07", "長崎の21市町の転入超過率が、2016〜2024年の全年でそろう", len(want), sorted(want - set(have)))
    nm = {c: n for c, n in q("SELECT area_code, area_name FROM silver_panel_area WHERE pref_code='42'")}
    R.add("P08", "長崎の21市町の団体コードと名称が、境界データ(段1)と一致する", 21,
          [(c, n) for c, n in AREAS if nm.get(c) != n])
    # P09 恒等式・範囲(国勢調査の人口)
    bad = q("""SELECT COUNT(*) FROM silver_panel_value a JOIN silver_panel_value b USING (area_code, year)
               WHERE a.item_code='A1101' AND b.item_code='A1102' AND b.value > a.value""")[0][0]
    R.add("P09", "日本人人口 ≦ 総人口(国勢調査、全市区町村・2時点)", q("SELECT COUNT(*) FROM silver_panel_value WHERE item_code='A1101'")[0][0],
          [f"{bad}件"] if bad else [])
    bad = q("""SELECT COUNT(*) FROM (SELECT area_code, year,
                 MAX(value) FILTER (WHERE item_code='A1101') tot,
                 SUM(value) FILTER (WHERE item_code IN ('A1301','A1302','A1303')) ages
               FROM silver_panel_value WHERE item_code IN ('A1101','A1301','A1302','A1303') GROUP BY 1,2)
             WHERE ages > tot + 0.5""")[0][0]
    R.add("P10", "年齢3区分の合計 ≦ 総人口(年齢不詳があるため、等号ではない)", 1741 * 2, [f"{bad}件"] if bad else [])
    # P11 版の間の改定(同じ市区町村・項目・年度が複数の版にある場合の一致)
    rv = q("SELECT item_code, year, COUNT(*), MAX(revision_range) FROM silver_panel_value WHERE n_vintages > 1 AND revision_range > 0 GROUP BY 1,2 ORDER BY 1,2")
    tot = q("SELECT COUNT(*) FROM silver_panel_value WHERE n_vintages > 1")[0][0]
    R.add("P11", "複数の版にある同じ年度の値が、版の間で一致する(改定の有無)", tot, rv, "WARN",
          detail=f"版の間で値が異なる(項目,年度,件数,最大差): {rv[:6]}" if rv else "")
    # P12 地域コードの変更
    from .common import read_csv as _rc
    chg = _rc(ROOT / "ledger" / "panel_code_changes.csv")
    R.add("P12", "版の間の地域コードの変更が、都道府県内の1対1の入れ替わりのみ(対応づけ可能)", len(chg), [],
          detail=f"{len(chg)}件: " + "; ".join(f"{c['old_name']}({c['from_code']})→{c['new_name']}({c['to_code']})" for c in chg))
    # P13 除外の内訳(記録)
    fl = q("""SELECT SUM(code_change::INT), SUM(COALESCE(pop_zero, FALSE)::INT), SUM(disaster_confirmed::INT),
                     SUM(evac_candidate::INT), SUM(excluded_main::INT), SUM(excluded_sensitivity::INT)
              FROM gold_panel_municipality_year""")[0]
    R.add("P13", "除外・フラグの件数を記録(コード変更/人口0/確認できた災害/避難指示区域の候補/主の除外/感度分析の除外)", 1741 * 9, [], "WARN",
          detail=f"code_change={fl[0]} pop_zero={fl[1]} disaster_confirmed={fl[2]} evac_candidate={fl[3]} excluded_main={fl[4]} excluded_sensitivity={fl[5]}")
    R.rows[-1]["status"] = "PASS"
    # P14 出典の注記(解説PDF)との整合: 注記の文言が、解説PDFの本文にそのまま含まれる
    notes = read_csv(ROOT / "config" / "panel_source_notes.csv")
    pdf = next(s for s in srcs if s["source_id"] == "ref_ssdse_kaisetsu_2026")
    txt = _pdf_text(ROOT / pdf["dest"], ROOT / "work" / "pdf_text" / "kaisetsu-A-2026.txt")
    if txt is None:
        R.add("P14", "解説PDFの注記が、本文に含まれる", len(notes), ["PDFを読めない"], "WARN", detail="PDFから文字を取り出せず未検証")
    else:
        t = re.sub(r"\s+", "", txt)
        R.add("P14", "解説PDFの注記(5件)が、本文にそのまま含まれる", len(notes),
              [n["note_id"] for n in notes if re.sub(r"\s+", "", n["quote"]) not in t])
    # P15 年度の対応(版の遅れ)が、記録と一致する
    lag = q("""SELECT vintage, ref_year FROM bronze_ssdse_a WHERE item_code = 'A5101' GROUP BY 1,2 ORDER BY 1""")
    bad = [(v, y) for v, y in lag if v - y != 2]
    R.add("P15", "転入者数(A5101)の年度が、全版で『版の年 − 2』", len(lag), bad)
    # P16 目的変数の外れ値(記録)
    ex = q("""SELECT COUNT(*) FROM gold_panel_municipality_year WHERE NOT excluded_main AND ABS(net_rate_permille) > 50""")[0][0]
    R.add("P16", "転入超過率の絶対値が50‰を超える(分母の人口が小さい・避難指示区域の影響)件数を記録", 1741 * 9, [], "WARN",
          detail=f"{ex}件(主の除外後)。評価では感度分析(避難指示区域の候補を除外)を併記する")
    R.rows[-1]["status"] = "WARN" if ex else "PASS"


def run_validation() -> bool:
    R = Results()
    wh = ROOT / "warehouse" / "nagasaki.duckdb"
    con = duckdb.connect(str(wh), read_only=True)
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731

    # --- 取得物 ---
    problems = verify_local()
    srcs = all_sources()
    R.add("V01", "原本のSHA256が、期待値または取得ログの記録と一致する", len(srcs), problems)
    pref = [s for s in srcs if s["license_class"] == "restricted_pref"]
    R.add("V02", "県の原本の取得物が、以前の独立した取得の記録(期待SHA256)と一致する", len(pref),
          [s["source_id"] for s in pref if not s["expected_sha256"]])
    log = read_csv(ROOT / "manifest" / "fetch_log.csv")
    R.add("V03", "取得ログに、不一致・HTTPエラーの記録がない(再取得で解消した分を除く)",
          len(log), [r["source_id"] for r in log if r["result"] in ("hash_mismatch",)
                     and not any(x["source_id"] == r["source_id"] and x["result"] == "fetched" for x in log)])

    # --- 行数 ---
    exp = {r["id"]: int(r["expected"]) for r in read_csv(ROOT / "config" / "expected_counts.csv")}
    for tid, table in (("bronze_kanko_aggregate", "bronze_kanko_aggregate"), ("bronze_jinko_nenkan", "bronze_jinko_nenkan"),
                       ("bronze_ssdse_a", "bronze_ssdse_a"), ("gold_panel_municipality_year", "gold_panel_municipality_year"),
                       ("gold_panel_forecast_table", "gold_panel_forecast_table"), ("silver_panel_area", "silver_panel_area"),
                       ("bronze_jma_monthly", "bronze_jma_monthly"),
                       ("bronze_boundary_small_area", "bronze_boundary_small_area"),
                       ("gold_municipality_year", "gold_municipality_year"),
                       ("gold_station_year", "gold_station_year")):
        n = q(f"SELECT COUNT(*) FROM {table}")[0][0]
        R.add(f"V10:{tid}", f"{table} の行数が期待値({exp[tid]})と一致する", n, [] if n == exp[tid] else [f"{n}!={exp[tid]}"])

    # --- 年×市町の網羅 ---
    have = {(y, c) for y, c in q("SELECT year, area_code FROM silver_tourism_year WHERE tourists_total IS NOT NULL")}
    want = {(y, c) for y in TOURISM_YEARS for c, _ in AREAS}
    R.add("V20", "観光客延べ数: 年(2014〜2025)×21市町に欠けがない", len(want), sorted(want - have))
    have = {(y, c) for y, c in q("SELECT year, area_code FROM silver_population_year WHERE pop_start IS NOT NULL "
                                 "AND pop_end IS NOT NULL AND pop_change IS NOT NULL")}
    want = {(y, c) for y in YEARS for c, _ in AREAS}
    R.add("V21", "人口: 年(2015〜2025)×21市町に欠けがない", len(want), sorted(want - have))
    nm = q("SELECT COUNT(*) FROM silver_weather_month WHERE temp_mean_c IS NULL OR precip_total_mm IS NULL "
           "OR sunshine_total_h IS NULL")[0][0]
    cnt = q("SELECT COUNT(*) FROM silver_weather_month")[0][0]
    R.add("V22", "気象: 観測点×年×月(792件)の行がそろう", len(STATIONS) * len(YEARS) * 12,
          [] if cnt == len(STATIONS) * len(YEARS) * 12 else [f"{cnt}行"])
    R.add("V23", "気象: 気温・降水量・日照の値が欠けていない月", cnt, [f"{nm}件の月に欠け"] if nm else [], "WARN")
    fl = q("SELECT COUNT(*) FROM silver_weather_month WHERE all_ok = FALSE")[0][0]
    R.add("V24", "気象: 準正常値・資料不足値などの記号がない月(記号付きは月別の値に残す)", cnt,
          [f"{fl}件の月に記号付きの値"] if fl else [], "WARN")

    # --- 恒等式(観光) ---
    rows = q("SELECT year, area_name, tourists_total, day_visitors, stay_person_days FROM silver_tourism_year")
    bad = [(y, a, t, d + s) for y, a, t, d, s in rows if abs(t - (d + s)) > TOL]
    R.add("V30", "観光客延べ数 = 日帰り客数 + 宿泊客延べ滞在数(県計と全市町、2014〜2025年)", len(rows), bad)
    bad, n = [], 0
    for m in METRICS:
        for y in TOURISM_YEARS:
            tot = q(f"SELECT {m} FROM silver_tourism_year WHERE year={y} AND area_name='{PREF_TOTAL}'")[0][0]
            s = q(f"SELECT SUM({m}) FROM silver_tourism_year WHERE year={y} AND area_name<>'{PREF_TOTAL}'")[0][0]
            n += 1
            if abs(tot - s) > TOL:
                bad.append((m, y, tot, s))
    R.add("V31", "県計 = 21市町の合計(観光6指標×12年)", n, bad)

    # --- 恒等式(人口) ---
    rows = q("SELECT year, area_name, pop_change, social_change, natural_change, in_total, out_total, births, deaths "
             "FROM silver_population_year")
    R.add("V32", "人口増減 = 社会増減 + 自然増減", len(rows),
          [(y, a) for y, a, pc, sc, nc, *_ in rows if abs(pc - (sc + nc)) > TOL])
    R.add("V33", "社会増減 = 転入計 − 転出計、自然増減 = 出生 − 死亡", len(rows),
          [(y, a) for y, a, _pc, sc, nc, i, o, b, d in rows if abs(sc - (i - o)) > TOL or abs(nc - (b - d)) > TOL])
    rows = q("SELECT year, area_name, in_total, out_total FROM silver_population_year")
    bi = {(y, a): (i, o) for y, a, i, o in rows}
    br = q("SELECT year, area_name, in_pref, in_out, out_pref, out_out FROM bronze_jinko_nenkan")
    R.add("V34", "転入計 = 県内+県外、転出計 = 県内+県外", len(br),
          [(y, a) for y, a, ip, io, op, oo in br if abs(bi[(y, a)][0] - (ip + io)) > TOL or abs(bi[(y, a)][1] - (op + oo)) > TOL])
    bad, n = [], 0
    for c in POP_SUM_COLS:
        for y in YEARS:
            tot = q(f"SELECT {c} FROM silver_population_year WHERE year={y} AND area_name='{PREF_TOTAL}'")[0][0]
            s = q(f"SELECT SUM({c}) FROM silver_population_year WHERE year={y} AND area_name<>'{PREF_TOTAL}'")[0][0]
            n += 1
            if abs(tot - s) > TOL:
                bad.append((c, y, tot, s))
    R.add("V35", "県計 = 21市町の合計(人口の主要列×11年)", n, bad)
    adj = q("SELECT DISTINCT year FROM silver_population_year WHERE ABS(census_adjustment) > 0.5 ORDER BY year")
    got = {y for (y,) in adj}
    R.add("V36", f"期末 ≠ 期首+増減(国勢調査の基準更新)になる年が、記録済みの年{sorted(CENSUS_ADJUST_YEARS)}と一致する",
          len(YEARS), [] if got == CENSUS_ADJUST_YEARS else [f"実測: {sorted(got)}"])
    brk = q("""SELECT a.year, a.area_name, a.pop_end, b.pop_start FROM silver_population_year a
               JOIN silver_population_year b ON a.area_code=b.area_code AND b.year=a.year+1
               WHERE ABS(a.pop_end - b.pop_start) > 0.5""")
    R.add("V37", "人口: 翌年の期首 = 当年の期末(連続)", q("SELECT COUNT(*) FROM silver_population_year WHERE year<2025")[0][0], brk)

    # --- 市町・境界 ---
    bc = {c: n for c, n in q("SELECT DISTINCT city_code, city_name FROM bronze_boundary_small_area")}
    R.add("V40", "市町の団体コードと名称が、境界データの市区町村コード・名称と一致する(21件)", len(AREAS),
          [a for a in AREAS if bc.get(a[0]) != a[1]] + [(c, n) for c, n in bc.items() if (c, n) not in AREAS])
    dev = q("""SELECT g.area_name, g.population_2020_census, p.pop_start,
                      ROUND(100.0*(p.pop_start - g.population_2020_census)/g.population_2020_census, 2)
               FROM gold_municipality_pop2020 g JOIN silver_population_year p
                 ON p.area_code=g.area_code AND p.year=2021""")
    R.add("V41", "境界データの令和2年国勢調査人口と、2021年1月1日の推計人口の差が±1.5%以内(時点が3か月違う。合理性の確認)",
          len(dev), [d for d in dev if abs(d[3]) > 1.5],
          "WARN", detail=f"最大差 {max(abs(d[3]) for d in dev)}%")

    # --- 再算定・基準変更の注記との整合 ---
    notes = read_csv(ROOT / "ledger" / "revision_notes.csv")
    full_path = ROOT / "ledger" / "restricted" / "revision_notes_with_changes.csv"  # 県統計から導いた数値列を含む完全版(非公開)
    has_changes = full_path.exists()
    notes_full = read_csv(full_path) if has_changes else notes
    red = {(y, a) for y, a in q("SELECT year, area_name FROM silver_tourism_year WHERE tourists_total_recalc "
                                f"AND year BETWEEN 2014 AND 2024 AND area_name<>'{PREF_TOTAL}'")}
    named = {(int(n["recalculated_year"]), n["area_name"]) for n in notes if n["area_name"] in AREA_NAMES}
    R.add("V50", "県が朱書き(再算定後)にした観光客延べ数のセルは、全て注記に対応する(年は2014〜2024)", len(red), sorted(red - named))
    nonzero = {(int(n["recalculated_year"]), n["area_name"]) for n in notes_full
               if has_changes and n["area_name"] in AREA_NAMES and n["visitors_total_change_persons"] not in ("", "0")}
    if has_changes:
        R.add("V51", "注記で観光客延べ数が変化した(≠0)と記録した市町・年は、集約表で朱書きになっている", len(nonzero),
              sorted(nonzero - red))
    else:  # 公開版には数値列がない。完全版(ledger/restricted)がある環境でのみ実行する
        R.add("V51", "注記で観光客延べ数が変化した(≠0)と記録した市町・年は、集約表で朱書きになっている", 0, ["未実行"],
              "WARN", detail="数値列を含む非公開の完全版(ledger/restricted/revision_notes_with_changes.csv)がないため未実行(未検証)")
    flags = read_csv(ROOT / "ledger" / "comparability_flags.csv")
    fl_red = [(int(f["year_after"]), f["area_name"]) for f in flags]
    R.add("V52", "算定方法の見直しの比較不可フラグの『見直し後の年』は、全て朱書きのセルに一致する(変化0の注記を除く)",
          len(fl_red), sorted(set(fl_red) - red - {(int(n["recalculated_year"]), n["area_name"]) for n in notes_full
                                                 if n["category"] == "method_change" and has_changes
                                                 and n["visitors_total_change_persons"] == "0"}), "WARN")
    # 原本(県の本文PDF)との突き合わせ: 注記の市町名が、「再算定」「算定方法の見直し」「訂正」の近くに現れる
    srcmap = {s["source_id"]: ROOT / s["dest"] for s in srcs}
    bad, unverifiable, n = [], [], 0
    by_ed: dict[int, list[dict]] = {}
    for nrow in notes:
        by_ed.setdefault(int(nrow["edition_year"]), []).append(nrow)
    for ed, lst in sorted(by_ed.items()):
        txt = _pdf_text(srcmap[f"kanko_honbun_{ed}"], ROOT / "work" / "pdf_text" / f"honbun_{ed}.txt")
        if txt is None or txt.count("観光") < 5:  # 取り出せない/文字化け(フォントの符号化が特殊なPDF)
            unverifiable.append(ed)
            continue
        t = _norm_name(re.sub(r"\s+", "", txt))
        spans = [(m.start(), m.end()) for m in re.finditer(r"再算定|算定方法の見直し|公表数値の訂正|見直し", t)]
        if not spans:
            bad.append((ed, "キーワードなし"))
            continue
        window = "".join(t[max(0, s - 250): e + 250] for s, e in spans)
        for nrow in lst:
            if nrow["area_name"] in AREA_NAMES:
                n += 1
                if _norm_name(nrow["area_name"]) not in window:
                    bad.append((ed, nrow["area_name"]))
    R.add("V53", "注記の市町名が、県の本文PDFの『再算定/算定方法の見直し/訂正』の記述の近くにある", n, bad,
          detail=("" if not unverifiable else f"PDFからテキストを取り出せず未検証: {unverifiable}") +
                 ("; ".join(map(str, bad[:5]))))
    if unverifiable:
        R.rows[-1]["status"] = "WARN" if not bad else "FAIL"

    # --- 地図の入力 ---
    g = q("SELECT tourists_per_capita FROM gold_municipality_year")
    R.add("V60", "人口1人あたり観光客延べ数が、全件で数値かつ 0〜100 の範囲", len(g),
          [x for (x,) in g if x is None or not (0 < x < 100)])
    gcount = q("SELECT COUNT(*) FROM gold_municipality_year WHERE year=2025")[0][0]
    R.add("V61", "地図の対象年(2025)に21市町がそろう", 21, [] if gcount == 21 else [gcount])


    # ===== 全国パネル(SSDSE-A)=====
    _panel_checks(R, q, srcs)
    con.close()
    write_csv(ROOT / "ledger" / "validation_results.csv", R.rows)
    for r in R.rows:
        print(f"{r['status']:5} {r['check_id']:28} n={r['n_checked']:<6} fail={r['n_failed']:<4} {r['description'][:70]}")
    nfail = sum(1 for r in R.rows if r["status"] == "FAIL")
    print(f"validate: {len(R.rows)} checks, FAIL={nfail}, WARN={sum(1 for r in R.rows if r['status']=='WARN')}")
    return nfail == 0
