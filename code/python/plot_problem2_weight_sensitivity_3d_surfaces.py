# -*- coding: utf-8 -*-
"""问题二：寿命权重二维网格灵敏度 — 三维曲面图（仅完整 ess×ev 网格时出图）。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

_here = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "problem2_lifecycle").is_dir()),
    None,
)
if REPO_ROOT is None:
    raise FileNotFoundError("未找到 results/problem2_lifecycle，请确认脚本位于仓库内。")

FIG_DIR = REPO_ROOT / "results" / "figures" / "problem2"


def _discover_summary_csvs() -> list[Path]:
    root_p2 = REPO_ROOT / "results" / "problem2_lifecycle"
    scans = root_p2 / "scans"
    tables = root_p2 / "tables"
    paths: list[Path] = []
    if scans.is_dir():
        paths.extend(scans.rglob("weight_scan_summary*.csv"))
    if tables.is_dir():
        paths.extend(tables.glob("weight_scan_summary*.csv"))
    out: list[Path] = []
    seen: set[str] = set()
    for p in sorted(paths, key=lambda x: str(x).lower()):
        k = str(p.resolve())
        if k not in seen and p.is_file():
            seen.add(k)
            out.append(p)
    return out


def _resolve_metric_columns(df: pd.DataFrame) -> dict[str, str]:
    need = {
        "operation_cost": "operation_cost",
        "ev_throughput": None,
        "ess_throughput": None,
    }
    cols = set(df.columns.astype(str))
    if "operation_cost" not in cols:
        raise KeyError("缺少列 operation_cost")
    if "ev_throughput" in cols:
        need["ev_throughput"] = "ev_throughput"
    elif "ev_throughput_kwh" in cols:
        need["ev_throughput"] = "ev_throughput_kwh"
    if "ess_throughput" in cols:
        need["ess_throughput"] = "ess_throughput"
    elif "ess_throughput_kwh" in cols:
        need["ess_throughput"] = "ess_throughput_kwh"
    if need["ev_throughput"] is None:
        raise KeyError("缺少列 ev_throughput 或 ev_throughput_kwh")
    if need["ess_throughput"] is None:
        raise KeyError("缺少列 ess_throughput 或 ess_throughput_kwh")
    return need  # type: ignore[return-value]


def _check_full_grid(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    req = {"ess_deg_weight", "ev_deg_weight"}
    miss = req - set(df.columns.astype(str))
    if miss:
        raise KeyError(f"缺少列: {sorted(miss)}")
    sub = df[["ess_deg_weight", "ev_deg_weight"]].copy()
    sub["ess_deg_weight"] = pd.to_numeric(sub["ess_deg_weight"], errors="coerce")
    sub["ev_deg_weight"] = pd.to_numeric(sub["ev_deg_weight"], errors="coerce")
    if sub.isna().any().any():
        raise ValueError("ess_deg_weight / ev_deg_weight 存在非数值。")
    U = np.sort(sub["ess_deg_weight"].unique())
    V = np.sort(sub["ev_deg_weight"].unique())
    pairs = set(zip(sub["ess_deg_weight"].round(12), sub["ev_deg_weight"].round(12)))
    expected = {(float(u), float(v)) for u in U for v in V}
    got = {(float(a), float(b)) for a, b in pairs}
    if len(sub) != len(expected) or got != expected:
        missing = sorted(expected - got, key=lambda t: (t[0], t[1]))
        extra = sorted(got - expected, key=lambda t: (t[0], t[1]))
        dup = sub.duplicated(subset=["ess_deg_weight", "ev_deg_weight"]).any()
        msg = (
            "不能绘制真正的三维曲面图：扫描结果不构成 ess_deg_weight × ev_deg_weight 的完整二维组合网格。\n"
            f"唯一 ess 个数={len(U)}，唯一 ev 个数={len(V)}，期望组合数={len(expected)}，实际行数={len(sub)}。\n"
            f"存在重复(ess,ev)行: {dup}。\n"
        )
        if missing:
            msg += f"缺失组合数={len(missing)}，示例(前12个): {missing[:12]}\n"
        if extra:
            msg += f"非网格内多余组合数={len(extra)}。\n"
        msg += (
            "当前仓库内寿命权重扫描多为对角扫描(ess_deg_weight=ev_deg_weight)，"
            "需重新运行独立二维网格扫描并汇总到 CSV 后再出图。"
        )
        raise RuntimeError(msg)
    return U, V


def _pivot_z(df: pd.DataFrame, u: np.ndarray, v: np.ndarray, col: str) -> np.ndarray:
    z = np.full((len(v), len(u)), np.nan, dtype=float)
    for i, ev in enumerate(v):
        for j, es in enumerate(u):
            m = (df["ess_deg_weight"].astype(float) == es) & (df["ev_deg_weight"].astype(float) == ev)
            zz = df.loc[m, col].astype(float)
            if len(zz) != 1:
                raise RuntimeError(f"组合 (ess={es}, ev={ev}) 匹配行数={len(zz)}，期望 1。")
            z[i, j] = float(zz.iloc[0])
    return z


def _load_first_full_grid_csv() -> tuple[pd.DataFrame, Path, np.ndarray, np.ndarray]:
    cands = _discover_summary_csvs()
    if not cands:
        raise FileNotFoundError(
            "未找到任何 weight_scan_summary*.csv（已搜索 results/problem2_lifecycle/scans/ 与 tables/）。"
        )
    errors: list[str] = []
    for p in cands:
        try:
            df = pd.read_csv(p)
            U, V = _check_full_grid(df)
            _resolve_metric_columns(df)
            return df, p, U, V
        except (RuntimeError, KeyError, ValueError) as e:
            errors.append(f"{p.relative_to(REPO_ROOT)}: {e}")
            continue
    raise RuntimeError(
        "不能绘制真正的三维曲面图：在已发现的汇总文件中，没有任何一个文件同时满足：\n"
        "  (1) 含 ess_deg_weight、ev_deg_weight；\n"
        "  (2) 构成二者笛卡尔积的完整二维网格；\n"
        "  (3) 含 operation_cost 及 ev/ess 吞吐量列。\n"
        "逐文件原因摘要：\n  - "
        + "\n  - ".join(errors[:20])
        + ("\n  ..." if len(errors) > 20 else "")
    )


def _plot_one_surface(
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    df: pd.DataFrame,
    zcol: str,
    title: str,
    zlabel: str,
    cbar_label: str,
    stem: str,
) -> None:
    z_span = float(np.nanmax(Z) - np.nanmin(Z)) + 1e-12
    z_floor = float(np.nanmin(Z)) - 0.06 * z_span

    fig = plt.figure(figsize=(9.2, 7.2), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.99, 0.99, 0.99, 1.0))
        axis.pane.set_edgecolor("#dddddd")
    ax.grid(True, color="#cccccc", linewidth=0.35, alpha=0.75)

    surf = ax.plot_surface(
        X,
        Y,
        Z,
        cmap=cm.cividis,
        linewidth=0,
        antialiased=True,
        rstride=1,
        cstride=1,
        alpha=0.92,
        shade=True,
    )

    xs = df["ess_deg_weight"].astype(float).values
    ys = df["ev_deg_weight"].astype(float).values
    zs = df[zcol].astype(float).values
    ax.scatter(xs, ys, zs, color="#c0392b", s=36, depthshade=True, label="扫描点", zorder=5)

    ax.contourf(X, Y, Z, zdir="z", offset=z_floor, cmap=cm.cividis, alpha=0.35, levels=14, antialiased=True)
    ax.contour(X, Y, Z, zdir="z", offset=z_floor, colors="#666666", linewidths=0.35, alpha=0.55, levels=10)

    ax.set_xlabel("ESS 寿命权重 ess_deg_weight", fontweight="bold", labelpad=10)
    ax.set_ylabel("EV 寿命权重 ev_deg_weight", fontweight="bold", labelpad=10)
    ax.set_zlabel(zlabel, fontweight="bold", labelpad=12)
    ax.set_title(title, fontweight="bold", fontsize=12, pad=12)
    ax.view_init(elev=26, azim=-55)
    try:
        ax.set_box_aspect((1, 1, 0.55 + 0.15 * (z_span / (np.nanmax(Z) + 1e-9))))
    except Exception:
        pass

    fig.colorbar(surf, ax=ax, shrink=0.55, pad=0.08, label=cbar_label)
    ax.legend(loc="upper left", fontsize=9)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    base = FIG_DIR / stem
    fig.savefig(base.with_suffix(".png"), dpi=400, bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10

    df, src, U, V = _load_first_full_grid_csv()
    cols = _resolve_metric_columns(df)

    X, Y = np.meshgrid(U, V)
    z_op = _pivot_z(df, U, V, cols["operation_cost"])
    z_ev = _pivot_z(df, U, V, cols["ev_throughput"])
    z_es = _pivot_z(df, U, V, cols["ess_throughput"])

    meta = f"（数据：{src.relative_to(REPO_ROOT)}）"

    _plot_one_surface(
        X,
        Y,
        z_op,
        df,
        cols["operation_cost"],
        "灵敏度曲面：运行成本 operation_cost" + meta,
        "operation_cost",
        "operation_cost",
        "sensitivity_surface_operation_cost",
    )
    _plot_one_surface(
        X,
        Y,
        z_ev,
        df,
        cols["ev_throughput"],
        "灵敏度曲面：EV 吞吐 ev_throughput" + meta,
        "ev_throughput",
        "ev_throughput",
        "sensitivity_surface_ev_throughput",
    )
    _plot_one_surface(
        X,
        Y,
        z_es,
        df,
        cols["ess_throughput"],
        "灵敏度曲面：ESS 吞吐 ess_throughput" + meta,
        "ess_throughput",
        "ess_throughput",
        "sensitivity_surface_ess_throughput",
    )


if __name__ == "__main__":
    main()
