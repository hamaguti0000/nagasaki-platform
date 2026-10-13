# privateリポジトリでの確認手順(あなたがやること)— 1ページ

目的: GitHubの**private**リポジトリに上げ、公開前に問題がないことを確かめる。公開(publicへの切り替え)は、全項目の確認後。
私は push しない。以下は、あなたが実行する手順。

## 0. 事前に決める(私は決めない)
- [ ] 作者名 `<PUBLIC_NAME>`(公開してよい表示名)、メール `<GITHUB_ID>+<GITHUB_USERNAME>@users.noreply.github.com`(GitHubの設定 > Emails で、自分の noreply アドレスを確認)
- [ ] ライセンス(`LICENSE` は MIT の案。著作権者名 `<COPYRIGHT HOLDER>` と、ライセンス自体の確定)
- [ ] 県の統計(観光統計・異動人口調査)の扱い。県への確認が済むまでは、現在の除外のままにする
- [ ] 要確認の残り8件(`publish/REVIEW_10_FILES.md`)の公開可否

> リモートの追加・push のコマンド(ユーザー名を含む)は、リポジトリに含めない `local/REMOTE_COMMANDS.md` にある。

## 1. ローカルで設定してからコミット(約5分)
```bash
cd nagasaki_platform
git config --local user.name  "<決めた表示名>"
git config --local user.email "<決めたnoreplyアドレス>"
PYTHONPATH=src NAGPLAT_SCAN_EXTRA="<自分のメール,姓,名(漢字・かな・英字)>" python -m nagplat.cli privacy-scan   # 0件であること
git add -A && git status                 # raw/・data/restricted/・outputs/restricted/・ledger/restricted/・manifest/restricted/ が出ないこと
git add -n -A | wc -l                    # 追加予定の件数が、publish/PUBLISH_LIST.md の公開用+要確認と一致すること
git commit -m "Initial commit"
git log --format='%an <%ae> | %cn <%ce>' # 作者・コミッターが、決めた値であること
```

## 2. GitHub側(画面での確認。私は確認できない)
- [ ] Settings > Emails: 「Keep my email addresses private」と「Block command line pushes that expose my email」が有効
- [ ] **private** でリポジトリを作成(README等の自動追加はしない)
- [ ] `git remote add origin ...` → `git push -u origin main`(初回のpushはこの1回のみ)

## 3. privateリポジトリでの確認(約30分)
| # | 確認 | 方法 | 合格の基準 |
|---|---|---|---|
| 1 | ファイル一覧 | GitHubのファイル一覧と `publish/PUBLISH_LIST.md` を比較 | 一覧にない・非公開のファイルがない |
| 2 | 個人情報 | リポジトリ内検索で、自分のメール・姓・名・ユーザー名・`/home/` を検索 | 0件 | <!-- privacy-scan: ignore -->
| 3 | コミットの作者 | 最初のコミットの作者表示 | 決めた名前とnoreplyアドレス |
| 4 | README | 表示を確認(mermaidの図、地図の画像、相対リンク) | 図と画像が表示される。リンク切れなし |
| 5 | 県統計 | `data/`・`outputs/`・`ledger/` に、県の統計値(観光客数・人口の値)がないこと | 公開版の `revision_notes.csv` に数値列がない。`data/public` に県統計の列がない |
| 6 | ライセンス表示 | `LICENSE`・`NOTICE` が表示される | 表示される。NOTICEの出典が各データと対応 |
| 7 | シークレット | Settings > Code security で secret scanning を有効にし、結果を確認 | 検出0件(`.env`・トークンがない) |
| 8 | 容量 | リポジトリの容量 | 想定内(Parquet・GeoJSONを含め数MB。未検証) |
| 9 | 再現 | 別の場所に `git clone` し、`pip install -r requirements.txt`、`make fetch`(約230件、約8分、1回のみ)、`make all`、`make test` | テスト全て通過。出力のハッシュが `manifest/output_hashes.csv` と一致 |
| 10 | 外部アクセス | `manifest/fetch_runs.csv` の User-Agent を確認 | 中立な固定文字列のみ |

## 4. 問題があった場合
- private のため、履歴の書き換え(`git commit --amend`、新しいリポジトリの作り直し)ができる。**publicにする前なら、やり直せる**。
- 一度でも public にした履歴・メールは、取り消せない前提で扱う。

## 5. publicへの切り替えの条件
- 上の3の10項目が全て合格。0の4項目を決めた。
- 切り替え後に、第三者の権利・県の確認が必要になった場合は、すぐに private に戻せる(ただし、その間に取得された内容は取り消せない)。
