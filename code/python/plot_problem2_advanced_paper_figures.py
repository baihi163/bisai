# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 论文高级图表生成脚本 (国奖质感版 - 修复排版)
依赖：results/problem2_lifecycle/scans/scan_auto_weight_scan/ 下 weight_scan_summary.csv 与 w_1/timeseries.csv
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import MultipleLocator

# 帕累托散点：浅灰米 → 陶土红（与 colorbar 一致）
CMAP_PARETO_WEIGHT = LinearSegmentedColormap.from_list(
    "pareto_beige_terracotta",
    ["#BEBAB9", "#C47070"],
    N=256,
)

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
ESS_JSON = REPO_ROOT / "data" / "processed" / "final_model_inputs" / "ess_params.json"


def _pick_weight_scan_csv() -> Path:
    primary = SCAN_AUTO / "weight_scan_summary.csv"
    if primary.is_file():
        return primary
    cands = list((P2_RESULTS_DIR / "tables").glob("weight_scan_summary_*.csv"))
    if not cands:
        raise FileNotFoundError("未找到 weight_scan_summary.csv 或 tables/weight_scan_summary_*.csv")
    return max(cands, key=lambda p: p.stat().st_mtime)


def _ess_energy_kwh(ts: pd.DataFrame, ess: dict) -> np.ndarray:
    dt = float(ts["delta_t_h"].iloc[0])
    eta_c = float(ess["charge_efficiency"])
    eta_d = float(ess["discharge_efficiency"])
    e = float(ess["initial_energy_kwh"])
    out: list[float] = []
    for _, r in ts.iterrows():
        pch = float(r["P_ess_ch_kw"])
        pdis = float(r["P_ess_dis_kw"])
        e = e + (eta_c * pch - pdis / eta_d) * dt
        out.append(e)
    return np.asarray(out, dtype=float)


def plot_advanced_pareto() -> None:
    """帕累托前沿：颜色渐变表示权重，折中点与两端标注。"""
    path = _pick_weight_scan_csv()
    df = pd.read_csv(path)
    need = {"operation_cost", "ess_throughput", "ev_throughput", "ess_deg_weight"}
    if not need.issubset(df.columns):
        raise KeyError(f"{path} 缺少列: {sorted(need - set(df.columns))}")

    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    df = df.dropna(subset=["operation_cost", "ess_throughput", "ev_throughput"])
    df["total_throughput"] = df["ess_throughput"].astype(float) + df["ev_throughput"].astype(float)
    # 按总吞吐量排序：左端低吞吐(偏寿命)、右端高吞吐(偏经济)
    df = df.sort_values("total_throughput").reset_index(drop=True)

    x = df["total_throughput"].to_numpy(dtype=float)
    y = df["operation_cost"].to_numpy(dtype=float)
    weights = df["ess_deg_weight"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.plot(x, y, linestyle="--", color="gray", alpha=0.6, zorder=1)
    scatter = ax.scatter(
        x,
        y,
        c=weights,
        cmap=CMAP_PARETO_WEIGHT,
        s=100,
        edgecolor="white",
        linewidth=1.5,
        zorder=2,
    )
    cbar = plt.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("寿命惩罚权重系数 (λ)", rotation=270, labelpad=15, fontweight="bold")

    # 先画左端「极致」说明；拐点框放在其下方 (更大负向 offset)，避免与图题重叠
    ax.annotate(
        "极致寿命保护\n(高电费, 低损耗)",
        xy=(x[0], y[0]),
        xytext=(15, -25),
        textcoords="offset points",
        fontsize=10,
        color="darkblue",
    )

    knee_idx = int(np.abs(weights - 1.0).argmin())
    ax.annotate(
        "推荐折中决策点\n(Knee Point)",
        xy=(x[knee_idx], y[knee_idx]),
        xytext=(18, -118),
        textcoords="offset points",
        ha="left",
        va="top",
        arrowprops=dict(
            facecolor="black",
            shrink=0.05,
            width=1.5,
            headwidth=6,
            connectionstyle="arc3,rad=-0.12",
        ),
        fontsize=11,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="orange", alpha=0.8),
    )
    ax.annotate(
        "纯经济驱动\n(低电费, 高损耗)",
        xy=(x[-1], y[-1]),
        xytext=(-80, 15),
        textcoords="offset points",
        fontsize=10,
        color="darkred",
    )

    ax.set_xlabel("系统总电池吞吐量 (kWh) [表征长期寿命损耗] →", fontweight="bold")
    ax.set_ylabel("微电网纯运行成本 (元) [表征短期经济性] →", fontweight="bold")
    ax.set_title("运行成本与电池寿命的帕累托前沿 (Pareto Frontier)", pad=18, fontweight="bold")
    ax.grid(True, linestyle=":", alpha=0.7)
    sns.despine()

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_advanced_pareto.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成高级帕累托图: {out_path}（数据: {path}）")


