"""個人情報スキャン(公開前の確認)。値そのものは出力せず、先頭と末尾以外を伏せる。

検索の対象:
  - 公開対象のファイル(PUBLISH_LIST の public/review。private のディレクトリは中身を読まない)
  - PNG/Parquet などのバイナリ(メタデータに文字列が入ることがあるため)
  - git のコミット履歴と設定(あれば)
検索する種類:
  email / path / username / phone / secret / name_hint / extra_identifier
`extra_identifier` は、環境変数 NAGPLAT_SCAN_EXTRA(カンマ区切り)で渡した語(利用者本人のメールアドレス・姓・名など)。
コードには個人の値を書かない。
"""
from __future__ import annotations

import getpass
import os
import re
import subprocess
from pathlib import Path

from .common import ROOT

PRIVATE_PREFIXES = ("raw/", "warehouse/", "work/", ".pylibs/", "data/restricted/", "outputs/restricted/",
                    "ledger/restricted/", "manifest/restricted/", "local/")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
BINARY_SUFFIXES = {".png", ".parquet", ".duckdb", ".zip", ".pdf", ".xls", ".xlsx"}

PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "path": re.compile(r"(?:/home/[^/\s\"']+|/Users/[^/\s\"']+|[A-Za-z]:\\\\?(?:Users|Documents and Settings)\\\\?[^\\\s\"']+|/mnt/[a-z]/[^\s\"']*|/tmp/claude-[^\s\"']*)"),
    "phone": re.compile(r"(?<![\d.])(?:\+81[-\s]?\d{1,4}|0\d{1,4})[-\s]\d{1,4}[-\s]\d{3,4}(?![\d])"),
    "secret": re.compile(r"(?i)(?:api[_-]?key|secret|token|passwd|password|authorization)\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+=]{12,}"
                         r"|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-[A-Za-z0-9]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "name_hint": re.compile(r"(?:作成者|執筆者|氏名|著者|Author|author)\s*[:：]\s*\S+|Co-Authored-By\s*:\s*\S+|Copyright\s*\(c\)\s*\d{4}\s+\S+|Copyright ©\s*\S+"),
}
# 公的機関の連絡先など、利用者個人ではないことが明らかな既知の文字列(誤検出の除外)
ALLOW_EMAIL_DOMAINS = {"example.com", "example.org", "users.noreply.github.com"}


def mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 5:
        return s[:1] + "***"
    return f"{s[:2]}***{s[-2:]}"


def _identifiers() -> dict[str, str]:
    """検索語(値は返すが、レポートには出さない)。由来のラベル → 値"""
    ids: dict[str, str] = {}
    try:
        ids["os_username"] = getpass.getuser()
    except Exception:  # noqa: BLE001
        pass
    home = str(Path.home())
    ids["home_path"] = home
    for key in ("user.name", "user.email"):
        v = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True).stdout.strip()
        if v:
            ids[f"git_{key}"] = v
    for i, v in enumerate(os.environ.get("NAGPLAT_SCAN_EXTRA", "").split(",")):
        if v.strip():
            ids[f"extra_{i + 1}"] = v.strip()
    return {k: v for k, v in ids.items() if len(v) >= 3 or any(ord(c) > 127 for c in v)}  # 漢字・かなは1〜2文字も検索


def _allow() -> list[tuple[str, str]]:
    """config/privacy_allow.csv: 公開してよいと所有者が決めた行(ファイル, 行に含まれる文字列)。"""
    p = ROOT / "config" / "privacy_allow.csv"
    if not p.exists():
        return []
    import csv
    with open(p, encoding="utf-8", newline="") as f:
        return [(r["file"], r["contains"]) for r in csv.DictReader(f)]


def target_files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):
            continue
        rel = str(p.relative_to(ROOT))
        if rel.startswith(PRIVATE_PREFIXES):
            continue
        out.append(p)
    gc = ROOT / ".git" / "config"  # git の設定(作者情報など)。.git の他の中身は対象外
    if gc.exists():
        out.append(gc)
    return out


def scan() -> dict:
    ids = _identifiers()
    allow = _allow()
    hits: list[dict] = []
    files = target_files()
    for p in files:
        rel = str(p.relative_to(ROOT))
        if rel in ("src/nagplat/privacy_scan.py", "publish/PRIVACY_SCAN.md", "config/privacy_allow.csv"):  # 検索規則・自分の出力・許可リストは対象外
            continue
        raw = p.read_bytes()
        binary = p.suffix in BINARY_SUFFIXES
        text = raw.decode("utf-8", errors="ignore") if not binary else raw.decode("latin-1")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "privacy-scan: ignore" in line:  # 規則の説明・規約の引用など、確認済みの行
                continue
            if any(rel == f and c in line for f, c in allow):
                continue
            for kind, pat in PATTERNS.items():
                for m in pat.finditer(line):
                    val = m.group(0)
                    if kind == "email" and val.split("@")[-1].lower() in ALLOW_EMAIL_DOMAINS:
                        continue
                    if kind == "name_hint" and re.search(r"<[A-Z_ ]+>", line):  # <COPYRIGHT HOLDER> などのプレースホルダー
                        continue
                    hits.append(dict(file=rel, line=lineno if not binary else 0, kind=kind, masked=mask(val),
                                     binary=binary))
            for label, v in ids.items():
                if v and v.lower() in line.lower():
                    hits.append(dict(file=rel, line=lineno if not binary else 0,
                                     kind="home_path" if label == "home_path" else "extra_identifier"
                                     if label.startswith("extra") else label, masked=mask(v), binary=binary))
        if binary:
            for label, v in ids.items():  # バイナリは行ではなくファイル単位
                pass
    # git
    git = {"repo": (ROOT / ".git").exists(), "commits": 0, "authors": []}
    if git["repo"]:
        r = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%an <%ae> | %cn <%ce>"], capture_output=True, text=True)
        lines = [x for x in r.stdout.splitlines() if x]
        git["commits"] = len(lines)
        git["authors"] = sorted({mask(x) for x in lines})
    local = subprocess.run(["git", "-C", str(ROOT), "config", "--local", "--list"], capture_output=True, text=True).stdout \
        if git["repo"] else ""
    return dict(files_scanned=len(files), hits=hits, identifiers=sorted(ids), git=git, local_config=bool(local.strip()))


def report_md(res: dict) -> str:
    from collections import Counter
    c = Counter(h["kind"] for h in res["hits"])
    lines = ["# 個人情報スキャンの結果", "",
             f"- 対象: 公開対象のファイル {res['files_scanned']} 件(private のディレクトリは読んでいない)",
             f"- 検索語の由来: {', '.join(res['identifiers'])}(値は伏せる)",
             f"- git: リポジトリ {'あり(コミットの作者情報は `git log --format` で別途確認する)' if res['git']['repo'] else 'なし(コミット履歴はない)'}",
             f"- 検出: {sum(c.values())} 件 {dict(c)}", ""]
    if res["hits"]:
        lines += ["| ファイル | 行 | 種類 | 値(伏せ字) |", "|---|---|---|---|"]
        for h in res["hits"]:
            lines.append(f"| `{h['file']}` | {h['line'] or '(バイナリ)'} | {h['kind']} | `{h['masked']}` |")
    else:
        lines.append("検出なし。")
    return "\n".join(lines) + "\n"


def main() -> int:
    res = scan()
    out = ROOT / "publish" / "PRIVACY_SCAN.md"
    out.write_text(report_md(res), encoding="utf-8")
    print(f"privacy-scan: files={res['files_scanned']} hits={len(res['hits'])} -> {out.relative_to(ROOT)}")
    return 0 if not res["hits"] else 1
