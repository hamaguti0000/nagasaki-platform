"""台帳: 利用条件の原文引用(取得した規約ページとの逐語照合)と、ソースごとの実測(行数・容量)。

- config/terms_quotes.csv の引用文が、取得済みの規約ページ(raw/terms)の本文に、そのまま(空白を除いて)含まれることを確認する。
  含まれない引用があれば異常終了する(ページが変わった、または引用の誤り)。
- 出力: ledger/terms_quotes_verified.csv, ledger/source_measurements.csv
"""
from __future__ import annotations

import html
import re
from collections import defaultdict

import duckdb

from .common import ROOT, read_csv, write_csv
from .fetch import all_sources, _last_logged_hashes


def _page_text(path) -> str:
    raw = path.read_bytes()
    try:
        t = raw.decode("utf-8")
    except UnicodeDecodeError:  # 統計局のページは Shift_JIS(cp932)
        t = raw.decode("cp932", errors="replace")
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return re.sub(r"\s+", "", t)


def verify_terms_quotes() -> list[dict]:
    srcs = {s["source_id"]: s for s in all_sources()}
    log = {r["source_id"]: r for r in read_csv(ROOT / "manifest" / "fetch_log.csv") if r["result"] == "fetched"}
    pages = {tid: _page_text(ROOT / srcs[sid]["dest"]) for tid, sid in
             (("T_ESTAT", "terms_estat"), ("T_ESTAT_GIS", "terms_estat_gis"), ("T_JMA", "terms_jma"),
              ("T_PREF_SITE", "terms_pref_site"), ("T_PDL1", "terms_public_data_v1"),
             ("T_KENEIBUS", "ref_keneibus_opendata"), ("T_JMA_HELP", "ref_jma_obsdl_help4"),
             ("T_STAT", "ref_stat_riyou"), ("T_IDOU", "ref_idou_top"), ("T_SSDS", "ref_ssds_items"),
             ("T_SSDSE", "ref_ssdse"))}
    pages["T_SSDS"] += _page_text(ROOT / srcs["ref_ssds_gaiyou"]["dest"])
    pages["T_JMA_HELP"] += _page_text(ROOT / srcs["ref_jma_obsdl_help1"]["dest"])  # 同じ説明ページ群(help1/help4)
    out, missing = [], []
    for q in read_csv(ROOT / "config" / "terms_quotes.csv"):
        ok = re.sub(r"\s+", "", q["quote"]) in pages[q["terms_id"]]
        sid = q["page_source_id"]
        out.append(dict(terms_id=q["terms_id"], topic=q["topic"], quote=q["quote"], verbatim_in_page="Y" if ok else "N",
                        page_url=srcs[sid]["url"], page_sha256=log[sid]["sha256"], fetched_at_utc=log[sid]["fetched_at_utc"]))
        if not ok:
            missing.append(q["quote"][:40])
    write_csv(ROOT / "ledger" / "terms_quotes_verified.csv", out)
    if missing:
        raise SystemExit(f"規約ページに見つからない引用: {missing}")
    return out


def measure_sources() -> list[dict]:
    """取得物の実測。確認できた値のみ。行数は解析後の件数(bronze)。"""
    srcs = all_sources()
    by_group = defaultdict(list)
    for s in srcs:
        by_group[s["group"]].append(s)
    con = duckdb.connect(str(ROOT / "warehouse" / "nagasaki.duckdb"), read_only=True)
    cnt = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    rows = []

    def add(name, group, parsed, unit, extra=""):
        files = by_group[group]
        b = sum((ROOT / s["dest"]).stat().st_size for s in files)
        rows.append(dict(source=name, group=group, n_files=len(files), total_bytes=b, parsed_rows=parsed,
                         parsed_unit=unit, note=extra))

    add("県観光統計 集約表(観光客数)", "kanko", cnt("SELECT COUNT(*) FROM bronze_kanko_aggregate"),
        "年×区分(21市町+県計)の行(6指標の列を持つ)", "17年(2009〜2025)×22区分。分析対象は2014〜2025年")
    add("県異動人口調査 年間集計", "jinko", cnt("SELECT COUNT(*) FROM bronze_jinko_nenkan"),
        "年×区分の行", "11年(2015〜2025)×22区分")
    n_pages = 0
    try:
        from pypdf import PdfReader
        n_pages = sum(len(PdfReader(str(ROOT / s["dest"])).pages) for s in by_group["kanko_notes"])
    except Exception:  # noqa: BLE001
        n_pages = -1
    add("県観光統計 本文PDF(再算定の注記の確認用)", "kanko_notes", n_pages, "ページ", "11年版(2015〜2025)。-1は未計測")
    add("気象庁 月ごとの値(官署6地点×11年×3表示)", "weather", cnt("SELECT COUNT(*) FROM bronze_jma_monthly"),
        "月×変数の値", "792か月×5変数。HTML 198ファイル+アメダス地点表(JSON)1ファイルを含む")
    add("統計GIS 境界データ(令和2年国勢調査 小地域 長崎県)", "boundary", cnt("SELECT COUNT(*) FROM bronze_boundary_small_area"),
        "小地域ポリゴン", "ZIP内のshpは約21MB(展開時)。市町に集約すると21ポリゴン")
    con.close()
    write_csv(ROOT / "ledger" / "source_measurements.csv", rows)
    return rows