def plot_advanced_soc_zoomed() -> None:
    """w=1 场景：前 72 h ESS 电量（由功率递推）与 EV 净功率面积图。"""
    ts_file = SCAN_AUTO / "w_1" / "timeseries.csv"
    if not ts_file.is_file():
        raise FileNotFoundError(f"缺少 {ts_file}，请先运行 p2.py 权重扫描。")
    if not ESS_JSON.is_file():
        raise FileNotFoundError(f"缺少 {ESS_JSON}")

    ess = json.loads(ESS_JSON.read_text(encoding="utf-8"))
    need_ess = {"initial_energy_kwh", "charge_efficiency", "discharge_efficiency", "time_step_hours"}
    if not need_ess.issubset(ess.keys()):
        raise KeyError(f"ess_params.json 缺少字段: {sorted(need_ess - set(ess.keys()))}")

    df = pd.read_csv(ts_file, parse_dates=["timestamp"])
    need_ts = {"P_ess_ch_kw", "P_ess_dis_kw", "P_ev_ch_total_kw", "P_ev_dis_total_kw", "delta_t_h"}
    if not need_ts.issubset(df.columns):
        raise KeyError(f"timeseries 缺少列: {sorted(need_ts - set(df.columns))}")

    dt = float(df["delta_t_h"].iloc[0])
    df["hour"] = np.arange(len(df), dtype=float) * dt
    df_zoom = df.loc[df["hour"] <= 72].copy()
    if df_zoom.empty:
        raise ValueError("截取 0–72 小时后数据为空。")

    e_ess = _ess_energy_kwh(df_zoom, ess)
    hour = df_zoom["hour"].to_numpy(dtype=float)

    color_soc = "#1f4e79"
    color_ev = "#c0504d"

    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    ax1.plot(hour, e_ess, color=color_soc, linewidth=2.5, label="ESS 储能电量 (kWh)")
    ax1.set_xlabel("运行时间 (小时)", fontweight="bold")
    ax1.set_ylabel("固定储能电量 (kWh)", color=color_soc, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor=color_soc)
    ax1.axhline(y=float(np.min(e_ess)), color="gray", linestyle=":", alpha=0.5)
    ax1.axhline(y=float(np.max(e_ess)), color="gray", linestyle=":", alpha=0.5)

    ax2 = ax1.twinx()
    ev_net = df_zoom["P_ev_ch_total_kw"].to_numpy(dtype=float) - df_zoom["P_ev_dis_total_kw"].to_numpy(
        dtype=float
    )
    ax2.fill_between(
        hour,
        0,
        ev_net,
        where=(ev_net >= 0),
        color=color_ev,
        alpha=0.4,
        label="EV 聚合充电功率 (kW)",
        step="mid",
    )
    ax2.fill_between(
        hour,
        0,
        ev_net,
        where=(ev_net < 0),
        color="#9bbb59",
        alpha=0.6,
        label="EV 聚合放电功率 (V2B)",
        step="mid",
    )
    ax2.set_ylabel("EV 聚合净功率 (kW)", color=color_ev, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor=color_ev)
    ax2.axhline(0, color="black", linewidth=1, linestyle="-", alpha=0.3)

    ax1.xaxis.set_major_locator(MultipleLocator(12))
    ax1.xaxis.set_minor_locator(MultipleLocator(6))
    ax1.grid(True, which="major", axis="x", linestyle="--", alpha=0.5)

    ax1.set_title(
        "引入寿命惩罚后的电池平滑运行轨迹 (局部放大：0-72小时)",
        pad=25,
        fontweight="bold",
    )

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines_1 + lines_2,
        labels_1 + labels_2,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=3,
        frameon=False,
    )
    fig.subplots_adjust(top=0.85)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_advanced_soc_zoomed.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成高级 SOC 局部轨迹图: {out_path}")


def main() -> None:
    _cjk = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    sns.set_theme(
        style="ticks",
        rc={
            "font.sans-serif": _cjk,
            "font.family": "sans-serif",
            "axes.unicode_minus": False,
            "font.size": 11,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 10,
            "figure.dpi": 600,
        },
    )

    print("开始生成问题二【国奖级】学术图表 (已修复排版)...")
    plot_advanced_pareto()
    plot_advanced_soc_zoomed()
    print(f"图表生成完毕。输出目录: {FIG_OUT_DIR}")


if __name__ == "__main__":
    main()
