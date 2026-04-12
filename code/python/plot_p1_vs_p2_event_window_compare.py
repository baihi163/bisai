# -*- coding: utf-8 -*-
"""特殊事件窗口：问题一协同 vs 问题二 w=1 资源分工对比图。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_here = Path(__file__).resolve().parent
_REPO = next(
    (p for p in (_here, *_here.parents) if (p / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv").is_file()),
    None,
)
if _REPO is None:
    raise FileNotFoundError("未找到仓库根下的 results/problem1_ultimate/p_1_5_timeseries.csv。")

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

WIN_START = "2025-07-18 17:00:00"
WIN_END = "2025-07-18 19:00:00"

OUT_DIR = _REPO / "results" / "figures" / "problem2"
OUT_STEM = "p1_vs_p2_w1_event_compare_stress_event_3_20250718"


def _load_event(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    m = (df["timestamp"] >= pd.Timestamp(WIN_START)) & (
        df["timestamp"] <= pd.Timestamp(WIN_END)
    )
    sub = df.loc[m].copy()
    if sub.empty:
        raise ValueError(f"事件窗口内无数据: {path}")
    return sub


def _stack_top(ess_d: np.ndarray, ev_d: np.ndarray) -> np.ndarray:
    return np.asarray(ess_d, dtype=float) + np.asarray(ev_d, dtype=float)


def _shared_ylim(p1: pd.DataFrame, p2: pd.DataFrame) -> tuple[float, float]:
    cols_buy = "P_buy_kw"
    cols_flex = "building_flex_power_kw"
    ess1, ev1 = p1["P_ess_dis_kw"].to_numpy(), p1["P_ev_dis_total_kw"].to_numpy()
    ess2, ev2 = p2["P_ess_dis_kw"].to_numpy(), p2["P_ev_dis_total_kw"].to_numpy()
    stack_top = np.concatenate([_stack_top(ess1, ev1), _stack_top(ess2, ev2)])
    buy_all = np.concatenate([p1[cols_buy].to_numpy(), p2[cols_buy].to_numpy()])
    flex_all = np.concatenate([p1[cols_flex].to_numpy(), p2[cols_flex].to_numpy()])
    hi = float(np.nanmax(np.concatenate([stack_top, buy_all, flex_all])))
    lo = float(np.nanmin(np.concatenate([np.zeros_like(buy_all), buy_all, flex_all, ess1, ev1, ess2, ev2])))
    pad = 0.06 * (hi - lo + 1e-9)
    return lo - pad, hi + pad


def _style_time_axis(ax: plt.Axes) -> None:
    # 2 小时窗内：每 30 分钟主刻度，减轻重叠
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")


def _plot_resource(ax: plt.Axes, df: pd.DataFrame, title: str, ylim: tuple[float, float]) -> None:
    t = df["timestamp"]
    ess_d = df["P_ess_dis_kw"].to_numpy()
    ev_d = df["P_ev_dis_total_kw"].to_numpy()
    flex = df["building_flex_power_kw"].to_numpy()
    buy = df["P_buy_kw"].to_numpy()

    # 配色（用户指定）：ESS #5EA0C7、EV #B4D7E5、外购电 #6BC179、建筑柔性 #BEDEAB
    C_ESS = "#5EA0C7"
    C_EV = "#B4D7E5"
    C_BUY = "#6BC179"
    C_FLEX = "#BEDEAB"
    ax.stackplot(
        t,
        ess_d,
        ev_d,
        labels=["ESS 放电功率", "EV 放电功率"],
        colors=[C_ESS, C_EV],
        alpha=0.82,
    )
    ax.plot(t, buy, color=C_BUY, linestyle="-", linewidth=2.0, label="外网购电功率", zorder=5)
    ax.plot(
        t,
        flex,
        color=C_FLEX,
        linestyle="--",
        linewidth=1.8,
        label="建筑柔性功率",
        zorder=6,
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

    p1 = _load_event(PATH_P1)
    p2 = _load_event(PATH_P2)
    ylim = _shared_ylim(p1, p2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_png = OUT_DIR / f"{OUT_STEM}.png"
    out_svg = OUT_DIR / f"{OUT_STEM}.svg"
    # 允许覆盖已有输出，便于重复运行出图

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, sharex=True, figsize=(10, 6.8), constrained_layout=False
    )
    fig.subplots_adjust(left=0.10, top=0.84, hspace=0.40)

    _plot_resource(ax_top, p1, "问题一协同主场景（事件窗口）", ylim)
    _plot_resource(ax_bot, p2, "问题二协同主场景（w=1，事件窗口）", ylim)
    _style_time_axis(ax_bot)
    ax_bot.set_xlabel("时间")

    fig.suptitle(
        "特殊事件窗口资源分工对比（问题一 vs 问题二 w=1）\n"
        f"窗口：{WIN_START} — {WIN_END}",
        fontsize=11,
        y=0.97,
    )

    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
