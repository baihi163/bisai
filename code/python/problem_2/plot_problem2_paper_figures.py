# -*- coding: utf-8 -*-
"""
论文第二题：结果图与表（可复现）。

图 1 — 典型日三场景调度对比（问题一 vs 第二题 w=1 vs w=2）
  数据：
    - results/problem1_ultimate/p_1_5_timeseries.csv
    - results/problem2_lifecycle/scans/scan_auto_weight_scan/w_1/timeseries.csv
    - results/problem2_lifecycle/scans/scan_auto_weight_scan/w_2/timeseries.csv
  典型日选取：在「参考场景 w=1」上按日打分
    score(d) = 当日 EV 放电能量(kWh) + 50 * 当日 P_buy_kw 标准差
    取 score 最大日（兼顾 EV 放电明显与购电波动）。

图 2 — w∈{0,1,2} 下 EV 放电量与吞吐量柱状对比
  数据：.../w_0|w_1|w_2/operational_metrics.json
  字段：ev_discharge_energy_kwh, ev_throughput_kwh

表 1 — 第二题主结果（w=1）
  数据：w_1/objective_breakdown.json, operational_metrics.json, timeseries.csv
  字段：见 MAIN_RESULT_FIELDS

表 2 — 权重敏感性与分工比例（w=0,1,2）
  ess_share_throughput_pct = 100 * ess_throughput / (ess_throughput + ev_throughput)
  ess_share_supply_pct     = 100 * ess_discharge / (ess_discharge + ev_discharge)

输出：
  results/figures/problem2/problem2_typical_day_dispatch_compare.{png,pdf}
  results/figures/problem2/problem2_ev_participation_compare.{png,pdf}
  results/tables/problem2_main_results.{csv,md}
  results/tables/problem2_weight_sensitivity_and_roles.{csv,md}

用法：
  python code/python/problem_2/plot_problem2_paper_figures.py --repo-root <仓库根>
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
_REPO = _HERE.parents[3]  # code/python/problem_2 -> 仓库根

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------------------
# 路径常量（相对 repo 根）
# ---------------------------------------------------------------------------
TS_P1 = Path("results/problem1_ultimate/p_1_5_timeseries.csv")
TS_W1 = Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_1/timeseries.csv")
TS_W2 = Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_2/timeseries.csv")

REQUIRED_TS_COLS = [
    "timestamp",
    "P_buy_kw",
    "P_sell_kw",
    "P_ess_ch_kw",
    "P_ess_dis_kw",
    "P_ev_ch_total_kw",
    "P_ev_dis_total_kw",
    "P_shift_out_total_kw",
    "P_recover_total_kw",
    "pv_curtail_kw",
    "delta_t_h",
]

OPTIONAL_FLEX_COL = "building_flex_power_kw"


def _repo_paths(repo: Path) -> dict[str, Path]:
    return {
        "p1": repo / TS_P1,
        "w1": repo / TS_W1,
        "w2": repo / TS_W2,
        "w0": repo / Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_0/timeseries.csv"),
        "w0_metrics": repo / Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_0/operational_metrics.json"),
        "w1_metrics": repo / Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_1/operational_metrics.json"),
        "w2_metrics": repo / Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_2/operational_metrics.json"),
        "w1_breakdown": repo / Path("results/problem2_lifecycle/scans/scan_auto_weight_scan/w_1/objective_breakdown.json"),
    }


def load_timeseries(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(
            f"缺少时序文件: {path}\n"
            "最短补齐：先运行第二题全周扫描或单次求解并写出 timeseries.csv（672 行）。"
        )
    df = pd.read_csv(path, encoding="utf-8-sig")
    miss = [c for c in REQUIRED_TS_COLS if c not in df.columns]
    if miss:
        raise KeyError(f"{path} 缺少列: {miss}")
    if len(df) < 90:
        raise ValueError(f"{path} 行数过少 ({len(df)})，全周对比需 672 行。")
    return df


def pick_typical_day(ref: pd.DataFrame, *, dt: float) -> str:
    """
    在参考场景（w=1）上选典型日：
    score(d) = 当日 EV 放电能量(kWh) + 50 * 当日 P_buy_kw 标准差
    """
    ref = ref.copy()
    ref["t"] = pd.to_datetime(ref["timestamp"])
    ref["_d"] = ref["t"].dt.date.astype(str)
    best_d, best_s = "", -1.0
    for d, g in ref.groupby("_d"):
        ev_dis = pd.to_numeric(g["P_ev_dis_total_kw"], errors="coerce").fillna(0.0)
        ev_e = float((ev_dis * dt).sum())
        pb = pd.to_numeric(g["P_buy_kw"], errors="coerce").fillna(0.0)
        std = float(pb.std()) if len(pb) > 1 else 0.0
        s = ev_e + 50.0 * std
        if s > best_s:
            best_s, best_d = s, str(d)
    if not best_d:
        raise RuntimeError("未能选出典型日。")
    return best_d


def _style_hour_axis(ax: plt.Axes) -> None:
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=28, ha="right")


def plot_typical_day_compare(repo: Path, paths: dict[str, Path], day: str, out_dir: Path) -> None:
    dt = 0.25
    dfs: dict[str, pd.DataFrame] = {}
    for k, p in [("问题一（p1_ultimate）", paths["p1"]), ("第二题 w=1", paths["w1"]), ("第二题 w=2", paths["w2"])]:
        df = load_timeseries(p)
        df = df.copy()
        df["t"] = pd.to_datetime(df["timestamp"])
        df["_d"] = df["t"].dt.date.astype(str)
        sub = df[df["_d"] == day].copy()
        if len(sub) < 10:
            raise ValueError(f"{k} 在日期 {day} 上数据点过少: {len(sub)}")
        dfs[k] = sub
        if "delta_t_h" in sub.columns:
            dt = float(pd.to_numeric(sub["delta_t_h"], errors="coerce").iloc[0])

    scenarios = list(dfs.keys())
    nrows, ncols = 4, 3
    fig, axes = plt.subplots(
        nrows,
        ncols,
        sharex="col",
        figsize=(15.0, 11.0),
        dpi=150,
        gridspec_kw={"hspace": 0.28, "wspace": 0.22},
    )

    for j, sc in enumerate(scenarios):
        g = dfs[sc]
        t = g["t"]
        buy = pd.to_numeric(g["P_buy_kw"], errors="coerce")
        ech = pd.to_numeric(g["P_ess_ch_kw"], errors="coerce")
        edc = pd.to_numeric(g["P_ess_dis_kw"], errors="coerce")
        vch = pd.to_numeric(g["P_ev_ch_total_kw"], errors="coerce")
        vdc = pd.to_numeric(g["P_ev_dis_total_kw"], errors="coerce")
        sh = pd.to_numeric(g["P_shift_out_total_kw"], errors="coerce")
        rc = pd.to_numeric(g["P_recover_total_kw"], errors="coerce")
        curt = pd.to_numeric(g["pv_curtail_kw"], errors="coerce")

        axes[0, j].plot(t, buy, drawstyle="steps-post", color="#1f77b4", lw=1.35, label="P_buy_kw")
        axes[0, j].set_ylabel("kW")
        axes[0, j].set_title(sc, fontsize=10)
        axes[0, j].grid(True, axis="y", alpha=0.2, linestyle=":")
        axes[0, j].legend(loc="upper left", fontsize=7)

        axes[1, j].plot(t, ech, drawstyle="steps-post", color="#2ca02c", lw=1.1, label="P_ess_ch_kw")
        axes[1, j].plot(t, edc, drawstyle="steps-post", color="#d62728", lw=1.1, label="P_ess_dis_kw")
        axes[1, j].set_ylabel("kW")
        axes[1, j].legend(loc="upper left", fontsize=7, ncol=2)
        axes[1, j].grid(True, axis="y", alpha=0.2, linestyle=":")

        axes[2, j].plot(t, vch, drawstyle="steps-post", color="#9467bd", lw=1.05, label="P_ev_ch_total_kw")
        axes[2, j].plot(t, vdc, drawstyle="steps-post", color="#8c564b", lw=1.05, label="P_ev_dis_total_kw")
        axes[2, j].set_ylabel("kW")
        axes[2, j].legend(loc="upper left", fontsize=7, ncol=2)
        axes[2, j].grid(True, axis="y", alpha=0.2, linestyle=":")

        axes[3, j].plot(t, sh, drawstyle="steps-post", color="#e377c2", lw=1.0, label="P_shift_out_total_kw")
        axes[3, j].plot(t, rc, drawstyle="steps-post", color="#7f7f7f", lw=1.0, label="P_recover_total_kw")
        mx_c = float(np.nanmax(curt.to_numpy())) if len(curt) else 0.0
        if mx_c > 1.0:
            axes[3, j].plot(t, curt, drawstyle="steps-post", color="#bcbd22", lw=1.0, alpha=0.85, label="pv_curtail_kw")
        else:
            axes[3, j].plot(
                t,
                curt,
                drawstyle="steps-post",
                color="#bcbd22",
                lw=0.75,
                alpha=0.35,
                label="pv_curtail_kw（近零）",
            )
        axes[3, j].set_ylabel("kW")
        axes[3, j].set_xlabel("时间", fontsize=9)
        axes[3, j].legend(loc="upper left", fontsize=6.5, ncol=2)
        axes[3, j].grid(True, axis="y", alpha=0.2, linestyle=":")
        _style_hour_axis(axes[3, j])

    for i in range(3):
        _style_hour_axis(axes[0, i])
        _style_hour_axis(axes[1, i])
        _style_hour_axis(axes[2, i])

    fig.suptitle(
        f"典型日调度对比（{day}）｜问题一 vs 第二题 w=1 vs w=2\n"
        "阶梯线：每 15 min 功率取常值；列依次为问题一、p2 扫描 w=1、w=2。",
        fontsize=11.5,
        y=0.995,
    )
    fig.text(
        0.5,
        0.01,
        f"典型日选取：在 w=1 时序上最大化「当日 EV 放电能量 + 50×当日购电功率标准差」→ {day}。",
        ha="center",
        fontsize=8,
        color="#333333",
    )
    fig.subplots_adjust(left=0.07, right=0.98, top=0.90, bottom=0.10)
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"problem2_typical_day_dispatch_compare.{ext}", dpi=300, bbox_inches="tight", format=ext)
    plt.close(fig)


def load_metrics(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"缺少 operational_metrics.json: {path}\n"
            "最短补齐：运行 p2.py 全周权重扫描（scan_auto_weight_scan）以生成 w_0/w_1/w_2 目录。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_breakdown(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def plot_ev_participation(repo: Path, paths: dict[str, Path], out_dir: Path) -> None:
    weights = [0.0, 1.0, 2.0]
    mpaths = [paths["w0_metrics"], paths["w1_metrics"], paths["w2_metrics"]]
    ev_dis = []
    ev_thr = []
    for p in mpaths:
        m = load_metrics(p)
        ev_dis.append(float(m["ev_discharge_energy_kwh"]))
        ev_thr.append(float(m["ev_throughput_kwh"]))

    x = np.arange(len(weights))
    w = 0.32
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    ax.bar(x - w / 2, ev_dis, width=w, label="ev_discharge_energy_kWh", color="#8c564b", edgecolor="#5c3a2b", linewidth=0.4)
    ax.bar(x + w / 2, ev_thr, width=w, label="ev_throughput_kWh", color="#c49c94", edgecolor="#7a5c52", linewidth=0.4)
    ax.set_xticks(x)
    ax.set_xticklabels([str(int(w_)) if w_ == int(w_) else str(w_) for w_ in weights])
    ax.set_xlabel("寿命权重 w（对角 ess_deg_weight = ev_deg_weight）", fontsize=10)
    ax.set_ylabel("能量（kWh）", fontsize=10)
    ax.set_title("EV 放电量与半周吞吐量对比（w=0,1,2）", fontsize=11)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, axis="y", alpha=0.25, linestyle=":")
    fig.text(
        0.5,
        0.02,
        "数据来源：results/problem2_lifecycle/scans/scan_auto_weight_scan/w_*/operational_metrics.json",
        ha="center",
        fontsize=7,
        color="#444444",
    )
    fig.subplots_adjust(bottom=0.18)
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"problem2_ev_participation_compare.{ext}", dpi=300, bbox_inches="tight", format=ext)
    plt.close(fig)


def write_main_results(repo: Path, paths: dict[str, Path], tbl_dir: Path) -> None:
    bd = load_breakdown(paths["w1_breakdown"])
    m = load_metrics(paths["w1_metrics"])
    ts = load_timeseries(paths["w1"])
    peak = float(pd.to_numeric(ts["P_buy_kw"], errors="coerce").max())

    row = {
        "scenario": "problem2_scan_auto_weight_w1",
        "objective_total": bd.get("objective_from_solver"),
        "operation_cost": bd.get("operation_cost"),
        "ess_degradation_cost": bd.get("ess_degradation_cost"),
        "ev_degradation_cost": bd.get("ev_degradation_cost"),
        "grid_import_energy_kwh": m.get("grid_import_energy_kwh"),
        "peak_grid_import_kw": peak,
        "ess_throughput_kwh": m.get("ess_throughput_kwh"),
        "ev_throughput_kwh": m.get("ev_throughput_kwh"),
        "source_objective_breakdown": str(paths["w1_breakdown"].relative_to(repo)),
        "source_operational_metrics": str(paths["w1_metrics"].relative_to(repo)),
        "source_timeseries_peak": str(paths["w1"].relative_to(repo)),
        "column_peak": "P_buy_kw max",
    }
    tbl_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    csv_p = tbl_dir / "problem2_main_results.csv"
    df.to_csv(csv_p, index=False, encoding="utf-8-sig")

    md_lines = [
        "# 第二题主结果汇总（w=1）",
        "",
        "| 指标 | 数值 | 来源 |",
        "|------|------|------|",
        f"| objective_total | {row['objective_total']} | `objective_breakdown.json` → `objective_from_solver` |",
        f"| operation_cost | {row['operation_cost']} | `objective_breakdown.json` → `operation_cost` |",
        f"| ess_degradation_cost | {row['ess_degradation_cost']} | `objective_breakdown.json` |",
        f"| ev_degradation_cost | {row['ev_degradation_cost']} | `objective_breakdown.json` |",
        f"| grid_import_energy_kwh | {row['grid_import_energy_kwh']} | `operational_metrics.json` |",
        f"| peak_grid_import_kw | {row['peak_grid_import_kw']} | `timeseries.csv` 列 `P_buy_kw` 全周 max |",
        f"| ess_throughput_kwh | {row['ess_throughput_kwh']} | `operational_metrics.json` |",
        f"| ev_throughput_kwh | {row['ev_throughput_kwh']} | `operational_metrics.json` |",
        "",
        f"文件：`{row['source_objective_breakdown']}`、`{row['source_operational_metrics']}`、`{row['source_timeseries_peak']}`。",
        "",
    ]
    (tbl_dir / "problem2_main_results.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(csv_p)


def write_weight_sensitivity(repo: Path, paths: dict[str, Path], tbl_dir: Path) -> None:
    rows = []
    for w, tag in [(0.0, "w_0"), (1.0, "w_1"), (2.0, "w_2")]:
        base = repo / "results/problem2_lifecycle/scans/scan_auto_weight_scan" / tag
        bd_p = base / "objective_breakdown.json"
        m_p = base / "operational_metrics.json"
        bd = load_breakdown(bd_p)
        m = load_metrics(m_p)
        ess_t = float(m["ess_throughput_kwh"])
        ev_t = float(m["ev_throughput_kwh"])
        ess_d = float(m["ess_discharge_energy_kwh"])
        ev_d = float(m["ev_discharge_energy_kwh"])
        den_t = ess_t + ev_t
        den_s = ess_d + ev_d
        rows.append(
            {
                "weight": w,
                "objective_total": float(bd["objective_from_solver"]),
                "operation_cost": float(bd["operation_cost"]),
                "ev_discharge_energy_kwh": float(m["ev_discharge_energy_kwh"]),
                "ev_throughput_kwh": float(m["ev_throughput_kwh"]),
                "ess_share_throughput_pct": round(100.0 * ess_t / den_t, 4) if den_t > 1e-9 else None,
                "ess_share_supply_pct": round(100.0 * ess_d / den_s, 4) if den_s > 1e-9 else None,
                "source_dir": str(base.relative_to(repo)),
            }
        )
    df = pd.DataFrame(rows)
    tbl_dir.mkdir(parents=True, exist_ok=True)
    csv_p = tbl_dir / "problem2_weight_sensitivity_and_roles.csv"
    df.to_csv(csv_p, index=False, encoding="utf-8-sig")

    def _md_table(d: pd.DataFrame) -> str:
        cols = list(d.columns)
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
        for _, r in d.iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
        return "\n".join(lines)

    md = [
        "# 寿命权重敏感性与 ESS/EV 分工比例（w=0,1,2）",
        "",
        "**分工定义**：",
        "- `ess_share_throughput_pct` = 100 × `ess_throughput_kwh` / (`ess_throughput_kwh` + `ev_throughput_kwh`)",
        "- `ess_share_supply_pct` = 100 × `ess_discharge_energy_kwh` / (`ess_discharge_energy_kwh` + `ev_discharge_energy_kwh`)",
        "",
        _md_table(df),
        "",
        "**数据**：各 `scan_auto_weight_scan/w_*/operational_metrics.json` 与 `objective_breakdown.json`。",
        "",
    ]
    (tbl_dir / "problem2_weight_sensitivity_and_roles.md").write_text("\n".join(md), encoding="utf-8")
    print(csv_p)


def main() -> int:
    ap = argparse.ArgumentParser(description="第二题论文图与表")
    ap.add_argument("--repo-root", type=Path, default=_REPO)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    paths = _repo_paths(repo)

    ref = load_timeseries(paths["w1"])
    dt = float(pd.to_numeric(ref["delta_t_h"], errors="coerce").fillna(0.25).iloc[0])
    day = pick_typical_day(ref, dt=dt)

    fig_dir = repo / "results" / "figures" / "problem2"
    tbl_dir = repo / "results" / "tables"
    fig_dir.mkdir(parents=True, exist_ok=True)

    plot_typical_day_compare(repo, paths, day, fig_dir)
    print(fig_dir / "problem2_typical_day_dispatch_compare.png")
    print(fig_dir / "problem2_typical_day_dispatch_compare.pdf")

    plot_ev_participation(repo, paths, fig_dir)
    print(fig_dir / "problem2_ev_participation_compare.png")
    print(fig_dir / "problem2_ev_participation_compare.pdf")

    write_main_results(repo, paths, tbl_dir)
    print(tbl_dir / "problem2_main_results.md")

    write_weight_sensitivity(repo, paths, tbl_dir)
    print(tbl_dir / "problem2_weight_sensitivity_and_roles.md")

    print(f"typical_day={day}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
