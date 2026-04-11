# -*- coding: utf-8 -*-
"""
基于 `run_unified_sensitivity_robustness_pack.py` 等脚本产出的结果，生成论文用
「灵敏度分析图」「鲁棒性分析图」及汇总表（相对基准变化率 %）。

输入（默认路径相对仓库根）：
  - results/robustness/ev_availability_results.csv
  - results/robustness/pv_scale_results.csv
  - results/problem2_lifecycle/scans/scan_auto_weight_scan/weight_scan_summary.csv（寿命权重 w）

输出：
  - results/robustness/ev_availability_sensitivity.{png,pdf}（旧版四宫格，保留兼容）
  - results/robustness/ev_availability_sensitivity_polished.{png,pdf}
  - results/robustness/pv_robust_*_improvement.{png,pdf}（旧版折线）
  - results/robustness/pv_robust_cost_improvement_polished.{png,pdf}
  - results/robustness/pv_robust_grid_improvement_polished.{png,pdf}
  - results/robustness/sensitivity_robustness_polished_figure_captions.md（三张图注）
  - results/sensitivity/tornado_operation_cost.{png,pdf}
  - results/sensitivity/tornado_operation_cost_polished.{png,pdf}
  - results/sensitivity/sensitivity_three_point_compare.{png,pdf}
  - results/sensitivity/tornado_operation_cost_summary.{csv,md}
  - results/sensitivity/sensitivity_analysis_summary.{csv,md}
  - results/robustness/robustness_analysis_summary.{csv,md}
  - results/sensitivity/paper_auto_conclusions.md（三段论文式结论文本）

用法：
  python code/python/analysis/plot_sensitivity_robustness_paper.py --repo-root <仓库根>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

_HERE = Path(__file__).resolve().parent
_REPO_DEFAULT = _HERE.parents[3]

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
# 论文级统一视觉（灵敏度浅蓝 #ACD6EC；对比/改进率 #F5A889）
STYLE = {
    "sens_line": "#ACD6EC",
    "sens_marker": "#ACD6EC",
    "robust_cost": "#F5A889",
    "robust_grid": "#F5A889",
    "ref_line": "#b0b0b0",
    "grid_alpha": 0.28,
    "title_fs": 12,
    "label_fs": 10.5,
    "tick_fs": 10,
    "suptitle_fs": 13,
}

PATH_EV = Path("results/robustness/ev_availability_results.csv")
PATH_PV = Path("results/robustness/pv_scale_results.csv")
PATH_WEIGHT = Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/weight_scan_summary.csv")


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def rel_pct(val: float, ref: float) -> float:
    if ref is None or abs(ref) < 1e-12:
        return float("nan")
    return float((val - ref) / ref * 100.0)


def load_ev(repo: Path) -> pd.DataFrame:
    p = repo / PATH_EV
    if not p.is_file():
        raise FileNotFoundError(f"缺少 {p}")
    return pd.read_csv(p, encoding="utf-8-sig")


def load_pv(repo: Path) -> pd.DataFrame:
    p = repo / PATH_PV
    if not p.is_file():
        raise FileNotFoundError(f"缺少 {p}")
    return pd.read_csv(p, encoding="utf-8-sig")


def load_weight_scan(repo: Path) -> pd.DataFrame:
    p = repo / PATH_WEIGHT
    if not p.is_file():
        raise FileNotFoundError(
            f"缺少 {p}\n请先运行问题二权重扫描或确认 scan_auto_weight_scan 已存在。"
        )
    return pd.read_csv(p, encoding="utf-8-sig")


def plot_ev_sensitivity(ev: pd.DataFrame, out_dir: Path) -> None:
    ref = ev[ev["ev_power_scale"] == 1.0]
    if ref.empty:
        raise ValueError("ev_availability_results.csv 中缺少 ev_power_scale=1.0 基准行。")
    r = ref.iloc[0]
    metrics = [
        ("operation_cost", "运行成本 operation_cost"),
        ("ev_throughput_kwh", "EV 吞吐 ev_throughput_kwh"),
        ("ev_discharge_energy_kwh", "EV 放电 ev_discharge_energy_kwh"),
        ("ess_throughput_kwh", "ESS 吞吐 ess_throughput_kwh"),
    ]
    x = ev["ev_power_scale"].astype(float).to_numpy()
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 7.0), dpi=150, constrained_layout=True)
    fig.suptitle("问题二：EV 可用性灵敏度分析（相对基准场景）", fontsize=13, fontweight="bold")
    for ax, (col, title) in zip(axes.flat, metrics):
        ref_v = float(r[col])
        y = np.array([rel_pct(float(v), ref_v) for v in ev[col].astype(float)], dtype=float)
        ax.axvline(1.0, color="#555", ls="--", lw=1.0, alpha=0.85)
        ax.axhline(0.0, color="#555", ls="--", lw=1.0, alpha=0.85)
        ax.plot(x, y, "o-", color="#1f77b4", lw=2.2, ms=8)
        ax.set_xlabel("EV 充/放功率上限缩放系数")
        ax.set_ylabel("相对基准变化率 (%)")
        ax.set_title(title)
    fig.savefig(out_dir / "ev_availability_sensitivity.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "ev_availability_sensitivity.pdf", bbox_inches="tight")
    plt.close(fig)


def _axes_paper_grid(ax: plt.Axes) -> None:
    ax.grid(True, axis="y", linestyle=":", alpha=STYLE["grid_alpha"], color="0.45")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_ev_availability_polished(ev: pd.DataFrame, out_dir: Path) -> None:
    """论文级三联图：运行成本、EV 放电、EV 吞吐相对标称（×1.0）变化率；ESS 过小时仅脚注。"""
    ev = ev.sort_values("ev_power_scale").reset_index(drop=True)
    ref = ev[ev["ev_power_scale"] == 1.0]
    if ref.empty:
        raise ValueError("ev_availability_results.csv 中缺少 ev_power_scale=1.0 基准行。")
    r = ref.iloc[0]
    x = ev["ev_power_scale"].astype(float).to_numpy()
    ref_ess = float(r["ess_throughput_kwh"])
    y_ess = np.array([rel_pct(float(v), ref_ess) for v in ev["ess_throughput_kwh"].astype(float)], dtype=float)
    ess_note = bool(np.nanmax(np.abs(y_ess)) < 0.05)

    panels: list[tuple[str, str, str]] = [
        ("operation_cost", "运行成本", "运行成本变化率（%）"),
        ("ev_discharge_energy_kwh", "EV 放电量", "EV 放电量变化率（%）"),
        ("ev_throughput_kwh", "EV 吞吐量", "EV 吞吐量变化率（%）"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 4.35), dpi=200)
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.20, top=0.82, wspace=0.34)
    fig.suptitle("EV可用性变化对系统调度行为的影响", fontsize=STYLE["suptitle_fs"], fontweight="semibold")

    for ax, (col, short_title, ylabel) in zip(axes, panels):
        ref_v = float(r[col])
        y = np.array([rel_pct(float(v), ref_v) for v in ev[col].astype(float)], dtype=float)
        ax.axvline(1.0, color=STYLE["ref_line"], ls="--", lw=1.05, zorder=0)
        ax.axhline(0.0, color=STYLE["ref_line"], ls="--", lw=1.05, zorder=0)
        ax.plot(
            x,
            y,
            "o-",
            color=STYLE["sens_line"],
            markerfacecolor=STYLE["sens_marker"],
            lw=2.0,
            ms=8,
            zorder=2,
        )
        ax.set_xlabel("EV充/放功率上限缩放系数", fontsize=STYLE["label_fs"])
        ax.set_ylabel(ylabel, fontsize=STYLE["label_fs"])
        ax.set_title(short_title, fontsize=STYLE["title_fs"], pad=6)
        ax.tick_params(axis="both", labelsize=STYLE["tick_fs"])
        _axes_paper_grid(ax)
        for xi, yi in zip(x, y):
            ax.annotate(
                f"{yi:.2f}",
                (xi, yi),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=9,
                color="0.25",
            )

    if ess_note:
        fig.text(
            0.5,
            0.04,
            "ESS 吞吐量变化幅度极小，表明其对 EV 可用性扰动不敏感。",
            ha="center",
            fontsize=10,
            style="italic",
            color="0.35",
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"ev_availability_sensitivity_polished.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def compute_pv_improvement(pv: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    for s in sorted(pv["pv_scale"].unique()):
        sub = pv[pv["pv_scale"] == s]
        b = sub.loc[sub["model"] == "baseline", "operation_cost"].astype(float)
        c = sub.loc[sub["model"] == "coordinated", "operation_cost"].astype(float)
        gb = sub.loc[sub["model"] == "baseline", "grid_import_energy_kwh"].astype(float)
        gc = sub.loc[sub["model"] == "coordinated", "grid_import_energy_kwh"].astype(float)
        rb = sub.loc[sub["model"] == "baseline", "renewable_consumption_ratio"].astype(float)
        rc = sub.loc[sub["model"] == "coordinated", "renewable_consumption_ratio"].astype(float)
        if len(b) != 1 or len(c) != 1:
            continue
        bv, cv = float(b.iloc[0]), float(c.iloc[0])
        gbv, gcv = float(gb.iloc[0]), float(gc.iloc[0])
        cost_imp = (bv - cv) / bv * 100.0 if abs(bv) > 1e-9 else float("nan")
        grid_imp = (gbv - gcv) / gbv * 100.0 if abs(gbv) > 1e-9 else float("nan")
        ren_imp = (float(rc.iloc[0]) - float(rb.iloc[0])) / max(float(rb.iloc[0]), 1e-12) * 100.0
        rows.append(
            {
                "pv_scale": float(s),
                "improvement_cost_pct": cost_imp,
                "improvement_grid_pct": grid_imp,
                "renewable_baseline": float(rb.iloc[0]),
                "renewable_coordinated": float(rc.iloc[0]),
                "renewable_improvement_pct": ren_imp,
            }
        )
    return pd.DataFrame(rows).sort_values("pv_scale")


def _save_pv_robust_polished_bar_figs(imp: pd.DataFrame, out_dir: Path) -> None:
    """由已算得的改进率表写出论文级柱状图（绿：成本；橙：购电）。"""
    scales = imp["pv_scale"].to_numpy()
    x = np.arange(len(scales))
    labels = [f"{s:g}" for s in scales]

    def _one_bar_fig(values: np.ndarray, ylabel: str, title: str, color: str, fname: str) -> None:
        fig, ax = plt.subplots(figsize=(7.4, 4.6), dpi=200)
        fig.subplots_adjust(left=0.12, right=0.96, top=0.88, bottom=0.14)
        ax.axhline(0.0, color=STYLE["ref_line"], ls="-", lw=1.0, zorder=0)
        bars = ax.bar(x, values, color=color, edgecolor="0.25", linewidth=0.6, width=0.55, zorder=2)
        ax.set_xticks(x, labels)
        ax.set_xlabel("光伏出力缩放系数", fontsize=STYLE["label_fs"])
        ax.set_ylabel(ylabel, fontsize=STYLE["label_fs"])
        ax.set_title(title, fontsize=STYLE["title_fs"], pad=10, fontweight="semibold")
        ax.tick_params(axis="both", labelsize=STYLE["tick_fs"])
        _axes_paper_grid(ax)
        ymax = float(np.nanmax(values)) if len(values) else 0.0
        ymin = float(np.nanmin(values)) if len(values) else 0.0
        span = max(abs(ymax), abs(ymin), 1e-6)
        pad = span * 0.18
        ax.set_ylim(ymin - pad, ymax + pad)
        for rect, v in zip(bars, values):
            h = rect.get_height()
            off = span * 0.05
            if h >= 0:
                y_text = h + off
                va = "bottom"
            else:
                y_text = h - off
                va = "top"
            ax.text(rect.get_x() + rect.get_width() / 2, y_text, f"{v:.2f}%", ha="center", va=va, fontsize=10, color="0.2")
        out_dir.mkdir(parents=True, exist_ok=True)
        for ext in ("png", "pdf"):
            fig.savefig(out_dir / f"{fname}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    cost_vals = imp["improvement_cost_pct"].to_numpy(dtype=float)
    grid_vals = imp["improvement_grid_pct"].to_numpy(dtype=float)
    _one_bar_fig(
        cost_vals,
        "成本改进率（%）",
        "不同光伏扰动场景下协同调度的成本改进率",
        STYLE["robust_cost"],
        "pv_robust_cost_improvement_polished",
    )
    _one_bar_fig(
        grid_vals,
        "购电改善率（%）",
        "不同光伏扰动场景下协同调度的购电改善率",
        STYLE["robust_grid"],
        "pv_robust_grid_improvement_polished",
    )


def plot_pv_robustness_polished(pv: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """柱状图版 PV 鲁棒性（论文级）；返回改进率表。"""
    imp = compute_pv_improvement(pv)
    _save_pv_robust_polished_bar_figs(imp, out_dir)
    return imp


def plot_pv_robustness(pv: pd.DataFrame, out_dir: Path) -> tuple[str, pd.DataFrame]:
    """返回消纳率备注与改进率明细表。"""
    imp = compute_pv_improvement(pv)
    _save_pv_robust_polished_bar_figs(imp, out_dir)

    scales = imp["pv_scale"].to_numpy()
    fig, ax = plt.subplots(figsize=(7.8, 4.8), dpi=150, constrained_layout=True)
    ax.axhline(0.0, color="#555", ls="--", lw=1.0)
    ax.plot(scales, imp["improvement_cost_pct"], "o-", color="#2ca02c", lw=2.4, ms=9, label="成本改进率")
    ax.set_xlabel("光伏出力缩放系数")
    ax.set_ylabel("改进率 (%) = (baseline−协同)/baseline×100")
    ax.set_title("PV 扰动鲁棒性：协同相对 baseline 的运行成本改进率")
    ax.legend(loc="best")
    fig.savefig(out_dir / "pv_robust_cost_improvement.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "pv_robust_cost_improvement.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.8, 4.8), dpi=150, constrained_layout=True)
    ax.axhline(0.0, color="#555", ls="--", lw=1.0)
    ax.plot(scales, imp["improvement_grid_pct"], "s-", color="#d62728", lw=2.4, ms=9, label="购电量改进率")
    ax.set_xlabel("光伏出力缩放系数")
    ax.set_ylabel("改进率 (%) = (baseline−协同)/baseline×100")
    ax.set_title("PV 扰动鲁棒性：协同相对 baseline 的购电量改进率")
    ax.legend(loc="best")
    fig.savefig(out_dir / "pv_robust_grid_improvement.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "pv_robust_grid_improvement.pdf", bbox_inches="tight")
    plt.close(fig)

    ren_vals = np.concatenate([imp["renewable_baseline"].values, imp["renewable_coordinated"].values])
    ren_note = ""
    if np.nanstd(ren_vals) < 1e-6 or (np.max(ren_vals) - np.min(ren_vals)) < 1e-5:
        ren_note = (
            "可再生能源本地消纳率（renewable_consumption_ratio）在各 PV 缩放下数值几乎恒定（见表），"
            "未单独绘制消纳率提升图。"
        )
    else:
        ren_note = "消纳率存在可见差异，可扩展绘制 improvement_renewable 图（当前脚本未生成独立图）。"
    return ren_note, imp


def build_p2_unified_tornado_summary(repo: Path) -> tuple[pd.DataFrame, float]:
    """
    统一基准：PV=1.0、EV 充放上限缩放=1.0、w=1.0 的 operation_cost（`weight_scan_summary` w=1 行）。

    w∈{0,2} 为全周扫描真实值相对基准；PV、EV 端点由短周期协同扫描经比例桥接到全周基准后再算变化率。
    """
    ev = load_ev(repo)
    pv = load_pv(repo)
    wdf = load_weight_scan(repo)
    w1 = wdf[wdf["ess_deg_weight"] == 1.0]
    if w1.empty:
        raise ValueError("weight_scan_summary 中缺少 ess_deg_weight=1.0 行。")
    ref = float(w1["operation_cost"].iloc[0])

    pv_ref = float(pv.loc[(pv["pv_scale"] == 1.0) & (pv["model"] == "coordinated"), "operation_cost"].iloc[0])
    c_pv_lo = float(pv.loc[(pv["pv_scale"] == 0.9) & (pv["model"] == "coordinated"), "operation_cost"].iloc[0])
    c_pv_hi = float(pv.loc[(pv["pv_scale"] == 1.1) & (pv["model"] == "coordinated"), "operation_cost"].iloc[0])
    cost_pv_lo = ref * (c_pv_lo / pv_ref)
    cost_pv_hi = ref * (c_pv_hi / pv_ref)
    low_pct_pv = rel_pct(cost_pv_lo, ref)
    high_pct_pv = rel_pct(cost_pv_hi, ref)

    ev_ref = float(ev.loc[ev["ev_power_scale"] == 1.0, "operation_cost"].iloc[0])
    c_ev_lo = float(ev.loc[ev["ev_power_scale"] == 0.8, "operation_cost"].iloc[0])
    c_ev_hi = float(ev.loc[ev["ev_power_scale"] == 1.2, "operation_cost"].iloc[0])
    cost_ev_lo = ref * (c_ev_lo / ev_ref)
    cost_ev_hi = ref * (c_ev_hi / ev_ref)
    low_pct_ev = rel_pct(cost_ev_lo, ref)
    high_pct_ev = rel_pct(cost_ev_hi, ref)

    w0 = wdf[wdf["ess_deg_weight"] == 0.0]
    w2 = wdf[wdf["ess_deg_weight"] == 2.0]
    if w0.empty or w2.empty:
        raise ValueError("weight_scan_summary 中缺少 w=0 或 w=2 行。")
    low_pct_w = rel_pct(float(w0["operation_cost"].iloc[0]), ref)
    high_pct_w = rel_pct(float(w2["operation_cost"].iloc[0]), ref)

    rows = [
        {
            "parameter": "PV出力缩放",
            "low_scenario": "PV=0.9",
            "high_scenario": "PV=1.1",
            "low_change_pct": low_pct_pv,
            "high_change_pct": high_pct_pv,
            "max_abs_change_pct": max(abs(low_pct_pv), abs(high_pct_pv)),
        },
        {
            "parameter": "EV可用性缩放",
            "low_scenario": "EV=0.8",
            "high_scenario": "EV=1.2",
            "low_change_pct": low_pct_ev,
            "high_change_pct": high_pct_ev,
            "max_abs_change_pct": max(abs(low_pct_ev), abs(high_pct_ev)),
        },
        {
            "parameter": "寿命权重",
            "low_scenario": "w=0",
            "high_scenario": "w=2",
            "low_change_pct": low_pct_w,
            "high_change_pct": high_pct_w,
            "max_abs_change_pct": max(abs(low_pct_w), abs(high_pct_w)),
        },
    ]
    df = pd.DataFrame(rows).sort_values("max_abs_change_pct", ascending=False).reset_index(drop=True)
    return df, ref


def plot_p2_unified_tornado_chart(summary: pd.DataFrame, sens_dir: Path) -> None:
    sens_dir.mkdir(parents=True, exist_ok=True)
    d = summary.sort_values("max_abs_change_pct", ascending=False).reset_index(drop=True)
    n = len(d)
    y_idx = np.arange(n)
    labels = d["parameter"].tolist()
    lows = d["low_change_pct"].to_numpy(dtype=float)
    highs = d["high_change_pct"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(9.2, 4.6), dpi=200)
    # 左侧留足空间，避免 y 轴参数名与负向柱上的数值重叠
    fig.subplots_adjust(left=0.30, right=0.96, top=0.90, bottom=0.14)
    c_lo = STYLE["sens_line"]
    c_hi = STYLE["robust_grid"]
    # 数值写在「背离 y 轴、朝向 x=0」一侧：负向端点用「向内一小步」避免越过 0 或与 y 轴字重叠
    gap = 0.22

    def _label_pos(x_end: float) -> tuple[float, str]:
        if x_end >= 0:
            return x_end + gap, "left"
        inward = min(gap, abs(x_end) * 0.38)
        return x_end + inward, "left"

    for i, y in enumerate(y_idx):
        lo, hi = float(lows[i]), float(highs[i])
        if lo < 0:
            ax.barh(y, -lo, left=lo, height=0.38, color=c_lo, edgecolor="0.25", linewidth=0.55, zorder=2)
        else:
            ax.barh(y, lo, left=0.0, height=0.38, color=c_lo, edgecolor="0.25", linewidth=0.55, zorder=2)
        if hi < 0:
            ax.barh(y, -hi, left=hi, height=0.38, color=c_hi, edgecolor="0.25", linewidth=0.55, zorder=2)
        else:
            ax.barh(y, hi, left=0.0, height=0.38, color=c_hi, edgecolor="0.25", linewidth=0.55, zorder=2)

        xl, hal = _label_pos(lo)
        ax.text(xl, y, f"{lo:.2f}%", ha=hal, va="center", fontsize=9, color="0.25", zorder=4)
        xh, hah = _label_pos(hi)
        ax.text(xh, y, f"{hi:.2f}%", ha=hah, va="center", fontsize=9, color="0.25", zorder=4)

    ax.axvline(0.0, color=STYLE["ref_line"], ls="--", lw=1.1, zorder=1)
    ax.set_yticks(y_idx, labels, fontsize=STYLE["tick_fs"])
    ax.tick_params(axis="y", pad=10)
    ax.invert_yaxis()
    ax.set_xlabel("相对基准运行成本变化率（%）", fontsize=STYLE["label_fs"])
    ax.set_title("关键参数对运行成本的灵敏度排序", fontsize=STYLE["title_fs"], fontweight="semibold", pad=10)
    ax.tick_params(axis="x", labelsize=STYLE["tick_fs"])
    _axes_paper_grid(ax)
    ax.legend(
        handles=[
            Patch(facecolor=c_lo, edgecolor="0.25", label="低值扰动"),
            Patch(facecolor=c_hi, edgecolor="0.25", label="高值扰动"),
        ],
        loc="lower right",
        fontsize=10,
        frameon=True,
    )
    ax.margins(x=0.08)

    for ext in ("png", "pdf"):
        fig.savefig(sens_dir / f"tornado_operation_cost.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_p2_unified_tornado_chart_polished(summary: pd.DataFrame, sens_dir: Path) -> None:
    """论文版龙卷风：副标题标明基准、小扰动引线标注；局部放大为右侧独立子图，避免与主轴重叠。"""
    sens_dir.mkdir(parents=True, exist_ok=True)
    d = summary.sort_values("max_abs_change_pct", ascending=False).reset_index(drop=True)
    n = len(d)
    y_idx = np.arange(n)
    labels = d["parameter"].tolist()
    lows = d["low_change_pct"].to_numpy(dtype=float)
    highs = d["high_change_pct"].to_numpy(dtype=float)
    c_lo = STYLE["sens_line"]
    c_hi = STYLE["robust_grid"]
    gap = 0.26
    small_thr = 0.30

    def _label_pos_large(x_end: float) -> tuple[float, str]:
        if x_end >= 0:
            return x_end + gap, "left"
        inward = min(gap, abs(x_end) * 0.38)
        return x_end + inward, "left"

    fig = plt.figure(figsize=(10.2, 5.55), dpi=200)
    # 左：主龙卷风（略抬高底边，为 x 轴标签与图例留出竖向空隙）；右：局部放大
    ax = fig.add_axes([0.11, 0.24, 0.52, 0.54])
    axins = fig.add_axes([0.68, 0.27, 0.28, 0.48])

    fig.suptitle("关键参数对运行成本的灵敏度排序", fontsize=STYLE["suptitle_fs"], fontweight="semibold", y=0.96)
    fig.text(
        0.5,
        0.895,
        "基准场景：PV=1.0，EV可用性=1.0，寿命权重=1.0\n（0 表示基准运行成本）",
        ha="center",
        va="top",
        fontsize=9.0,
        color="0.38",
        linespacing=1.25,
    )

    for i, y in enumerate(y_idx):
        lo, hi = float(lows[i]), float(highs[i])
        if lo < 0:
            ax.barh(y, -lo, left=lo, height=0.38, color=c_lo, edgecolor="0.25", linewidth=0.55, zorder=2)
        else:
            ax.barh(y, lo, left=0.0, height=0.38, color=c_lo, edgecolor="0.25", linewidth=0.55, zorder=2)
        if hi < 0:
            ax.barh(y, -hi, left=hi, height=0.38, color=c_hi, edgecolor="0.25", linewidth=0.55, zorder=2)
        else:
            ax.barh(y, hi, left=0.0, height=0.38, color=c_hi, edgecolor="0.25", linewidth=0.55, zorder=2)

        lo_s = f"{lo:.2f}%"
        hi_s = f"{hi:.2f}%"
        if abs(lo) < small_thr:
            ax.annotate(
                lo_s,
                xy=(lo, y),
                xytext=(26, 14 if (i % 2 == 0) else 10),
                textcoords="offset points",
                ha="left",
                va="bottom",
                fontsize=8.8,
                color="0.28",
                zorder=5,
                arrowprops=dict(arrowstyle="-", lw=0.5, color="0.42", shrinkA=2, shrinkB=2),
            )
        else:
            xl, hal = _label_pos_large(lo)
            ax.text(xl, y, lo_s, ha=hal, va="center", fontsize=9, color="0.28", zorder=4)
        if abs(hi) < small_thr:
            ax.annotate(
                hi_s,
                xy=(hi, y),
                xytext=(26, -14 if (i % 2 == 0) else -10),
                textcoords="offset points",
                ha="left",
                va="top",
                fontsize=8.8,
                color="0.28",
                zorder=5,
                arrowprops=dict(arrowstyle="-", lw=0.5, color="0.42", shrinkA=2, shrinkB=2),
            )
        else:
            xh, hah = _label_pos_large(hi)
            ax.text(xh, y, hi_s, ha=hah, va="center", fontsize=9, color="0.28", zorder=4)

    ax.axvline(0.0, color=STYLE["ref_line"], ls="--", lw=1.15, zorder=1)
    ax.set_yticks(y_idx, labels, fontsize=STYLE["tick_fs"])
    ax.tick_params(axis="y", pad=12)
    ax.invert_yaxis()
    ax.set_xlabel("相对基准运行成本变化率（%）", fontsize=STYLE["label_fs"], labelpad=8)
    ax.tick_params(axis="x", labelsize=STYLE["tick_fs"])
    _axes_paper_grid(ax)
    ax.margins(x=0.09)

    leg_handles = [
        Patch(facecolor=c_lo, edgecolor="0.25", label="低值扰动"),
        Patch(facecolor=c_hi, edgecolor="0.25", label="高值扰动"),
    ]
    # 图例锚在图下方空白处，loc=upper_center 使图框向下生长，避免压住主图 x 轴标签
    fig.legend(
        handles=leg_handles,
        loc="upper center",
        bbox_to_anchor=(0.40, 0.068),
        ncol=2,
        fontsize=9.5,
        frameon=True,
        fancybox=False,
        edgecolor="0.35",
    )

    zoom_names = ["EV可用性缩放", "寿命权重"]
    sub = d.loc[d["parameter"].isin(zoom_names)].copy()
    sub["_ord"] = sub["parameter"].map({zoom_names[0]: 0, zoom_names[1]: 1})
    sub = sub.sort_values("_ord")
    y_in = np.arange(len(sub))
    for j, (_, row) in enumerate(sub.iterrows()):
        yj = float(y_in[j])
        lo, hi = float(row["low_change_pct"]), float(row["high_change_pct"])
        if lo < 0:
            axins.barh(yj, -lo, left=lo, height=0.36, color=c_lo, edgecolor="0.25", linewidth=0.45, zorder=2)
        else:
            axins.barh(yj, lo, left=0.0, height=0.36, color=c_lo, edgecolor="0.25", linewidth=0.45, zorder=2)
        if hi < 0:
            axins.barh(yj, -hi, left=hi, height=0.36, color=c_hi, edgecolor="0.25", linewidth=0.45, zorder=2)
        else:
            axins.barh(yj, hi, left=0.0, height=0.36, color=c_hi, edgecolor="0.25", linewidth=0.45, zorder=2)
        # 上下错位标注，不用引线，避免与右轴挤在一起
        axins.text(lo, yj + 0.22, f"{lo:.2f}%", ha="center", va="bottom", fontsize=8.6, color="0.32")
        axins.text(hi, yj - 0.22, f"{hi:.2f}%", ha="center", va="top", fontsize=8.6, color="0.32")
    axins.axvline(0.0, color=STYLE["ref_line"], ls="--", lw=1.0, zorder=1)
    axins.set_xlim(-0.2, 0.2)
    axins.set_yticks(y_in, sub["parameter"].tolist(), fontsize=8.8)
    axins.set_title("局部放大（±0.2%）", fontsize=9.2, pad=6)
    axins.set_xlabel("变化率（%）", fontsize=8.5, labelpad=4)
    axins.tick_params(axis="x", labelsize=8)
    axins.grid(True, axis="x", linestyle=":", alpha=0.35)
    axins.spines["top"].set_visible(False)
    axins.spines["right"].set_visible(False)
    axins.set_ylim(-0.48, float(len(y_in) - 1) + 0.48)

    for ext in ("png", "pdf"):
        fig.savefig(sens_dir / f"tornado_operation_cost_polished.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_sensitivity_three_point_compare(summary: pd.DataFrame, sens_dir: Path) -> None:
    """低—基准(0)—高 三点连线对比图。"""
    sens_dir.mkdir(parents=True, exist_ok=True)
    order = ["PV出力缩放", "EV可用性缩放", "寿命权重"]
    rows = []
    for name in order:
        sub = summary.loc[summary["parameter"] == name]
        if sub.empty:
            continue
        rows.append(sub.iloc[0])
    d = pd.DataFrame(rows).reset_index(drop=True)
    n = len(d)
    y_idx = np.arange(n)
    c_lo = STYLE["sens_line"]
    c_hi = STYLE["robust_grid"]
    c_mid = "#666666"

    fig, ax = plt.subplots(figsize=(8.2, 4.45), dpi=200)
    fig.subplots_adjust(left=0.26, right=0.96, top=0.78, bottom=0.14)
    fig.text(
        0.5,
        0.91,
        "基准场景：PV=1.0，EV可用性=1.0，寿命权重=1.0；0表示基准运行成本",
        ha="center",
        fontsize=8.8,
        color="0.38",
    )
    for i, y in enumerate(y_idx):
        lo = float(d.iloc[i]["low_change_pct"])
        hi = float(d.iloc[i]["high_change_pct"])
        xs = [lo, 0.0, hi]
        ax.plot(xs, [y, y, y], color="0.45", lw=1.05, ls="-", zorder=1)
        ax.scatter([lo], [y], s=52, color=c_lo, edgecolors="0.25", linewidths=0.6, zorder=3)
        ax.scatter([0.0], [y], s=52, color=c_mid, edgecolors="0.25", linewidths=0.6, zorder=3)
        ax.scatter([hi], [y], s=52, color=c_hi, edgecolors="0.25", linewidths=0.6, zorder=3)
        ax.text(lo, y + 0.19, f"{lo:.2f}%", ha="center", va="bottom", fontsize=8.5, color="0.32")
        ax.text(0.0, y + 0.19, "0.00%", ha="center", va="bottom", fontsize=8.5, color="0.32")
        ax.text(hi, y + 0.19, f"{hi:.2f}%", ha="center", va="bottom", fontsize=8.5, color="0.32")

    ax.axvline(0.0, color=STYLE["ref_line"], ls="--", lw=1.1, zorder=0)
    ax.set_yticks(y_idx, d["parameter"].tolist(), fontsize=STYLE["tick_fs"])
    ax.set_xlabel("相对基准运行成本变化率（%）", fontsize=STYLE["label_fs"])
    ax.set_title("关键参数扰动下运行成本相对基准的变化", fontsize=STYLE["title_fs"], fontweight="semibold", pad=6)
    ax.tick_params(axis="x", labelsize=STYLE["tick_fs"])
    _axes_paper_grid(ax)
    ax.margins(x=0.06)
    mx = max(abs(float(d["low_change_pct"].min())), abs(float(d["high_change_pct"].max())), 0.5) * 1.12
    ax.set_xlim(-mx, mx)
    ax.set_ylim(-0.55, (n - 1) + 0.55)

    for ext in ("png", "pdf"):
        fig.savefig(sens_dir / f"sensitivity_three_point_compare.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def tornado_summary_to_long_rows(summary: pd.DataFrame, ref_cost: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, r in summary.iterrows():
        rows.append(
            {
                "parameter": f"{r['parameter']}｜{r['low_scenario']}",
                "scenario": "p2_unified_tornado",
                "metric": "operation_cost",
                "raw_value": float("nan"),
                "relative_change_pct": float(r["low_change_pct"]),
                "baseline_reference": f"ref_operation_cost={ref_cost:.6f}",
            }
        )
        rows.append(
            {
                "parameter": f"{r['parameter']}｜{r['high_scenario']}",
                "scenario": "p2_unified_tornado",
                "metric": "operation_cost",
                "raw_value": float("nan"),
                "relative_change_pct": float(r["high_change_pct"]),
                "baseline_reference": f"ref_operation_cost={ref_cost:.6f}",
            }
        )
    return pd.DataFrame(rows)


def write_tornado_operation_cost_summary_md(
    summary: pd.DataFrame,
    ref_cost: float,
    conclusion: str,
    out_md: Path,
) -> None:
    note = (
        "## 基准与口径\n\n"
        f"- **统一基准**（PV=1.0、EV 充放上限缩放=1.0、w=1.0）下 `operation_cost` = **{ref_cost:.6f}** 元（来源：`{PATH_WEIGHT.as_posix()}`，`ess_deg_weight=1.0`）。\n"
        "- **寿命权重** w=0、w=2：全周扫描真实运行成本相对基准的变化率。\n"
        "- **PV 出力缩放**、**EV 可用性缩放**：与全周基准量纲不一致的短周期协同结果，采用 **比例桥接** "
        "`C_扰动^* = C_ref × C_扰动^{short} / C_名义^{short}` 后，再按 `(C^*−C_ref)/C_ref×100` 计算；"
        "该百分比等于短周期名义点上的相对变化率。\n"
    )
    tbl = _md_table(
        summary[
            [
                "parameter",
                "low_scenario",
                "high_scenario",
                "low_change_pct",
                "high_change_pct",
                "max_abs_change_pct",
            ]
        ]
    )
    out_md.write_text(note + "\n## 汇总表\n\n" + tbl + "\n\n## 自动结论（论文可用）\n\n" + conclusion + "\n", encoding="utf-8")


def tornado_auto_conclusion_text(summary: pd.DataFrame, ref_cost: float) -> str:
    s = summary.sort_values("max_abs_change_pct", ascending=False).reset_index(drop=True)
    most, least = s.iloc[0], s.iloc[-1]
    w_row = s.loc[s["parameter"] == "寿命权重"]
    w_row = w_row.iloc[0] if len(w_row) else None
    w_span = max(abs(float(w_row["low_change_pct"])), abs(float(w_row["high_change_pct"]))) if w_row is not None else 0.0
    pv_row = s.loc[s["parameter"] == "PV出力缩放"]
    pv_span = (
        max(abs(float(pv_row.iloc[0]["low_change_pct"])), abs(float(pv_row.iloc[0]["high_change_pct"])))
        if len(pv_row)
        else 0.0
    )

    p1 = (
        f"在统一基准运行成本（约 {ref_cost:.2f} 元）下，**{most['parameter']}** 对运行成本最为敏感："
        f"低值（{most['low_scenario']}）与高值（{most['high_scenario']}）相对基准的最大绝对变化率约为 **{float(most['max_abs_change_pct']):.2f}%**。"
    )
    p2 = (
        f"**{least['parameter']}** 的影响相对最弱，其低/高端点相对基准的最大绝对变化率约为 **{float(least['max_abs_change_pct']):.2f}%**。"
    )
    p3 = (
        "寿命权重支路在全周模型上直接改变退化惩罚权重，优化器主要通过 **抑制 EV/ESS 吞吐与放电形态** 来降低退化货币化成本，"
        f"因而在 w=0 与 w=2 端点之间，**运行成本** `operation_cost` 的相对波动幅度通常较小（本算例约 **{w_span:.2f}%** 量级），"
        f"明显弱于 **PV 出力缩放** 通过改变可再生可用功率与购电结构所带来的成本杠杆（约 **{pv_span:.2f}%** 量级）。"
        "换言之，寿命权重更显著地体现在 **资源调用轨迹与退化分项** 的再分配上，而非短期电费账面的剧烈跳变。"
    )
    return p1 + "\n\n" + p2 + "\n\n" + p3


def build_sensitivity_table(ev: pd.DataFrame, wdf: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    ev_ref = ev[ev["ev_power_scale"] == 1.0].iloc[0]
    for _, r in ev.iterrows():
        sc = float(r["ev_power_scale"])
        for col in ["operation_cost", "ev_throughput_kwh", "ev_discharge_energy_kwh", "ess_throughput_kwh"]:
            ref_v = float(ev_ref[col])
            rows.append(
                {
                    "parameter": f"ev_power_scale={sc}",
                    "scenario": "problem2_lifecycle_ev_scale",
                    "metric": col,
                    "raw_value": float(r[col]),
                    "relative_change_pct": rel_pct(float(r[col]), ref_v),
                    "baseline_reference": f"ev_power_scale=1.0, {col}={ref_v}",
                }
            )

    w_ref = wdf[wdf["ess_deg_weight"] == 1.0].iloc[0]
    for _, r in wdf.iterrows():
        wv = float(r["ess_deg_weight"])
        for col in ["operation_cost", "objective_total", "ev_throughput", "ess_throughput"]:
            if col not in r.index:
                continue
            ref_v = float(w_ref[col])
            try:
                rv = float(r[col])
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "parameter": f"lifetime_weight_w={wv}",
                    "scenario": "problem2_lifecycle_weight_scan",
                    "metric": col,
                    "raw_value": rv,
                    "relative_change_pct": rel_pct(rv, ref_v),
                    "baseline_reference": f"w=1.0, {col}={ref_v}",
                }
            )

    return pd.DataFrame(rows)


def build_robustness_table(pv: pd.DataFrame, imp: pd.DataFrame, ren_note: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, r in imp.iterrows():
        s = float(r["pv_scale"])
        for m in ["operation_cost", "grid_import_energy_kwh", "renewable_consumption_ratio"]:
            b = float(pv.loc[(pv["pv_scale"] == s) & (pv["model"] == "baseline"), m].iloc[0])
            c = float(pv.loc[(pv["pv_scale"] == s) & (pv["model"] == "coordinated"), m].iloc[0])
            rows.append(
                {
                    "parameter": f"pv_scale={s}",
                    "scenario": "baseline",
                    "metric": m,
                    "raw_value": b,
                    "relative_change_pct": 0.0,
                    "baseline_reference": f"pv_scale=1.0 baseline {m}",
                }
            )
            rows.append(
                {
                    "parameter": f"pv_scale={s}",
                    "scenario": "coordinated",
                    "metric": m,
                    "raw_value": c,
                    "relative_change_pct": rel_pct(c, float(pv.loc[(pv["pv_scale"] == 1.0) & (pv["model"] == "coordinated"), m].iloc[0])),
                    "baseline_reference": f"pv_scale=1.0 coordinated {m}",
                }
            )
        rows.append(
            {
                "parameter": f"pv_scale={s}",
                "scenario": "improvement_cost_pct",
                "metric": "improvement_cost_pct",
                "raw_value": r["improvement_cost_pct"],
                "relative_change_pct": r["improvement_cost_pct"],
                "baseline_reference": "(baseline−协同)/baseline×100",
            }
        )
        rows.append(
            {
                "parameter": f"pv_scale={s}",
                "scenario": "improvement_grid_pct",
                "metric": "improvement_grid_pct",
                "raw_value": r["improvement_grid_pct"],
                "relative_change_pct": r["improvement_grid_pct"],
                "baseline_reference": "(baseline−协同)/baseline×100",
            }
        )
    df = pd.DataFrame(rows)
    try:
        df.attrs["renewable_note"] = ren_note
    except Exception:
        pass
    return df


def write_polished_figure_captions(ev: pd.DataFrame, imp: pd.DataFrame, out_path: Path) -> None:
    """三张论文级重绘图的图注（中文、可直接粘贴）。"""
    ev = ev.sort_values("ev_power_scale").reset_index(drop=True)
    r = ev[ev["ev_power_scale"] == 1.0].iloc[0]
    ref_ess = float(r["ess_throughput_kwh"])
    y_ess = [rel_pct(float(v), ref_ess) for v in ev["ess_throughput_kwh"].astype(float)]
    ess_note = max(abs(x) for x in y_ess) < 0.05

    def series_sentence(col: str, name_zh: str) -> str:
        bits = []
        for _, row in ev.iterrows():
            sc = float(row["ev_power_scale"])
            p = rel_pct(float(row[col]), float(r[col]))
            bits.append(f"缩放系数为 {sc} 时，{name_zh}相对标称工况变化 {p:+.2f}%")
        return "；".join(bits) + "。"

    cap_ev = (
        "【图注·EV可用性变化对系统调度行为的影响】\n\n"
        "横轴为电动汽车充、放电功率上限的同比缩放系数（标称工况为 1.0），纵轴为相对标称工况的变化率（%）；"
        "从左至右依次为运行成本、EV 放电量与 EV 吞吐量的灵敏度曲线。"
        "灰色竖虚线标示标称缩放系数，灰色横虚线标示零变化；曲线上各点标注两位小数的相对变化率。\n\n"
        + series_sentence("operation_cost", "运行成本")
        + "\n\n"
        + series_sentence("ev_discharge_energy_kwh", "全周期 EV 放电量")
        + "\n\n"
        + series_sentence("ev_throughput_kwh", "EV 吞吐量")
        + "\n\n"
        + (
            "在全周结果中，储能系统吞吐量对各缩放系数的变化幅度均小于 0.05%，故未单独绘制 ESS 子图，"
            "而以图下注释说明其对 EV 可用性扰动不敏感。"
            if ess_note
            else "储能系统吞吐量的灵敏度另可单独评估。"
        )
    )

    imp_s = imp.sort_values("pv_scale")
    cost_bits = "；".join(
        f"光伏缩放系数 {float(row['pv_scale'])} 时，成本改进率为 {float(row['improvement_cost_pct']):.2f}%"
        for _, row in imp_s.iterrows()
    )
    cap_cost = (
        "【图注·不同光伏扰动场景下协同调度的成本改进率】\n\n"
        "横轴为光伏出力缩放系数（0.9、1.0、1.1），纵轴为协同调度相对基线运行方案的成本改进率（%）；"
        "改进率定义为（基线运行成本 − 协同运行成本）与基线运行成本之比，以百分数表示。\n\n"
        f"{cost_bits}。\n\n"
        "图中给出 y=0 基线，柱顶标注各档数值，用于比较不同光伏水平下协同带来的成本收益是否稳定。"
    )

    grid_bits = "；".join(
        f"光伏缩放系数 {float(row['pv_scale'])} 时，购电改善率为 {float(row['improvement_grid_pct']):.2f}%"
        for _, row in imp_s.iterrows()
    )
    cap_grid = (
        "【图注·不同光伏扰动场景下协同调度的购电改善率】\n\n"
        "横轴为光伏出力缩放系数（0.9、1.0、1.1），纵轴为协同调度相对基线的全周期购电量改善率（%），"
        "定义与成本改进率相同，将「运行成本」替换为「全周期购电量」后按基线归一化。\n\n"
        f"{grid_bits}。\n\n"
        "改善率为正表示协同方案购电少于基线，为负则相反；该指标与成本最优不必同向，需结合电价与弃光等约束一并解读。"
    )

    out_path.write_text(
        "\n\n".join([cap_ev, cap_cost, cap_grid]) + "\n",
        encoding="utf-8",
    )


def auto_conclusions(
    ev: pd.DataFrame,
    imp: pd.DataFrame,
    tornado_summary: pd.DataFrame,
    ref_cost: float,
    ren_note: str,
) -> tuple[str, str, str]:
    ev_ref = float(ev.loc[ev["ev_power_scale"] == 1.0, "operation_cost"].iloc[0])
    ev08 = rel_pct(float(ev.loc[ev["ev_power_scale"] == 0.8, "operation_cost"].iloc[0]), ev_ref)
    ev12 = rel_pct(float(ev.loc[ev["ev_power_scale"] == 1.2, "operation_cost"].iloc[0]), ev_ref)
    c1 = (
        f"在 EV 充放功率上限缩放条件下，以缩放系数 1.0 为基准，运行成本相对变化在 "
        f"{min(ev08, ev12):.3f}%～{max(ev08, ev12):.3f}% 量级；"
        f"EV 吞吐与放电量随可用功率放宽而上升、收紧而下降，符合可调资源约束收紧时运行域收缩的直觉。"
        f"图中 x=1.0 与 y=0% 参考线便于对照名义设计点。"
    )

    cost_imps = imp["improvement_cost_pct"].to_numpy()
    grid_imps = imp["improvement_grid_pct"].to_numpy()
    cost_stable = bool(np.all(cost_imps > 0))
    c2 = (
        "在 PV=0.9、1.0、1.1 的离散扰动下，协同相对 baseline 的运行成本改进率 "
        f"（(baseline−协同)/baseline×100%）三档分别为 {', '.join(f'{v:.2f}%' for v in cost_imps)}；"
        f"{'各档均为正，说明协同在运行成本上相对 baseline 的优势在该 PV 盒内稳定。' if cost_stable else '若某档成本改进率非正，需检查该档求解状态或数据截断口径。'}"
        " 购电量改进率同式定义：为正表示协同全周购电少于 baseline，为负则相反（成本最优未必同步减少购电量）。"
        f" {ren_note}"
    )

    c3 = tornado_auto_conclusion_text(tornado_summary, ref_cost)
    return c1, c2, c3


def main() -> int:
    ap = argparse.ArgumentParser(description="论文用灵敏度/鲁棒性图与表")
    ap.add_argument("--repo-root", type=Path, default=_REPO_DEFAULT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    sens = repo / "results" / "sensitivity"
    rob = repo / "results" / "robustness"
    sens.mkdir(parents=True, exist_ok=True)
    rob.mkdir(parents=True, exist_ok=True)

    ev = load_ev(repo)
    pv = load_pv(repo)
    wdf = load_weight_scan(repo)

    plot_ev_sensitivity(ev, rob)
    plot_ev_availability_polished(ev, rob)
    ren_note, imp = plot_pv_robustness(pv, rob)
    write_polished_figure_captions(ev, imp, rob / "sensitivity_robustness_polished_figure_captions.md")
    tornado_summary, ref_cost = build_p2_unified_tornado_summary(repo)
    plot_p2_unified_tornado_chart(tornado_summary, sens)
    plot_p2_unified_tornado_chart_polished(tornado_summary, sens)
    plot_sensitivity_three_point_compare(tornado_summary, sens)
    tornado_summary.to_csv(sens / "tornado_operation_cost_summary.csv", index=False, encoding="utf-8-sig")
    tw_text = tornado_auto_conclusion_text(tornado_summary, ref_cost)
    write_tornado_operation_cost_summary_md(tornado_summary, ref_cost, tw_text, sens / "tornado_operation_cost_summary.md")

    sens_tbl = pd.concat(
        [build_sensitivity_table(ev, wdf), tornado_summary_to_long_rows(tornado_summary, ref_cost)],
        ignore_index=True,
    )
    sens_tbl.to_csv(sens / "sensitivity_analysis_summary.csv", index=False, encoding="utf-8-sig")
    rob_tbl = build_robustness_table(pv, imp, ren_note)
    ren_note_attr = str(rob_tbl.attrs.get("renewable_note", ""))
    rob_tbl.to_csv(rob / "robustness_analysis_summary.csv", index=False, encoding="utf-8-sig")

    c1, c2, c3 = auto_conclusions(ev, imp, tornado_summary, ref_cost, ren_note_attr)

    (sens / "sensitivity_analysis_summary.md").write_text(
        "\n".join(
            [
                "# 灵敏度分析汇总表",
                "",
                "## 自动生成结论（EV 与权重及龙卷风）",
                "",
                c1,
                "",
                c3,
                "",
                "## 明细表",
                "",
                _md_table(sens_tbl.head(80)),
                "",
                "*完整数据见 `sensitivity_analysis_summary.csv`。*",
            ]
        ),
        encoding="utf-8",
    )

    (rob / "robustness_analysis_summary.md").write_text(
        "\n".join(
            [
                "# 鲁棒性分析汇总表（PV 扰动）",
                "",
                "## 可再生能源消纳率说明",
                "",
                ren_note_attr,
                "",
                "## 自动生成结论（PV 扰动）",
                "",
                c2,
                "",
                "## 明细表（节选）",
                "",
                _md_table(rob_tbl.head(40)),
                "",
                "*完整数据见 `robustness_analysis_summary.csv`。*",
            ]
        ),
        encoding="utf-8",
    )

    (sens / "paper_auto_conclusions.md").write_text(
        "\n".join(
            [
                "# 论文用自动结论（灵敏度与鲁棒性）",
                "",
                "## 1. EV 可用性灵敏度分析",
                "",
                c1,
                "",
                "## 2. PV 扰动鲁棒性分析",
                "",
                c2,
                "",
                "## 3. 关键参数对运行成本的敏感度排序",
                "",
                c3,
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("OK", rob / "ev_availability_sensitivity_polished.png")
    print("OK", rob / "pv_robust_cost_improvement_polished.png")
    print("OK", rob / "sensitivity_robustness_polished_figure_captions.md")
    print(sens / "tornado_operation_cost_polished.png")
    print(sens / "sensitivity_three_point_compare.png")
    print(sens / "paper_auto_conclusions.md")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
