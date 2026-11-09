"""共通: パス・ハッシュ・設定の読み込み。"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 分析対象の年。2014年は前年値(参考)として観光側だけ持つ。
YEARS = list(range(2015, 2026))
TOURISM_YEARS = [2014] + YEARS

# 21市町(13市8町)。団体コードは、境界データの市区町村コードと突き合わせて検証する(validate)。
AREAS = [
    ("42201", "長崎市"), ("42202", "佐世保市"), ("42203", "島原市"), ("42204", "諫早市"),
    ("42205", "大村市"), ("42207", "平戸市"), ("42208", "松浦市"), ("42209", "対馬市"),
    ("42210", "壱岐市"), ("42211", "五島市"), ("42212", "西海市"), ("42213", "雲仙市"),
    ("42214", "南島原市"), ("42307", "長与町"), ("42308", "時津町"), ("42321", "東彼杵町"),
    ("42322", "川棚町"), ("42323", "波佐見町"), ("42383", "小値賀町"), ("42391", "佐々町"),
    ("42411", "新上五島町"),
]
AREA_NAMES = [n for _, n in AREAS]
NAME_TO_CODE = {n: c for c, n in AREAS}
PREF_TOTAL = "県計"

# 気象庁の官署(5桁の地点番号)。市町内に観測点がない市町があるため、地図では点で示す。
STATIONS = [
    ("47800", "厳原", "84072"), ("47805", "平戸", "84171"), ("47812", "佐世保", "84266"),
    ("47817", "長崎", "84496"), ("47818", "雲仙岳", "84519"), ("47843", "福江", "84536"),
]
JMA_VIEWS = ("a1", "a2", "a4")  # a1=気圧・降水量 a2=気温・湿度 a4=日照・雪


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else [])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def jma_url(block: str, year: int, view: str) -> str:
    return (
        "https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php"
        f"?prec_no=84&block_no={block}&year={year}&month=&day=&view={view}"
    )


def jma_dest(block: str, year: int, view: str) -> str:
    return f"raw/public/jma/monthly_{block}_{year}_{view}.html"
