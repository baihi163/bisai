# -*- coding: utf-8 -*-
"""
问题二：寿命权重扫描 —— 「引入寿命损耗前后调度行为变化」论文级可视化。

主对比：w=0（忽略寿命惩罚） vs w=2（强化寿命保护），w=1 为中间参考。

输出：
  results/figures/problem2/p2_typical_day_dispatch_compare.{png,pdf}
  results/figures/problem2/p2_weekly_behavior_compare.{png,pdf}
  results/figures/problem2/p2_weekly_cost_health_compare.{png,pdf}
  results/figures/problem2/p2_role_share_compare.{png,pdf}
  results/figures/problem2/p2_weight_response_curves.{png,pdf}
  results/tables/p2_dispatch_change_summary.{csv,md}

用法：
  python code/python/problem_2/plot_p2_lifetime_dispatch_change_paper.py --repo-root <仓库根>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[3]

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

SCAN_REL = Path("results/problem2_lifecycle/scans/scan_auto_weight_scan")
ESS_PARAMS_REL = Path("data/processed/final_model_inputs/ess_params.json")

WEIGHT_TO_DIR: dict[float, str] = {
    0.0: "w_0",
    0.1: "w_0p1",
    0.5: "w_0p5",
    1.0: "w_1",
    2.0: "w_2",
}

REQUIRED_TS_COLS = [
    "timestamp",
    "P_buy_kw",
    "P_ess_ch_kw",
    "P_ess_dis_kw",
    "P_ev_ch_total_kw",
    "P_ev_dis_total_kw",
    "delta_t_h",
]


def load_timeseries(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少时序: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    miss = [c for c in REQUIRED_TS_COLS if c not in df.columns]
    if miss:
        raise KeyError(f"{path} 缺少列: {miss}")
    if len(df) < 90:
        raise ValueError(f"{path} 行数过少 ({len(df)})。")
    return df


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ess_params(repo: Path) -> dict[str, float]:
    p = repo / ESS_PARAMS_REL
    d = load_json(p)
    return {
        "E0": float(d["initial_energy_kwh"]),
        "eta_c": float(d["charge_efficiency"]),
        "eta_d": float(d["discharge_efficiency"]),
        "E_min": float(d["min_energy_kwh"]),
        "E_max": float(d["max_energy_kwh"]),
        "dt_default": float(d.get("time_step_hours", 0.25)),
    }


def reconstruct_ess_energy_kwh(df: pd.DataFrame, ess: dict[str, float]) -> np.ndarray:
    """由 P_ess_ch / P_ess_dis 与效率递推 E_ess(kWh)，与模型能量守恒一致。"""
    dt = pd.to_numeric(df["delta_t_h"], errors="coerce").fillna(ess["dt_default"]).to_numpy(dtype=float)
    pch = pd.to_numeric(df["P_ess_ch_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    pdis = pd.to_numeric(df["P_ess_dis_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    n = len(df)
    e = np.empty(n, dtype=float)
    e[0] = float(ess["E0"])
    eta_c, eta_d = ess["eta_c"], ess["eta_d"]
    emin, emax = ess["E_min"], ess["E_max"]
    for t in range(n - 1):
        e[t + 1] = e[t] + eta_c * pch[t] * dt[t] - (pdis[t] / eta_d) * dt[t]
        e[t + 1] = float(np.clip(e[t + 1], emin, emax))
    return e


def pick_typical_day(ref: pd.DataFrame, *, dt: float) -> str:
    """在参考 w=1 上：score = 当日 EV 放电能量 + 50 * std(P_buy)。"""
    g = ref.copy()
    g["t"] = pd.to_datetime(g["timestamp"])
    g["_d"] = g["t"].dt.date.astype(str)
    best_d, best_s = "", -1.0
    for d, sub in g.groupby("_d"):
        ev_dis = pd.to_numeric(sub["P_ev_dis_total_kw"], errors="coerce").fillna(0.0)
        ev_e = float((ev_dis * dt).sum())
        pb = pd.to_numeric(sub["P_buy_kw"], errors="coerce").fillna(0.0)
        std = float(pb.std()) if len(pb) > 1 else 0.0
        s = ev_e + 50.0 * std
        if s > best_s:
            best_s, best_d = s, str(d)
    if not best_d:
        raise RuntimeError("未能选出典型日。")
    return best_d


def scenario_dir(repo: Path, w: float) -> Path:
    tag = WEIGHT_TO_DIR[w]
    return repo / SCAN_REL / tag


def peak_grid_kw(df: pd.DataFrame) -> float:
    return float(pd.to_numeric(df["P_buy_kw"], errors="coerce").fillna(0.0).max())


def peak_buy_kw_on_calendar_day(repo: Path, w: float, day: str) -> float:
    df = load_timeseries(scenario_dir(repo, w) / "timeseries.csv")
    df = df.copy()
    df["t"] = pd.to_datetime(df["timestamp"])
    df["_d"] = df["t"].dt.date.astype(str)
    sub = df[df["_d"] == day]
    if sub.empty:
        return float("nan")
    return float(pd.to_numeric(sub["P_buy_kw"], errors="coerce").fillna(0.0).max())


def max_slot_discharge_energy_kwh(df: pd.DataFrame, col_kw: str) -> float:
    dt = pd.to_numeric(df["delta_t_h"], errors="coerce").fillna(0.25).to_numpy(dtype=float)
    p = pd.to_numeric(df[col_kw], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    return float(np.max(p * dt))


def peak_discharge_share_at_max_buy(df: pd.DataFrame) -> tuple[float, float]:
    """在 P_buy 最大的时刻，ESS 与 EV 放电功率占比（%）。"""
    buy = pd.to_numeric(df["P_buy_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    t_star = int(np.argmax(buy)) if len(buy) else 0
    ess = float(pd.to_numeric(df["P_ess_dis_kw"], errors="coerce").fillna(0.0).iloc[t_star])
    ev = float(pd.to_numeric(df["P_ev_dis_total_kw"], errors="coerce").fillna(0.0).iloc[t_star])
    tot = ess + ev
    if tot < 1e-9:
        return 50.0, 50.0
    return 100.0 * ess / tot, 100.0 * ev / tot


def build_summary_rows(repo: Path, ess: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for w in sorted(WEIGHT_TO_DIR.keys()):
        d = scenario_dir(repo, w)
        ts = load_timeseries(d / "timeseries.csv")
        om = load_json(d / "operational_metrics.json")
        ob = load_json(d / "objective_breakdown.json")
        ess_deg = float(ob.get("ess_degradation_cost", 0.0))
        ev_deg = float(ob.get("ev_degradation_cost", 0.0))
        op = float(ob.get("operation_cost", 0.0))
        rows.append(
            {
                "scenario": "p2_weight_scan",
                "weight": w,
                "operation_cost": op,
                "ess_deg_cost": ess_deg,
                "ev_deg_cost": ev_deg,
                "total_degradation_cost": ess_deg + ev_deg,
                "ev_throughput_kwh": float(om.get("ev_throughput_kwh", 0.0)),
                "ev_discharge_energy_kwh": float(om.get("ev_discharge_energy_kwh", 0.0)),
                "ess_throughput_kwh": float(om.get("ess_throughput_kwh", 0.0)),
                "ess_peak_energy_kwh": max_slot_discharge_energy_kwh(ts, "P_ess_dis_kw"),
                "ev_peak_energy_kwh": max_slot_discharge_energy_kwh(ts, "P_ev_dis_total_kw"),
                "peak_grid_purchase_kw": peak_grid_kw(ts),
            }
        )
    return rows


def _style_hour_axis(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=28, ha="right")


def plot_typical_day_w0_w2(repo: Path, day: str, ess: dict[str, float], out_dir: Path) -> None:
    paths = {
        "w=0（忽略寿命惩罚）": scenario_dir(repo, 0.0) / "timeseries.csv",
        "w=2（强化寿命保护）": scenario_dir(repo, 2.0) / "timeseries.csv",
    }
    dfs: dict[str, pd.DataFrame] = {}
    dt = ess["dt_default"]
    for label, p in paths.items():
        df = load_timeseries(p)
        df = df.copy()
        df["t"] = pd.to_datetime(df["timestamp"])
        df["_d"] = df["t"].dt.date.astype(str)
        sub = df[df["_d"] == day].copy()
        if len(sub) < 10:
            raise ValueError(f"{label} 在日期 {day} 上数据点过少: {len(sub)}")
        dfs[label] = sub
        dt = float(pd.to_numeric(sub["delta_t_h"], errors="coerce").iloc[0])

    fig, axes = plt.subplots(4, 2, sharex="col", figsize=(11.5, 10.5), dpi=150, gridspec_kw={"hspace": 0.32, "wspace": 0.22})
    fig.suptitle(
        "引入寿命损耗前后典型日调度行为对比\n"
        f"代表性日：{day}（典型日按 w=1 参考：EV 放电能量 + 50×购电功率标准差 最大选取）",
        fontsize=12,
        y=0.995,
    )

    for j, (label, g) in enumerate(dfs.items()):
        t = g["t"]
        vch = pd.to_numeric(g["P_ev_ch_total_kw"], errors="coerce")
        vdc = pd.to_numeric(g["P_ev_dis_total_kw"], errors="coerce")
        ech = pd.to_numeric(g["P_ess_ch_kw"], errors="coerce")
        edc = pd.to_numeric(g["P_ess_dis_kw"], errors="coerce")
        buy = pd.to_numeric(g["P_buy_kw"], errors="coerce")
        e_ess = reconstruct_ess_energy_kwh(g, ess)

        axes[0, j].plot(t, vch, drawstyle="steps-post", color="#9467bd", lw=1.15, label="EV 充电")
        axes[0, j].plot(t, vdc, drawstyle="steps-post", color="#8c564b", lw=1.15, label="EV 放电")
        axes[0, j].set_ylabel("kW")
        axes[0, j].set_title(label, fontsize=10)
        axes[0, j].legend(loc="upper left", fontsize=7, ncol=2)
        axes[0, j].grid(True, axis="y", alpha=0.2, linestyle=":")

        axes[1, j].plot(t, ech, drawstyle="steps-post", color="#2ca02c", lw=1.1, label="ESS 充电")
        axes[1, j].plot(t, edc, drawstyle="steps-post", color="#d62728", lw=1.1, label="ESS 放电")
        axes[1, j].set_ylabel("kW")
        axes[1, j].legend(loc="upper left", fontsize=7, ncol=2)
        axes[1, j].grid(True, axis="y", alpha=0.2, linestyle=":")

        axes[2, j].plot(t, buy, drawstyle="steps-post", color="#1f77b4", lw=1.35, label="外网购电")
        axes[2, j].set_ylabel("kW")
        axes[2, j].legend(loc="upper left", fontsize=7)
        axes[2, j].grid(True, axis="y", alpha=0.2, linestyle=":")

        axes[3, j].plot(t, e_ess, drawstyle="steps-post", color="#17becf", lw=1.2, label="ESS 能量（递推）")
        axes[3, j].set_ylabel("kWh")
        axes[3, j].set_xlabel("时刻")
        axes[3, j].legend(loc="upper left", fontsize=7)
        axes[3, j].grid(True, axis="y", alpha=0.2, linestyle=":")
        _style_hour_axis(axes[3, j])

    axes[0, 0].set_ylabel("EV 聚合功率\nkW")
    axes[1, 0].set_ylabel("ESS 功率\nkW")
    axes[2, 0].set_ylabel("外网购电\nkW")
    axes[3, 0].set_ylabel("ESS 能量\nkWh")

    for ax in axes.flat:
        if ax is not axes[3, 0] and ax is not axes[3, 1]:
            _style_hour_axis(ax)

    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"p2_typical_day_dispatch_compare.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_weekly_behavior(_repo: Path, summary: pd.DataFrame, out_dir: Path) -> None:
    sub = summary[summary["weight"].isin([0.0, 1.0, 2.0])].copy()
    sub["w_label"] = sub["weight"].map({0.0: "w=0", 1.0: "w=1", 2.0: "w=2"})
    x = np.arange(3)
    widx = {0.0: 0, 1.0: 1, 2.0: 2}

    def vals(col: str) -> np.ndarray:
        a = np.zeros(3)
        for _, r in sub.iterrows():
            a[widx[float(r["weight"])]] = float(r[col])
        return a

    metrics = [
        ("ev_throughput_kwh", "EV 吞吐量 (kWh)"),
        ("ev_discharge_energy_kwh", "EV 放电能量 (kWh)"),
        ("ess_throughput_kwh", "ESS 吞吐量 (kWh)"),
        ("peak_grid_purchase_kw", "峰值购电功率 (kW)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 7.2), dpi=150)
    fig.suptitle("全周资源行为：w=0 / w=1 / w=2 分组对比", fontsize=12)
    colors = ["#7fc97f", "#beaed4", "#fdc086"]
    for ax, (key, title) in zip(axes.flat, metrics):
        heights = vals(key)
        bars = ax.bar(x, heights, color=colors, edgecolor="0.2", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(["w=0", "w=1", "w=2"])
        ax.set_title(title, fontsize=10)
        ax.grid(True, axis="y", alpha=0.2, linestyle=":")
        for b, h in zip(bars, heights):
            ax.text(b.get_x() + b.get_width() / 2, h, f"{h:.1f}", ha="center", va="bottom", fontsize=7)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"p2_weekly_behavior_compare.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_weekly_cost_health(repo: Path, summary: pd.DataFrame, out_dir: Path) -> None:
    sub = summary[summary["weight"].isin([0.0, 1.0, 2.0])].copy()
    widx = {0.0: 0, 1.0: 1, 2.0: 2}
    x = np.arange(3)

    def vals(col: str) -> np.ndarray:
        a = np.zeros(3)
        for _, r in sub.iterrows():
            a[widx[float(r["weight"])]] = float(r[col])
        return a

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2), dpi=150)
    fig.suptitle("全周系统结果：运行成本与退化成本（w=0 / w=1 / w=2）", fontsize=12)
    colors = ["#7fc97f", "#beaed4", "#fdc086"]
    h1 = vals("operation_cost")
    h2 = vals("total_degradation_cost")
    b1 = axes[0].bar(x, h1, color=colors, edgecolor="0.2", linewidth=0.6)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(["w=0", "w=1", "w=2"])
    axes[0].set_title("运行成本 operation_cost", fontsize=10)
    axes[0].set_ylabel("元")
    axes[0].grid(True, axis="y", alpha=0.2, linestyle=":")
    for b, h in zip(b1, h1):
        axes[0].text(b.get_x() + b.get_width() / 2, h, f"{h:.0f}", ha="center", va="bottom", fontsize=7)
    b2 = axes[1].bar(x, h2, color=colors, edgecolor="0.2", linewidth=0.6)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["w=0", "w=1", "w=2"])
    axes[1].set_title("总退化成本（ESS+EV）", fontsize=10)
    axes[1].set_ylabel("元")
    axes[1].grid(True, axis="y", alpha=0.2, linestyle=":")
    for b, h in zip(b2, h2):
        axes[1].text(b.get_x() + b.get_width() / 2, h, f"{h:.1f}", ha="center", va="bottom", fontsize=7)
    plt.tight_layout(rect=[0, 0, 1, 0.90])
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"p2_weekly_cost_health_compare.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_role_shares(repo: Path, summary: pd.DataFrame, out_dir: Path) -> None:
    """三类分工：吞吐(store/throughput)、供给(supply discharge)、峰值时刻放电(peak at max P_buy)。"""
    sub = summary[summary["weight"].isin([0.0, 1.0, 2.0])].copy()
    w_order = [0.0, 1.0, 2.0]
    ess_thr: list[float] = []
    ess_sup: list[float] = []
    ess_peak: list[float] = []
    for w in w_order:
        r = sub[sub["weight"] == w].iloc[0]
        ess_t = float(r["ess_throughput_kwh"])
        ev_t = float(r["ev_throughput_kwh"])
        om = load_json(scenario_dir(repo, w) / "operational_metrics.json")
        ess_d = float(om["ess_discharge_energy_kwh"])
        ev_d = float(om["ev_discharge_energy_kwh"])
        ts = load_timeseries(scenario_dir(repo, w) / "timeseries.csv")
        p_ess, p_ev = peak_discharge_share_at_max_buy(ts)
        ess_thr.append(100.0 * ess_t / (ess_t + ev_t + 1e-12))
        ess_sup.append(100.0 * ess_d / (ess_d + ev_d + 1e-12))
        ess_peak.append(p_ess)
    ev_thr = [100.0 - e for e in ess_thr]
    ev_sup = [100.0 - e for e in ess_sup]
    ev_peak = [100.0 - e for e in ess_peak]

    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.0), dpi=150, sharey=True)
    fig.suptitle(
        "分工比例（100% 堆叠）：吞吐 / 供给放电 / 购电峰值时刻放电\n"
        "（吞吐=全周吞吐量占比；供给=放电能量占比；峰值=argmax(P_buy) 时刻放电功率占比）",
        fontsize=11,
    )
    labels_w = ["w=0", "w=1", "w=2"]
    x = np.arange(3)
    w_ess = "#2ca02c"
    w_ev = "#9467bd"
    titles = ["吞吐分工 (throughput)", "供给分工 (discharge supply)", "峰值时刻放电分工 (at max P_buy)"]
    series_list = [
        (ess_thr, ev_thr),
        (ess_sup, ev_sup),
        (ess_peak, ev_peak),
    ]
    for ax, title, (e1, e2) in zip(axes, titles, series_list):
        ax.bar(x, e1, color=w_ess, edgecolor="0.2", linewidth=0.5, label="ESS %")
        ax.bar(x, e2, bottom=e1, color=w_ev, edgecolor="0.2", linewidth=0.5, label="EV %")
        ax.set_xticks(x)
        ax.set_xticklabels(labels_w)
        ax.set_ylim(0, 100)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("占比 %")
        ax.grid(True, axis="y", alpha=0.2, linestyle=":")
        for i in range(3):
            ax.text(i, e1[i] / 2, f"{e1[i]:.1f}", ha="center", va="center", fontsize=8, color="white")
            ax.text(i, e1[i] + e2[i] / 2, f"{e2[i]:.1f}", ha="center", va="center", fontsize=8, color="white")
    axes[0].legend(loc="upper right", fontsize=8)
    plt.tight_layout(rect=[0, 0, 1, 0.86])
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"p2_role_share_compare.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_weight_response(summary: pd.DataFrame, out_dir: Path) -> None:
    sub = summary.sort_values("weight").copy()
    wx = sub["weight"].to_numpy()
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 7.0), dpi=150)
    fig.suptitle("寿命权重—行为响应曲线（w∈{0, 0.1, 0.5, 1, 2}）", fontsize=12)
    pairs = [
        ("ev_throughput_kwh", "EV 吞吐量 (kWh)"),
        ("ev_discharge_energy_kwh", "EV 放电能量 (kWh)"),
        ("ess_throughput_kwh", "ESS 吞吐量 (kWh)"),
        ("operation_cost", "运行成本 (元)"),
    ]
    for ax, (col, ttl) in zip(axes.flat, pairs):
        y = sub[col].to_numpy(dtype=float)
        ax.plot(wx, y, "o-", color="#1f77b4", lw=1.5, ms=6)
        ax.set_xlabel("寿命权重 w")
        ax.set_title(ttl, fontsize=10)
        ax.grid(True, alpha=0.2, linestyle=":")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"p2_weight_response_curves.{ext}", bbox_inches="tight")
    plt.close(fig)


def write_table_and_conclusions(repo: Path, summary: pd.DataFrame, day: str, out_csv: Path, out_md: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_csv, index=False, encoding="utf-8-sig")

    r0 = summary[summary["weight"] == 0.0].iloc[0]
    r1 = summary[summary["weight"] == 1.0].iloc[0]
    r2 = summary[summary["weight"] == 2.0].iloc[0]
    day_peak0 = peak_buy_kw_on_calendar_day(repo, 0.0, day)
    day_peak2 = peak_buy_kw_on_calendar_day(repo, 2.0, day)

    def fmt_row(r: pd.Series) -> str:
        return (
            f"| {r['scenario']} | {r['weight']} | {r['operation_cost']:.4f} | {r['ess_deg_cost']:.4f} | "
            f"{r['ev_deg_cost']:.4f} | {r['total_degradation_cost']:.4f} | {r['ev_throughput_kwh']:.4f} | "
            f"{r['ev_discharge_energy_kwh']:.4f} | {r['ess_throughput_kwh']:.4f} | {r['ess_peak_energy_kwh']:.4f} | "
            f"{r['ev_peak_energy_kwh']:.4f} | {r['peak_grid_purchase_kw']:.4f} |"
        )

    header = (
        "| scenario | weight | operation_cost | ess_deg_cost | ev_deg_cost | total_degradation_cost | "
        "ev_throughput_kwh | ev_discharge_energy_kwh | ess_throughput_kwh | ess_peak_energy_kwh | "
        "ev_peak_energy_kwh | peak_grid_purchase_kw |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    body = "\n".join(fmt_row(summary.loc[i]) for i in summary.index)
    note = (
        "\n\n**指标说明**：`ess_peak_energy_kwh` / `ev_peak_energy_kwh` 为全周 horizon 上 "
        "单时段最大放电能量 $\\max_t(P_{\\mathrm{dis}}(t)\\Delta t)$（kWh）。"
        "`operation_cost` 与退化分项来自各场景 `objective_breakdown.json`。\n"
    )

    p1 = (
        "**（1）典型日调度变化。** "
        f"以代表性日 {day} 为例（在 w=1 参考时序上按「当日 EV 放电能量 + 50×当日购电功率标准差」最大选取），"
        f"对比 w=0 与 w=2：该日内外网购电功率峰值约由 {day_peak0:.1f} kW 变为 {day_peak2:.1f} kW；"
        f"在全周尺度上，EV 放电能量由 {r0['ev_discharge_energy_kwh']:.1f} kWh 变为 {r2['ev_discharge_energy_kwh']:.1f} kWh，"
        f"EV 吞吐量由 {r0['ev_throughput_kwh']:.1f} kWh 变为 {r2['ev_throughput_kwh']:.1f} kWh。"
        "图示上，强化寿命权重后 EV 聚合充放电更趋保守，ESS 递推能量轨迹与外网购电曲线同步调整，"
        "体现优化器在典型峰谷结构下对「可循环资源」用法的再分配。"
    )
    p2 = (
        "**（2）全周资源行为。** "
        f"w=0、1、2 下 ESS 吞吐量分别约为 {r0['ess_throughput_kwh']:.1f}、{r1['ess_throughput_kwh']:.1f}、{r2['ess_throughput_kwh']:.1f} kWh，"
        f"运行成本由约 {r0['operation_cost']:.0f} 元变化至 {r2['operation_cost']:.0f} 元（变化幅度相对退化项较小），"
        f"而总退化成本由 {r0['total_degradation_cost']:.2f} 元升至 {r2['total_degradation_cost']:.2f} 元，"
        "体现寿命惩罚进入目标后，优化器在「电费/移峰」与「资产退化」之间进行折中。"
    )
    p3 = (
        "**（3）分工比例与经济—健康权衡。** "
        "吞吐与供给两类分工比例反映 ESS 与 EV 在全周能量循环与放电供给中的相对角色；"
        "在购电功率最大的时刻，放电功率在 ESS 与 EV 间的分配（峰值时刻放电分工）随权重调整。"
        f"综合 w=0→2：运行成本小幅波动而退化成本显著抬升（相对 w=0 的零退化），"
        f"w=2 相对 w=0 总退化成本增加约 {r2['total_degradation_cost'] - r0['total_degradation_cost']:.2f} 元（扫描解集内），"
        "说明提高寿命权重主要改变「健康」维度而非单纯线性压低电费；"
        "论文中可结合图 2–4 将上述权衡表述为可复核的量化证据。"
    )

    out_md.write_text(
        "# 问题二：寿命权重扫描 — 调度变化汇总表\n\n"
        + header
        + "\n"
        + body
        + note
        + "\n## 自动生成结论（论文可用草稿）\n\n"
        + p1
        + "\n\n"
        + p2
        + "\n\n"
        + p3
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=_REPO)
    args = ap.parse_args()
    repo: Path = args.repo_root.resolve()

    ess = load_ess_params(repo)
    ref = load_timeseries(scenario_dir(repo, 1.0) / "timeseries.csv")
    dt = float(pd.to_numeric(ref["delta_t_h"], errors="coerce").iloc[0])
    day = pick_typical_day(ref, dt=dt)

    summary = pd.DataFrame(build_summary_rows(repo, ess))
    out_fig = repo / "results" / "figures" / "problem2"
    out_fig.mkdir(parents=True, exist_ok=True)

    plot_typical_day_w0_w2(repo, day, ess, out_fig)
    plot_weekly_behavior(repo, summary, out_fig)
    plot_weekly_cost_health(repo, summary, out_fig)
    plot_role_shares(repo, summary, out_fig)
    plot_weight_response(summary, out_fig)

    out_csv = repo / "results" / "tables" / "p2_dispatch_change_summary.csv"
    out_md = repo / "results" / "tables" / "p2_dispatch_change_summary.md"
    write_table_and_conclusions(repo, summary, day, out_csv, out_md)

    print("OK:", out_fig)
    print("OK:", out_csv, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
