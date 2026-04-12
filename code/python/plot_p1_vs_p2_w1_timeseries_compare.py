# -*- coding: utf-8 -*-
"""问题一协同 vs 问题二 w=1 同一典型日直接时序对比图。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# 仓库根目录：本文件位于 code/python/
_REPO = Path(__file__).resolve().parents[2]

# 上一步确认的主时序文件
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

# 典型日窗口：2025-07-18 整日（96 个 15min 点）
WIN_START = "2025-07-18 00:00:00"
WIN_END = "2025-07-18 23:45:00"

OUT_DIR = _REPO / "results" / "figures" / "problem2"
OUT_NAME = "p1_vs_p2_w1_typicalday_20250718_timeseries_compare.png"


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


def _plot_ax(ax: plt.Axes, df: pd.DataFrame, title: str) -> None:
    t = df["timestamp"]
    C_BUY, C_ESS, C_EV, C_FLEX = "#999999", "#015493", "#019092", "#F4A99B"
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
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / OUT_NAME
    # 允许覆盖已有输出

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, sharex=True, figsize=(11, 7), constrained_layout=True
    )
    _plot_ax(ax_top, p1, "问题一协同主场景（典型日）")
    _plot_ax(ax_bot, p2, "问题二协同主场景（w=1，典型日）")
    ax_bot.set_xlabel("时间")

    fig.suptitle(
        "问题一协同 vs 问题二（w=1）调度行为时序对比\n"
        f"窗口：{WIN_START} — {WIN_END}",
        fontsize=11,
    )

    fig.savefig(out_path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    main()
