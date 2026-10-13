"""県異動人口調査 年間集計(推計人口・世帯数(年計))の解析。xls(2015〜2021)と xlsx(2022〜)。

列(0始まり): 2=期首人口(1月1日) 3=転入(県内) 4=転入(県外) 5=転入計 6=転出(県内) 7=転出(県外) 8=転出計
9=社会増減 13=出生 14=死亡 15=自然増減 19=人口増減 23=期末人口(翌年1月1日)
列の位置は、ヘッダー行の「X.1.1」「転入計」などの文字で確認し、ずれていれば異常終了する。
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import openpyxl
import xlrd

from .common import AREA_NAMES, PREF_TOTAL

COLS = {
    "pop_start": 2, "in_pref": 3, "in_out": 4, "in_total": 5, "out_pref": 6, "out_out": 7, "out_total": 8,
    "social_change": 9, "births": 13, "deaths": 14, "natural_change": 15, "pop_change": 19, "pop_end": 23,
}


def _sheet_rows(path: Path) -> tuple[str, list[list]]:
    warnings.filterwarnings("ignore")
    if path.suffix == ".xls":
        book = xlrd.open_workbook(str(path))
        cands = [s for s in book.sheets() if "推計人口" in s.name and "日本人" not in s.name and "外国人" not in s.name]
        s = cands[0]
        return s.name, [[s.cell_value(r, c) for c in range(s.ncols)] for r in range(s.nrows)]
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = [w for w in wb.worksheets if "推計人口" in w.title and "日本人" not in w.title and "外国人" not in w.title][0]
    return ws.title, [list(r) for r in ws.iter_rows(values_only=True)]


def _norm(v) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


_TXT_NUM = re.compile(r"^([△▲\-]?)\s*([\d,]+(?:\.\d+)?)$")


def _num(v):
    """数値。2017年版のように、負数を文字列『△ 7,089』で持つセルも数値にする(△ = マイナス)。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = _TXT_NUM.match(v.strip().replace("\u3000", " "))
        if m:
            x = float(m.group(2).replace(",", ""))
            return -x if m.group(1) in ("△", "▲", "-") else x
    return None


def parse_nenkan(path: Path, year: int) -> list[dict]:
    sheet, rows = _sheet_rows(path)
    hdr = [[_norm(c) for c in r] for r in rows[:9]]
    flat = " ".join(c for r in hdr for c in r)
    # ヘッダーの確認(期首・期末の「N.1.1」と、列の見出し)
    assert re.search(r"[HR]\d+\.1\.1", flat), f"{path.name}: 期首の見出しが見つからない"
    assert hdr[6][5] == "転入計" and hdr[6][8] == "転出計", f"{path.name}: 転入計/転出計の列位置が想定と異なる"
    assert "社会" in hdr[5][9] or "増減" in hdr[6][9], f"{path.name}: 社会増減の列位置が想定と異なる"
    out = []
    for i, r in enumerate(rows):
        c0 = _norm(r[0]) if len(r) > 0 else ""
        c1 = _norm(r[1]) if len(r) > 1 else ""
        if c0 == PREF_TOTAL:
            name = PREF_TOTAL
        elif c1 in AREA_NAMES:
            name = c1
        else:
            continue
        d = {"year": year, "area_name": name, "source_row": i + 1, "source_sheet": sheet}
        for k, j in COLS.items():
            d[k] = _num(r[j]) if j < len(r) else None
        out.append(d)
    return out
