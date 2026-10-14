# nagasaki_platform — 長崎データ基盤

**English summary.** A small, reproducible data pipeline for public data about Nagasaki Prefecture, Japan.
It fetches national statistics (e-Stat statistical GIS boundaries and the 2020 census population) and the
Japan Meteorological Agency's monthly observations, stores them in layered tables (bronze/silver/gold; DuckDB and Parquet),
validates them (hashes, row counts, completeness, accounting identities, consistency with the prefecture's revision notes),
and draws municipality-level maps. Every source is recorded with URL, timestamp and SHA256; terms of use are quoted
verbatim and checked against the fetched pages (see `NOTICE`). Prefecture statistics (tourism and migration surveys) are
**not included** because the prefecture's site restricts reproduction; only fetch scripts, URLs, hashes and a summary
ledger of revision notes are provided. Stage 1 is implemented. Stage 2 (a nationwide municipal panel for analysing and forecasting net migration, applied to Nagasaki's 21 municipalities) has the data acquisition, validation and four baseline forecasts implemented; machine-learning models are not built yet. Power BI is not used.
Code: MIT. Data: see `NOTICE`.

---

## 目的と、できること
長崎の公開データを、**自動で集め、検証し、地図にする**ための小さな基盤です。データサイエンスのポートフォリオと、長崎の事業者向けの分析の入口を兼ねています。

段1(実装済み)でできること:
- 国(e-Stat 統計GIS)と気象庁のデータを、**取得元URL・日時・SHA256を記録しながら**取得する
- 取得物を、層(bronze → silver → gold)に分けて DuckDB / Parquet に蓄積する
- 取得物の**ハッシュ・行数・年×市町の欠け・恒等式・県の再算定の注記との整合**を検証する(30項目)
- 市町の塗り分け地図とデータの系譜(どのソースから作ったか)を出力する
- 再実行で同じ結果になることをテストで確認する

段2(全国の市区町村パネルで転入超過率を分析し、長崎の21市町に当てはめる)は、**データ取得・検証・基準手法の評価まで実装済み**で、機械学習モデルは未実装です(設計: `docs/全国パネル_社会増減_設計.md`、結果: `docs/全国パネル_段2_結果.md`)。気象庁の時別値の大規模取得は、サーバー負荷を考えて見送りました(`docs/段2_月次予測_設計.md`)。

## 地図(公開してよい版)
令和2年国勢調査の人口(市町別、対数目盛)と、気象庁の観測点(▲、2025年の平均気温・年降水量)。国と気象庁のデータのみから作成しています。

![令和2年国勢調査の人口と気象庁の観測点](outputs/public/map_population_2020_weather_2025.png)

- 出典: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査)、気象庁ホームページ「過去の気象データ」を加工して作成
- 県の観光統計を使う地図(人口1人あたり観光客延べ数)も作れますが、県統計を含むため、このリポジトリには含めていません(下記)。

## 再現手順
Python 3.12 で確認しています(他の版は未検証)。

```bash
pip install -r requirements.txt     # 仮想環境を推奨
make fetch      # 原本の取得(約230件。同じホストへは1.5秒間隔。初回は約8分)
make all        # build(蓄積)→ validate(検証)→ map(地図)
make test       # テスト(再ビルドの同一性を含む。約2分)
```
その他: `make verify-raw`(原本のハッシュ確認)、`make publish-list`(公開用・非公開用の一覧)、
`python -m nagplat.cli privacy-scan`(個人情報のスキャン)、`python -m nagplat.cli qc-report`(気象の品質記号の集計)。

> 県の統計(観光統計・異動人口調査)の取得には、`make fetch` が県のサイトへアクセスします。
> 取得物は、`config/sources.csv` の期待SHA256と一致しない場合は保存しません。

## 取得 → 蓄積 → 検証 → 地図の流れ
```mermaid
flowchart LR
  A[config/sources.csv<br/>URL・期待SHA256] --> B[fetch<br/>1.5秒間隔・中立なUser-Agent]
  B --> C[raw/ 原本<br/>manifest/fetch_log.csv に URL・SHA256・日時]
  C --> D[bronze<br/>原本の構造のままParquet化]
  D --> E[silver<br/>市町コード・年・単位を揃える]
  E --> F[gold<br/>指標・記号の方針を適用]
  F --> G[validate<br/>30項目]
  G -->|FAILなら停止| H[map<br/>PNG + 系譜JSON]
  I[ledger/<br/>再算定の注記・比較不可フラグ] --> G
  I --> F
```

1. **取得**: URL・HTTP・容量・SHA256・取得日時を `manifest/fetch_log.csv` に追記。期待ハッシュがある原本は、不一致なら保存しない。取得済みで一致するものは再取得しない。
2. **蓄積**: bronze(原本の構造のまま)→ silver(団体コード・年・単位を揃える)→ gold(指標)。DuckDB(スレッド数1、並び順を指定)。
3. **検証**: ハッシュ、行数、年×市町の網羅、恒等式(観光客延べ数=日帰り+宿泊、人口増減=社会増減+自然増減 など)、県の注記との整合。FAILがあれば地図を作らない。
4. **地図**: 市町の塗り分け(PNG)と、データの系譜(JSON: ソース・ハッシュ・コードのハッシュ・フォントとライブラリの版)。
5. **テスト**: pytest 19件。再ビルドで、CSV・GeoJSON・PNG・系譜のハッシュが一致することを確認。

## 実測(2026-10-13 時点)
| 項目 | 値 |
|---|---|
| 取得 | 245件、全て HTTP 200、ハッシュ不一致 0 |
| 検証 | 30項目: PASS 28 / WARN 2 / FAIL 0 |
| テスト | 19件(`tests/`) |
| 気象庁の記号つきの値 | 90値(54か月)。準正常値 85、資料不足値 5(扱いは `docs/段2_月次予測_設計.md` B) |

取得物の容量・行数は `ledger/source_measurements.csv`、検証結果は `ledger/validation_results.csv`。

## データの出典とライセンス
詳細・原文の引用は **`NOTICE`**(規約ページとの逐語照合済み: `ledger/terms_quotes_verified.csv`)。

| データ | 提供元 | 条件の要点 | このリポジトリ |
|---|---|---|---|
| 境界データ・国勢調査人口(令和2年) | 総務省統計局 統計GIS(e-Stat) | 出典・加工の記載が必要。商用利用も可能。機能利用規約 第6条: コンテンツの条件は e-Stat 利用規約に準じる | 加工物のみ(`data/public`) |
| 月ごとの気象データ・観測点の位置 | 気象庁 | 出典・加工の記載が必要。公共データ利用規約(第1.0版)準拠、商用利用も可能 | 加工物のみ(`data/public`) |
| バス情報(GTFS。件数の実測のみ) | 長崎県営バス | CC BY 4.0(事業者のページの記載) | 含まない |
| 全国の市区町村パネル(転入者数・転出者数、国勢調査の人口、学校数など) | 統計センター SSDSE-市区町村(元: 総務省統計局 社会・人口統計体系) | 出典・加工の記載が必要。商用利用も可能(統計センターのサイトポリシーに準じる) | 加工物のみ(`data/public`。SSDSE-A の31/125項目を、版の値のまま) |
| 観光統計・異動人口調査 | 長崎県 | 県サイトの著作権の条項(下記) | **含まない** |

### 出典の表記(SSDSE。全国パネルの表・地図を使う場合)
> 独立行政法人 統計センター SSDSE-A-2018〜SSDSE-A-2026(各版。https://www.nstac.go.jp/use/literacy/SSDSE/)を加工して作成
> 元の出典: 総務省統計局「統計でみる都道府県・市区町村のすがた(社会・人口統計体系)」

**私の解釈(法的な助言ではありません)**: 国・気象庁・統計センターのデータは、出典と加工の記載をすれば、公開・商用で利用できると読んでいます。

## 含めていないデータ(長崎県の統計)とその理由
- 対象: 長崎県観光統計(市町別の観光客数など)、異動人口調査(年間集計)。取得元URLとSHA256は `config/sources.csv` と `manifest/fetch_log.csv` にあり、取得スクリプトで再取得できます。
- 理由: 県の公式サイト「このサイトについて」の著作権の項に、次の記載があります(原文)。
  - 「当県サイトに掲載されている文字、写真、イラストなどの個々の情報に関する著作権は、原則として長崎県に帰属します。」
  - 「『私的使用のための複製』や『引用』など著作権法上認められた場合を除き、無断で転載、複製、改変、放送、送信、翻訳、販売、貸与などの利用をすることはできません。」
- 統計の数値の再掲載が許されるかは、私には判断できません。**県への確認が済むまで、原本・蓄積データ・加工値の地図は `.gitignore` で除外**しています。
- 含めているもの: 取得スクリプト、URL、SHA256、再算定の注記の**要約**(`ledger/revision_notes.csv`。要約であり原文の転載ではない)、比較不可フラグ、検証結果。

## 構成
```
config/      取得元URL・期待SHA256・期待行数・規約の引用文
src/nagplat/ fetch / parse_* / build / validate / mapmaker / ledger / qc_report / notice / privacy_scan / publish_list
tests/       pytest
ledger/      台帳: 再算定の注記の要約(数値列を除く)、比較不可フラグ、検証結果、規約の引用、実測、気象の品質記号
manifest/    取得ログ(URL・SHA256・日時)、取得の実行記録、出力のハッシュ
data/public/ 国・気象庁のデータのみから作った蓄積データ(出典を付けて公開可)
outputs/public/ 地図とデータの系譜
docs/        設計文書(01〜05の設計時点の文書、段2、全国パネル、再現手順)
publish/     公開用・非公開用の一覧、個人情報スキャン、確認用の資料
```
(`raw/`・`data/restricted/`・`outputs/restricted/`・`ledger/restricted/`・`manifest/restricted/`・`warehouse/`・`work/` はリポジトリに含めません。)

## 段2(全国パネル)の結果の要約 — 基準手法のみ。機械学習モデルは未実装
詳細・表は `docs/全国パネル_段2_結果.md`。**盛らずに読むこと**:
- **主の集計(事前に固定)では、前年値(B0)に勝つ手法はなかった**。直近3年の平均(B1)は −1.3%(全国)。
- 避難指示区域の**候補**12町村を除く感度分析では、B1が +10.1% で勝つ。これは、事前に固定した評価計画の外の**補助的な分析**で、結果と外れ値を見た後に読んだもの。確認済みの除外は**双葉町のみ**(他は候補。名称は私の知識で、国・県の一覧との照合は未確認)。
- 長崎21市町のB1の改善 +12.4% は、95%区間が **+0.6%〜+21.1%**(下端がほぼ0)。21市町・5年では、**勝ったとは言い切れない**。
- 評価は 2020〜2024年の5年のみ。分母は国勢調査の日本人人口(2015年・2020年の2時点)で、年ごとの実際の人口とずれる(下記)。

## 注意・限界
- **分母の限界(全国パネル)**: 転入超過率の分母は、国勢調査の日本人人口(2016〜2019年は2015年、2020〜2024年は2020年)で、年ごとの実際の人口ではない。2015→2020年の日本人人口の変化率は、全国の中央値が −5.9%(四分位 −8.8%〜−2.6%)、長崎21市町は −11.4%〜+2.0%(中央値 −7.3%)。分母が古いほど、率の水準がずれ、2019→2020年の切り替えで率が不連続になる(感度分析の集合で、2019年の率の平均の絶対差は 0.55‰)。
- 観測点(官署6地点)が市町内にない市町があります。地図は観測点を点で示し、市町の値には混ぜていません。
- 気象庁の準正常値(資料数が基準の80%以上)は使い、資料不足値を含む変数の年の値は空欄にしています。
- 県の観光客数は、県が算定方法を市町ごと・時期ごとに見直しているため、年をまたぐ比較には注意が必要です(`ledger/comparability_flags.csv`)。
- 2015年版の県の本文PDFは、文字を取り出せず、注記の原本照合が**未検証**です。
- Power BI での表示は未検証です。

## AI支援について
このプロジェクトは、Anthropic の Claude Code の支援を使って開発しています(コード・文書の作成と、調査の補助)。設計の判断、データの確認、検証の責任は筆者にあります。
*This project was developed with the assistance of Claude Code (Anthropic). The author is responsible for the design decisions, the data checks and the validation.*

## ライセンス
- コード: MIT License(`LICENSE`)
- データ: `NOTICE` を参照

## 段3: 予測モデル(Ridge・勾配ブースティング)
- 結果と設計: `docs/全国パネル_段3_結果.md`。リークの一覧: `ledger/panel_leakage_register.csv`。実行: `make panel-model`。
- 主の集計では、モデルは前年値・直近3年の平均に**勝てなかった**(改善率の区間が0を含む)。長崎の21市町でも、直近3年の平均に勝てなかった。避難指示区域の候補を除いた感度分析(別枠・事後の補助的な分析)では、小さな改善がある。重要度は相関であって、因果ではない。
- 実装の注意: Ridge と勾配ブースティングは、scikit-learn が環境にないため numpy で自前実装した。他のライブラリの実装との一致は**未検証**(小さな例でのテストのみ)。

## 段4: 前向き予測(2026年の転入超過率)
- 設計(事前登録): `docs/段4_前向き予測_設計.md`。実行: `make panel-forward`。2025年までの情報で、2026年を予測し、結果の公表後に答え合わせをする(公表は2027年4月ごろの見込み。未確認)。
- **注意: 段3で、モデルは前年値に勝てなかった(主の集計・2020〜2024年。改善率の95%区間が0をまたぐ)。この予測は参考値で、精度は2027年の答え合わせまで未検証。**
- 予測の表: `outputs/public/forecast_2026_predictions.csv`(説明: `outputs/public/forecast_2026_README.md`)。固定の記録: `ledger/forecast_2026_manifest.csv`。勝敗の判定の基準: `docs/段4_前向き予測_設計_追記1.md`。答え合わせは**未実施**で、精度は**未検証**。2025年のバックテストは参考値で、判定に使わない。
- 出典: 総務省統計局「住民基本台帳人口移動報告」(2025年結果)を加工して作成。

## 大村市の調査(1市の事例。「なぜ」への答えは出ていません)
- 設計(結果を見る前に固定): `docs/大村市_なぜ_設計.md`。結果: `docs/大村市_なぜ_結果.md`。実行: `python -m nagplat.cli omura`。
- 2016〜2024年の9年とも、大村市の転入超過率は、県内の市と、全国の同規模の市の中央値より大きい(記述)。**原因は特定できていません**。子育て・世帯数などが値と整合しても、人が転入した結果でもあるため、原因とは言えません。住宅・交通・所得・転入元は、指標が無く、**判断できません**。
- **対象の市を、結果(目立つ市)を見てから選んでいます**。1市の事例で、他の市に一般化できません。
- タグ `omura-why-code-v1` が指すコードは、**バグのある版**です(国勢調査の年の取り違え)。結果は、その後の修正後のコードによります(経緯は結果の文書 §5)。

