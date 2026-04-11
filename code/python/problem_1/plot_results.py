import sys

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from pathlib import Path

# 设置中文字体，防止乱码
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 路径配置：plot_results.py 位于 repo/code/python/problem_1/
ROOT = Path(__file__).resolve().parents[3]
baseline_csv = ROOT / "results" / "problem1_baseline" / "baseline_timeseries_results.csv"
optimized_csv = ROOT / "results" / "problem1_pulp_enhanced" / "p_1_2_final_timeseries.csv"


def _safe_print(msg: str) -> None:
    """避免 Windows GBK 控制台无法编码 emoji / 特殊符号导致崩溃。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))


def main() -> int:
    for path, label in (
        (baseline_csv, "基准结果"),
        (optimized_csv, "协同优化结果"),
    ):
        if not path.is_file():
            _safe_print(f"错误：缺少{label} CSV: {path}")
            return 1

    df_base = pd.read_csv(baseline_csv)
    df_opt = pd.read_csv(optimized_csv)

    need_base = {"grid_import_kw", "buy_price"}
    need_opt = {"P_buy"}
    miss = (need_base - set(df_base.columns)) | (need_opt - set(df_opt.columns))
    if miss:
        _safe_print(f"错误：CSV 缺少列: {sorted(miss)}")
        return 1

    # 提取前 3 天的数据用于曲线展示 (3天 * 96个时段 = 288)
    max_show = 288
    n_common = min(len(df_base), len(df_opt), max_show)
    if n_common < 1:
        _safe_print("错误：CSV 无有效行")
        return 1

    show_steps = n_common
    t_axis = np.arange(show_steps)

    grid_import_base = df_base["grid_import_kw"].to_numpy(dtype=float)[:show_steps]
    grid_import_opt = df_opt["P_buy"].to_numpy(dtype=float)[:show_steps]
    buy_price = df_base["buy_price"].to_numpy(dtype=float)[:show_steps]

    # constrained_layout 与 twinx 比 tight_layout 更不易告警
    fig = plt.figure(figsize=(16, 10), layout="constrained")
    gs = GridSpec(2, 1, figure=fig, height_ratios=[1, 1.6], hspace=0.28)

    # ================= 图1：经济性对比柱状图 =================
    ax1 = fig.add_subplot(gs[0])
    costs = [46304.53, 38094.35]
    labels = ["非协同基准 (Baseline)", "协同优化 (Optimized)"]
    colors = ["#E74C3C", "#2ECC71"]

    bars = ax1.bar(labels, costs, color=colors, width=0.5)
    ax1.set_ylabel("周运行总成本 (元)", fontsize=12)
    ax1.set_title("微电网调度策略经济性对比", fontsize=14, fontweight="bold")
    ax1.set_ylim(0, 55000)

    for bar in bars:
        yval = bar.get_height()
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            yval + 1000,
            f"{yval:.2f} 元",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )

    # ================= 图2：前若干时段向电网购电功率对比 =================
    ax2 = fig.add_subplot(gs[1])
    ax2_twin = ax2.twinx()
    ax2_twin.plot(t_axis, buy_price, color="gray", linestyle="--", alpha=0.5, label="分时购电价")
    ax2_twin.set_ylabel("电价 (元/kWh)", color="gray", fontsize=12)

    ax2.plot(
        t_axis,
        grid_import_base,
        label="非协同基准购电功率",
        color="#E74C3C",
        alpha=0.8,
        linewidth=2,
    )
    ax2.plot(t_axis, grid_import_opt, label="协同优化购电功率", color="#2ECC71", linewidth=2)

    ax2.set_xlabel(f"时间步 (15min/步, 共展示 {show_steps} 步)", fontsize=12)
    ax2.set_ylabel("向电网购电功率 (kW)", fontsize=12)
    ax2.set_title("电网购电功率对比", fontsize=14, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)

    lines, leg_labels = ax2.get_legend_handles_labels()
    lines2, leg_labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines + lines2, leg_labels + leg_labels2, loc="upper left", fontsize=11)

    out_path = ROOT / "results" / "problem1_comparison_plot.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    _safe_print(f"图表已生成并保存至: {out_path}")
    if not isinstance(fig.canvas, FigureCanvasAgg):
        plt.show()
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
