"""取得: 必要な原本だけを取得し、URL・HTTP・サイズ・SHA256・取得日時を manifest/fetch_log.csv に記録する。

- 既にローカルにあり、期待ハッシュ(または記録済みハッシュ)と一致するファイルは取得しない(再実行で外部アクセスしない)。
- 期待ハッシュ(config/sources.csv)があり、取得物が一致しない場合は保存せず、不一致として記録して異常終了する。
- 同じホストへのアクセスは間隔を空ける。
"""
from __future__ import annotations

import csv
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .common import (JMA_VIEWS, ROOT, STATIONS, TOURISM_YEARS, YEARS, jma_dest, jma_url,
                     read_csv, sha256_bytes, sha256_file)

UA = "nagasaki-platform/0.1 (research; non-commercial)"
# 外部に送る情報の規則: User-Agent は中立な固定文字列のみ。メールアドレス・氏名・パス・ユーザー名を含めない。  # privacy-scan: ignore
# Cookie・認証情報・~/.netrc・環境のプロキシ設定も送らない(trust_env=False)。
_FORBIDDEN_IN_UA = re.compile(r"@|/home/|/Users/|[A-Za-z]:\\")  # privacy-scan: ignore


def _check_ua(ua: str) -> None:
    import getpass
    if _FORBIDDEN_IN_UA.search(ua) or getpass.getuser().lower() in ua.lower():
        raise SystemExit("User-Agent に個人情報の可能性がある文字列が含まれています")


LOG = ROOT / "manifest" / "fetch_log.csv"
RUN_LOG = ROOT / "manifest" / "fetch_runs.csv"
RUN_FIELDS = ["run_utc", "user_agent", "request_headers_sent", "delay_sec", "n_fetched", "n_skipped", "n_problems"]
LOG_FIELDS = ["fetched_at_utc", "source_id", "url", "dest", "http", "bytes", "sha256", "expected_sha256", "result"]
DELAY_SEC = 1.5


def all_sources() -> list[dict]:
    rows = read_csv(ROOT / "config" / "sources.csv")
    for block, _name, _amd in STATIONS:
        for y in YEARS:
            for v in JMA_VIEWS:
                rows.append(dict(
                    source_id=f"jma_{block}_{y}_{v}", group="weather", url=jma_url(block, y, v),
                    dest=jma_dest(block, y, v), expected_sha256="", license_class="jma",
                    terms_id="T_JMA", note="気象庁 月ごとの値(官署)"))
    return rows


def _last_logged_hashes() -> dict[str, str]:
    out: dict[str, str] = {}
    if LOG.exists():
        for r in read_csv(LOG):
            if r["result"] in ("fetched", "pinned"):
                out[r["source_id"]] = r["sha256"]
    return out


def _append_log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)


def fetch_all(groups: set[str] | None = None) -> int:
    sources = [s for s in all_sources() if not groups or s["group"] in groups]
    logged = _last_logged_hashes()
    _check_ua(UA)
    session = requests.Session()
    session.trust_env = False  # ~/.netrc・プロキシ環境変数を使わない
    session.headers.clear()
    session.headers.update({"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"})
    last_host_time: dict[str, float] = {}
    bad = 0
    n_fetch = n_skip = 0
    for s in sources:
        dest = ROOT / s["dest"]
        want = s["expected_sha256"] or logged.get(s["source_id"], "")
        if dest.exists() and want and sha256_file(dest) == want:
            n_skip += 1
            continue
        host = s["url"].split("/")[2]
        wait = DELAY_SEC - (time.time() - last_host_time.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        resp = None
        for attempt in range(3):
            try:
                resp = session.get(s["url"], timeout=60)
                last_host_time[host] = time.time()
                if resp.status_code == 200:
                    break
            except requests.RequestException as e:  # noqa: PERF203
                print(f"  retry {s['source_id']}: {e}", file=sys.stderr)
            time.sleep(3)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if resp is None or resp.status_code != 200:
            _append_log(dict(fetched_at_utc=now, source_id=s["source_id"], url=s["url"], dest=s["dest"],
                             http=getattr(resp, "status_code", "ERR"), bytes=0, sha256="",
                             expected_sha256=s["expected_sha256"], result="http_error"))
            bad += 1
            continue
        digest = sha256_bytes(resp.content)
        if s["expected_sha256"] and digest != s["expected_sha256"]:
            _append_log(dict(fetched_at_utc=now, source_id=s["source_id"], url=s["url"], dest=s["dest"],
                             http=200, bytes=len(resp.content), sha256=digest,
                             expected_sha256=s["expected_sha256"], result="hash_mismatch"))
            print(f"HASH MISMATCH {s['source_id']}: {digest} != {s['expected_sha256']}", file=sys.stderr)
            bad += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        _append_log(dict(fetched_at_utc=now, source_id=s["source_id"], url=s["url"], dest=s["dest"],
                         http=200, bytes=len(resp.content), sha256=digest,
                         expected_sha256=s["expected_sha256"], result="fetched"))
        n_fetch += 1
    if n_fetch or bad:
        new = not RUN_LOG.exists()
        with open(RUN_LOG, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=RUN_FIELDS, lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(dict(run_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), user_agent=UA,
                            request_headers_sent="|".join(sorted(session.headers)), delay_sec=DELAY_SEC,
                            n_fetched=n_fetch, n_skipped=n_skip, n_problems=bad))
    print(f"fetch: fetched={n_fetch} skipped(already verified)={n_skip} problems={bad} total={len(sources)}")
    return bad


def verify_local() -> list[str]:
    """ローカルの原本が、記録(期待ハッシュまたは取得ログ)と一致するか。差異の一覧を返す。"""
    logged = _last_logged_hashes()
    problems = []
    for s in all_sources():
        p = ROOT / s["dest"]
        want = s["expected_sha256"] or logged.get(s["source_id"], "")
        if not p.exists():
            problems.append(f"missing {s['source_id']}")
        elif not want:
            problems.append(f"unpinned {s['source_id']}")
        elif sha256_file(p) != want:
            problems.append(f"hash {s['source_id']}")
    return problems


__all__ = ["fetch_all", "verify_local", "all_sources", "TOURISM_YEARS", "Path"]
