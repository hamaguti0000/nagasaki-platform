# 公開用・非公開用のファイル一覧

GitHubに上げる前に、この一覧を確認する(このファイルは `python -m nagplat.cli publish-list` で再生成する)。

## 公開用(出典を付けて公開してよい)

| パス | ファイル数 | 容量(byte) | 理由 | 必要な表記 |
|---|---|---|---|---|
| `.gitignore` | 1 | 609 | プロジェクトの説明・設定 |  |
| `LICENSE` | 1 | 1,292 | プロジェクトの説明・設定 |  |
| `Makefile` | 1 | 856 | プロジェクトの説明・設定 |  |
| `NOTICE` | 1 | 13,596 | プロジェクトの説明・設定 |  |
| `README.md` | 1 | 10,680 | プロジェクトの説明・設定 |  |
| `config/expected_counts.csv` | 1 | 811 | 取得元URL・期待ハッシュ・期待行数・規約の引用文 |  |
| `config/panel_source_notes.csv` | 1 | 871 | 取得元URL・期待ハッシュ・期待行数・規約の引用文 |  |
| `config/privacy_allow.csv` | 1 | 441 | 取得元URL・期待ハッシュ・期待行数・規約の引用文 |  |
| `config/sources.csv` | 1 | 12,881 | 取得元URL・期待ハッシュ・期待行数・規約の引用文 |  |
| `config/terms_quotes.csv` | 1 | 7,489 | 取得元URL・期待ハッシュ・期待行数・規約の引用文 |  |
| `data/public/bronze/bronze_boundary_small_area.csv` | 1 | 309,949 | e-Stat 境界データの属性 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 |
| `data/public/bronze/bronze_boundary_small_area.parquet` | 1 | 84,458 | e-Stat 境界データの属性 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 |
| `data/public/bronze/bronze_jma_monthly.csv` | 1 | 559,676 | 気象庁のデータの整形 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/bronze/bronze_jma_monthly.parquet` | 1 | 48,286 | 気象庁のデータの整形 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_municipality_pop2020.csv` | 1 | 794 | e-Stat 境界データの属性(国勢調査人口)の集計 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 |
| `data/public/gold/gold_municipality_pop2020.parquet` | 1 | 1,149 | e-Stat 境界データの属性(国勢調査人口)の集計 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 |
| `data/public/gold/gold_panel_forecast_table.csv` | 1 | 1,772,462 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_panel_forecast_table.parquet` | 1 | 411,277 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_panel_municipality_year.csv` | 1 | 5,917,783 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_panel_municipality_year.parquet` | 1 | 1,059,307 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_station_year.csv` | 1 | 4,318 | 気象庁のデータの集計 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/gold_station_year.parquet` | 1 | 3,018 | 気象庁のデータの集計 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/gold/municipality_boundary.geojson` | 1 | 2,718,978 | e-Stat 境界データの加工物(市町に集約・簡略化) | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 |
| `data/public/silver/silver_area.csv` | 1 | 787 | 市町の団体コード・名称(境界データのコードと照合済み) |  |
| `data/public/silver/silver_area.parquet` | 1 | 992 | 市町の団体コード・名称(境界データのコードと照合済み) |  |
| `data/public/silver/silver_panel_area.csv` | 1 | 80,125 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_panel_area.parquet` | 1 | 22,559 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_ssdse_area_map.csv` | 1 | 111,555 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_ssdse_area_map.parquet` | 1 | 37,186 | 国・気象庁のデータのみから作成 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_station.csv` | 1 | 481 | 気象庁アメダス地点表から作成した観測点の位置 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_station.parquet` | 1 | 1,070 | 気象庁アメダス地点表から作成した観測点の位置 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_weather_month.csv` | 1 | 60,696 | 気象庁のデータの整形 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `data/public/silver/silver_weather_month.parquet` | 1 | 16,573 | 気象庁のデータの整形 | 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `docs/全国パネル_段2_結果.md` | 1 | 10,729 | 設計・説明 |  |
| `docs/全国パネル_社会増減_設計.md` | 1 | 21,183 | 設計・説明 |  |
| `docs/再現手順_自分で理解するために.md` | 1 | 4,951 | 設計・説明 |  |
| `docs/段2_月次予測_設計.md` | 1 | 17,686 | 設計・説明 |  |
| `ledger/README.md` | 1 | 3,388 | 台帳の説明 |  |
| `ledger/panel_code_changes.csv` | 1 | 306 | 台帳の説明 |  |
| `ledger/panel_items.csv` | 1 | 7,331 | 台帳の説明 |  |
| `ledger/revision_notes.csv` | 1 | 13,315 | 県の本文の再算定の注記の要約(数値列を除いた公開版。原文の転載ではない) | 出典: 長崎県「長崎県観光統計」(各年版)を要約 |
| `ledger/source_measurements.csv` | 1 | 862 | 取得物の件数・容量・行数 |  |
| `ledger/terms_quotes_verified.csv` | 1 | 12,999 | 利用規約の引用(規約ページとの逐語照合済み) |  |
| `ledger/weather_qc_flags.csv` | 1 | 13,953 | 台帳の説明 |  |
| `ledger/weather_qc_impact.csv` | 1 | 2,055 | 台帳の説明 |  |
| `manifest/fetch_runs.csv` | 1 | 1,228 | 取得の実行記録(時刻・User-Agent・件数) |  |
| `manifest/output_hashes.csv` | 1 | 1,397 | 公開用の出力のパスとSHA256(非公開分は manifest/restricted/ に分離) |  |
| `outputs/public/map_net_migration_rate_2024.lineage.json` | 1 | 3,165 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/map_net_migration_rate_2024.png` | 1 | 254,564 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/map_population_2020_weather_2025.lineage.json` | 1 | 9,802 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/map_population_2020_weather_2025.png` | 1 | 270,190 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_by_prefecture.csv` | 1 | 4,147 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_by_year.csv` | 1 | 3,189 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_nagasaki.csv` | 1 | 797 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_nagasaki_by_municipality.csv` | 1 | 5,005 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_nagasaki_by_year.csv` | 1 | 2,743 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `outputs/public/panel_baseline_overall.csv` | 1 | 1,252 | 国・気象庁のデータのみから作成した地図と系譜 | 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)を加工して作成 / 出典: 気象庁ホームページ「過去の気象データ」を加工して作成 |
| `publish/EXTERNAL_ACCESS_CHECK.md` | 1 | 3,398 | この一覧 |  |
| `publish/GIT_AUTHOR_PROPOSAL.md` | 1 | 2,924 | この一覧 |  |
| `publish/PRIVACY_SCAN.md` | 1 | 426 | この一覧 |  |
| `publish/PRIVATE_REPO_CHECKLIST.md` | 1 | 4,392 | この一覧 |  |
| `publish/PUBLISH_LIST.csv` | 1 | 16,409 | この一覧 |  |
| `publish/PUBLISH_LIST.md` | 1 | 17,851 | この一覧 |  |
| `publish/REVIEW_10_FILES.md` | 1 | 7,137 | この一覧 |  |
| `requirements.txt` | 1 | 222 | プロジェクトの説明・設定 |  |
| `src/nagplat/__init__.py` | 1 | 0 | コード |  |
| `src/nagplat/build.py` | 1 | 14,937 | コード |  |
| `src/nagplat/cli.py` | 1 | 2,002 | コード |  |
| `src/nagplat/common.py` | 1 | 2,698 | コード |  |
| `src/nagplat/fetch.py` | 1 | 6,978 | コード |  |
| `src/nagplat/ledger.py` | 1 | 4,842 | コード |  |
| `src/nagplat/mapmaker.py` | 1 | 13,381 | コード |  |
| `src/nagplat/notice.py` | 1 | 5,514 | コード |  |
| `src/nagplat/panel.py` | 1 | 13,838 | コード |  |
| `src/nagplat/panel_eval.py` | 1 | 6,967 | コード |  |
| `src/nagplat/panel_report.py` | 1 | 5,007 | コード |  |
| `src/nagplat/parse_boundary.py` | 1 | 2,309 | コード |  |
| `src/nagplat/parse_jinko.py` | 1 | 3,322 | コード |  |
| `src/nagplat/parse_jma.py` | 1 | 2,005 | コード |  |
| `src/nagplat/parse_kanko.py` | 1 | 2,175 | コード |  |
| `src/nagplat/privacy_scan.py` | 1 | 7,856 | コード |  |
| `src/nagplat/publish_list.py` | 1 | 7,378 | コード |  |
| `src/nagplat/qc_report.py` | 1 | 3,651 | コード |  |
| `src/nagplat/validate.py` | 1 | 21,386 | コード |  |
| `tests/conftest.py` | 1 | 196 | テスト |  |
| `tests/test_pipeline.py` | 1 | 11,886 | テスト |  |

