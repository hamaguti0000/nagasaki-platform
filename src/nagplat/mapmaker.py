"""地図: 市町の塗り分けPNGと、データの系譜(lineage)JSON を出力する。

- outputs/restricted/map_tourists_per_capita_2025.png : 人口1人あたり観光客延べ数(県統計由来。GitHubに上げない)
- outputs/public/map_population_2020_weather_2025.png : 令和2年国勢調査人口と気象庁の観測点(公開候補)
"""
from __future__ import annotations

import json
import platform
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors, font_manager  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402

from .common import ROOT, read_csv, sha256_file  # noqa: E402

WAREHOUSE = ROOT / "warehouse" / "nagasaki.duckdb"
GEOJSON = ROOT / "data" / "public" / "gold" / "municipality_boundary.geojson"
FONT_NAME = "Noto Sans CJK JP"
YEAR = 2025
DPI = 150


def _font() -> Path:
    path = Path(font_manager.findfont(font_manager.FontProperties(family=FONT_NAME), fallback_to_default=False))
    plt.rcParams["font.family"] = FONT_NAME
    return path


def _poly_patch(geom_json: dict, **kw) -> list[PathPatch]:
    polys = geom_json["coordinates"] if geom_json["type"] == "MultiPolygon" else [geom_json["coordinates"]]
    patches = []
    for poly in polys:
        verts, codes = [], []
        for ring in poly:
            ring = np.asarray(ring)
            verts.extend(ring.tolist())
            codes.extend([MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 2) + [MPath.CLOSEPOLY])
        patches.append(PathPatch(MPath(verts, codes), **kw))
    return patches


def _label_pos(feat: dict) -> tuple[float, float]:
    """最大のポリゴンの重心(描画用の簡易な位置。島の多い市町は最大の島)。"""
    g = feat["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    best = max(polys, key=lambda p: len(p[0]))
    ring = np.asarray(best[0])
    return float(ring[:, 0].mean()), float(ring[:, 1].mean())


LABEL_OFFSETS = {  # 見やすさのための手動の調整(経度, 緯度の差)。位置のみで値には影響しない
    "長崎市": (-0.02, -0.10), "時津町": (-0.15, 0.04), "長与町": (-0.17, -0.02), "諫早市": (0.0, 0.05),
    "大村市": (0.11, 0.0), "東彼杵町": (0.0, 0.0), "川棚町": (0.0, 0.0), "波佐見町": (0.0, 0.0),
    "佐々町": (0.0, 0.0), "平戸市": (-0.12, 0.10), "松浦市": (0.0, 0.04), "雲仙市": (-0.02, 0.07),
    "島原市": (0.07, 0.02), "南島原市": (0.0, -0.05), "佐世保市": (-0.08, 0.10), "西海市": (0.0, -0.02),
}
# 観測点ラベルの位置(経度, 緯度の差, 文字の水平位置)
STATION_LABEL = {"平戸": (-0.04, 0.05, "right"), "雲仙岳": (0.04, -0.08, "left"), "長崎": (0.05, -0.02, "left"),
                 "佐世保": (-0.04, -0.07, "right")}


def _draw(fig_title: str, values: dict[str, float | None], cmap_name: str, norm, cbar_label: str,
          stations: list[dict], footer: str, out: Path, hatch_codes: set[str] | None = None) -> None:
    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    base = plt.get_cmap(cmap_name)
    cmap = colors.LinearSegmentedColormap.from_list(cmap_name + "_t", base(np.linspace(0.18, 1.0, 256)))  # 最小値も背景と区別できる色にする
    fig, ax = plt.subplots(figsize=(8.2, 9.4))
    for f in gj["features"]:
        code = f["properties"]["city_code"]
        v = values.get(code)
        fc = "#d9d9d9" if v is None else cmap(norm(v))
        hatch = "///" if hatch_codes and code in hatch_codes else None
        for p in _poly_patch(f["geometry"], facecolor=fc, edgecolor="#ffffff", linewidth=0.5, hatch=hatch):
            ax.add_patch(p)
    for f in gj["features"]:
        x, y = _label_pos(f)
        dx, dy = LABEL_OFFSETS.get(f["properties"]["city_name"], (0.0, 0.0))
        ax.text(x + dx, y + dy, f["properties"]["city_name"], fontsize=5.8, ha="center", va="center", color="#111111",
                path_effects=[pe.withStroke(linewidth=1.6, foreground="white")], zorder=7)
    for s in stations:
        ax.plot(s["lon"], s["lat"], marker="^", color="#08306b", markersize=5.5, markeredgecolor="white",
                markeredgewidth=0.6, zorder=5)
        key = s["label"].split(" ")[0]
        dx, dy, ha = STATION_LABEL.get(key, (0.04, 0.03, "left"))
        ax.text(s["lon"] + dx, s["lat"] + dy, s["label"], fontsize=5.4, color="#08306b", ha=ha, zorder=8,
                path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])
    ax.set_xlim(128.05, 130.45)
    ax.set_ylim(32.55, 34.75)
    ax.set_aspect(1 / np.cos(np.deg2rad(33.4)))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.01, shrink=0.55)
    cb.set_label(cbar_label, fontsize=7)
    cb.ax.tick_params(labelsize=6)
    ax.set_title(fig_title, fontsize=11, loc="left")
    fig.text(0.02, 0.012, footer, fontsize=5.6, ha="left", va="bottom", color="#333333", wrap=True)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.12)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, metadata={"Software": None})
    plt.close(fig)


