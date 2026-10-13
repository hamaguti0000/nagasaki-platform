"""公開用/非公開用のファイル一覧を作る(publish/PUBLISH_LIST.csv と .md)。GitHubに上げる前に、人が確認する。

区分:
  public   : 出典・加工の注記を付けて公開してよい(規約の原文は ledger/terms_quotes_verified.csv)
  review   : 県統計の要約・派生物など。設計で「置く」と決めた範囲だが、公開前に確認する
  private  : GitHubに上げない(.gitignore で除外)
"""
from __future__ import annotations

from pathlib import Path

from .common import ROOT, write_csv

CREDIT_ESTAT = "出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成"
CREDIT_JMA = "出典: 気象庁ホームページ「過去の気象データ」を加工して作成"
CREDIT_SSDSE = ("独立行政法人 統計センター SSDSE-A-2018〜2026(https://www.nstac.go.jp/use/literacy/SSDSE/)を加工して作成。"
                "元の出典: 総務省統計局「統計でみる都道府県・市区町村のすがた(社会・人口統計体系)」")

RULES = [  # (パス接頭辞, 区分, 理由, 出典の表記)
    ("raw/", "private", "取得した原本(県の統計・本文PDFを含む)。取得スクリプトと manifest/fetch_log.csv(URL・SHA256)で再現する", ""),
    ("warehouse/", "private", "作業用のDuckDBファイル(再生成できる。県統計由来を含む)", ""),
    ("work/", "private", "作業用(PDFのテキスト抽出など。県の本文PDF由来)", ""),
    (".pylibs/", "private", "ローカルのライブラリ置き場", ""),
    ("local/", "private", "個人の作業メモ(リモートの設定コマンドなど。ユーザー名を含む)", ""),
    ("ledger/restricted/", "private", "県統計から導いた数値列を含む台帳の完全版(検証V51用)", ""),
    ("manifest/restricted/", "private", "非公開ファイルのパスとハッシュ", ""),
    ("data/restricted/", "private", "県の統計由来の蓄積データ。県への確認が済むまで公開しない", ""),
    ("outputs/restricted/", "private", "県の統計の加工値を含む地図。県への確認が済むまで公開しない", ""),
    ("data/public/gold/municipality_boundary.geojson", "public", "e-Stat 境界データの加工物(市町に集約・簡略化)", CREDIT_ESTAT),
    ("data/public/gold/gold_panel_", "public", "SSDSE-A(国のデータ)から組み立てた全国パネル(値は版の値のまま+差・率・フラグ)", CREDIT_SSDSE),
    ("data/public/silver/silver_panel_", "public", "SSDSE-A の地域・コードの対応(版の値のまま+フラグ)", CREDIT_SSDSE),
    ("data/public/silver/silver_ssdse_", "public", "SSDSE-A の地域コードの対応", CREDIT_SSDSE),
    ("outputs/public/panel_baseline_", "public", "全国パネルでの基準手法の評価(SSDSE-A由来の加工値)", CREDIT_SSDSE),
    ("outputs/public/map_net_migration", "public", "SSDSE-A と e-Stat 境界データから作った地図", CREDIT_SSDSE + " / " + CREDIT_ESTAT),
    ("data/public/bronze/bronze_jma", "public", "気象庁のデータの整形", CREDIT_JMA),
    ("data/public/silver/silver_weather", "public", "気象庁のデータの整形", CREDIT_JMA),
    ("data/public/silver/silver_station", "public", "気象庁アメダス地点表から作成した観測点の位置", CREDIT_JMA),
    ("data/public/gold/gold_station", "public", "気象庁のデータの集計", CREDIT_JMA),
    ("data/public/bronze/bronze_boundary", "public", "e-Stat 境界データの属性", CREDIT_ESTAT),
    ("data/public/gold/gold_municipality_pop2020", "public", "e-Stat 境界データの属性(国勢調査人口)の集計", CREDIT_ESTAT),
    ("data/public/silver/silver_area", "public", "市町の団体コード・名称(境界データのコードと照合済み)", ""),
    ("data/public/", "public", "国・気象庁のデータのみから作成", CREDIT_ESTAT + " / " + CREDIT_JMA),
    ("outputs/public/", "public", "国・気象庁のデータのみから作成した地図と系譜", CREDIT_ESTAT + " / " + CREDIT_JMA),
    ("ledger/revision_notes.csv", "public", "県の本文の再算定の注記の要約(数値列を除いた公開版。原文の転載ではない)", "出典: 長崎県「長崎県観光統計」(各年版)を要約"),
    ("ledger/comparability_flags.csv", "review", "県の注記から導いた比較不可フラグ(派生物)", "出典: 長崎県「長崎県観光統計」(各年版)の注記から作成"),
    ("ledger/validation_results.csv", "review", "県統計を含む検証結果(件数と合否。値は失敗時の例のみ)", ""),
    ("ledger/source_measurements.csv", "public", "取得物の件数・容量・行数", ""),
    ("ledger/terms_quotes_verified.csv", "public", "利用規約の引用(規約ページとの逐語照合済み)", ""),
    ("ledger/", "public", "台帳の説明", ""),
    ("manifest/output_hashes.csv", "public", "公開用の出力のパスとSHA256(非公開分は manifest/restricted/ に分離)", ""),
    ("manifest/fetch_runs.csv", "public", "取得の実行記録(時刻・User-Agent・件数)", ""),
    ("manifest/", "review", "取得ログ(URL・SHA256・日時)。県のURLとハッシュを含む(設計で置くと決めた範囲)", ""),
    ("config/", "public", "取得元URL・期待ハッシュ・期待行数・規約の引用文", ""),
    ("src/", "public", "コード", ""),
    ("tests/", "public", "テスト", ""),
    ("docs/", "public", "設計・説明", ""),
    ("publish/", "public", "この一覧", ""),
]
ROOT_FILES = {"README.md", "Makefile", "requirements.txt", ".gitignore", "LICENSE", "NOTICE"}
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


