# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 多维核心指标随权重演变趋势图
依赖：results/problem2_lifecycle/scans/scan_auto_weight_scan/weight_scan_summary.csv
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
    except FileNotFoundError as e:
        print(str(e))
        return None
    df = pd.read_csv(path)
    need = {
        "operation_cost",
        "ess_throughput",
        "ev_throughput",
        "grid_import_energy",
        "ess_deg_weight",
    }
    if not need.issubset(df.columns):
        raise KeyError(f"{path} 缺少列: {sorted(need - set(df.columns))}")
    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    df = df.dropna(subset=["operation_cost", "ess_throughput", "ev_throughput", "grid_import_energy"])
    return df.sort_values("ess_deg_weight").reset_index(drop=True)


def plot_multi_metrics_trend() -> None:
    df = get_latest_scan_data()
    if df is None or len(df) < 2:
        print("未找到权重扫描数据或数据不足，请检查路径。")
        return

    weights = df["ess_deg_weight"].to_numpy(dtype=float)
    cost = df["operation_cost"].to_numpy(dtype=float)
    grid_import = df["grid_import_energy"].to_numpy(dtype=float)
    ess_tp = df["ess_throughput"].to_numpy(dtype=float)
    ev_tp = df["ev_throughput"].to_numpy(dtype=float)

    idx_1 = int(np.argmin(np.abs(weights - 1.0)))

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.subplots_adjust(wspace=0.32)

    axes[0].plot(weights, cost, marker="o", markersize=8, color="#d9534f", linewidth=2.5, label="纯运行成本")
    axes[0].set_title("(a) 微电网纯运行成本演变", fontweight="bold", pad=12)
    axes[0].set_xlabel("寿命惩罚权重系数 (λ)", fontweight="bold")
    axes[0].set_ylabel("成本金额 (元)", fontweight="bold")
    axes[0].grid(True, linestyle="--", alpha=0.6)
    axes[0].annotate(
        f"{cost[0]:.1f}",
        (weights[0], cost[0]),
        textcoords="offset points",
        xytext=(10, -15),
        ha="center",
        color="#d9534f",
        fontweight="bold",
    )
    axes[0].annotate(
        f"{cost[idx_1]:.1f}",
        (weights[idx_1], cost[idx_1]),
        textcoords="offset points",
        xytext=(-15, 10),
        ha="center",
        color="#d9534f",
        fontweight="bold",
    )

    axes[1].plot(weights, grid_import, marker="s", markersize=8, color="#5bc0de", linewidth=2.5, label="电网总购电量")
    axes[1].set_title("(b) 系统总购电量演变 (充放电损耗下降)", fontweight="bold", pad=12)
    axes[1].set_xlabel("寿命惩罚权重系数 (λ)", fontweight="bold")
    axes[1].set_ylabel("购电量 (kWh)", fontweight="bold")
    axes[1].grid(True, linestyle="--", alpha=0.6)
    axes[1].annotate(
        f"{grid_import[0]:.1f}",
        (weights[0], grid_import[0]),
        textcoords="offset points",
        xytext=(15, 10),
        ha="center",
        color="#31708f",
        fontweight="bold",
    )
    axes[1].annotate(
        f"{grid_import[idx_1]:.1f}",
        (weights[idx_1], grid_import[idx_1]),
        textcoords="offset points",
        xytext=(-15, -15),
        ha="center",
        color="#31708f",
        fontweight="bold",
    )

    axes[2].plot(weights, ess_tp, marker="^", markersize=8, color="#5cb85c", linewidth=2.5, label="ESS 吞吐量")
    axes[2].plot(weights, ev_tp, marker="D", markersize=8, color="#f0ad4e", linewidth=2.5, label="EV 吞吐量")
    axes[2].set_title("(c) 储能与车辆物理吞吐量演化", fontweight="bold", pad=12)
    axes[2].set_xlabel("寿命惩罚权重系数 (λ)", fontweight="bold")
    axes[2].set_ylabel("等效吞吐量 (kWh)", fontweight="bold")
    axes[2].grid(True, linestyle="--", alpha=0.6)
    axes[2].legend(loc="center right")

    fig.suptitle("不同寿命偏好下微电网核心物理与经济指标的演变规律", fontsize=15, fontweight="bold", y=1.02)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_multi_metrics_trend.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成多维指标演变趋势图: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 11
    plt.rcParams["figure.dpi"] = 600
    plot_multi_metrics_trend()


if __name__ == "__main__":
    main()