def _lineage(out: Path, title: str, tables: list[str], source_ids: list[str], font: Path, metric: str, note: str) -> None:
    log = {}
    for r in read_csv(ROOT / "manifest" / "fetch_log.csv"):
        if r["result"] == "fetched":
            log[r["source_id"]] = r
    srcs = {s["source_id"]: s for s in read_csv(ROOT / "config" / "sources.csv")}
    nodes = []
    for sid in sorted(source_ids):
        l = log.get(sid, {})
        s = srcs.get(sid, {})
        nodes.append(dict(source_id=sid, url=l.get("url") or s.get("url", ""), fetched_at_utc=l.get("fetched_at_utc", ""),
                          sha256=l.get("sha256", ""), license_class=s.get("license_class", "jma" if sid.startswith("jma_") else ""),
                          terms_id=s.get("terms_id", "T_JMA" if sid.startswith("jma_") else "")))
    code = {p.name: sha256_file(p) for p in sorted((ROOT / "src" / "nagplat").glob("*.py"))}
    doc = dict(title=title, metric=metric, note=note, gold_and_silver_tables=tables, sources=nodes,
               transform_code_sha256=code, font=dict(name=FONT_NAME, file=font.name, sha256=sha256_file(font)),
               libraries=dict(python=platform.python_version(), duckdb=duckdb.__version__,
                              matplotlib=matplotlib.__version__, numpy=np.__version__))
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_maps() -> None:
    font = _font()
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    # 観測点(2025年の年平均気温・年降水量)
    st = con.execute(f"""SELECT s.station_name, s.lat, s.lon, g.temp_mean_c, g.precip_total_mm, g.n_quasi_normal_values
                         FROM silver_station s JOIN gold_station_year g USING (block_no) WHERE g.year={YEAR}
                         ORDER BY s.block_no""").fetchall()
    stations = [dict(lat=lat, lon=lon, label=(f"{n} {t:.1f}℃/{p:.0f}mm" if t is not None and p is not None
                                              else f"{n} 年の値なし(資料不足)")) for n, lat, lon, t, p, _q in st]
    quasi = [n for n, *_r, q in st if q]
    note_q = (f"{'・'.join(quasi)}の一部の月は準正常値(統計の資料数が基準の80%以上)を含む。" if quasi else "")
    foot_weather = ("▲気象庁の観測点(官署)。表示は2025年の月平均気温の単純平均と月降水量の合計。" + note_q +
                    "出典: 気象庁ホームページ「過去の気象データ」(https://www.data.jma.go.jp/stats/etrn/)を加工して作成")
    foot_gis = ("境界: 政府統計の総合窓口(e-Stat)統計GIS 境界データ(令和2年国勢調査 小地域)を市町に集約し、描画用に簡略化して作成。"
                "出典: 政府統計の総合窓口(e-Stat)(https://www.e-stat.go.jp/)")

    # --- 1. 観光客延べ数 / 人口(restricted)---
    rows = con.execute(f"""SELECT area_code, tourists_per_capita, tourists_total, population_jan1,
                                  tourists_recalculated_by_prefecture
                           FROM gold_municipality_year WHERE year={YEAR}""").fetchall()
    vals = {c: v for c, v, *_ in rows}
    norm = colors.PowerNorm(gamma=0.5, vmin=0, vmax=max(vals.values()))
    footer = (f"指標: {YEAR}年の観光客延べ数(人)÷ {YEAR}年1月1日の推計人口(人)。算定方法は市町ごと・時期ごとに県が見直しており、"
              "市町間・年間の比較には注意が必要。\n"
              "出典: 長崎県「長崎県観光統計」(令和7年)、長崎県「異動人口調査」年間集計(令和7年)を加工して作成。\n"
              + foot_gis + "\n" + foot_weather)
    out1 = ROOT / "outputs" / "restricted" / "map_tourists_per_capita_2025.png"
    _draw(f"人口1人あたりの観光客延べ数({YEAR}年、市町別)", vals, "YlOrRd", norm, "人/人", stations, footer, out1)
    _lineage(out1.with_suffix(".lineage.json"), "人口1人あたり観光客延べ数(2025)",
             ["gold_municipality_year", "silver_tourism_year", "silver_population_year", "silver_station",
              "gold_station_year", "bronze_kanko_aggregate", "bronze_jinko_nenkan", "bronze_jma_monthly",
              "bronze_boundary_small_area", "ledger_comparability_flags"],
             ["kanko_agg_visitors", "jinko_nenkan_2025", "boundary_koku2020_42", "jma_station_table"] +
             [f"jma_{b}_2025_{v}" for b in ("47800", "47805", "47812", "47817", "47818", "47843") for v in ("a1", "a2", "a4")],
             font, "tourists_total / population_jan1 (year=2025)",
             "公開区分: restricted(県統計の加工値を含む。県の確認が済むまで公開しない)")

    # --- 2. 国勢調査人口 + 気象(public)---
    rows = con.execute("SELECT area_code, population_2020_census FROM gold_municipality_pop2020").fetchall()
    vals2 = {c: float(v) for c, v in rows}
    norm2 = colors.LogNorm(vmin=min(vals2.values()), vmax=max(vals2.values()))
    footer2 = ("指標: 令和2年(2020年)国勢調査の人口(人。小地域の人口を市町ごとに合計。対数目盛)。\n" + foot_gis + "\n" + foot_weather)
    out2 = ROOT / "outputs" / "public" / "map_population_2020_weather_2025.png"
    _draw("令和2年国勢調査の人口と、気象庁の観測点(市町別)", vals2, "Blues", norm2, "人(対数目盛)", stations, footer2, out2)
    _lineage(out2.with_suffix(".lineage.json"), "令和2年国勢調査の人口と気象庁の観測点",
             ["gold_municipality_pop2020", "silver_station", "gold_station_year", "bronze_boundary_small_area",
              "bronze_jma_monthly"],
             ["boundary_koku2020_42", "jma_station_table"] +
             [f"jma_{b}_2025_{v}" for b in ("47800", "47805", "47812", "47817", "47818", "47843") for v in ("a1", "a2", "a4")],
             font, "sum(JINKO) by city (令和2年国勢調査)", "公開区分: public(国・気象庁のデータのみ。出典・加工の注記つき)")
    con.close()
    print("map: OK")
