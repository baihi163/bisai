# -*- coding: utf-8 -*-
"""
问题2：兼顾寿命损耗的协同调度 - 三维帕累托前沿演变图 (3D Pareto Frontier)
依赖：results/problem2_lifecycle/scans/scan_auto_weight_scan/weight_scan_summary.csv
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — 注册 3d 投影

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
    need = {"operation_cost", "ess_throughput", "ev_throughput", "ess_deg_weight"}
    if not need.issubset(df.columns):
        raise KeyError(f"{path} 缺少列: {sorted(need - set(df.columns))}")
    if "solver_status" in df.columns:
        df = df.loc[df["solver_status"].astype(str) == "Optimal"].copy()
    df = df.dropna(subset=["operation_cost", "ess_throughput", "ev_throughput"])
    return df.sort_values("ess_deg_weight").reset_index(drop=True)


def _is_key_lambda(lam: float, targets: tuple[float, ...], *, rtol: float = 1e-5, atol: float = 1e-8) -> bool:
    return any(np.isclose(lam, t, rtol=rtol, atol=atol) for t in targets)


def plot_3d_pareto() -> None:
    df = get_latest_scan_data()
    if df is None or len(df) < 2:
        print("未找到权重扫描数据或数据不足，请检查路径。")
        return

    x = df["operation_cost"].to_numpy(dtype=float)
    y = df["ess_throughput"].to_numpy(dtype=float)
    z = df["ev_throughput"].to_numpy(dtype=float)
    weights = df["ess_deg_weight"].to_numpy(dtype=float)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    ax.plot(x, y, z, color="gray", linestyle="--", linewidth=1.5, alpha=0.6, label="帕累托演化轨迹")

    scatter = ax.scatter(
        x,
        y,
        z,
        c=weights,
        cmap="coolwarm",
        s=120,
        edgecolors="black",
        depthshade=True,
        alpha=0.9,
    )

    key_lambdas = (0.0, 0.1, 0.5, 1.0, 2.0)
    z_pad = max(5.0, 0.01 * (float(np.nanmax(z)) - float(np.nanmin(z)) + 1.0))
    for i in range(len(df)):
        lam = float(weights[i])
        if _is_key_lambda(lam, key_lambdas):
            ax.text(x[i], y[i], z[i] + z_pad, f"λ={lam:g}", size=9, color="black", fontweight="bold")

    ax.set_xlabel("系统纯运行成本 (元)", fontweight="bold", labelpad=12)
    ax.set_ylabel("固定储能 ESS 吞吐量 (kWh)", fontweight="bold", labelpad=12)
    ax.set_zlabel("电动汽车 EV 吞吐量 (kWh)", fontweight="bold", labelpad=12)
    ax.view_init(elev=25, azim=135)

    cbar = fig.colorbar(scatter, ax=ax, shrink=0.55, pad=0.12)
    cbar.set_label("寿命惩罚权重系数 (λ)", fontweight="bold")

    ax.set_title("兼顾寿命调度的三维帕累托前沿演变 (成本-储能-车辆)", fontsize=13, fontweight="bold", pad=16)
    ax.legend(loc="upper left", fontsize=9)

    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_OUT_DIR / "fig_3d_pareto_frontier.png"
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"已生成三维帕累托前沿图: {out_path}")


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Songti SC", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10
    plt.rcParams["figure.dpi"] = 600
    plot_3d_pareto()


if __name__ == "__main__":
    main()
