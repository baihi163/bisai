# -*- coding: utf-8 -*-
"""
问题2：储能与 EV 寿命权重的 3D 运行成本曲面

- 若结果中存在「ess_deg_weight ≠ ev_deg_weight」的充分交叉扫描点，则用 griddata 在真实 (X,Y) 网格上插值。
- 否则（当前仓库常态）：仅有对角线扫描，采用 PCHIP(operation_cost vs λ) 与 λ̄=(λ_ESS+λ_EV)/2 的光滑延拓，
  图题注明非独立双变量 MILP 网格真解，避免虚构二次响应面。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import LightSource
from matplotlib.ticker import FormatStrFormatter, LinearLocator
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

_here = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "problem2_lifecycle").is_dir()),
    None,
)
if REPO_ROOT is None:
    raise FileNotFoundError("未找到 results/problem2_lifecycle。")

P2_ROOT = REPO_ROOT / "results" / "problem2_lifecycle"
SCAN_AUTO = P2_ROOT / "scans" / "scan_auto_weight_scan"
FIG_OUT_DIR = P2_ROOT / "figures"


def _pick_primary_scan() -> Path:
    p = SCAN_AUTO / "weight_scan_summary.csv"
    if p.is_file():
        return p
    cands = list((P2_ROOT / "tables").glob("weight_scan_summary_*.csv"))
    if not cands:
        raise FileNotFoundError("未找到 weight_scan_summary*.csv")
    return max(cands, key=lambda x: x.stat().st_mtime)


def _try_cross_weight_dataframe() -> tuple[pd.DataFrame | None, Path | None]:
    """寻找含非对角 (λ_ESS≠λ_EV) 且点数足够的扫描表。"""
    best: tuple[pd.DataFrame | None, Path | None] = (None, None)
    best_n = 0
    for path in sorted(P2_ROOT.rglob("weight_scan_summary*.csv")):
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
        except OSError:
            continue
        need = {"ess_deg_weight", "ev_deg_weight", "operation_cost"}
        if not need.issubset(df.columns):
            continue
        if "solver_status" in df.columns:
            df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
        df = df.dropna(subset=list(need))
        d = (df["ess_deg_weight"].astype(float) - df["ev_deg_weight"].astype(float)).abs()
        off = df.loc[d > 1e-5]
        if len(off) >= 8:
            if len(off) > best_n:
                best_n = len(off)
                best = (off, path)
    return best


def _smooth_cost_vs_lambda(lam: np.ndarray, cost: np.ndarray, lam_q: np.ndarray) -> np.ndarray:
    lam = np.asarray(lam, dtype=float)
    cost = np.asarray(cost, dtype=float)
    lam_q = np.asarray(lam_q, dtype=float)
    try:
        from scipy.interpolate import PchipInterpolator

        return np.asarray(PchipInterpolator(lam, cost, extrapolate=True)(lam_q), dtype=float)
    except ImportError:
        n_fine = max(200, len(lam) * 50)
        lf = np.linspace(float(lam.min()), float(lam.max()), n_fine)
        cf = np.interp(lf, lam, cost)
        win = max(3, min(15, n_fine // 8))
        if win % 2 == 0:
            win += 1
        ker = np.ones(win, dtype=float) / float(win)
        cs = np.convolve(cf, ker, mode="same")
        return np.interp(lam_q, lf, cs)


def plot_sensitivity_surface() -> None:
    cross_df, cross_path = _try_cross_weight_dataframe()
    grid_n = 90
    x = np.linspace(0.0, 2.0, grid_n)
    y = np.linspace(0.0, 2.0, grid_n)
    X, Y = np.meshgrid(x, y)

    subtitle = ""
    if cross_df is not None and cross_path is not None:
        try:
            from scipy.interpolate import griddata
        except ImportError:
            cross_df, cross_path = None, None

    if cross_df is not None and cross_path is not None:
        xd = cross_df["ess_deg_weight"].to_numpy(dtype=float)
        yd = cross_df["ev_deg_weight"].to_numpy(dtype=float)
        zd = cross_df["operation_cost"].to_numpy(dtype=float)
        pts = np.column_stack([xd, yd])
        Z = griddata(pts, zd, (X, Y), method="linear")
        nan_mask = np.isnan(Z)
        if np.any(nan_mask):
            Z_near = griddata(pts, zd, (X, Y), method="nearest")
            Z = np.where(nan_mask, Z_near, Z)
        subtitle = f"（真实交叉扫描插值：{cross_path.relative_to(REPO_ROOT)}）"
        z_known = zd
        x_known, y_known = xd, yd
    else:
        path = _pick_primary_scan()
        df = pd.read_csv(path)
        if "solver_status" in df.columns:
            df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
        df = df.dropna(subset=["ess_deg_weight", "ev_deg_weight", "operation_cost"]).sort_values(
            "ess_deg_weight"
        )
        lam = df["ess_deg_weight"].to_numpy(dtype=float)
        cost = df["operation_cost"].to_numpy(dtype=float)
        lam_bar = (X + Y) / 2.0
        lam_bar = np.clip(lam_bar, float(lam.min()), float(lam.max()))
        Z = _smooth_cost_vs_lambda(lam, cost, lam_bar.ravel()).reshape(X.shape)
        x_known = df["ess_deg_weight"].to_numpy(dtype=float)
        y_known = df["ev_deg_weight"].to_numpy(dtype=float)
        z_known = df["operation_cost"].to_numpy(dtype=float)
        subtitle = f"（对角扫描 + $(\\lambda_{{ESS}}+\\lambda_{{EV}})/2$ 光滑延拓：{path.relative_to(REPO_ROOT)}）"

    z_min_plot = float(np.min(Z)) - 0.02 * (float(np.max(Z)) - float(np.min(Z)) + 1e-9)

    fig = plt.figure(figsize=(12, 9), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.98, 0.98, 0.98, 1.0))
        axis.pane.set_edgecolor("#d0d0d0")
    ax.grid(True, color="#c8c8c8", linestyle="-", linewidth=0.4, alpha=0.85)

    ls = LightSource(azdeg=225, altdeg=40)
    rgba = ls.shade(Z, cmap=cm.viridis, vert_exag=0.1, blend_mode="soft")
    surf = ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=rgba,
        linewidth=0,
        antialiased=True,
        rstride=1,
        cstride=1,
        shade=False,
    )

    ax.contourf(X, Y, Z, zdir="z", offset=z_min_plot, cmap=cm.viridis, alpha=0.35, levels=14)

    norm_z = plt.Normalize(vmin=float(np.min(Z)), vmax=float(np.max(Z)))
    ax.scatter(
        x_known,
        y_known,
        z_known,
        c=z_known,
        cmap=cm.viridis,
        norm=norm_z,
        s=36,
        alpha=0.95,
        edgecolors=(0.2, 0.2, 0.2, 0.35),
        linewidths=0.3,
        depthshade=True,
        label="扫描真值点",
        zorder=10,
    )

    ax.set_xlabel(r"固定储能寿命权重 ($\lambda_{ESS}$)", fontweight="bold", labelpad=12)
    ax.set_ylabel(r"电动汽车寿命权重 ($\lambda_{EV}$)", fontweight="bold", labelpad=12)
    ax.set_zlabel("微电网纯运行成本 (元)", fontweight="bold", labelpad=12)
    ax.zaxis.set_major_locator(LinearLocator(6))
    ax.zaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.set_zlim(z_min_plot, float(np.max(Z)) + 0.02 * (float(np.max(Z)) - float(np.min(Z)) + 1e-9))
    ax.view_init(elev=28, azim=-50)

    sm = cm.ScalarMappable(cmap=cm.viridis, norm=norm_z)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.52, pad=0.09)
    cbar.set_label("纯运行成本 (元)", fontweight="bold")

    ax.set_title(
        "微电网运行成本对储能与车辆寿命权重的灵敏度" + subtitle,
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.legend(loc="upper left", fontsize=9)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_sensitivity_3d_surface.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11
    plt.rcParams["figure.dpi"] = 600
    plot_sensitivity_surface()


if __name__ == "__main__":
    main()
