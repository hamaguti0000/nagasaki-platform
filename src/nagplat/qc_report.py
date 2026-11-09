"""気象庁の月ごとの値の品質記号(準正常値・資料不足値など)の集計と、扱いによる影響の確認。

出力: ledger/weather_qc_flags.csv(記号つきの値の一覧)、ledger/weather_qc_impact.csv(観測点×年の影響)
記号の意味は、気象庁「過去の気象データ・ダウンロード データについて」(help4)の表記による(docs/段2 参照)。
"""
from __future__ import annotations

import duckdb

from .common import ROOT, write_csv

MEANING = {
    "quasi_normal": "準正常値 ')' : 統計の対象資料が許容範囲で欠けている(資料数の80%が基準)",
    "insufficient": "資料不足値 ']' : 統計の対象資料が許容範囲を超えて欠けている",
    "missing": "欠測 '///'", "abnormal": "疑問値 '#'", "no_phenomenon": "該当現象なし '--'",
}


def run() -> dict:
    con = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    flags = con.execute("""
        SELECT s.station_name, w.year, w.month, w.variable, w.raw, w.value, w.flag
        FROM bronze_jma_monthly w JOIN silver_station s USING (block_no)
        WHERE w.flag <> 'ok' ORDER BY s.block_no, w.year, w.month, w.variable""").fetchall()
    rows = [dict(station=a, year=b, month=c, variable=d, raw=e, value=f, flag=g, meaning=MEANING.get(g, g))
            for a, b, c, d, e, f, g in flags]
    write_csv(ROOT / "ledger" / "weather_qc_flags.csv", rows,
              ["station", "year", "month", "variable", "raw", "value", "flag", "meaning"])
    # 影響: 観測点×年。記号つきの月を (A)使う (B)除く で比べる
    impact = con.execute("""
        WITH m AS (SELECT * FROM silver_weather_month),
        f AS (SELECT block_no, year, month,
                     MAX(CASE WHEN flag <> 'ok' THEN 1 ELSE 0 END) AS any_flag
              FROM bronze_jma_monthly GROUP BY block_no, year, month)
        SELECT m.station_name, m.year,
               COUNT(*) AS n_months,
               SUM(f.any_flag) AS n_months_with_flag,
               ROUND(AVG(m.temp_mean_c), 2) AS temp_mean_all,
               ROUND(AVG(CASE WHEN f.any_flag=0 THEN m.temp_mean_c END), 2) AS temp_mean_excl_flagged,
               ROUND(SUM(m.precip_total_mm), 1) AS precip_sum_all,
               ROUND(SUM(CASE WHEN f.any_flag=1 THEN m.precip_total_mm END), 1) AS precip_in_flagged_months,
               ROUND(SUM(m.sunshine_total_h), 1) AS sunshine_sum_all,
               ROUND(SUM(CASE WHEN f.any_flag=1 THEN m.sunshine_total_h END), 1) AS sunshine_in_flagged_months
        FROM m JOIN f ON f.block_no = m.block_no AND f.year = m.year AND f.month = m.month
        GROUP BY m.station_name, m.year HAVING SUM(f.any_flag) > 0
        ORDER BY m.station_name, m.year""").fetchall()
    cols = ["station", "year", "n_months", "n_months_with_flag", "temp_mean_all", "temp_mean_excl_flagged",
            "precip_sum_all", "precip_in_flagged_months", "sunshine_sum_all", "sunshine_in_flagged_months"]
    write_csv(ROOT / "ledger" / "weather_qc_impact.csv", [dict(zip(cols, r)) for r in impact], cols)
    summary = con.execute("""SELECT w.flag, w.variable, COUNT(*) FROM bronze_jma_monthly w WHERE w.flag<>'ok'
                             GROUP BY 1,2 ORDER BY 1,2""").fetchall()
    n_months = con.execute("""SELECT COUNT(*) FROM (SELECT block_no, year, month FROM bronze_jma_monthly
                             WHERE flag <> 'ok' GROUP BY 1,2,3)""").fetchone()[0]
    con.close()
    return dict(n_values=len(rows), n_months=n_months, by_flag_variable=summary, n_station_years=len(impact))


def main() -> int:
    r = run()
    print("qc-report:", r)
    return 0
