"""全国パネルでの予測モデル(段3): 正則化線形モデル(Ridge)と勾配ブースティング。

段2で固定した評価の枠組み(panel_eval)をそのまま使う。変えていない点・決めた点(結果を見る前に固定):
  予測の対象   : 翌年(T)の転入超過率(‰)。年 t = T-1 までの情報だけを使う(段2と同じ)
  検証         : (a) 時間で切る(評価年 T = 2020〜2024。学習は目的年 <= T-1 のみ)
                 (b) 評価する都道府県を学習から外す(47分割)+ 時間で切る。長崎の行 = (c)
  比較         : B0 前年値 / B1 直近3年の平均 / Ridge / 勾配ブースティング(モデルの種類は増やさない)
  学習の目的   : 残差 r = y(T) − B1。最終の予測 = B1 + r̂(B1を出発点にする。線形モデルの関数族は変わらない)
  損失         : Huber型(δ = 10‰)。評価指標がMAEで、避難指示区域の町村に数百〜数千‰の外れ値があるため。
  ハイパーパラメータ : 学習期間内の時間順の検証(直近2年を順に検証)のみ。評価年の結果は使わない
  乱数         : seed 固定(SEED)。同じ入力で同じ結果になる

特徴量(予測時点で入手可能な値だけ。根拠と残る問題は ledger/panel_leakage_register.csv):
  - 目的変数のラグ y(t), y(t-1), y(t-2)(欠けたラグは、得られている値の平均で埋める。B1と同じ規則)
  - 国勢調査の項目: 年 t より前に結果が出ている調査(t <= 2020 は 2015年、t >= 2021 は 2020年)
  - 年次の項目: 年 t−1 の値(1年余分に遅らせる。公表時期の確認ができないため)
  - 就業状態(F1102・F1107)は使わない(基本集計より公表が遅いため)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass

import numpy as np

from . import panel_eval as pe
from .common import ROOT

SEED = pe.SEED
HUBER_DELTA = 10.0                       # ‰
N_BINS = 32
RIDGE_ALPHAS = [10.0, 100.0, 1000.0, 10000.0]
GBDT_GRID = [(2, 100), (2, 300), (4, 100), (4, 300)]    # (深さ, 木の数)
GBDT_LR = 0.05
GBDT_MIN_LEAF = 30
GBDT_LAMBDA = 1.0
GBDT_SUBSAMPLE = 0.7
FIRST_TARGET_YEAR = 2018                 # t = 2017 から(t−1 の年次項目が要るため)
MODELS = ["M1_ridge", "M2_gbdt"]
ALL_METHODS = ["B0_previous_year", "B1_mean_last3"] + MODELS

# (特徴量名, 区分, 入力の項目)。区分: lag=目的変数のラグ / census=国勢調査(年tまでに公表) / annual=年次(t−1年の値)
FEATURES = [
    ("y_t", "lag", "net_rate_permille(t)"),
    ("y_t_minus1", "lag", "net_rate_permille(t-1)"),
    ("y_t_minus2", "lag", "net_rate_permille(t-2)"),
    ("log_pop_japanese", "census", "A1102"),
    ("share_under15", "census", "A1301 / A1101"),
    ("share_65plus", "census", "A1303 / A1101"),
    ("share_foreign", "census", "A1700 / A1101"),
    ("household_size", "census", "A1101 / A7101"),
    ("share_single_households", "census", "A810105 / A7101"),
    ("log_density_habitable", "annual", "A1102 / B1103"),
    ("share_habitable_area", "annual", "B1103 / B1101"),
    ("births_per_1000", "annual", "A4101 / A1102"),
    ("deaths_per_1000", "annual", "A4200 / A1102"),
    ("marriages_per_1000", "annual", "A9101 / A1102"),
    ("divorces_per_1000", "annual", "A9201 / A1102"),
    ("kindergarten_pupils_per_1000", "annual", "E1501 / A1102"),
    ("elementary_pupils_per_1000", "annual", "E2501 / A1102"),
    ("junior_high_pupils_per_1000", "annual", "E3501 / A1102"),
    ("high_school_students_per_1000", "annual", "E4501 / A1102"),
    ("hospitals_per_10000", "annual", "I510120 / A1102"),
    ("clinics_per_10000", "annual", "I5102 / A1102"),
    ("dental_clinics_per_10000", "annual", "I5103 / A1102"),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
EXCLUDED_ITEMS = {"F1102": "就業状態等基本集計(国勢調査)", "F1107": "同上"}


# ---------------------------------------------------------------- 特徴量
@dataclass
class Table:
    """予測の1行 = 年 t の情報 → 年 t+1 の転入超過率。"""
    area: np.ndarray       # 地域コード
    pref: np.ndarray       # 都道府県コード
    t: np.ndarray          # 情報の年 t(目的年 = t+1)
    X: np.ndarray          # 特徴量(NaNを含みうる)
    y_t: np.ndarray
    b1: np.ndarray         # B1(直近3年の平均。得られるものの平均)
    y: np.ndarray          # 実績 y(t+1)
    pop_t: np.ndarray
    pop_target: np.ndarray
    ok: np.ndarray         # 除外されていない(t と t+1 とも)かつ y_t・y が得られている

    @property
    def target_year(self) -> np.ndarray:
        return self.t + 1


def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where((b > 0) & ~np.isnan(a) & ~np.isnan(b), a / np.where(b > 0, b, 1), np.nan)
    return out


def build_table(con, scope: str = "main") -> Table:
    """gold_panel_municipality_year から、予測の行(t = 2016〜2023)と特徴量を組み立てる。"""
    ex = "excluded_main" if scope == "main" else "excluded_sensitivity"
    cols = ["births", "deaths", "marriages", "divorces", "kindergarten_pupils", "elementary_pupils",
            "junior_high_pupils", "high_school_students", "general_hospitals", "clinics", "dental_clinics",
            "area_total", "area_habitable", "pop_total_asof", "pop_japanese_asof", "pop_under15_asof",
            "pop_65plus_asof", "pop_foreign_asof", "households_asof", "single_households_asof"]
    q = f"""SELECT area_code, pref_code, year, net_rate_permille, pop_jp_denominator, COALESCE({ex}, TRUE), {", ".join(cols)}
            FROM gold_panel_municipality_year ORDER BY area_code, year"""
    data: dict[tuple[str, int], tuple] = {}
    pref_of: dict[str, str] = {}
    for r in con.execute(q).fetchall():
        data[(r[0], r[2])] = r
        pref_of[r[0]] = r[1]
    ci = {c: 6 + i for i, c in enumerate(cols)}

    def v(row, name):
        x = row[ci[name]]
        return np.nan if x is None else float(x)

    out = {k: [] for k in ("area", "pref", "t", "X", "y_t", "b1", "y", "pop_t", "pop_target", "ok")}
    for (area, year), r in data.items():
        t = year
        nxt = data.get((area, t + 1))
        if nxt is None:
            continue
        prev = data.get((area, t - 1))
        prev2 = data.get((area, t - 2))

        def rate(row):
            return np.nan if row is None or row[3] is None else float(row[3])
        y_t, y_1, y_2 = rate(r), rate(prev), rate(prev2)
        avail = [x for x in (y_t, y_1, y_2) if not np.isnan(x)]
        b1 = float(np.mean(avail)) if avail else np.nan
        y_1f = y_1 if not np.isnan(y_1) else b1       # 欠けたラグは、得られている値の平均で埋める
        y_2f = y_2 if not np.isnan(y_2) else b1
        pop_j = v(r, "pop_japanese_asof")             # 国勢調査(年tまでに公表された調査)の日本人人口
        pop_tot = v(r, "pop_total_asof")
        hh = v(r, "households_asof")
        a = prev                                       # 年次の項目は年 t−1 の値
        if a is None:
            ann = {k: np.nan for k in cols}
        else:
            ann = {k: v(a, k) for k in cols}
        f = [
            y_t, y_1f, y_2f,
            np.log(pop_j) if pop_j > 0 else np.nan,
            _div(v(r, "pop_under15_asof"), pop_tot), _div(v(r, "pop_65plus_asof"), pop_tot),
            _div(v(r, "pop_foreign_asof"), pop_tot), _div(pop_tot, hh), _div(v(r, "single_households_asof"), hh),
            np.log(pop_j / ann["area_habitable"]) if pop_j > 0 and ann["area_habitable"] > 0 else np.nan,
            _div(ann["area_habitable"], ann["area_total"]),
            _div(ann["births"], pop_j) * 1000, _div(ann["deaths"], pop_j) * 1000,
            _div(ann["marriages"], pop_j) * 1000, _div(ann["divorces"], pop_j) * 1000,
            _div(ann["kindergarten_pupils"], pop_j) * 1000, _div(ann["elementary_pupils"], pop_j) * 1000,
            _div(ann["junior_high_pupils"], pop_j) * 1000, _div(ann["high_school_students"], pop_j) * 1000,
            _div(ann["general_hospitals"], pop_j) * 10000, _div(ann["clinics"], pop_j) * 10000,
            _div(ann["dental_clinics"], pop_j) * 10000,
        ]
        yv = rate(nxt)
        out["area"].append(area)
        out["pref"].append(pref_of[area])
        out["t"].append(t)
        out["X"].append(f)
        out["y_t"].append(y_t)
        out["b1"].append(b1)
        out["y"].append(yv)
        out["pop_t"].append(float(r[4]) if r[4] is not None else np.nan)
        out["pop_target"].append(float(nxt[4]) if nxt[4] is not None else np.nan)
        out["ok"].append(not r[5] and not nxt[5] and not np.isnan(y_t) and not np.isnan(yv))
    X = np.array(out["X"], dtype=float)
    return Table(area=np.array(out["area"]), pref=np.array(out["pref"]), t=np.array(out["t"]), X=X,
                 y_t=np.array(out["y_t"]), b1=np.array(out["b1"]), y=np.array(out["y"]),
                 pop_t=np.array(out["pop_t"]), pop_target=np.array(out["pop_target"]),
                 ok=np.array(out["ok"], dtype=bool))


# ---------------------------------------------------------------- モデル
def _impute(X: np.ndarray, med: np.ndarray) -> np.ndarray:
    Z = X.copy()
    i = np.where(np.isnan(Z))
    Z[i] = med[i[1]]
    return Z


def fit_ridge(X: np.ndarray, r: np.ndarray, alpha: float, delta: float = HUBER_DELTA, iters: int = 10) -> dict:
    """Huber型の損失(反復再重み付け)のRidge。説明変数は標準化。切片は罰則なし。"""
    med = np.nanmedian(X, axis=0)
    Z = _impute(X, med)
    mu, sd = Z.mean(0), Z.std(0)
    sd[sd == 0] = 1.0
    A = np.c_[(Z - mu) / sd, np.ones(len(Z))]
    pen = np.eye(A.shape[1]) * alpha
    pen[-1, -1] = 0.0
    w = np.ones(len(r))
    beta = np.zeros(A.shape[1])
    for _ in range(iters):
        Aw = A * w[:, None]
        beta = np.linalg.solve(A.T @ Aw + pen, Aw.T @ r)
        res = np.abs(r - A @ beta)
        w = np.where(res <= delta, 1.0, delta / np.maximum(res, 1e-12))
    return dict(kind="ridge", med=med, mu=mu, sd=sd, beta=beta, alpha=alpha)


def predict_ridge(m: dict, X: np.ndarray) -> np.ndarray:
    Z = (_impute(X, m["med"]) - m["mu"]) / m["sd"]
    return np.c_[Z, np.ones(len(Z))] @ m["beta"]


def _bin_edges(X: np.ndarray) -> list[np.ndarray]:
    qs = np.linspace(0, 1, N_BINS + 1)[1:-1]
    return [np.unique(np.quantile(X[:, j], qs)) for j in range(X.shape[1])]


def _bin(X: np.ndarray, edges: list[np.ndarray]) -> np.ndarray:
    out = np.empty(X.shape, dtype=np.int16)
    for j, e in enumerate(edges):
        out[:, j] = np.searchsorted(e, X[:, j], side="left")
    return out


def _build_tree(Xb, g, depth, gain_acc):
    n, nf = Xb.shape
    node = np.zeros(n, dtype=np.int64)
    feats, thrs = [], []
    for lev in range(depth):
        nn = 1 << lev
        hg = np.empty((nn, nf, N_BINS))
        hc = np.empty((nn, nf, N_BINS))
        for j in range(nf):
            key = node * N_BINS + Xb[:, j]
            hg[:, j, :] = np.bincount(key, weights=g, minlength=nn * N_BINS).reshape(nn, N_BINS)
            hc[:, j, :] = np.bincount(key, minlength=nn * N_BINS).reshape(nn, N_BINS)
        G = hg[:, 0, :].sum(1)
        C = hc[:, 0, :].sum(1)
        GL = np.cumsum(hg, axis=2)[:, :, :-1]
        CL = np.cumsum(hc, axis=2)[:, :, :-1]
        GR = G[:, None, None] - GL
        CR = C[:, None, None] - CL
        gain = (GL ** 2 / (CL + GBDT_LAMBDA) + GR ** 2 / (CR + GBDT_LAMBDA)
                - (G ** 2 / (C + GBDT_LAMBDA))[:, None, None])
        gain[(CL < GBDT_MIN_LEAF) | (CR < GBDT_MIN_LEAF)] = -np.inf
        flat = gain.reshape(nn, -1)
        best = flat.argmax(1)
        bg = flat[np.arange(nn), best]
        f = best // (N_BINS - 1)
        th = best % (N_BINS - 1)
        no = ~np.isfinite(bg) | (bg <= 1e-9)
        f = np.where(no, 0, f)
        th = np.where(no, N_BINS, th)              # 分割しない: 全て左へ
        for k in range(nn):
            if not no[k]:
                gain_acc[f[k]] += bg[k]
        feats.append(f)
        thrs.append(th)
        node = 2 * node + (Xb[np.arange(n), f[node]] > th[node])
    nl = 1 << depth
    sg = np.bincount(node, weights=g, minlength=nl)
    sc = np.bincount(node, minlength=nl)
    return dict(feats=feats, thrs=thrs, leaf=sg / (sc + GBDT_LAMBDA))


def _tree_predict(tree, Xb):
    node = np.zeros(len(Xb), dtype=np.int64)
    ar = np.arange(len(Xb))
    for f, th in zip(tree["feats"], tree["thrs"]):
        node = 2 * node + (Xb[ar, f[node]] > th[node])
    return tree["leaf"][node]


def fit_gbdt(X: np.ndarray, r: np.ndarray, depth: int, n_trees: int, seed: int = SEED,
             delta: float = HUBER_DELTA) -> dict:
    """勾配ブースティング(Huber型の勾配のクリップ。深さ固定の木、行の一部を抽出、seed固定)。"""
    med = np.nanmedian(X, axis=0)
    Z = _impute(X, med)
    edges = _bin_edges(Z)
    Xb = _bin(Z, edges)
    rng = np.random.default_rng(seed)
    f0 = float(np.median(r))
    F = np.full(len(r), f0)
    trees, gain = [], np.zeros(X.shape[1])
    for _ in range(n_trees):
        g = np.clip(r - F, -delta, delta)
        sel = rng.random(len(r)) < GBDT_SUBSAMPLE
        tr = _build_tree(Xb[sel], g[sel], depth, gain)
        F = F + GBDT_LR * _tree_predict(tr, Xb)
        trees.append(tr)
    return dict(kind="gbdt", med=med, edges=edges, f0=f0, trees=trees, depth=depth, gain=gain)


def predict_gbdt(m: dict, X: np.ndarray, n_trees: int | None = None) -> np.ndarray:
    Xb = _bin(_impute(X, m["med"]), m["edges"])
    out = np.full(len(X), m["f0"])
    for tr in m["trees"][: n_trees or len(m["trees"])]:
        out = out + GBDT_LR * _tree_predict(tr, Xb)
    return out


# ---------------------------------------------------------------- 学習・検証
def _val_years(T: int) -> list[int]:
    """ハイパーパラメータの検証に使う目的年。学習期間(目的年 <= T-1)の中の、直近2年。"""
    return [v for v in (T - 2, T - 1) if v >= FIRST_TARGET_YEAR + 1]


def _train_ok(tb: Table) -> np.ndarray:
    return tb.ok & ~np.isnan(tb.X).any(axis=1) & (tb.target_year >= FIRST_TARGET_YEAR)


def tune_and_fit(tb: Table, train: np.ndarray, T: int) -> dict:
    """学習行(train)の中の時間順の検証で、ハイパーパラメータを選び、全学習行で再学習する。
    評価年 T の行・T 以降の目的年は、ここに入らない(呼び出し側が train で保証。assertで確認)。"""
    assert tb.target_year[train].max() <= T - 1
    r = tb.y - tb.b1
    ty = tb.target_year
    folds = [(train & (ty < v), train & (ty == v)) for v in _val_years(T)]
    folds = [(a, b) for a, b in folds if a.sum() > 0 and b.sum() > 0]
    # Ridge
    best_r = (np.inf, None)
    gb_scores = {c: [] for c in GBDT_GRID}
    rd_scores = {a: [] for a in RIDGE_ALPHAS}
    for tr, va in folds:
        for a in RIDGE_ALPHAS:
            m = fit_ridge(tb.X[tr], r[tr], a)
            rd_scores[a].append(float(np.mean(np.abs(predict_ridge(m, tb.X[va]) - r[va]))))
        for depth in sorted({d for d, _ in GBDT_GRID}):
            nmax = max(n for d, n in GBDT_GRID if d == depth)
            m = fit_gbdt(tb.X[tr], r[tr], depth, nmax)
            for d, n in GBDT_GRID:
                if d == depth:
                    gb_scores[(d, n)].append(float(np.mean(np.abs(predict_gbdt(m, tb.X[va], n) - r[va]))))
    if folds:
        alpha = min(RIDGE_ALPHAS, key=lambda a: (np.mean(rd_scores[a]), a))
        cfg = min(GBDT_GRID, key=lambda c: (np.mean(gb_scores[c]), c))
        cv_r, cv_g = float(np.mean(rd_scores[alpha])), float(np.mean(gb_scores[cfg]))
    else:                                               # 検証できない場合の既定値(設計で固定)
        alpha, cfg, cv_r, cv_g = 1000.0, (2, 100), float("nan"), float("nan")
    ridge = fit_ridge(tb.X[train], r[train], alpha)
    gb = fit_gbdt(tb.X[train], r[train], cfg[0], cfg[1])
    return dict(ridge=ridge, gbdt=gb, alpha=alpha, gbdt_depth=cfg[0], gbdt_trees=cfg[1],
                cv_mae_ridge=cv_r, cv_mae_gbdt=cv_g, n_train=int(train.sum()), n_folds=len(folds))


def _task(args):
    tb, train, test, T = args
    fit = tune_and_fit(tb, train, T)
    pr = tb.b1[test] + predict_ridge(fit["ridge"], tb.X[test])
    pg = tb.b1[test] + predict_gbdt(fit["gbdt"], tb.X[test])
    return test, pr, pg, {k: fit[k] for k in ("alpha", "gbdt_depth", "gbdt_trees", "cv_mae_ridge", "cv_mae_gbdt",
                                              "n_train", "n_folds")}


def evaluate_models(con, scope: str = "main", workers: int = 6, keep_models: bool = False) -> dict:
    """段2の評価行(pe.load_rows)と同じ行で、(a) と (b) の予測を作る。
    戻り値: rows(段2と同じ)、a / b = {手法: 予測の配列}、hyper = 選ばれたハイパーパラメータ、(keep_models: a の T ごとのモデル)。"""
    from concurrent.futures import ProcessPoolExecutor
    rows = pe.load_rows(con, scope)
    xs = pe.all_cross_sections(con, scope)
    tb = build_table(con, scope)
    pos = {(a, int(t)): i for i, (a, t) in enumerate(zip(tb.area, tb.t))}
    ridx = np.array([pos[(r.area_code, r.t)] for r in rows])       # 段2の行 → 表の行
    assert np.all(tb.ok[ridx]), "段2の評価行が、特徴量の表で有効でない"
    assert np.allclose(tb.y[ridx], [r.y for r in rows]) and np.allclose(tb.y_t[ridx], [r.y_t for r in rows])
    base = pe.predict(rows, xs, "a")
    tr_ok = _train_ok(tb)
    n = len(rows)
    res = {"rows": rows, "scope": scope, "n_features": len(FEATURE_NAMES),
           "a": {m: np.full(n, np.nan) for m in ALL_METHODS}, "b": {m: np.full(n, np.nan) for m in ALL_METHODS},
           "hyper": []}
    for s in ("a", "b"):
        res[s]["B0_previous_year"] = base["B0_previous_year"].copy()
        res[s]["B1_mean_last3"] = base["B1_mean_last3"].copy()
    ty_rows = np.array([r.t + 1 for r in rows])
    pref_rows = np.array([r.pref for r in rows])
    tasks, meta = [], []
    for T in pe.EVAL_YEARS:
        train_a = tr_ok & (tb.target_year <= T - 1)
        test_mask = ty_rows == T
        tasks.append((tb, train_a, ridx[test_mask], T))
        meta.append(("a", T, "all", np.where(test_mask)[0]))
        for P in sorted(set(pref_rows[test_mask])):
            sel = test_mask & (pref_rows == P)
            train_b = train_a & (tb.pref != P)
            tasks.append((tb, train_b, ridx[sel], T))
            meta.append(("b", T, P, np.where(sel)[0]))
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            outs = list(ex.map(_task, tasks, chunksize=1))
    else:
        outs = [_task(t) for t in tasks]
    for (setting, T, P, where), (_, pr, pg, hp) in zip(meta, outs):
        res[setting]["M1_ridge"][where] = pr
        res[setting]["M2_gbdt"][where] = pg
        res["hyper"].append(dict(scope=scope, setting=setting, eval_year=T, held_out_pref=P, **hp))
    for s in ("a", "b"):
        for m in MODELS:
            assert not np.isnan(res[s][m]).any(), (s, m)
    if keep_models:
        res["fits"] = {T: tune_and_fit(tb, tr_ok & (tb.target_year <= T - 1), T) for T in pe.EVAL_YEARS}
        res["table"] = tb
        res["ridx"] = ridx
    return res


# ---------------------------------------------------------------- 区間・重要度
def cluster_bootstrap(rows, preds: dict[str, np.ndarray], pairs: list[tuple[str, str]], cluster: np.ndarray,
                      n_boot: int = pe.N_BOOT, seed: int = SEED) -> dict:
    """クラスタ(市町または市区町村)を単位に再抽出し、MAEの改善率 1 − MAE(手法)/MAE(基準) の95%区間を出す。
    pairs = [(手法, 基準), ...]。同じ再抽出を全ての組に使う(seed固定)。"""
    y = np.array([r.y for r in rows])
    uniq, inv = np.unique(cluster, return_inverse=True)
    k = len(uniq)
    cnt = np.bincount(inv, minlength=k).astype(float)
    err = {m: np.abs(preds[m] - y) for m in preds}
    sums = {m: np.bincount(inv, weights=e, minlength=k) for m, e in err.items()}
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, k, size=(n_boot, k))
    n_tot = cnt[draws].sum(1)
    mae = {m: sums[m][draws].sum(1) / n_tot for m in sums}
    out = {}
    for m, b in pairs:
        v = 1 - mae[m] / mae[b]
        out[(m, b)] = (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
    return out


def permutation_importance(fit: dict, tb: Table, test_idx: np.ndarray, seed: int = SEED, repeats: int = 5) -> list[dict]:
    """評価年の行で、特徴量を並べ替えたときのMAEの増加(‰)。相関の強さの目安で、因果ではない。"""
    X = tb.X[test_idx]
    r = tb.y[test_idx] - tb.b1[test_idx]
    rng = np.random.default_rng(seed)
    base = {"M1_ridge": np.mean(np.abs(predict_ridge(fit["ridge"], X) - r)),
            "M2_gbdt": np.mean(np.abs(predict_gbdt(fit["gbdt"], X) - r))}
    out = []
    for j, name in enumerate(FEATURE_NAMES):
        inc = {"M1_ridge": [], "M2_gbdt": []}
        for _ in range(repeats):
            Xp = X.copy()
            Xp[:, j] = rng.permutation(Xp[:, j])
            inc["M1_ridge"].append(np.mean(np.abs(predict_ridge(fit["ridge"], Xp) - r)) - base["M1_ridge"])
            inc["M2_gbdt"].append(np.mean(np.abs(predict_gbdt(fit["gbdt"], Xp) - r)) - base["M2_gbdt"])
        out.append(dict(feature=name, perm_mae_increase_ridge=float(np.mean(inc["M1_ridge"])),
                        perm_mae_increase_gbdt=float(np.mean(inc["M2_gbdt"]))))
    return out


# ---------------------------------------------------------------- リークの台帳
LEAK_REGISTER = [
    # (id, 項目, リークの可能性, 対策(決めたこと), 残る問題, 状態)
    ("L01", "目的変数の年tの値の公表時期", "住民基本台帳人口移動報告の年tの結果は、年tの終了後(翌年初め。日付は未確認)に公表される。「年tまでの情報」で翌年を予測する段2の枠組みは、年初に予測する設定より楽観的になりうる",
     "段2の枠組み(年tまでの情報)を変えない。基準手法(B0・B1)も同じ入力を使うため、手法間の比較は公平", "年初時点の厳密なリアルタイムの精度は未検証(SSDSEの版で考えると、年tの値の利用は2年後になる)", "未検証"),
    ("L02", "SSDSE-Aの版の公開時期", "各版は、版の年の6月ごろ公開(2026年版は2026-06-30)。転入者数・転出者数は『版の年−2』、出生数・死亡数などは2023年版から『版の年−3』。最新の版(2026年版)の値を、過去の予測時点で使うことになる",
     "値は、版の年ではなく参照年で整列した。複数の版にある同じ年度の41,784件は全て一致(改定なし。検証P11)ため、値は予測時点の版でも同じ", "版の遅れ(2〜3年)は、予測時点の入手可能性の評価に使っていない。年次の項目は1年余分に遅らせた(L06)", "確認済み(改定0件)"),
    ("L03", "国勢調査の分母(評価の目的変数)", "2020年の人口を、2019年以前の予測に使うと、将来の情報が入る",
     "目的変数の分母は、2016〜2019年が2015年、2020〜2024年が2020年の国勢調査(段2のまま)。評価年T=2020の学習ラベル(目的年<=2019)と特徴量は、2015年の人口のみ。2020年の人口は、目的年>=2020のラベル(定義)にのみ入る", "評価年のラベルは2020年の人口で定義される(段2の限界)。分母の切り替え(2019→2020年)の不連続は残る", "確認済み(テストで検証)"),
    ("L04", "国勢調査の特徴量(人口・年齢・世帯・外国人)", "調査年の結果は、調査の翌年以降に公表される(2020年の結果: 2021年6月の速報と同年11月の基本集計。日付は私の知識で未確認)",
     "t<=2020 は2015年、t>=2021 は2020年(段2の census_year_asof)。年tの終了時点で、基本集計が公表されている調査だけを使う", "t=2021(目的年2022)で、2020年の基本集計の公表日(2021年11月ごろ。未確認)が年末より前かどうかは確認していない", "未確認"),
    ("L05", "就業状態(F1102 就業者数・F1107 完全失業者数)", "就業状態等基本集計は、人口等基本集計より後に公表される(2020年の結果は2022年5月ごろ。未確認)",
     "特徴量に使わない(段2のパネルには列がある)", "就業・失業の関連は見ていない", "対策済み"),
    ("L06", "年次の項目(出生・死亡・婚姻・離婚・学校・医療施設・面積)", "各統計の市区町村別の結果の公表時期は、年t内か翌年かが項目で異なる(確認していない)",
     "全て、年 t−1 の値を使う(1年余分に遅らせる)。t=2016 の行は、t−1 の値がなく学習に使えない(目的年2017は学習から外れる)", "公表がさらに遅い項目があるか(2年以上)は未確認", "対策済み(未確認の残り)"),
    ("L07", "学習期間(時間のリーク)", "評価年T以降の目的年のラベルや、同年の他県のデータを学習に使うと、同年のショックを共有する",
     "学習は、目的年 <= T−1 の行のみ。(b)は、評価する都道府県を学習から外す。tune_and_fit が最大の目的年を assert。テストで、T以降のラベルを書き換えても予測が変わらないことを確認", "なし", "確認済み(テスト)"),
    ("L08", "ハイパーパラメータの選択", "評価年の結果を見て選ぶと、評価の使い回しになる",
     "学習期間内の時間順の検証(直近2年)のみ。グリッドは固定(コード内)。(b)の各分割も、学習行(評価する都道府県を除く)の中だけで選ぶ", "なし", "確認済み"),
    ("L09", "標準化・分位点の境界・欠損の補完", "全期間・全行から計算すると、評価行の情報が入る",
     "学習行のみから計算(fit_ridge・fit_gbdt の内部)。評価行の欠損は、学習行の中央値で補う", "なし", "確認済み"),
    ("L10", "同年の横断面の統計(B2・B3)", "年tの全国の統計は、年tの情報で、翌年の予測には使える(段2)。評価対象の都道府県を含むと、(b)で漏れる",
     "モデルは横断面の統計を特徴量に使わない。B2・B3はモデルとの比較の対象にしない(段2の結果は変えない)", "なし", "確認済み"),
    ("L11", "除外・フラグの定義(双葉町・避難指示区域の候補12町村)", "評価の結果を見てから除外を決めると、選択の漏れになる",
     "主の集計は、確認できた除外(双葉町・人口0・コード変更)のみ。候補12町村は、段2で名称をコードに書いた後の事後の補助的な分析として、感度分析に分けて報告(段2から継続。混ぜない)", "候補の名称は私の知識(国・県の一覧との照合は未確認)", "未確認(一覧との照合)"),
    ("L12", "評価年t=2020の入力の分母", "y(2020)(目的年2021の入力)は、2020年の国勢調査の人口を分母にしている。2020年の結果が公表される前(2021年初め)には作れない",
     "枠組み(段2)を変えない。B0・B1・モデルとも同じ入力。目的年2021の評価にのみ影響", "影響の大きさは未検証", "未検証"),
    ("L13", "地域コードの変更(那珂川町→那珂川市)", "コードの寄せ方で、将来の情報が入る可能性",
     "段2で除外(code_change)。モデルの学習・評価に入らない", "なし", "確認済み"),
    ("L14", "都道府県の識別", "都道府県の固定効果を入れると、(b)の「学習していない地域」の検証と整合しない",
     "都道府県のコード・名称を特徴量に使わない(FEATURESに無い)", "地域の特徴は、年齢構成・規模・施設などの代理変数で入る", "確認済み"),
]


def write_leak_register(path=None) -> None:
    path = path or ROOT / "ledger" / "panel_leakage_register.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "item", "leak_risk", "countermeasure", "remaining_issue", "status"])
        w.writerows(LEAK_REGISTER)
    feat = ROOT / "ledger" / "panel_model_features.csv"
    with open(feat, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["feature", "kind", "source_items", "time_rule"])
        rule = {"lag": "年t・t-1・t-2の目的変数(欠けは得られている値の平均)",
                "census": "年tまでに結果が公表されている国勢調査(t<=2020: 2015年、t>=2021: 2020年)",
                "annual": "年 t−1 の値(1年余分に遅らせる)"}
        for name, kind, src in FEATURES:
            w.writerow([name, kind, src, rule[kind]])
        for code, why in EXCLUDED_ITEMS.items():
            w.writerow([f"(未使用){code}", "excluded", code, f"使わない: {why}は公表が遅い"])
