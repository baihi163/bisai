# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 创新型学术图表生成脚本 (雷达图 & 堆叠柱状图)
雷达图：真实物理吞吐量 + 示意性吞吐折旧叠加 (0.05 元/kWh)，min–max 映射到 0.1–1.0 增强对比。
依赖：results/problem2_lifecycle/scans/scan_auto_weight_scan/weight_scan_summary.csv
     或 tables/weight_scan_summary_*.csv
"""
from __future__ import annotations

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
    except FileNotFoundError:
        return None
    df = pd.read_csv(path)
    need = {
        "operation_cost",
        "ess_deg_cost",
        "ev_deg_cost",
        "ess_throughput",
        "ev_throughput",
        "ess_deg_weight",
        "objective_recomputed",
    }
    if not need.issubset(df.columns):
        raise KeyError(f"{path} 缺少列: {sorted(need - set(df.columns))}")
    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    df = df.dropna(subset=["operation_cost", "ess_throughput", "ev_throughput"])
    return df.sort_values("ess_deg_weight").reset_index(drop=True)


def plot_cost_composition_stacked_bar() -> None:
    """不同 λ 下运行电费 + ESS 折旧 + EV 折旧 堆叠柱状图。"""
    df = get_latest_scan_data()
    if df is None or df.empty:
        print("未找到权重扫描结果。")
        return

    target_weights = [0.1, 0.5, 1.0, 2.0, 5.0]
    selected_rows: list[pd.Series] = []
    for tw in target_weights:
        idx = int((np.abs(df["ess_deg_weight"].to_numpy(dtype=float) - tw)).argmin())
        selected_rows.append(df.iloc[idx])
    df_plot = pd.DataFrame(selected_rows).drop_duplicates(subset=["ess_deg_weight"])

    labels = [f"λ={float(w):g}" for w in df_plot["ess_deg_weight"]]
    op_cost = df_plot["operation_cost"].to_numpy(dtype=float)
    ess_cost = df_plot["ess_deg_cost"].to_numpy(dtype=float)
    ev_cost = df_plot["ev_deg_cost"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(8, 6))
    width = 0.55
    c_op = "#4f81bd"
    c_ess = "#c0504d"
    c_ev = "#9bbb59"

    x = np.arange(len(labels))
    ax.bar(x, op_cost, width, label="微电网纯运行成本 (电费等)", color=c_op, edgecolor="black", linewidth=0.5)
    ax.bar(x, ess_cost, width, bottom=op_cost, label="固定储能 (ESS) 寿命折旧成本", color=c_ess, edgecolor="black", linewidth=0.5)
    ax.bar(
        x,
        ev_cost,
        width,
        bottom=op_cost + ess_cost,
        label="电动汽车 (EV) 寿命折旧成本",
        color=c_ev,
        edgecolor="black",
        linewidth=0.5,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("各项成本金额 (元)", fontweight="bold")
    ax.set_xlabel("寿命惩罚权重系数 (λ)", fontweight="bold")
    ax.set_title("不同寿命偏好下的微电网成本结构演变", pad=15, fontweight="bold")

    totals = op_cost + ess_cost + ev_cost
    ymax = float(np.nanmax(totals)) if len(totals) else 0.0
    pad = max(30.0, 0.02 * ymax)
    for i, total in enumerate(totals):
        ax.text(i, total + pad, f"{total:.0f}", ha="center", va="bottom", fontweight="bold", fontsize=10)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False, fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.subplots_adjust(bottom=0.24)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_cost_stacked_bar.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成成本结构堆叠柱状图: {out_path}")


def _radar_scale(v: float, m: float, mi: float) -> float:
    """将每个维度在两场景间的取值线性映射到 [0.1, 1.0]，放大差异。"""
    if m <= mi + 1e-18:
        return 0.55
    t = (v - mi) / (m - mi)
    t = max(0.0, min(1.0, t))
    return 0.1 + 0.9 * t


def plot_performance_radar() -> None:
    """纯经济 (最小 λ) vs 兼顾寿命 (λ≈1)；物理吞吐量 + 示意综合量，高对比雷达图。"""
    df = get_latest_scan_data()
    if df is None or len(df) < 2:
        print("数据不足以绘制雷达图。")
        return

    row_eco = df.iloc[0]
    idx_bal = int((np.abs(df["ess_deg_weight"].to_numpy(dtype=float) - 1.0)).argmin())
    row_bal = df.iloc[idx_bal]

    categories = [
        "微电网纯运行电费",
        "固定储能物理损耗 (kWh)",
        "电动汽车物理损耗 (kWh)",
        "系统总吞吐量 (kWh)",
        "真实综合折旧评估",
    ]
    n = len(categories)

    def _throughputs(r: pd.Series) -> tuple[float, float, float]:
        ess = float(r["ess_throughput"])
        ev = float(r["ev_throughput"])
        return ess, ev, ess + ev

    def _real_eval_cost(r: pd.Series, unit_cny_per_kwh: float = 0.05) -> float:
        _, _, tp = _throughputs(r)
        return float(r["operation_cost"]) + tp * unit_cny_per_kwh

    ess_e, ev_e, tp_e = _throughputs(row_eco)
    ess_b, ev_b, tp_b = _throughputs(row_bal)
    real_eco = _real_eval_cost(row_eco)
    real_bal = _real_eval_cost(row_bal)

    vals_eco = [float(row_eco["operation_cost"]), ess_e, ev_e, tp_e, real_eco]
    vals_bal = [float(row_bal["operation_cost"]), ess_b, ev_b, tp_b, real_bal]

    max_vals = [max(e, b) for e, b in zip(vals_eco, vals_bal)]
    min_vals = [min(e, b) for e, b in zip(vals_eco, vals_bal)]
    norm_eco = [_radar_scale(e, m, mi) for e, m, mi in zip(vals_eco, max_vals, min_vals)]
    norm_bal = [_radar_scale(b, m, mi) for b, m, mi in zip(vals_bal, max_vals, min_vals)]
    norm_eco = norm_eco + norm_eco[:1]
    norm_bal = norm_bal + norm_bal[:1]

    angles = [i / float(n) * 2 * np.pi for i in range(n)]
    angles = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    ax.plot(
        angles,
        norm_eco,
        linewidth=2.5,
        linestyle="--",
        color="#d9534f",
        label=f"纯经济驱动调度 (λ={float(row_eco['ess_deg_weight']):g})",
    )
    ax.fill(angles, norm_eco, color="#d9534f", alpha=0.15)

    ax.plot(
        angles,
        norm_bal,
        linewidth=3.0,
        linestyle="-",
        color="#5bc0de",
        label=f"兼顾寿命协同调度 (λ={float(row_bal['ess_deg_weight']):g})",
    )
    ax.fill(angles, norm_bal, color="#5bc0de", alpha=0.4)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontweight="bold", size=11)

    ax.set_yticklabels([])
    ax.grid(color="gray", linestyle=":", linewidth=0.5, alpha=0.7)

    ax.set_title("纯经济调度 vs 兼顾寿命调度的多维物理效益对比", size=15, fontweight="bold", pad=36)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), frameon=True, edgecolor="black", fontsize=10)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_performance_radar.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成【高冲击力】多维效益雷达图: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11
    plt.rcParams["figure.dpi"] = 600

    print("开始生成问题二【创新型】学术图表...")
    plot_cost_composition_stacked_bar()
    plot_performance_radar()
    print(f"图表生成完毕。输出目录: {FIG_OUT_DIR}")


if __name__ == "__main__":
    main()
