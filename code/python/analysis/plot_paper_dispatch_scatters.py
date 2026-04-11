# -*- coding: utf-8 -*-
"""
读取 ``paper_scatter_fig*.csv`` 绘制论文用散点图（透明度 + 分模型趋势线 +
高价时段描边强调）。需安装：matplotlib

  pip install matplotlib

输出：results/figures/paper_scatter_fig0N_*.png（标题与轴标签为中文；依赖系统黑体/雅黑等，缺字时请安装字体或修改 rcParams）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

try:
    import matplotlib.pyplot as plt
except ImportError:
    print("请安装 matplotlib: pip install matplotlib", file=sys.stderr)
    raise

# 中文标题与坐标轴（Windows 常见黑体/雅黑；无则回退）
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

MODEL_COLORS = {
    "problem1_coordinated": "#1f77b4",
    "baseline_noncooperative": "#ff7f0e",
}
MODEL_LABELS = {
    "problem1_coordinated": "问题一（协调优化）",
    "baseline_noncooperative": "非协同基线",
}


def _trend_line(ax, x: np.ndarray, y: np.ndarray, color: str, zorder: int = 1) -> None:
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 5:
        return
    xs, ys = x[mask], y[mask]
    coef = np.polyfit(xs, ys, 1)
    xp = np.linspace(np.nanpercentile(xs, 2), np.nanpercentile(xs, 98), 50)
    ax.plot(xp, np.poly1d(coef)(xp), color=color, linewidth=2.2, linestyle="--", zorder=zorder, alpha=0.9)


def plot_one(
    repo: Path,
    csv_name: str,
    xcol: str,
    ycol: str,
    xlab: str,
    ylab: str,
    title: str,
    out_name: str,
    *,
    xlim: tuple[float, float] | None = None,
    ylim: tuple[float, float] | None = None,
) -> Path:
    p = repo / "results" / "tables" / csv_name
    df = pd.read_csv(p, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(5.2, 4.2), dpi=150)
    for m, sub in df.groupby("model_name"):
        c = MODEL_COLORS.get(m, "#333333")
        lab = MODEL_LABELS.get(m, m)
        x = pd.to_numeric(sub[xcol], errors="coerce").to_numpy()
        y = pd.to_numeric(sub[ycol], errors="coerce").to_numpy()
        pk = pd.to_numeric(sub["is_price_peak_slot"], errors="coerce").fillna(0).to_numpy().astype(bool)
        ax.scatter(
            x[~pk],
            y[~pk],
            s=12,
            alpha=0.32,
            c=c,
            edgecolors="none",
            label=lab,
            rasterized=True,
        )
        if pk.any():
            ax.scatter(
                x[pk],
                y[pk],
                s=22,
                alpha=0.75,
                c=c,
                edgecolors="#222222",
                linewidths=0.35,
                zorder=5,
            )
        _trend_line(ax, x, y, color=c, zorder=3)

    ax.legend(fontsize=8, loc="best", framealpha=0.92)

    ax.set_xlabel(xlab, fontsize=10)
    ax.set_ylabel(ylab, fontsize=10)
    ax.set_title(title, fontsize=10.5)
    if xlim:
        ax.set_xlim(xlim)
    if ylim:
        ax.set_ylim(ylim)
    ax.grid(True, alpha=0.25, linestyle=":")
    fig.tight_layout()
    out_dir = repo / "results" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="绘制调度机制对比散点图")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()

    specs = [
        (
            "paper_scatter_fig01_price_buy_vs_grid_import.csv",
            "price_buy_yuan_per_kwh",
            "grid_import_kw",
            "分时购电价（元/kWh）",
            "外网购电功率（kW）",
            "图1  购电价与外网购电功率",
            "paper_scatter_fig01_price_vs_grid_import.png",
        ),
        (
            "paper_scatter_fig02_native_load_vs_net_grid.csv",
            "native_load_kw",
            "net_grid_kw",
            "原生负荷功率（kW）",
            "净购电功率（kW）",
            "图2  原生负荷与净购电功率",
            "paper_scatter_fig02_load_vs_net_grid.png",
        ),
        (
            "paper_scatter_fig03_native_load_vs_flex_support.csv",
            "native_load_kw",
            "flex_support_kw",
            "原生负荷功率（kW）",
            "柔性支撑功率（储能放+EV放+建筑移位，kW）",
            "图3  原生负荷与柔性支撑功率",
            "paper_scatter_fig03_load_vs_flex_support.png",
        ),
        (
            "paper_scatter_fig04_pv_available_vs_ess_charge.csv",
            "pv_available_kw",
            "ess_charge_kw",
            "光伏可发功率（kW）",
            "储能充电功率（kW）",
            "图4  光伏可发与储能充电功率",
            "paper_scatter_fig04_pv_vs_ess_charge.png",
        ),
        (
            "paper_scatter_fig05_price_buy_vs_ess_net.csv",
            "price_buy_yuan_per_kwh",
            "ess_net_kw",
            "分时购电价（元/kWh）",
            "储能净放电功率（放电−充电，kW）",
            "图5  购电价与储能净放电功率",
            "paper_scatter_fig05_price_vs_ess_net.png",
        ),
    ]

    for spec in specs:
        csv_name, xc, yc, xl, yl, ti, on = spec
        if not (repo / "results" / "tables" / csv_name).is_file():
            print(f"跳过（缺文件）: {csv_name}", file=sys.stderr)
            continue
        outp = plot_one(repo, csv_name, xc, yc, xl, yl, ti, on)
        print(f"已保存 {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
