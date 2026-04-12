# -*- coding: utf-8 -*-
"""
基于光伏出力与 EV 供电（功率/可用性）缩放的双变量灵敏度 3D 曲面（运行成本相对变化率 %）

数据来源：results/sensitivity/sensitivity_analysis_summary.csv 中 scenario=p2_unified_tornado、
metric=operation_cost 的 PV 与 EV 单点扰动相对变化率（相对 ref_operation_cost=38973.22 量级）。

说明：仓库中无 (pv_scale, ev_scale) 全因子联合求解网格；曲面采用
  Z(pv, ev) = Δ%_PV(pv) + Δ%_EV(ev)
在各自参考点 1.0 处为 0；为文献中常见的一阶、无交互项近似，非 MILP 全交叉真值。
图中横轴为 EV 缩放、纵轴为 PV 缩放（与常见“先横后纵”的阅读顺序一致）。
底面投影采用曲率参数网采样，仅影响可视化网格；Z 仍按可加模型在 (EV, PV) 处取值。
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import LightSource, LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter, LinearLocator
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

_here = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "sensitivity").is_dir()),
    None,
)
if REPO_ROOT is None:
    raise FileNotFoundError("未找到 results/sensitivity，请确认脚本位于仓库内。")

SENS_CSV = REPO_ROOT / "results" / "sensitivity" / "sensitivity_analysis_summary.csv"
FIG_OUT_DIR = REPO_ROOT / "results" / "problem2_lifecycle" / "figures"


def _marginal_pct_from_tornado() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """返回 (pv_x, pv_pct, ev_x, ev_pct)，仅在已知扰动点有真值。"""
    if not SENS_CSV.is_file():
        raise FileNotFoundError(f"缺少 {SENS_CSV}")
    df = pd.read_csv(SENS_CSV)
    need = {"parameter", "scenario", "metric", "relative_change_pct"}
    if not need.issubset(df.columns):
        raise KeyError(f"{SENS_CSV} 缺少列: {sorted(need - set(df.columns))}")
    sub = df.loc[
        (df["scenario"].astype(str) == "p2_unified_tornado")
        & (df["metric"].astype(str) == "operation_cost")
    ].copy()
    pv_x: list[float] = []
    pv_p: list[float] = []
    ev_x: list[float] = []
    ev_p: list[float] = []
    for _, row in sub.iterrows():
        par = str(row["parameter"])
        pct = row["relative_change_pct"]
        if pd.isna(pct):
            continue
        pv_m = re.search(r"PV=([\d.]+)", par)
        ev_m = re.search(r"EV=([\d.]+)", par)
        if pv_m:
            pv_x.append(float(pv_m.group(1)))
            pv_p.append(float(pct))
        if ev_m:
            ev_x.append(float(ev_m.group(1)))
            ev_p.append(float(pct))
    if len(pv_x) < 2 or len(ev_x) < 2:
        raise ValueError("未解析到足够的 p2_unified_tornado PV/EV 扰动行。")
    # 插入名义点 1.0 -> 0%
    pv_x, pv_p = zip(*sorted(zip(pv_x + [1.0], pv_p + [0.0]), key=lambda t: t[0]))
    ev_x, ev_p = zip(*sorted(zip(ev_x + [1.0], ev_p + [0.0]), key=lambda t: t[0]))
    return (
        np.asarray(pv_x, dtype=float),
        np.asarray(pv_p, dtype=float),
        np.asarray(ev_x, dtype=float),
        np.asarray(ev_p, dtype=float),
    )


def _curved_ev_pv_mesh(n: int = 62) -> tuple[np.ndarray, np.ndarray]:
    """
    在 [0.8, 1.2]^2 上构造平滑曲率参数网：轴线方向略作幂次加密，并加轻微正弦耦合，
    使 u/v 等值线在 EV–PV 平面上呈弧线，观感接近「反函数 / 双曲型」坐标线，仍严格落在方域内。
    """
    lo, hi = 0.8, 1.2
    span = hi - lo
    u = np.linspace(0.0, 1.0, n)
    v = np.linspace(0.0, 1.0, n)
    U, V = np.meshgrid(u, v, indexing="xy")
    ue = u**0.84
    ve = v**0.84
    Ue, Ve = np.meshgrid(ue, ve, indexing="xy")
    bend = 0.052
    X = lo + span * (Ue + bend * np.sin(np.pi * Ve) * Ue * (1.0 - Ue))
    Y = lo + span * (Ve + bend * np.sin(np.pi * Ue) * Ve * (1.0 - Ve))
    np.clip(X, lo, hi, out=X)
    np.clip(Y, lo, hi, out=Y)
    return X, Y


def _interp_extrap_1d(x_nodes: np.ndarray, y_nodes: np.ndarray, xq: np.ndarray) -> np.ndarray:
    """分段线性插值；区间外按端点斜率外推。"""
    order = np.argsort(x_nodes)
    xn = x_nodes[order]
    yn = y_nodes[order]
    out = np.empty_like(xq, dtype=float)
    for i, xv in enumerate(xq.ravel()):
        if xv <= xn[0]:
            m = (yn[1] - yn[0]) / (xn[1] - xn[0] + 1e-18)
            out.flat[i] = yn[0] + m * (xv - xn[0])
        elif xv >= xn[-1]:
            m = (yn[-1] - yn[-2]) / (xn[-1] - xn[-2] + 1e-18)
            out.flat[i] = yn[-1] + m * (xv - xn[-1])
        else:
            out.flat[i] = float(np.interp(xv, xn, yn))
    return out.reshape(xq.shape)


def plot_pv_supply_surface() -> None:
    pv_x, pv_pct, ev_x, ev_pct = _marginal_pct_from_tornado()

    # X = EV 缩放，Y = PV 缩放；曲面在底平面的投影为曲率参数网（更立体、略似反函数坐标线）
    X, Y = _curved_ev_pv_mesh(62)
    Z = _interp_extrap_1d(ev_x, ev_pct, X) + _interp_extrap_1d(pv_x, pv_pct, Y)

    z_span = float(np.max(Z)) - float(np.min(Z)) + 1e-9
    z_min_plot = float(np.min(Z)) - 0.05 * z_span
    z_thr = 10.2

    fig = plt.figure(figsize=(12, 9), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")
    try:
        ax.set_box_aspect((1, 1, 0.92))
    except AttributeError:
        pass
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((1.0, 1.0, 1.0, 1.0))
        axis.pane.set_edgecolor("#e2e2e2")
    ax.grid(True, color="#dcdcdc", linestyle="-", linewidth=0.35, alpha=0.75)

    cmap_surf = LinearSegmentedColormap.from_list(
        "pv_ev_cost",
        ["#ACD6EC", "#F5A889"],
        N=256,
    )
    # 略强起伏 + 适中混合：立体感更强，仍保持 soft 高光过渡
    ls = LightSource(azdeg=208, altdeg=44)
    z_norm = plt.Normalize(vmin=float(np.min(Z)), vmax=float(np.max(Z)))
    rgba = ls.shade(
        Z,
        cmap=cmap_surf,
        norm=z_norm,
        vert_exag=0.088,
        blend_mode="soft",
        fraction=0.58,
    )
    ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=rgba,
        linewidth=0.06,
        edgecolor="#b0b0b0",
        antialiased=True,
        rstride=1,
        cstride=1,
        shade=False,
        alpha=0.97,
    )

    rs = max(2, X.shape[0] // 14)
    ax.plot_wireframe(
        X,
        Y,
        np.full_like(X, z_thr, dtype=float),
        rstride=rs,
        cstride=rs,
        colors="#c8c8c8",
        linewidths=0.65,
        alpha=0.85,
    )

    ax.contourf(X, Y, Z, zdir="z", offset=z_min_plot, cmap=cmap_surf, alpha=0.28, levels=18)
    ax.contour(
        X,
        Y,
        Z,
        zdir="z",
        offset=z_min_plot,
        colors="#9a9a9a",
        linewidths=0.28,
        alpha=0.35,
        levels=10,
    )

    ax.set_xlabel("柔性供电(EV)可用性/功率缩放系数", fontweight="bold", labelpad=12)
    ax.set_ylabel("光伏出力缩放系数", fontweight="bold", labelpad=12)
    ax.set_ylim(1.2, 0.8)
    # Z 轴：label 沿 Z 轴方向（竖向）；刻度保持常规横向
    ax.set_zlabel("运行成本相对变化率 / %", fontweight="bold", labelpad=18)
    ax.zaxis.set_rotate_label(True)
    ax.tick_params(axis="z", labelsize=10, pad=10)
    ax.zaxis.set_major_locator(LinearLocator(6))
    ax.zaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.2f}%"))
    z_top = max(float(np.max(Z)), z_thr) + 0.08 * z_span
    ax.set_zlim(z_min_plot, z_top)
    ax.view_init(elev=20, azim=-126)
    try:
        ax.dist = 9.35
    except AttributeError:
        pass

    sm = cm.ScalarMappable(cmap=cmap_surf, norm=plt.Normalize(vmin=float(np.min(Z)), vmax=float(np.max(Z))))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.52, pad=0.09)
    cbar.set_label("成本变化率 / %", fontweight="bold")

    ax.set_title(
        "光伏与 EV 缩放双扰动下的运行成本变化率（可加近似）\n"
        f"数据：{SENS_CSV.relative_to(REPO_ROOT)} · p2_unified_tornado",
        fontsize=12,
        fontweight="bold",
        pad=14,
    )

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_pv_supply_3d_surface.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight", pad_inches=0.55)
    plt.close(fig)
    print(f"已生成: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11
    plt.rcParams["figure.dpi"] = 600
    plot_pv_supply_surface()


if __name__ == "__main__":
    main()
