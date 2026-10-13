"""NOTICE を生成する。利用条件の引用は、取得した規約ページと逐語照合済みの ledger/terms_quotes_verified.csv から取る。"""
from __future__ import annotations

from .common import ROOT, read_csv

SECTIONS = [
    dict(title="1. 境界データ・国勢調査の人口(統計GIS)", terms=["T_ESTAT", "T_ESTAT_GIS"],
         provider="総務省統計局 政府統計の総合窓口(e-Stat)統計地理情報システム",
         url="https://www.e-stat.go.jp/gis",
         data="令和2年国勢調査 小地域の境界データ(長崎県、世界測地系・緯度経度)。市町に集約し、描画用に簡略化したものと、小地域の人口の市町別合計を data/public に含む。",
         credit="出典: 政府統計の総合窓口(e-Stat)(https://www.e-stat.go.jp/) 統計GIS 境界データ(令和2年国勢調査)を加工して作成",
         included="加工物のみ(原本のZIPは含まない)"),
    dict(title="2. 気象データ(気象庁)", terms=["T_JMA", "T_PDL1", "T_JMA_HELP"],
         provider="気象庁",
         url="https://www.data.jma.go.jp/stats/etrn/",
         data="過去の気象データ(官署6地点、月ごとの値、2015〜2025年)と、アメダス地点表の位置情報。月別の表と年の集計を data/public に含む。",
         credit="出典: 気象庁ホームページ「過去の気象データ」(https://www.data.jma.go.jp/stats/etrn/)を加工して作成",
         included="加工物のみ(取得したHTMLの原本は含まない)"),
    dict(title="3. バス情報(長崎県営バス GTFS)", terms=["T_KENEIBUS"],
         provider="長崎県営バス(長崎県交通局)",
         url="https://www.keneibus.jp/local/OpenData",
         data="2026年10月1日版のGTFSの件数(停留所・便・時刻)の実測にのみ使用(docs/段2_月次予測_設計.md)。データそのものは含まない。",
         credit="出典: 長崎県営バス「公開データ(GTFS準拠)」(https://www.keneibus.jp/local/OpenData)、CC BY 4.0",
         included="含まない(件数の実測値のみを文書に記載)"),
    dict(title="4. 長崎県の統計(観光統計・異動人口調査)— 含めていない", terms=["T_PREF_SITE"],
         provider="長崎県",
         url="https://www.pref.nagasaki.jp/pages/site_info.html",
         data="長崎県観光統計(集約表・本文)、異動人口調査(年間集計)。取得スクリプト、取得元URL、SHA256、再算定の注記の要約のみを含む。",
         credit="(データを含めないため該当なし。要約の出典: 長崎県「長崎県観光統計」(各年版))",
         included="含まない。県サイトの著作権の条項(下記)により、県への確認が済むまで公開しない"),
]


def build() -> str:
    q = read_csv(ROOT / "ledger" / "terms_quotes_verified.csv")
    out = ["NOTICE", "======", "",
           "This project's source code is licensed under the MIT License (see LICENSE; draft).",
           "The data handled by this project come from the providers below. Attribution and conditions of use follow.",
           "The quoted conditions were checked verbatim against the pages fetched on the dates recorded in",
           "ledger/terms_quotes_verified.csv. The interpretation in README.md is not legal advice.", ""]
    for s in SECTIONS:
        out += [s["title"], "-" * len(s["title"]), f"提供元: {s['provider']}", f"URL: {s['url']}",
                f"利用しているデータ: {s['data']}", f"本リポジトリへの収録: {s['included']}",
                f"出典表記: {s['credit']}", "利用条件(原文の引用):"]
        for r in q:
            if r["terms_id"] in s["terms"] and r["verbatim_in_page"] == "Y":
                out.append(f"  - 「{r['quote']}」 [{r['terms_id']} / {r['topic']} / {r['page_url']} / 取得 {r['fetched_at_utc']}]")
        out.append("")
    out += ["Not included in this repository / 本リポジトリに含まれないもの",
            "-------------------------------------------------------------",
            "長崎県の統計の原本・蓄積データ・加工値の地図(data/restricted, outputs/restricted)は、.gitignore で除外している。", ""]
    return "\n".join(out)


def write() -> None:
    (ROOT / "NOTICE").write_text(build(), encoding="utf-8")
