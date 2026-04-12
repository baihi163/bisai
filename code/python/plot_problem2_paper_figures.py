# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 论文图表一键生成脚本。
依赖：results/problem2_lifecycle/scans/scan_auto_weight_scan/ 下权重扫描与 w_0、w_1 时序。
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
    """优先使用对角权重扫描主表；否则在 tables 下取最新 weight_scan_summary_*.csv。"""
    primary = SCAN_AUTO / "weight_scan_summary.csv"
    if primary.is_file():
        return primary
    scan_tables = P2_RESULTS_DIR / "tables"
    cands = list(scan_tables.glob("weight_scan_summary_*.csv"))
    if not cands:
        raise FileNotFoundError(
            "未找到 weight_scan_summary.csv（可先运行 p2.py --scan-weights）。"
        )
    return max(cands, key=lambda p: p.stat().st_mtime)


def plot_pareto_frontier() -> None:
    """运行成本 vs 总电池吞吐量（ESS+EV），权重标注 ess_deg_weight。"""
    latest_scan_file = _pick_weight_scan_csv()
    df = pd.read_csv(latest_scan_file)

    need = {"operation_cost", "ess_throughput", "ev_throughput", "ess_deg_weight"}
    missing = need - set(df.columns)
    if missing:
        raise KeyError(f"{latest_scan_file} 缺少列: {sorted(missing)}")

    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    df = df.dropna(subset=["operation_cost", "ess_throughput", "ev_throughput"])
    df["total_throughput"] = df["ess_throughput"].astype(float) + df["ev_throughput"].astype(float)
    df = df.sort_values("total_throughput")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(
        df["total_throughput"],
        df["operation_cost"],
        marker="o",
        linestyle="-",
        linewidth=2,
        markersize=8,
        color="#1f77b4",
        label="帕累托前沿",
    )
    for _, row in df.iterrows():
        lam = float(row["ess_deg_weight"])
        ax.annotate(
            f"w={lam:g}",
            (float(row["total_throughput"]), float(row["operation_cost"])),
            textcoords="offset points",
            xytext=(6, 6),
            ha="left",
            fontsize=9,
        )

    ax.set_xlabel("系统总电池吞吐量 (kWh)", fontweight="bold")
    ax.set_ylabel("微电网运行成本 (元)", fontweight="bold")
    ax.set_title("短期运行成本与电池吞吐量的权衡关系", fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend(loc="best")

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_pareto_frontier.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"已生成帕累托前沿图: {out_path}（数据: {latest_scan_file}）")


def _ess_energy_kwh(ts: pd.DataFrame, ess: dict) -> np.ndarray:
    """由 P_ess_ch_kw、P_ess_dis_kw 与 ess_params 递推时段末电量（与 MILP 状态方程一致）。"""
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


def plot_soc_smoothing() -> None:
    """对比 w=0 与 w=1 下 ESS 电量轨迹；EV 为聚合净功率柱状（右轴）。"""
    ts0 = SCAN_AUTO / "w_0" / "timeseries.csv"
    ts1 = SCAN_AUTO / "w_1" / "timeseries.csv"
    if not ts0.is_file() or not ts1.is_file():
        raise FileNotFoundError(f"缺少时序: {ts0} 或 {ts1}，请先运行 p2.py 权重扫描。")

    if not ESS_JSON.is_file():
        raise FileNotFoundError(f"缺少 {ESS_JSON}")
    ess = json.loads(ESS_JSON.read_text(encoding="utf-8"))
    need_ess = {
        "initial_energy_kwh",
        "charge_efficiency",
        "discharge_efficiency",
        "time_step_hours",
    }
    miss = need_ess - set(ess.keys())
    if miss:
        raise KeyError(f"ess_params.json 缺少字段: {sorted(miss)}")

    df0 = pd.read_csv(ts0, parse_dates=["timestamp"])
    df1 = pd.read_csv(ts1, parse_dates=["timestamp"])
    for name, d in (("w_0", df0), ("w_1", df1)):
        need = {"P_ess_ch_kw", "P_ess_dis_kw", "P_ev_ch_total_kw", "P_ev_dis_total_kw", "delta_t_h"}
        if not need.issubset(d.columns):
            raise KeyError(f"{name} timeseries 缺少列: {sorted(need - set(d.columns))}")

    e0 = _ess_energy_kwh(df0, ess)
    e1 = _ess_energy_kwh(df1, ess)
    x = np.arange(len(df0))
    if len(df1) != len(x):
        raise ValueError("w_0 与 w_1 时序长度不一致，无法对比。")

    ev_net = df1["P_ev_ch_total_kw"].to_numpy(dtype=float) - df1["P_ev_dis_total_kw"].to_numpy(
        dtype=float
    )

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(x, e0, color="#7f7f7f", linewidth=1.8, label="ESS 电量 w=0 (kWh)")
    ax1.plot(x, e1, color="#ff7f0e", linewidth=2.0, label="ESS 电量 w=1 (kWh)")
    ax1.set_xlabel("时间步 (15 min/步)", fontweight="bold")
    ax1.set_ylabel("固定储能电量 (kWh)", color="#333333", fontweight="bold")
    ax1.tick_params(axis="y", labelcolor="#333333")
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    ax2.bar(x, ev_net, width=0.8, color="#2ca02c", alpha=0.35, label="EV 聚合净功率 w=1 (kW)")
    ax2.set_ylabel("EV 聚合净功率 (kW) [>0 充电]", color="#2ca02c", fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#2ca02c")

    ax1.set_title("不同寿命权重下 ESS 电量轨迹与 EV 净功率（w=1）", fontweight="bold")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_soc_smoothing.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"已生成 ESS/EV 轨迹图: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 12
    plt.rcParams["figure.dpi"] = 300

    print("开始生成问题二学术图表...")
    plot_pareto_frontier()
    plot_soc_smoothing()
    print(f"图表生成完毕。输出目录: {FIG_OUT_DIR}")


if __name__ == "__main__":
    main()