def classify(rel: str) -> tuple[str, str, str]:
    import re
    if re.fullmatch(r"docs/0[1-5]_.*\.md", rel):
        return "review", "設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない)", ""
    if rel in ROOT_FILES:
        return "public", "プロジェクトの説明・設定", ""
    for pre, cls, why, credit in RULES:
        if rel.startswith(pre):
            return cls, why, credit
    return "review", "未分類(確認が必要)", ""


def make_list() -> list[dict]:
    rows = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        rel = str(p.relative_to(ROOT))
        cls, why, credit = classify(rel)
        rows.append(dict(path=rel, klass=cls, bytes=p.stat().st_size, reason=why, credit=credit))
    # .pylibs と raw は数が多いので、ディレクトリ単位にまとめる
    folded: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        top = r["path"].split("/")[0] + "/"
        if top in (".pylibs/", "raw/", "warehouse/", "work/") :
            if top in seen:
                agg = next(x for x in folded if x["path"] == top)
                agg["bytes"] += r["bytes"]
                agg["n_files"] += 1
                continue
            seen.add(top)
            folded.append(dict(path=top, klass=r["klass"], bytes=r["bytes"], reason=r["reason"], credit="", n_files=1))
        else:
            r["n_files"] = 1
            folded.append(r)
    return folded


def write_list() -> list[dict]:
    rows = make_list()
    write_csv(ROOT / "publish" / "PUBLISH_LIST.csv", rows, ["path", "klass", "n_files", "bytes", "reason", "credit"])
    names = {"public": "公開用(出典を付けて公開してよい)", "review": "要確認(公開前に確認する)", "private": "非公開(GitHubに上げない)"}
    md = ["# 公開用・非公開用のファイル一覧", "",
          "GitHubに上げる前に、この一覧を確認する(このファイルは `python -m nagplat.cli publish-list` で再生成する)。", ""]
    for k in ("public", "review", "private"):
        md += [f"## {names[k]}", "", "| パス | ファイル数 | 容量(byte) | 理由 | 必要な表記 |", "|---|---|---|---|---|"]
        for r in rows:
            if r["klass"] == k:
                md.append(f"| `{r['path']}` | {r['n_files']} | {r['bytes']:,} | {r['reason']} | {r['credit']} |")
        md.append("")
    (ROOT / "publish" / "PUBLISH_LIST.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return rows
