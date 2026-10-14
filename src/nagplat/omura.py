"""大村市の転入超過の調査(設計: docs/大村市_なぜ_設計.md、固定: タグ omura-why-design-v1)。

設計の固定の後に実行する。比較群の基準・指標・判定の規則は、設計のとおり(結果を見て変えない)。
入力: data/public/gold/gold_panel_municipality_year.csv、raw/public/ssdse/SSDSE-A-2026.csv(単年の項目)。
出力: outputs/public/omura_*.csv
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import numpy as np

from .common import ROOT, write_csv

YEARS = list(range(2016, 2025))
PREF = "42"
OMURA_NAME = "大村市"
BAND = (0.67, 1.5)
BAND_WIDE = (0.5, 2.0)
METRO = {"11", "12", "13", "14", "21", "23", "24", "26", "27", "28", "29"}   # 本調査の定義(設計 §4)
KYUSHU = {"40", "41", "42", "43", "44", "45", "46", "47"}
SEED = 20261014
N_BOOT = 2000
OUT = ROOT / "outputs" / "public"

# 指標: (id, 仮説, 名称, 方向(+1 = 高いほど支持, -1 = 低いほど支持))
INDICATORS = [
    ("I1a", "H1", "世帯数の増加率(2015→2020)", +1),
    ("I1b", "H1", "一般世帯の平均世帯人員(2020)", +1),
    ("I3a", "H3", "民営の従業者数÷日本人人口(2021)", +1),
    ("I3b", "H3", "民営の事業所数÷日本人人口(2021)", +1),
    ("I3c", "H3", "第3次産業就業者の比率(2020)", +1),
    ("I3d", "H3", "完全失業率(2020)", -1),
    ("I5a", "H5", "年少人口(15歳未満)比率(2020)", +1),
    ("I5b", "H5", "小学校児童数の比(2024÷2016)", +1),
    ("I5c", "H5", "保育所等数÷15歳未満人口(2023)", +1),
    ("I5d", "H5", "出生数÷日本人人口(2016〜2023の平均)", +1),
    ("I6a", "H6", "一般病院+一般診療所数÷人口(2023)", +1),
    ("I6b", "H6", "医師数÷人口(2022)", +1),
    ("I7", "H7a", "総回転率 (転入者+転出者)÷日本人人口(2016〜2024の平均)", +1),
]


def _f(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except ValueError:
        return None
    return v if v == v else None


def load_panel() -> dict[str, dict[int, dict]]:
    p: dict[str, dict[int, dict]] = {}
    with open(ROOT / "data" / "public" / "gold" / "gold_panel_municipality_year.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p.setdefault(r["area_code"], {})[int(r["year"])] = r
    return p


def load_ssdse_single() -> dict[str, dict[str, float]]:
    """SSDSE-A 2026 年版の単年の項目(地域コードは最新コードに寄せる)。"""
    cmap = {}
    with open(ROOT / "data" / "public" / "silver" / "silver_ssdse_area_map.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cmap[r["ssdse_code"]] = r["area_code"]
    out: dict[str, dict[str, float]] = {}
    with open(ROOT / "raw" / "public" / "ssdse" / "SSDSE-A-2026.csv", encoding="cp932") as fh:
        rd = csv.reader(fh)
        codes = next(rd)
        next(rd)
        next(rd)
        for row in rd:
            ac = cmap.get(row[0])
            if ac is None:
                continue
            out[ac] = {c: v for c in codes[3:] for v in [_f(row[codes.index(c)])] if v is not None}
    return out


def _row_ok(p, code) -> bool:
    return all(y in p[code] and _f(p[code][y]["net_rate_permille"]) is not None
               and p[code][y]["excluded_main"] == "false" for y in YEARS)


def _flag_any(p, code, col) -> bool:
    return any(p[code][y][col] == "true" for y in YEARS if y in p[code])


def pop2020(p, code) -> float | None:
    r = p[code].get(2020)
    return _f(r["pop_jp_denominator"]) if r else None


def rankdata(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a))
    sa = a[order]
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = rankdata(x), rankdata(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return float("nan")
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def boot_spearman(x: np.ndarray, y: np.ndarray, seed: int = SEED) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    n = len(x)
    est = spearman(x, y)
    bs = []
    for _ in range(N_BOOT):
        i = rng.integers(0, n, n)
        v = spearman(x[i], y[i])
        if v == v:
            bs.append(v)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return est, float(lo), float(hi)


def indicators_for(p, ss, code) -> dict[str, float | None]:
    r15 = p[code].get(2016)
    r20 = p[code].get(2020)
    r23 = p[code].get(2023)
    r24 = p[code].get(2024)
    r16 = p[code].get(2016)
    s = ss.get(code, {})
    out: dict[str, float | None] = {}

    def div(a, b):
        return a / b if a is not None and b not in (None, 0) else None

    hh15 = _f(r15["households_asof"]) if r15 and r15["census_year_asof"] == "2015" else None
    hh20 = _f(r20["households_asof"]) if r20 else None
    out["I1a"] = div(hh20, hh15)
    out["I1b"] = div(s.get("A710201"), s.get("A710101"))
    pj20 = pop2020(p, code)
    out["I3a"] = div(s.get("C2208"), pj20)
    out["I3b"] = div(s.get("C2108"), pj20)
    out["I3c"] = div(s.get("F2221"), _f(r20["employed_asof"]) if r20 else None)
    emp = _f(r20["employed_asof"]) if r20 else None
    une = _f(r20["unemployed_asof"]) if r20 else None
    out["I3d"] = div(une, (emp + une) if emp is not None and une is not None else None)
    tot20 = _f(r20["pop_total_asof"]) if r20 else None
    u15 = _f(r20["pop_under15_asof"]) if r20 else None
    out["I5a"] = div(u15, tot20)
    e24 = _f(r24["elementary_pupils"]) if r24 else None
    e16 = _f(r16["elementary_pupils"]) if r16 else None
    out["I5b"] = div(e24, e16)
    out["I5c"] = div(s.get("J250302"), u15)
    rates = []
    for y in range(2016, 2024):
        r = p[code].get(y)
        if r:
            b, d = _f(r["births"]), _f(r["pop_jp_denominator"])
            if b is not None and d:
                rates.append(b / d * 1000)
    out["I5d"] = float(np.mean(rates)) if rates else None
    gh = _f(r23["general_hospitals"]) if r23 else None
    cl = _f(r23["clinics"]) if r23 else None
    out["I6a"] = div((gh + cl) if gh is not None and cl is not None else None, tot20)
    out["I6b"] = div(s.get("I6100"), tot20)
    turn = []
    for y in YEARS:
        r = p[code].get(y)
        if r:
            a, b, d = _f(r["transfers_in_jp"]), _f(r["transfers_out_jp"]), _f(r["pop_jp_denominator"])
            if None not in (a, b) and d:
                turn.append((a + b) / d * 1000)
    out["I7"] = float(np.mean(turn)) if turn else None
    return out


def mean_net(p, code) -> float:
    return float(np.mean([_f(p[code][y]["net_rate_permille"]) for y in YEARS]))


def groups(p) -> dict[str, list[str]]:
    omura = next(c for c in p if p[c][2020]["area_name"] == OMURA_NAME and p[c][2020]["pref_code"] == PREF)
    pop0 = pop2020(p, omura)
    city = [c for c in p if c != omura and 2020 in p[c] and p[c][2020]["area_name"].endswith("市") and _row_ok(p, c)]
    pref = lambda c: p[c][2020]["pref_code"]  # noqa: E731
    inband = lambda c, b: (pop2020(p, c) is not None and b[0] * pop0 <= pop2020(p, c) <= b[1] * pop0)  # noqa: E731
    g: dict[str, list[str]] = {}
    g["C1"] = [c for c in city if pref(c) == PREF]
    g["C1p"] = [c for c in p if c != omura and 2020 in p[c] and pref(c) == PREF and _row_ok(p, c)]
    g["C2"] = [c for c in city if pref(c) not in METRO and inband(c, BAND)]
    g["S1"] = [c for c in city if pref(c) not in METRO and inband(c, BAND_WIDE)]
    g["S2"] = [c for c in city if inband(c, BAND)]
    g["S3"] = [c for c in city if pref(c) in KYUSHU and inband(c, BAND)]
    g["S5"] = [c for c in g["C2"] if not _flag_any(p, c, "evac_candidate") and p[c][2020]["excluded_sensitivity"] == "false"]
    # S4: 2015年の値(国勢調査)で、標準化した距離が近い20市(結果の変数を使わない)
    def cov(c):
        r = p[c].get(2016)
        if not r or r["census_year_asof"] != "2015":
            return None
        t, u, o = _f(r["pop_total_asof"]), _f(r["pop_under15_asof"]), _f(r["pop_65plus_asof"])
        if not t or u is None or o is None:
            return None
        return [np.log(t), u / t, o / t]
    cand = [c for c in city if pref(c) not in METRO and cov(c) is not None]
    X = np.array([cov(c) for c in cand])
    mu, sd = X.mean(0), X.std(0)
    xo = (np.array(cov(omura)) - mu) / sd
    d = np.sqrt((((X - mu) / sd - xo) ** 2).sum(1))
    g["S4"] = [cand[i] for i in np.argsort(d, kind="stable")[:20]]
    g["omura"] = [omura]
    return g


def classify(ind_id: str, direction: int, omura_val, grp_vals: dict[str, float], c1_vals: dict[str, float],
             netmean: dict[str, float], c1_codes: list[str]) -> dict:
    if omura_val is None:
        return dict(verdict="データでは判断できない", reason="指標が欠損")
    def better_share(vals):
        v = np.array(list(vals))
        if len(v) == 0:
            return None
        return float(((v > omura_val) if direction > 0 else (v < omura_val)).mean())
    sh_c2 = better_share(grp_vals.values())
    sh_c1 = better_share(c1_vals.values())
    med = float(np.median(list(grp_vals.values())))
    opposite = (omura_val < med) if direction > 0 else (omura_val > med)
    codes = [c for c in grp_vals if c in netmean]
    est = lo = hi = float("nan")
    if len(codes) >= 10:
        est, lo, hi = boot_spearman(np.array([grp_vals[c] for c in codes]), np.array([netmean[c] for c in codes]))
    same_sign_ci = (lo > 0) if direction > 0 else (hi < 0)
    opp_sign_ci = (hi < 0) if direction > 0 else (lo > 0)
    top_c2 = sh_c2 is not None and sh_c2 <= 0.25
    top_c1 = sh_c1 is not None and sh_c1 <= 0.25
    if top_c2 and top_c1 and same_sign_ci:
        v = "データが支持する"
    elif opposite or opp_sign_ci:
        v = "データと合わない"
    else:
        v = "データでは判断できない"
    return dict(verdict=v, share_better_c2=sh_c2, share_better_c1=sh_c1, c2_median=med, spearman=est,
                spearman_lo=lo, spearman_hi=hi, n_c2=len(codes))


def run_group(p, ss, omura: str, gcodes: list[str], c1: list[str]) -> dict:
    """1つの比較群について、年ごとの差・前提の判定・仮説の判定を返す。"""
    yearly = []
    for y in YEARS:
        og = _f(p[omura][y]["net_rate_permille"])
        v2 = np.array([_f(p[c][y]["net_rate_permille"]) for c in gcodes])
        v1 = np.array([_f(p[c][y]["net_rate_permille"]) for c in c1])
        yearly.append(dict(year=y, omura=og, c1_median=float(np.median(v1)), c2_median=float(np.median(v2)),
                           c2_p25=float(np.percentile(v2, 25)), c2_p75=float(np.percentile(v2, 75)),
                           share_below_omura_c2=float((v2 < og).mean())))
    both = sum(1 for r in yearly if r["omura"] > r["c1_median"] and r["omura"] > r["c2_median"])
    gap2 = [r["omura"] - r["c2_median"] for r in yearly]
    open_year = None
    for i in range(len(YEARS)):
        if all(g > 0 for g in gap2[i:]):
            open_year = YEARS[i]
            break
    ind_o = indicators_for(p, ss, omura)
    ind_g = {c: indicators_for(p, ss, c) for c in set(gcodes) | set(c1)}
    netmean = {c: mean_net(p, c) for c in ind_g}
    verdicts = {}
    for iid, hyp, name, d in INDICATORS:
        gv = {c: ind_g[c][iid] for c in gcodes if ind_g[c][iid] is not None}
        cv = {c: ind_g[c][iid] for c in c1 if ind_g[c][iid] is not None}
        verdicts[iid] = classify(iid, d, ind_o[iid], gv, cv, netmean, c1) | dict(omura=ind_o[iid])
    return dict(yearly=yearly, years_above_both=both, open_year=open_year, verdicts=verdicts,
                mean_gap=float(np.mean(gap2)))


def main() -> int:
    p = load_panel()
    ss = load_ssdse_single()
    g = groups(p)
    omura = g["omura"][0]
    c1, c2 = g["C1"], g["C2"]
    print(f"大村市={omura} 2020年日本人人口={pop2020(p, omura):.0f} C1={len(c1)} C1'={len(g['C1p'])} C2={len(c2)}"
          f" S1={len(g['S1'])} S2={len(g['S2'])} S3={len(g['S3'])} S4={len(g['S4'])} S5={len(g['S5'])}")

    # 比較群の一覧
    rows = []
    for k in ("C1", "C1p", "C2", "S1", "S2", "S3", "S4", "S5"):
        for c in g[k]:
            rows.append(dict(group=k, area_code=c, pref_name=p[c][2020]["pref_name"], area_name=p[c][2020]["area_name"],
                             pop_jp_2020=pop2020(p, c)))
    write_csv(OUT / "omura_comparison_groups.csv", rows)

    main_res = run_group(p, ss, omura, c2, c1)

    # 年ごとの表(主)
    yr = []
    pref_others = g["C1p"]
    for r in main_res["yearly"]:
        y = r["year"]
        o = p[omura][y]
        pop = _f(o["pop_jp_denominator"])
        rin, rout = _f(o["transfers_in_jp"]) / pop * 1000, _f(o["transfers_out_jp"]) / pop * 1000
        in2 = [_f(p[c][y]["transfers_in_jp"]) / _f(p[c][y]["pop_jp_denominator"]) * 1000 for c in c2]
        out2 = [_f(p[c][y]["transfers_out_jp"]) / _f(p[c][y]["pop_jp_denominator"]) * 1000 for c in c2]
        in1 = [_f(p[c][y]["transfers_in_jp"]) / _f(p[c][y]["pop_jp_denominator"]) * 1000 for c in c1]
        out1 = [_f(p[c][y]["transfers_out_jp"]) / _f(p[c][y]["pop_jp_denominator"]) * 1000 for c in c1]
        yr.append(dict(
            year=y, omura_net_permille=round(r["omura"], 3), c1_median=round(r["c1_median"], 3),
            c2_median=round(r["c2_median"], 3), c2_p25=round(r["c2_p25"], 3), c2_p75=round(r["c2_p75"], 3),
            gap_vs_c1=round(r["omura"] - r["c1_median"], 3), gap_vs_c2=round(r["omura"] - r["c2_median"], 3),
            share_of_c2_below_omura=round(r["share_below_omura_c2"], 3),
            omura_in_rate=round(rin, 3), omura_out_rate=round(rout, 3),
            c2_median_in_rate=round(float(np.median(in2)), 3), c2_median_out_rate=round(float(np.median(out2)), 3),
            c1_median_in_rate=round(float(np.median(in1)), 3), c1_median_out_rate=round(float(np.median(out1)), 3),
            omura_in=int(_f(o["transfers_in_jp"])), omura_out=int(_f(o["transfers_out_jp"])),
            omura_net=int(_f(o["net_transfers_jp"])),
            pref42_other20_net_sum=int(sum(_f(p[c][y]["net_transfers_jp"]) for c in pref_others)),
            n_c1=len(c1), n_c2=len(c2)))
    write_csv(OUT / "omura_yearly.csv", yr)

    # 指標
    irows = []
    for iid, hyp, name, d in INDICATORS:
        v = main_res["verdicts"][iid]
        irows.append(dict(indicator=iid, hypothesis=hyp, name=name, direction=("高いほど" if d > 0 else "低いほど"),
                          omura=_r(v["omura"]), c2_median=_r(v.get("c2_median")),
                          share_c2_better_than_omura=_r(v.get("share_better_c2")),
                          share_c1_better_than_omura=_r(v.get("share_better_c1")),
                          spearman_c2=_r(v.get("spearman")), spearman_lo=_r(v.get("spearman_lo")),
                          spearman_hi=_r(v.get("spearman_hi")), n_c2=v.get("n_c2"), verdict=v["verdict"]))
    write_csv(OUT / "omura_indicators.csv", irows)

    # 感度分析
    srows = []
    for k, label in (("C2", "主(C2)"), ("S1", "S1 規模の幅0.5〜2.0倍"), ("S2", "S2 三大都市圏を含む全国"),
                     ("S3", "S3 九州・沖縄のみ"), ("S4", "S4 2015年の値が近い20市"), ("S5", "S5 避難指示区域の候補を除く")):
        res = main_res if k == "C2" else run_group(p, ss, omura, g[k], c1)
        row = dict(group=k, label=label, n=len(g[k]), years_above_both=res["years_above_both"],
                   gap_open_year=res["open_year"] or "", mean_gap_vs_median=round(res["mean_gap"], 3))
        for iid, *_ in INDICATORS:
            row[iid] = res["verdicts"][iid]["verdict"]
        srows.append(row)
    write_csv(OUT / "omura_sensitivity.csv", srows)

    print("前提(両方の中央値より大きい年数):", main_res["years_above_both"], "/ 9。差が開いた年:", main_res["open_year"])
    for r in irows:
        print(r["indicator"], r["verdict"], r["omura"], r["c2_median"], r["share_c2_better_than_omura"], r["spearman_c2"])
    return 0


def _r(x):
    return None if x is None or (isinstance(x, float) and x != x) else round(float(x), 4)


if __name__ == "__main__":
    raise SystemExit(main())
