# -*- coding: utf-8 -*-
"""分车型：平均额定容量与平均吞吐退化成本（双轴图）。"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_here = Path(__file__).resolve().parent
_REPO = next(
    (p for p in (_here, *_here.parents) if (p / "data" / "processed" / "final_model_inputs").is_dir()),
    None,
)
if _REPO is None:
    raise FileNotFoundError("未定位到仓库根目录（缺少 data/processed/final_model_inputs）。")

CSV_PATH = _REPO / "data" / "processed" / "final_model_inputs" / "ev_sessions_model_ready.csv"
OUT_DIR = _REPO / "results" / "figures" / "problem2"
OUT_STEM = "ev_type_capacity_degradation_polished"

# 横轴车型顺序（按 ev_type 小写键）；展示名为「中文 + 英文」
TYPE_ORDER = ("compact", "sedan", "suv")
TYPE_LABEL_ZH = {
    "compact": "紧凑型 compact",
    "sedan": "轿车 sedan",
    "suv": "SUV型 SUV",
}


def main() -> None:
    if not CSV_PATH.is_file():
        raise FileNotFoundError(f"缺少数据文件: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    need = {"ev_type", "battery_capacity_kwh", "degradation_cost_cny_per_kwh_throughput"}
    missing = need - set(df.columns)
    if missing:
        raise KeyError(f"CSV 缺少必要字段: {sorted(missing)}")

    # 分组字段：ev_type（统一小写便于合并 SUV/suv）；统计口径：会话级简单算术平均
    df = df.copy()
    df["_type_key"] = df["ev_type"].astype(str).str.strip().str.lower()
    if df["_type_key"].isin(["", "nan"]).any():
        raise ValueError("ev_type 存在空值或非法字符串。")

    g = (
        df.groupby("_type_key", as_index=False)
        .agg(
            mean_capacity_kwh=("battery_capacity_kwh", "mean"),
            mean_deg_cny_per_kwh_throughput=("degradation_cost_cny_per_kwh_throughput", "mean"),
            n_sessions=("ev_index", "count"),
        )
    )

    rows = []
    for k in TYPE_ORDER:
        sub = g.loc[g["_type_key"] == k]
        if sub.empty:
            raise ValueError(f"车型中无会话数据: {k}（请检查 CSV 中 ev_type 取值）")
        rows.append(sub.iloc[0])
    plot_df = pd.DataFrame(rows)
    x_labels = [TYPE_LABEL_ZH[k] for k in TYPE_ORDER]
    x = np.arange(len(TYPE_ORDER))
    cap = plot_df["mean_capacity_kwh"].to_numpy(dtype=float)
    deg = plot_df["mean_deg_cny_per_kwh_throughput"].to_numpy(dtype=float)

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax1 = plt.subplots(figsize=(6.2, 4.2), layout="constrained")
    ax2 = ax1.twinx()

    # 柱：平均额定容量（左轴）；折线：平均退化单价（右轴）
    bar_w = 0.45
    bars = ax1.bar(
        x,
        cap,
        width=bar_w,
        color="#4a4a4a",
        edgecolor="black",
        linewidth=0.6,
        alpha=0.78,
        label="平均额定容量",
        zorder=2,
    )
    (line,) = ax2.plot(
        x,
        deg,
        color="#c0392b",
        marker="o",
        markersize=7,
        linewidth=1.6,
        label="平均吞吐退化成本",
        zorder=3,
    )

    ax1.set_xticks(x)
    ax1.set_xticklabels(x_labels, fontsize=9)
    ax1.set_ylabel("平均额定容量 / kWh", fontsize=10, color="#222222")
    ax2.set_ylabel("平均吞吐退化成本 /（元/kWh）", fontsize=10, color="#c0392b")
    ax1.set_xlabel("车型", fontsize=10)
    ax1.tick_params(axis="y", labelcolor="#222222")
    ax2.tick_params(axis="y", labelcolor="#c0392b")
    ax1.set_title("分车型容量—吞吐退化成本异质性", fontsize=11, pad=10)
    ax1.grid(axis="y", linestyle=":", alpha=0.45, zorder=0)

    # 柱顶标注容量
    for rect, v in zip(bars, cap):
        ax1.annotate(
            f"{v:.1f}",
            xy=(rect.get_x() + rect.get_width() / 2.0, rect.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#111111",
        )

    # 折线点旁标注退化成本
    for xi, v in zip(x, deg):
        ax2.annotate(
            f"{v:.3f}",
            xy=(xi, v),
            xytext=(8, 4),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=8,
            color="#c0392b",
        )

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=True, framealpha=0.95)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / f"{OUT_STEM}.png", dpi=220)
    fig.savefig(OUT_DIR / f"{OUT_STEM}.svg")
    fig.savefig(OUT_DIR / f"{OUT_STEM}.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