## 要確認(公開前に確認する)

| パス | ファイル数 | 容量(byte) | 理由 | 必要な表記 |
|---|---|---|---|---|
| `docs/01_データソース台帳.md` | 1 | 19,644 | 設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない) |  |
| `docs/02_アーキテクチャ案.md` | 1 | 7,985 | 設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない) |  |
| `docs/03_MVP提案.md` | 1 | 6,759 | 設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない) |  |
| `docs/04_予測・機械学習の設計.md` | 1 | 6,559 | 設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない) |  |
| `docs/05_リスクと未確認.md` | 1 | 8,067 | 設計時点の文書。県サイトの条項の短い引用・県統計の件数を含む(県の統計値は含まない) |  |
| `ledger/comparability_flags.csv` | 1 | 4,208 | 県の注記から導いた比較不可フラグ(派生物) | 出典: 長崎県「長崎県観光統計」(各年版)の注記から作成 |
| `ledger/validation_results.csv` | 1 | 5,403 | 県統計を含む検証結果(件数と合否。値は失敗時の例のみ) |  |
| `manifest/fetch_log.csv` | 1 | 69,763 | 取得ログ(URL・SHA256・日時)。県のURLとハッシュを含む(設計で置くと決めた範囲) |  |

## 非公開(GitHubに上げない)

