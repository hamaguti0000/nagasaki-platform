# 外部アクセスのルールの確認

規則: 取得は中立なUser-Agentのみ。個人情報(メールアドレス・氏名・ユーザー名・パス)を外部に送らない。必要最小限の取得のみ。 <!-- privacy-scan: ignore -->

## コードの確認(`src/nagplat/fetch.py`、テスト `test_user_agent_is_neutral_and_network_code_is_confined`)
| 項目 | 結果 |
|---|---|
| User-Agent | 固定文字列 `nagasaki-platform/0.1 (research; non-commercial)`。実行時に、`@`・`/home/`・`/Users/`・OSのユーザー名を含む場合は異常終了する | <!-- privacy-scan: ignore -->
| 送信するヘッダー | `User-Agent`・`Accept`・`Accept-Encoding` のみ(`session.headers` を初期化。実行記録 `manifest/fetch_runs.csv` に記録) |
| 認証情報・Cookie | 送らない。`trust_env=False` で `~/.netrc`・プロキシの環境変数を使わない(プロキシが必要な環境では、このコードの変更が要る) |
| ネットワークを使うコード | `fetch.py` のみ(テストで、`requests`・`urllib` 等を import するファイルが `fetch.py` だけであることを確認) |
| URLのクエリ | 公開ページの固定パラメータのみ(観測点番号・年・表示の種類・統計GISの調査コード)。個人情報を含むURLは0件(`manifest/fetch_log.csv` の全245件を確認) |
| 取得ホスト | `www.data.jma.go.jp`・`www.jma.go.jp`・`www.pref.nagasaki.jp`・`www.e-stat.go.jp`・`www.keneibus.jp`・`www.digital.go.jp`・`www.stat.go.jp`・`www.nstac.go.jp`(後ろの2つは、全国パネルの設計の調査。参考ページ11件、ZIP・Excelは各1件) |
| 取得間隔 | 同一ホストに1.5秒以上 |
| 取得の重複 | 取得済みで期待ハッシュまたは記録済みハッシュと一致するものは、再取得しない |

## 取得ログの確認
- `manifest/fetch_log.csv`: 245件、全て HTTP 200、不一致 0。時刻・URL・容量・SHA256のみを記録(リクエストのヘッダーは記録しない)。
- `manifest/fetch_runs.csv`: 実行ごとの User-Agent・送信ヘッダー名・件数。**この記録は、準備作業の中で追加したもの**。それ以前の初回の大規模な取得(227件)の実行記録はないが、当時のコードの User-Agent も同じ固定文字列(中立)だった。ただし、当時のコードのファイルは保存していないため、**コードの履歴としての証明はできない**(取得ログにはヘッダーを記録していない)。

## 実装前の調査での取得(訂正済みの事実)
段1の実装前の調査(確認用の `curl`)で、**User-Agent にメールアドレスを入れて**、次のホストにアクセスした(約10件)。依頼されていない送信で、誤りだった。
- `www.data.jma.go.jp`: 7件(robots.txt、都道府県の観測点一覧、月ごとの値の表示4種+1)
- `www.e-stat.go.jp`: 3件(利用規約、統計GISの機能利用規約、境界データの先頭100バイトの確認)
これらは取得ログ(`fetch_log.csv`)に載っていない(実装の外の確認用)。相手のサーバーのログからは消せない。
実装以降は、上記の固定の User-Agent のみを使っている。メールアドレスは、リポジトリのコード・設定・出力に含まれていない(個人情報のスキャンで0件)。
