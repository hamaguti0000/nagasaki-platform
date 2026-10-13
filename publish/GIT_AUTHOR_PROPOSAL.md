# git の作者情報: 公開用の案(実際の値は、あなたが決める)

## 現状(確認済み。2026-10-13 更新)
- `nagasaki_platform` で `git init -b main` を実行済み(ローカルのみ。リモートなし。**コミットはしていない**)。
- ローカル設定は仮の値のみ: `user.name=<PUBLIC_NAME>`、`user.email=<GITHUB_ID>+<GITHUB_USERNAME>@users.noreply.github.com`、`user.useConfigOnly=true`。実際の値は、あなたが決めてから設定する。
- コミット履歴は0件。履歴に個人情報が入ることはない。
- git の設定(global/system): `user.name`・`user.email` は**未設定**。設定されているのは `credential.helper`(`store`)のみ。
- 注意: `credential.helper=store` は、認証情報を**平文でホームディレクトリのファイルに保存**する。リポジトリの外だが、公開用の環境では、OSの資格情報マネージャーなどへの変更を検討する(私は変更していない)。

## 案
| 項目 | 案 | 説明 |
|---|---|---|
| 作者名 `user.name` | `<PUBLIC_NAME>` | 公開してよい表示名(ハンドル名でも可)。実名にするかは、あなたが決める |
| メール `user.email` | `<GITHUB_ID>+<GITHUB_USERNAME>@users.noreply.github.com` | GitHubのnoreply形式。GitHubの設定(Emails)で、この文字列を確認できる(確認は私にはできない) |
| コミッター | 作者と同じ | `GIT_COMMITTER_NAME/EMAIL` も同じ値にする |

## 手順案(私は実行していない)
```bash
cd nagasaki_platform
git init -b main
git config --local user.name  "<PUBLIC_NAME>"
git config --local user.email "<GITHUB_ID>+<GITHUB_USERNAME>@users.noreply.github.com"
git config --local user.useConfigOnly true     # 未設定のとき、ホスト名から名前・メールを推測してコミットしない
git add -A && git status                        # 公開対象だけが追加されていること(下記の確認)
git commit -m "Initial commit"
git log --format='%an <%ae> | %cn <%ce>'        # 作者・コミッターが仮の値であることを確認
```
- GitHub側の設定: 「Keep my email addresses private」と「Block command line pushes that expose my email」を有効にする(GitHubの設定項目。画面での確認は私にはできない)。
- 公開前の確認: `python -m nagplat.cli privacy-scan`(0件であること)、`make test`、`git ls-files` が `publish/PUBLISH_LIST.md` の公開用+要確認(修正後)と一致すること。

## 確認済み(2026-10-13): `.gitignore` の効果
別の作業用 git ディレクトリで `git add -n -A` を実行して確認した(プロジェクト内には `.git` を作っていない)。
追加される予定のファイルは64件。`raw/`・`warehouse/`・`work/`・`.pylibs/`・`data/restricted/`・`outputs/restricted/` のファイルは、追加対象に**含まれない**。
