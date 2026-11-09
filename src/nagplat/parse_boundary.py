"""統計GIS 境界データ(令和2年国勢調査 小地域、長崎県、世界測地系・緯度経度)の読み込みと市町への集約。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import shapefile
from shapely.geometry import shape as to_shape
from shapely.ops import unary_union

SIMPLIFY_DEG = 0.0004  # 約40m。描画用。面積・人口の集計には元の形を使う。


def read_small_areas(zip_path: Path) -> list[dict]:
    z = zipfile.ZipFile(zip_path)
    stem = [n for n in z.namelist() if n.endswith(".shp")][0][:-4]
    r = shapefile.Reader(shp=io.BytesIO(z.read(stem + ".shp")), dbf=io.BytesIO(z.read(stem + ".dbf")),
                         shx=io.BytesIO(z.read(stem + ".shx")), encoding="cp932")
    out = []
    for sr in r.iterShapeRecords():
        d = sr.record.as_dict()
        out.append(dict(
            key_code=d["KEY_CODE"], city_code=d["PREF"] + d["CITY"], city_name=d["CITY_NAME"],
            s_area=d["S_AREA"], hcode=int(d["HCODE"]), area_m2=float(d["AREA"]),
            jinko=int(d["JINKO"]), setai=int(d["SETAI"]), geometry=sr.shape.__geo_interface__))
    return out


def dissolve_by_city(small: list[dict]) -> dict[str, dict]:
    """市町ごとに小地域のポリゴンを結合する。戻り値: city_code -> {name, geometry(shapely), jinko, n}"""
    groups: dict[str, list[dict]] = {}
    for s in small:
        groups.setdefault(s["city_code"], []).append(s)
    out = {}
    for code in sorted(groups):
        g = groups[code]
        geom = unary_union([to_shape(s["geometry"]).buffer(0) for s in g])
        out[code] = dict(name=g[0]["city_name"], geometry=geom, jinko=sum(s["jinko"] for s in g), n=len(g))
    return out


def to_geojson(cities: dict[str, dict], simplify: float = SIMPLIFY_DEG) -> dict:
    feats = []
    for code, c in cities.items():
        geom = c["geometry"].simplify(simplify, preserve_topology=True)
        feats.append({"type": "Feature", "properties": {"city_code": code, "city_name": c["name"],
                                                         "jinko_2020": c["jinko"], "n_small_areas": c["n"]},
                      "geometry": json.loads(json.dumps(geom.__geo_interface__))})
    return {"type": "FeatureCollection", "features": feats}