| パス | ファイル数 | 容量(byte) | 理由 | 必要な表記 |
|---|---|---|---|---|
| `.pylibs/` | 5425 | 417,891,343 | ローカルのライブラリ置き場 |  |
| `data/restricted/bronze/bronze_jinko_nenkan.csv` | 1 | 65,264 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/bronze/bronze_jinko_nenkan.parquet` | 1 | 18,606 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/bronze/bronze_kanko_aggregate.csv` | 1 | 82,465 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/bronze/bronze_kanko_aggregate.parquet` | 1 | 15,636 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/gold/gold_municipality_year.csv` | 1 | 19,230 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/gold/gold_municipality_year.parquet` | 1 | 7,532 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/silver/silver_population_year.csv` | 1 | 48,879 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/silver/silver_population_year.parquet` | 1 | 14,143 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/silver/silver_tourism_year.csv` | 1 | 60,388 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `data/restricted/silver/silver_tourism_year.parquet` | 1 | 12,495 | 県の統計由来の蓄積データ。県への確認が済むまで公開しない |  |
| `ledger/restricted/revision_notes_with_changes.csv` | 1 | 13,826 | 県統計から導いた数値列を含む台帳の完全版(検証V51用) |  |
| `local/REMOTE_COMMANDS.md` | 1 | 3,158 | 個人の作業メモ(リモートの設定コマンドなど。ユーザー名を含む) |  |
| `local/説明メモ.md` | 1 | 9,331 | 個人の作業メモ(リモートの設定コマンドなど。ユーザー名を含む) |  |
| `manifest/restricted/output_hashes_restricted.csv` | 1 | 615 | 非公開ファイルのパスとハッシュ |  |
| `outputs/restricted/map_tourists_per_capita_2025.lineage.json` | 1 | 10,614 | 県の統計の加工値を含む地図。県への確認が済むまで公開しない |  |
| `outputs/restricted/map_tourists_per_capita_2025.png` | 1 | 278,108 | 県の統計の加工値を含む地図。県への確認が済むまで公開しない |  |
| `raw/` | 259 | 51,735,143 | 取得した原本(県の統計・本文PDFを含む)。取得スクリプトと manifest/fetch_log.csv(URL・SHA256)で再現する |  |
| `warehouse/` | 1 | 28,848,128 | 作業用のDuckDBファイル(再生成できる。県統計由来を含む) |  |
| `work/` | 12 | 161,678,799 | 作業用(PDFのテキスト抽出など。県の本文PDF由来) |  |

