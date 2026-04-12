# -*- coding: utf-8 -*-
"""
光伏与 EV 缩放双扰动下的运行成本相对变化率（%）— 乘性组合 3D 曲面

数据：results/sensitivity/sensitivity_analysis_summary.csv · p2_unified_tornado
边际相对变化率转为成本乘子 factor = 1 + Δ%/100，在名义点插入 factor=1。
曲面（非线性、无虚构多项式）：
  Δ%(pv,ev) = ( factor_pv(pv) * factor_ev(ev) - 1 ) * 100
仍非 (pv,ev) 全因子联合求解真网格。
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import LightSource
from matplotlib.ticker import FuncFormatter, LinearLocator
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

_here = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "sensitivity").is_dir()),
    None,
)
if REPO_ROOT is None:
    raise FileNotFoundError("未找到 results/sensitivity。")

SENS_CSV = REPO_ROOT / "results" / "sensitivity" / "sensitivity_analysis_summary.csv"
FIG_OUT_DIR = REPO_ROOT / "results" / "problem2_lifecycle" / "figures"


def _marginal_factors() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """返回排序后的 (pv_x, factor_pv, ev_x, factor_ev)，factor=1+pct/100。"""
    if not SENS_CSV.is_file():
        raise FileNotFoundError(f"缺少 {SENS_CSV}")
    df = pd.read_csv(SENS_CSV)
    sub = df.loc[
        (df["scenario"].astype(str) == "p2_unified_tornado")
        & (df["metric"].astype(str) == "operation_cost")
    ]
    pv_x: list[float] = []
    fv: list[float] = []
    ev_x: list[float] = []
    fe: list[float] = []
    for _, row in sub.iterrows():
        par = str(row["parameter"])
        pct = row["relative_change_pct"]
        if pd.isna(pct):
            continue
        p = float(pct) / 100.0
        if m := re.search(r"PV=([\d.]+)", par):
            pv_x.append(float(m.group(1)))
            fv.append(1.0 + p)
        if m := re.search(r"EV=([\d.]+)", par):
            ev_x.append(float(m.group(1)))
            fe.append(1.0 + p)
    pv_x, fv = zip(*sorted(zip(pv_x + [1.0], fv + [1.0]), key=lambda t: t[0]))
    ev_x, fe = zip(*sorted(zip(ev_x + [1.0], fe + [1.0]), key=lambda t: t[0]))
    return (
        np.asarray(pv_x, dtype=float),
        np.asarray(fv, dtype=float),
        np.asarray(ev_x, dtype=float),
        np.asarray(fe, dtype=float),
    )


def _interp_extrap_1d(x_nodes: np.ndarray, y_nodes: np.ndarray, xq: np.ndarray) -> np.ndarray:
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


def plot_pv_supply_surface_nonlinear() -> None:
    pv_x, f_pv, ev_x, f_ev = _marginal_factors()

    x = np.linspace(0.8, 1.2, 48)
    y = np.linspace(0.8, 1.2, 48)
    X, Y = np.meshgrid(x, y)
    Fp = _interp_extrap_1d(pv_x, f_pv, X)
    Fe = _interp_extrap_1d(ev_x, f_ev, Y)
    Z = (Fp * Fe - 1.0) * 100.0

    z_span = float(np.max(Z)) - float(np.min(Z)) + 1e-9
    z_min_plot = float(np.min(Z)) - 0.06 * z_span
    # 参考平面高度：取分布上侧分位，便于与曲面相交（期刊 tipping-plane 风格）
    z_thr = float(np.percentile(Z, 72))

    fig = plt.figure(figsize=(12, 10), facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")
    try:
        ax.set_box_aspect((1, 1, 0.78))
    except AttributeError:
        pass
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((1.0, 1.0, 1.0, 1.0))
        axis.pane.set_edgecolor("#e2e2e2")
    ax.grid(True, color="#dcdcdc", linestyle="-", linewidth=0.35, alpha=0.75)

    cmap_surf = cm.magma
    ls = LightSource(azdeg=220, altdeg=38)
    rgba = ls.shade(Z, cmap=cmap_surf, vert_exag=0.12, blend_mode="soft")
    ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=rgba,
        linewidth=0,
        antialiased=True,
        rstride=1,
        cstride=1,
        shade=False,
        alpha=0.95,
    )

    # 顶部浅色线框平面（非实心），与参考图「tipping 网格」一致
    rs = max(2, X.shape[0] // 14)
    ax.plot_wireframe(
        X,
        Y,
        np.full_like(X, z_thr, dtype=float),
        rstride=rs,
        cstride=rs,
        colors="#f2f2f2",
        linewidths=0.55,
        alpha=0.95,
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

    ax.set_xlabel("光伏出力缩放系数", fontweight="bold", labelpad=14)
    ax.set_ylabel("柔性供电(EV)可用性/功率缩放系数", fontweight="bold", labelpad=14)
    ax.set_zlabel("运行成本相对变化率 / %", fontweight="bold", labelpad=26)
    ax.zaxis.set_rotate_label(False)
    ax.tick_params(axis="z", labelsize=10, pad=10)
    ax.zaxis.set_major_locator(LinearLocator(7))
    ax.zaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:.2f}%"))
    z_top = max(float(np.max(Z)), z_thr) + 0.08 * z_span
    ax.set_zlim(z_min_plot, z_top)
    ax.view_init(elev=23, azim=-128)
    try:
        ax.dist = 10.5
    except AttributeError:
        pass

    sm = cm.ScalarMappable(cmap=cmap_surf, norm=plt.Normalize(vmin=float(np.min(Z)), vmax=float(np.max(Z))))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.12)
    cbar.set_label("成本变化率 / %", fontweight="bold")

    ax.set_title(
        "光伏与 EV 缩放双扰动（乘性组合，非线性）\n"
        f"数据：{SENS_CSV.relative_to(REPO_ROOT)} · p2_unified_tornado",
        fontsize=12,
        fontweight="bold",
        pad=16,
    )

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_pv_supply_3d_surface_nonlinear.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight", pad_inches=0.55)
    plt.close(fig)
    print(f"已生成: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 12
    plt.rcParams["figure.dpi"] = 600
    plot_pv_supply_surface_nonlinear()


if __name__ == "__main__":
    main()
