# -*- coding: utf-8 -*-
"""问题一协同 vs 问题二 w=1 同一典型日直接时序对比图。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

# 仓库根：从当前文件向上查找含主时序的目录
_here = Path(__file__).resolve().parent
_REPO = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv").is_file()),
    None,
)
if _REPO is None:
    raise FileNotFoundError(
        "未找到仓库根下的 results/problem1_ultimate/p_1_5_timeseries.csv，请确认脚本位于仓库内。"
    )

PATH_P1 = _REPO / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
PATH_P2 = (
    _REPO
    / "results"
    / "problem2_lifecycle"
    / "scans"
    / "scan_auto_weight_scan"
    / "w_1"
    / "timeseries.csv"
)

WIN_START = "2025-07-18 00:00:00"
WIN_END = "2025-07-18 23:45:00"

OUT_DIR = _REPO / "results" / "figures" / "problem2"
OUT_STEM = "p1_vs_p2_w1_typicalday_20250718_timeseries_compare"


def _load_window(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    m = (df["timestamp"] >= pd.Timestamp(WIN_START)) & (
        df["timestamp"] <= pd.Timestamp(WIN_END)
    )
    sub = df.loc[m].copy()
    if sub.empty:
        raise ValueError(f"窗口内无数据: {path}")
    # 净功率：放电为正、充电为负
    sub["ess_net_kw"] = sub["P_ess_dis_kw"] - sub["P_ess_ch_kw"]
    sub["ev_net_kw"] = sub["P_ev_dis_total_kw"] - sub["P_ev_ch_total_kw"]
    return sub


def _shared_ylim(p1: pd.DataFrame, p2: pd.DataFrame) -> tuple[float, float]:
    cols = ["P_buy_kw", "ess_net_kw", "ev_net_kw", "building_flex_power_kw"]
    lo = min(p1[cols].min().min(), p2[cols].min().min())
    hi = max(p1[cols].max().max(), p2[cols].max().max())
    pad = 0.05 * (hi - lo + 1e-9)
    return float(lo - pad), float(hi + pad)


def _style_time_axis(ax: plt.Axes) -> None:
    # 主刻度每 2 小时，标签 HH:MM
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")


def _plot_ax(ax: plt.Axes, df: pd.DataFrame, title: str, ylim: tuple[float, float]) -> None:
    t = df["timestamp"]
    # 配色（用户指定）：外购电 #999999、ESS #015493、EV #019092、建筑柔性 #F4A99B
    C_BUY = "#999999"
    C_ESS = "#015493"
    C_EV = "#019092"
    C_FLEX = "#F4A99B"
    ax.plot(t, df["P_buy_kw"], color=C_BUY, linestyle="-", linewidth=1.35, label="外网购电功率")
    ax.plot(t, df["ess_net_kw"], color=C_ESS, linestyle="-", linewidth=1.2, label="ESS 净功率")
    ax.plot(t, df["ev_net_kw"], color=C_EV, linestyle="--", linewidth=1.2, label="EV 净功率")
    ax.plot(
        t,
        df["building_flex_power_kw"],
        color=C_FLEX,
        linestyle="-.",
        linewidth=1.2,
        label="建筑柔性功率",
    )
    ax.set_ylabel("功率 / kW")
    ax.set_ylim(ylim)
    # 图例在子图上方左侧；图名在其右侧（同一行，axes 坐标）
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.02),
        bbox_transform=ax.transAxes,
        ncol=2,
        fontsize=8,
        frameon=True,
        framealpha=0.95,
        borderaxespad=0.0,
    )
    ax.text(
        0.48,
        1.02,
        title,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=11,
        fontweight="bold",
    )
    ax.grid(True, alpha=0.3)


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    if not PATH_P1.is_file():
        raise FileNotFoundError(PATH_P1)
    if not PATH_P2.is_file():
        raise FileNotFoundError(PATH_P2)

    p1 = _load_window(PATH_P1)
    p2 = _load_window(PATH_P2)
    ylim = _shared_ylim(p1, p2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_png = OUT_DIR / f"{OUT_STEM}.png"
    out_svg = OUT_DIR / f"{OUT_STEM}.svg"
    # 允许覆盖已有输出，便于重复运行出图

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, sharex=True, figsize=(11, 7.2), constrained_layout=False
    )
    fig.subplots_adjust(left=0.09, top=0.86, hspace=0.38)

    _plot_ax(ax_top, p1, "问题一协同主场景（典型日）", ylim)
    _plot_ax(ax_bot, p2, "问题二协同主场景（w=1，典型日）", ylim)
    _style_time_axis(ax_bot)
    ax_bot.set_xlabel("时间")

    fig.suptitle(
        "问题一协同 vs 问题二（w=1）调度行为时序对比\n"
        f"窗口：{WIN_START} — {WIN_END}",
        fontsize=11,
        y=0.97,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
