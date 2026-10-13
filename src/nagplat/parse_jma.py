"""気象庁「過去の気象データ」月ごとの値(官署 monthly_s1)の解析。

値の末尾の記号(原文のまま `raw` に残し、`flag` に分類する):
  ")" 準正常値  "]" 資料不足値  "×" 欠測  "--" 現象なし  空 = 値なし
"""
from __future__ import annotations

import html
import re
from pathlib import Path

# 表示(view)ごとの、月の行内の列位置 → 変数名
VARS = {
    "a1": {5: "precip_total_mm"},
    "a2": {1: "temp_mean_c", 3: "temp_max_c", 8: "temp_min_c"},
    "a4": {1: "sunshine_total_h"},
}
_NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([)\]#*])?\s*$")


def _cells(tr: str) -> list[str]:
    cs = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\n", "").strip() for c in cs]


def parse_value(raw: str) -> tuple[float | None, str]:
    if raw in ("", "///"):
        return None, "none"
    if raw in ("--",):
        return None, "no_phenomenon"
    if raw in ("×", "×"):
        return None, "missing"
    m = _NUM.match(raw)
    if not m:
        return None, "unparsed"
    mark = m.group(2) or ""
    flag = {"": "ok", ")": "quasi_normal", "]": "insufficient", "#": "abnormal", "*": "estimated"}[mark]
    return float(m.group(1)), flag


def parse_monthly(path: Path, block: str, year: int, view: str) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = [_cells(tr) for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S)]
    out = []
    for cells in rows:
        if not cells or not re.fullmatch(r"\d{1,2}", cells[0]):
            continue
        month = int(cells[0])
        if not 1 <= month <= 12 or len(cells) < 6:
            continue
        for idx, var in VARS[view].items():
            raw = cells[idx] if idx < len(cells) else ""
            val, flag = parse_value(raw)
            out.append(dict(block_no=block, year=year, month=month, variable=var, raw=raw, value=val, flag=flag))
    return out
