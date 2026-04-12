# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 三维曲面分析图 (3D Surface Plot)

当前权重扫描为对角线 ess_deg_weight = ev_deg_weight，无完整 (λ_ESS, λ_EV) 网格真值。
曲面采用：混合权重 (λ_ESS + λ_EV) / 2，对 operation_cost(λ) 使用 PCHIP 样条（无 scipy 时为一维滑动平均）
得到光滑 Z(λ_ESS, λ_EV)；在扫描 λ 处仍过真值点；其余为展示性延拓。
真实求解点以三维散点标出。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import LightSource, LinearSegmentedColormap
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

_here = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "problem2_lifecycle").is_dir()),
    None,
)
if REPO_ROOT is None:
    raise FileNotFoundError("未找到 results/problem2_lifecycle，请确认脚本位于仓库内。")

P2_RESULTS_DIR = REPO_ROOT / "results" / "problem2_lifecycle"
SCAN_AUTO = P2_RESULTS_DIR / "scans" / "scan_auto_weight_scan"
FIG_OUT_DIR = P2_RESULTS_DIR / "figures"

# 曲面 / 散点 / 色条统一：灰米 → 淡薄荷绿
CMAP_SURFACE = LinearSegmentedColormap.from_list(
    "surface_gray_mint",
    ["#BDB9B8", "#DFEBD5"],
    N=256,
)


def _pick_weight_scan_csv() -> Path:
    primary = SCAN_AUTO / "weight_scan_summary.csv"
    if primary.is_file():
        return primary
    cands = list((P2_RESULTS_DIR / "tables").glob("weight_scan_summary_*.csv"))
    if not cands:
        raise FileNotFoundError("未找到 weight_scan_summary.csv 或 tables/weight_scan_summary_*.csv")
    return max(cands, key=lambda p: p.stat().st_mtime)


def get_latest_scan_data() -> pd.DataFrame | None:
    try:
        path = _pick_weight_scan_csv()
    except FileNotFoundError as e:
        print(str(e))
        return None
    df = pd.read_csv(path)
    need = {"operation_cost", "ess_deg_weight", "ev_deg_weight"}
    if not need.issubset(df.columns):
        raise KeyError(f"{path} 缺少列: {sorted(need - set(df.columns))}")
    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    return df.dropna(subset=["operation_cost", "ess_deg_weight", "ev_deg_weight"]).sort_values(
        "ess_deg_weight"
    ).reset_index(drop=True)


def _smooth_cost_vs_lambda(lam: np.ndarray, cost: np.ndarray, lam_q: np.ndarray) -> np.ndarray:
    """在 λ 上得到光滑 cost(λ)，严格穿过已知 (lam, cost) 结点。"""
    lam = np.asarray(lam, dtype=float)
    cost = np.asarray(cost, dtype=float)
    lam_q = np.asarray(lam_q, dtype=float)
    try:
        from scipy.interpolate import PchipInterpolator

        p = PchipInterpolator(lam, cost, extrapolate=True)
        return np.asarray(p(lam_q), dtype=float)
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


def plot_3d_surface() -> None:
    df = get_latest_scan_data()
    if df is None or len(df) < 2:
        print("未找到数据或数据不足，请检查路径。")
        return

    lam = df["ess_deg_weight"].to_numpy(dtype=float)
    cost = df["operation_cost"].to_numpy(dtype=float)
    x_known = df["ess_deg_weight"].to_numpy(dtype=float)
    y_known = df["ev_deg_weight"].to_numpy(dtype=float)
    z_known = df["operation_cost"].to_numpy(dtype=float)

    w_min = float(np.min(np.concatenate([x_known, y_known])))
    w_max = float(np.max(np.concatenate([x_known, y_known])))
    pad = 0.02 * (w_max - w_min + 1e-9)
    lo, hi = w_min - pad, w_max + pad

    grid_n = 120
    grid_x, grid_y = np.mgrid[lo : hi : complex(0, grid_n), lo : hi : complex(0, grid_n)]
    lam_blend = (grid_x + grid_y) / 2.0
    lam_blend = np.clip(lam_blend, float(np.min(lam)), float(np.max(lam)))
    grid_z = _smooth_cost_vs_lambda(lam, cost, lam_blend.ravel()).reshape(grid_x.shape)

    z_min = float(np.min(grid_z))
    z_max = float(np.max(grid_z))
    z_span = max(z_max - z_min, 1e-9)

    fig = plt.figure(figsize=(11.5, 8.2), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")

    # 浅色坐标“墙面”+ 细网格（期刊风底图）
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.98, 0.98, 0.98, 1.0))
        axis.pane.set_edgecolor("#d0d0d0")
        axis.pane.set_alpha(0.92)
    ax.grid(True, color="#c8c8c8", linestyle="-", linewidth=0.45, alpha=0.85)

    # 光照着色曲面（比单色 cmap 更有体积感）
    ls = LightSource(azdeg=225, altdeg=42)
    rgba = ls.shade(grid_z, cmap=CMAP_SURFACE, vert_exag=0.12, blend_mode="soft")
    surf = ax.plot_surface(
        grid_x,
        grid_y,
        grid_z,
        facecolors=rgba,
        linewidth=0,
        antialiased=True,
        rstride=1,
        cstride=1,
        shade=False,
    )

    # 顶部半透明“参考平面”（浅白网格，类似 tipping-point 示意）
    z_plane = z_max + 0.045 * z_span
    zz = np.full_like(grid_x, z_plane, dtype=float)
    ax.plot_surface(
        grid_x,
        grid_y,
        zz,
        color="white",
        alpha=0.18,
        edgecolor="#a8a8a8",
        linewidth=0.35,
        rstride=max(2, grid_n // 24),
        cstride=max(2, grid_n // 24),
        shade=False,
    )

    # 真值点：按成本着色与曲面同一色标，略小、弱描边
    norm_pts = plt.Normalize(vmin=z_min, vmax=z_max)
    ax.scatter(
        x_known,
        y_known,
        z_known,
        c=z_known,
        cmap=CMAP_SURFACE,
        norm=norm_pts,
        s=38,
        alpha=0.92,
        edgecolors=(0.2, 0.2, 0.2, 0.35),
        linewidths=0.35,
        depthshade=True,
        label="扫描真值点",
        zorder=10,
    )

    ax.set_xlabel(r"固定储能寿命权重 ($\lambda_{ESS}$)", fontweight="bold", labelpad=12)
    ax.set_ylabel(r"电动汽车寿命权重 ($\lambda_{EV}$)", fontweight="bold", labelpad=12)
    ax.set_zlabel("微电网纯运行成本 (元)", fontweight="bold", labelpad=12)
    ax.view_init(elev=22, azim=-52)
    ax.set_zlim(z_min - 0.02 * z_span, z_plane + 0.06 * z_span)

    sm = cm.ScalarMappable(cmap=CMAP_SURFACE, norm=plt.Normalize(vmin=z_min, vmax=z_max))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.58, pad=0.08, aspect=22)
    cbar.set_label("纯运行成本 (元)", fontweight="bold")
    cbar.outline.set_linewidth(0.4)

    ax.set_title(
        r"纯运行成本随寿命权重的三维曲面（平均权重 $(\lambda_{ESS}+\lambda_{EV})/2$ 一维插值延拓）",
        fontsize=13,
        fontweight="bold",
        pad=18,
    )
    ax.legend(loc="upper left", fontsize=9)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_3d_cost_surface.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成三维成本曲面图: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11
    plt.rcParams["figure.dpi"] = 600
    plot_3d_surface()


if __name__ == "__main__":
    main()
