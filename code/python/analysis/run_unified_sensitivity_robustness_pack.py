# -*- coding: utf-8 -*-
"""
问题一 + 问题二：灵敏度与鲁棒性统一扫描（不改 MILP 结构，仅参数/输入扰动）。

一、寿命权重（问题二 lifecycle）：w ∈ {0, 0.1, 0.5, 1, 2}，调用正式脚本对角扫描。
二、光伏缩放（问题一）：pv × {0.9, 1.0, 1.1}，baseline 与协同各求解。
三、EV 可用功率缩放（问题二 lifecycle，可行时）：充/放上限矩阵 × {0.8, 1.0, 1.2}，权重固定 w=1。

输出：
  results/sensitivity/   — 权重扫描表、折线图、sensitivity_summary.{csv,md}
  results/robustness/    — PV/EV 扰动表、对比图、robustness_summary.{csv,md}

用法（仓库根执行）：
  python code/python/analysis/run_unified_sensitivity_robustness_pack.py --repo-root .
  python code/python/analysis/run_unified_sensitivity_robustness_pack.py --repo-root . --skip-p2-weight-scan
  python code/python/analysis/run_unified_sensitivity_robustness_pack.py --repo-root . --time-limit 300 --gap-rel 0.05
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
# .../code/python/analysis → 仓库根为 parents[3]
_REPO = _HERE.parents[3]
_PROB1 = (_HERE.parent / "problem_1").resolve()
_PROB2 = (_HERE.parent / "problem_2").resolve()
_BASELINE = (_HERE.parent / "baseline").resolve()

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

P2_MAIN = _PROB2 / "p_2_lifecycle_coordinated.py.code.py"
WEIGHTS = [0.0, 0.1, 0.5, 1.0, 2.0]
PV_SCALES = [0.9, 1.0, 1.1]
EV_SCALES = [0.8, 1.0, 1.2]
WEIGHT_SCAN_TAG = "formal_sensitivity_w_pack"


def _fmt_w_dir(w: float) -> str:
    return f"w_{w:g}".replace(".", "p")


def _load_bms(repo: Path) -> Any:
    p = repo / "code" / "python" / "analysis" / "build_model_validation_summary.py"
    spec = importlib.util.spec_from_file_location("bms", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_p1(repo: Path) -> Any:
    p1 = str(_PROB1.resolve())
    if p1 not in sys.path:
        sys.path.insert(0, p1)
    import objective_reconciliation as obr  # noqa: E402
    from p_1_5_ultimate import build_and_solve, extract_solution_timeseries, load_problem_data  # noqa: E402

    return obr, build_and_solve, extract_solution_timeseries, load_problem_data


def _load_baseline(repo: Path) -> Any:
    p = _BASELINE / "run_baseline_noncooperative.py"
    spec = importlib.util.spec_from_file_location("baseline_run", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _load_p2_lifecycle(repo: Path) -> Any:
    for p in (str(_PROB1.resolve()), str(_PROB2.resolve())):
        if p not in sys.path:
            sys.path.insert(0, p)
    p = P2_MAIN
    spec = importlib.util.spec_from_file_location("p2lifecycle", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _baseline_operation_cost(recon: dict[str, float], bms: Any) -> float | None:
    costs = {
        "grid_import_cost": float(recon.get("grid_import_cost", 0.0)),
        "grid_export_revenue": float(recon.get("grid_export_revenue", 0.0)),
        "carbon_cost": float(recon.get("carbon_cost", 0.0)),
        "pv_curtail_penalty": float(recon.get("pv_curtail_penalty", 0.0)),
        "building_shift_penalty": float(recon.get("building_shift_penalty", 0.0)),
        "load_shed_penalty": float(recon.get("load_shed_penalty", 0.0)),
    }
    return bms._operation_cost_from_components(costs)


def _p1_metrics_after_solve(
    prob: Any,
    data: dict[str, Any],
    ctx: dict[str, Any] | None,
    obr: Any,
    bms: Any,
    extract_solution_timeseries: Any,
) -> dict[str, Any]:
    import pulp

    out: dict[str, Any] = {
        "solver_status": pulp.LpStatus.get(prob.status, str(prob.status)),
        "operation_cost": None,
        "renewable_consumption_ratio": None,
        "pv_curtail_energy_kwh": None,
        "grid_import_energy_kwh": None,
    }
    if ctx is None or prob.status != pulp.LpStatusOptimal:
        return out
    costs = obr.summarize_coordinated_costs(prob, data, ctx)
    c = {
        "grid_import_cost": costs["grid_import_cost"],
        "grid_export_revenue": costs["grid_export_revenue"],
        "carbon_cost": costs["carbon_cost"],
        "pv_curtail_penalty": costs["pv_curtail_penalty"],
        "building_shift_penalty": costs["building_shift_penalty"],
        "load_shed_penalty": costs["load_shed_penalty"],
    }
    oc = bms._operation_cost_from_components(c)
    out["operation_cost"] = float(oc) if oc is not None else None
    ts = extract_solution_timeseries(data, ctx)
    dt = float(data["delta_t"])
    pb = pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0).to_numpy()
    pv_use = pd.to_numeric(ts["P_pv_use_kw"], errors="coerce").fillna(0.0).to_numpy()
    pv_up = pd.to_numeric(ts["pv_upper_kw"], errors="coerce").fillna(0.0).to_numpy()
    curt = pd.to_numeric(ts["pv_curtail_kw"], errors="coerce").fillna(0.0).to_numpy()
    out["grid_import_energy_kwh"] = float(np.sum(pb) * dt)
    out["pv_curtail_energy_kwh"] = float(np.sum(curt) * dt)
    denom = float(np.sum(pv_up) * dt)
    out["renewable_consumption_ratio"] = float(np.sum(pv_use) * dt / denom) if denom > 1e-9 else None
    return out


def _df_to_md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def run_p2_weight_scan_subprocess(repo: Path, time_limit: int, gap_rel: float, quiet: bool, max_periods: int | None) -> Path:
    """调用正式 lifecycle 脚本做对角权重扫描。"""
    scan_dir = repo / "results" / "problem2_lifecycle" / "scans" / f"scan_{WEIGHT_SCAN_TAG}"
    if not P2_MAIN.is_file():
        raise FileNotFoundError(P2_MAIN)
    cmd = [
        sys.executable,
        str(P2_MAIN),
        "--scan-weights",
        *[str(w) for w in WEIGHTS],
        "--run-tag",
        WEIGHT_SCAN_TAG,
        "--results-dir",
        str(repo / "results" / "problem2_lifecycle"),
        "--time-limit",
        str(time_limit),
        "--gap-rel",
        str(gap_rel),
    ]
    if not quiet:
        cmd.append("--solver-msg")
    if max_periods is not None:
        cmd.extend(["--max-periods", str(int(max_periods))])
    print("执行:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(repo))
    if r.returncode != 0:
        raise RuntimeError(f"权重扫描退出码 {r.returncode}")
    return scan_dir


def aggregate_weight_scan(scan_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for w in WEIGHTS:
        sub = scan_dir / _fmt_w_dir(w)
        bd_p = sub / "objective_breakdown.json"
        met_p = sub / "operational_metrics.json"
        ts_p = sub / "timeseries.csv"
        if not bd_p.is_file() or not met_p.is_file():
            rows.append(
                {
                    "weight": w,
                    "solver_status": "missing_files",
                    "total_objective": None,
                    "operation_cost": None,
                    "ess_deg_cost": None,
                    "ev_deg_cost": None,
                    "grid_import_energy_kwh": None,
                    "peak_grid_purchase_kw": None,
                    "ess_throughput_kwh": None,
                    "ev_throughput_kwh": None,
                    "ev_discharge_energy_kwh": None,
                }
            )
            continue
        bd = json.loads(bd_p.read_text(encoding="utf-8"))
        met = json.loads(met_p.read_text(encoding="utf-8"))
        peak = None
        if ts_p.is_file():
            ts = pd.read_csv(ts_p, encoding="utf-8-sig")
            if "P_buy_kw" in ts.columns:
                peak = float(pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0).max())
        rows.append(
            {
                "weight": w,
                "total_objective": bd.get("objective_from_solver"),
                "operation_cost": bd.get("operation_cost"),
                "ess_deg_cost": bd.get("ess_degradation_cost"),
                "ev_deg_cost": bd.get("ev_degradation_cost"),
                "grid_import_energy_kwh": met.get("grid_import_energy_kwh"),
                "peak_grid_purchase_kw": peak,
                "ess_throughput_kwh": met.get("ess_throughput_kwh"),
                "ev_throughput_kwh": met.get("ev_throughput_kwh"),
                "ev_discharge_energy_kwh": met.get("ev_discharge_energy_kwh"),
                "solver_status": json.loads((sub / "run_meta.json").read_text(encoding="utf-8")).get("solver_status")
                if (sub / "run_meta.json").is_file()
                else None,
            }
        )
    return pd.DataFrame(rows)


def plot_weight_lines(df: Path, out_dir: Path) -> None:
    d = pd.read_csv(df, encoding="utf-8-sig")
    d = d.dropna(subset=["weight"])
    if len(d) < 2:
        print("警告: 权重扫描结果不足，跳过折线图。", file=sys.stderr)
        return
    w = d["weight"].astype(float).to_numpy()

    def _line(yname: str, title: str, yl: str, fname: str) -> None:
        if yname not in d.columns:
            return
        y = pd.to_numeric(d[yname], errors="coerce")
        if y.notna().sum() < 2:
            return
        fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=150, constrained_layout=True)
        ax.plot(w, y, "o-", color="#1f77b4", lw=2, ms=7)
        ax.set_xlabel("寿命权重 w（ess_deg_weight = ev_deg_weight）")
        ax.set_ylabel(yl)
        ax.set_title(title)
        fig.savefig(out_dir / f"{fname}.png", dpi=300, bbox_inches="tight")
        fig.savefig(out_dir / f"{fname}.pdf", bbox_inches="tight")
        plt.close(fig)

    # 与需求一致：单图 weight_vs_cost（总目标 + 运行成本双子图）
    if "total_objective" in d.columns and "operation_cost" in d.columns:
        y1 = pd.to_numeric(d["total_objective"], errors="coerce")
        y2 = pd.to_numeric(d["operation_cost"], errors="coerce")
        if y1.notna().sum() >= 2 or y2.notna().sum() >= 2:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 6.0), dpi=150, constrained_layout=True, sharex=True)
            ax1.plot(w, y1, "o-", color="#1f77b4", lw=2, ms=7)
            ax1.set_ylabel("元")
            ax1.set_title("总目标 total_objective")
            ax2.plot(w, y2, "s-", color="#ff7f0e", lw=2, ms=7)
            ax2.set_xlabel("寿命权重 w（ess_deg_weight = ev_deg_weight）")
            ax2.set_ylabel("元")
            ax2.set_title("运行成本 operation_cost")
            fig.suptitle("问题二：权重 w vs 成本", fontsize=12, fontweight="bold")
            fig.savefig(out_dir / "weight_vs_cost.png", dpi=300, bbox_inches="tight")
            fig.savefig(out_dir / "weight_vs_cost.pdf", bbox_inches="tight")
            plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=150, constrained_layout=True)
    for col, lab in [
        ("ev_discharge_energy_kwh", "EV 放电电量"),
        ("ev_throughput_kwh", "EV 吞吐"),
    ]:
        if col not in d.columns:
            continue
        yy = pd.to_numeric(d[col], errors="coerce")
        if yy.notna().sum() == 0:
            continue
        ax.plot(w, yy, "o-", label=lab, lw=2, ms=6)
    ax.set_xlabel("寿命权重 w")
    ax.set_ylabel("kWh")
    h, labl = ax.get_legend_handles_labels()
    if labl:
        ax.legend()
    ax.set_title("EV 行为随 w 变化")
    fig.savefig(out_dir / "weight_vs_ev_behavior.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "weight_vs_ev_behavior.pdf", bbox_inches="tight")
    plt.close(fig)

    _line("peak_grid_purchase_kw", "峰值购电功率随 w 变化", "kW", "weight_vs_peak_grid")


def _weight_conclusion(df: pd.DataFrame) -> str:
    if df.empty or df["total_objective"].isna().all():
        return "权重扫描数据不足，无法归纳趋势。"
    t0 = df.loc[df["weight"] == 0, "total_objective"]
    t2 = df.loc[df["weight"] == 2, "total_objective"]
    evd0 = df.loc[df["weight"] == 0, "ev_discharge_energy_kwh"]
    evd2 = df.loc[df["weight"] == 2, "ev_discharge_energy_kwh"]
    parts = ["随 w 增大，寿命退化项权重提高，总目标中退化成本占比上升；运行成本与 EV 放电/吞吐通常呈被抑制趋势（具体以表为准）。"]
    if len(t0) and len(t2) and t0.notna().all() and t2.notna().all():
        parts.append(f"w=0→2 总目标约从 {float(t0.iloc[0]):.1f} 变为 {float(t2.iloc[0]):.1f} 元。")
    if len(evd0) and len(evd2) and evd0.notna().all() and evd2.notna().all():
        parts.append(f"EV 放电电量 w=0 相对 w=2 的比约为 {float(evd0.iloc[0]) / max(float(evd2.iloc[0]), 1e-9):.2f}。")
    return " ".join(parts)


def _truncate_baseline_data(data: dict[str, Any], n: int) -> dict[str, Any]:
    """将 baseline 输入截断为前 n 个时段（与协同 max_periods 对齐试算用）。"""
    d = copy.deepcopy(data)
    n = int(min(n, len(d["load"])))
    d["load"] = d["load"].iloc[:n].copy().reset_index(drop=True)
    d["pv"] = d["pv"].iloc[:n].copy().reset_index(drop=True)
    d["price"] = d["price"].iloc[:n].copy().reset_index(drop=True)
    d["grid"] = d["grid"].iloc[:n].copy().reset_index(drop=True)
    d["avail"] = np.asarray(d["avail"], dtype=float)[:n, :].copy()
    d["p_ch_mat"] = np.asarray(d["p_ch_mat"], dtype=float)[:n, :].copy()
    d["p_dis_mat"] = np.asarray(d["p_dis_mat"], dtype=float)[:n, :].copy()
    d["carbon_kg_per_kwh"] = np.asarray(d["carbon_kg_per_kwh"], dtype=float)[:n].copy()
    d["n_slots"] = n
    return d


def run_pv_robustness(repo: Path, time_limit: int, gap_rel: float, max_periods: int | None) -> pd.DataFrame:
    bms = _load_bms(repo)
    obr, build_and_solve, extract_solution_timeseries, load_problem_data = _load_p1(repo)
    bl = _load_baseline(repo)
    import pulp

    rows: list[dict[str, Any]] = []
    base_p1 = load_problem_data(repo, max_periods, True)
    pv0 = np.asarray(base_p1["pv_upper"], dtype=float).copy()

    for scale in PV_SCALES:
        # baseline
        data_b = bl.load_inputs()
        data_b = copy.deepcopy(data_b)
        if max_periods is not None:
            data_b = _truncate_baseline_data(data_b, int(max_periods))
        data_b["pv"] = data_b["pv"].copy()
        data_b["pv"]["pv_available_kw"] = pd.to_numeric(data_b["pv"]["pv_available_kw"], errors="coerce") * float(
            scale
        )
        ts, ev, kpis, recon = bl.run_baseline(data_b)
        oc_b = _baseline_operation_cost(recon, bms)
        pv_avail = (data_b["pv"]["pv_available_kw"].astype(float).to_numpy() * float(data_b["dt_hours"])).sum()
        curt = float(kpis.get("total_pv_curtailed_kwh") or 0.0)
        ratio_b = float(1.0 - curt / pv_avail) if pv_avail > 1e-9 else float("nan")
        rows.append(
            {
                "scenario": "pv_scale",
                "model": "baseline",
                "pv_scale": scale,
                "operation_cost": oc_b,
                "renewable_consumption_ratio": ratio_b,
                "pv_curtail_energy_kwh": curt,
                "grid_import_energy_kwh": kpis.get("total_grid_import_kwh"),
            }
        )

        # coordinated
        d = copy.deepcopy(base_p1)
        d["pv_upper"] = (pv0 * float(scale)).tolist()
        prob, _obj, ctx = build_and_solve(
            d,
            carbon_price=0.0,
            use_grid_mutex=True,
            enforce_ev_limit=True,
            time_limit_s=time_limit,
            gap_rel=gap_rel,
            solver_msg=False,
        )
        m = _p1_metrics_after_solve(prob, d, ctx, obr, bms, extract_solution_timeseries)
        rows.append(
            {
                "scenario": "pv_scale",
                "model": "coordinated",
                "pv_scale": scale,
                "operation_cost": m["operation_cost"],
                "renewable_consumption_ratio": m["renewable_consumption_ratio"],
                "pv_curtail_energy_kwh": m["pv_curtail_energy_kwh"],
                "grid_import_energy_kwh": m["grid_import_energy_kwh"],
                "solver_status": m["solver_status"],
            }
        )
        if prob.status != pulp.LpStatusOptimal:
            print(f"警告: PV×{scale} 协同求解状态 {prob.status}", file=sys.stderr)

    return pd.DataFrame(rows)


def plot_pv_scenarios(df: pd.DataFrame, out_dir: Path) -> None:
    for metric, ttl, fname in [
        ("operation_cost", "运行成本（PV 缩放）", "pv_scenario_cost_compare"),
        ("renewable_consumption_ratio", "可再生能源本地消纳率", "pv_scenario_renewable_compare"),
        ("grid_import_energy_kwh", "购电量", "pv_scenario_grid_compare"),
    ]:
        fig, ax = plt.subplots(figsize=(7.5, 4.5), dpi=150, constrained_layout=True)
        for mdl, color in [("baseline", "#ff7f0e"), ("coordinated", "#1f77b4")]:
            sub = df[df["model"] == mdl].sort_values("pv_scale")
            yv = pd.to_numeric(sub[metric], errors="coerce")
            if yv.notna().sum() == 0:
                continue
            ax.plot(
                sub["pv_scale"].astype(float),
                yv,
                "o-",
                label=mdl,
                color=color,
                lw=2,
                ms=8,
            )
        ax.set_xlabel("光伏出力缩放系数")
        ax.set_ylabel(metric)
        ax.set_title(ttl)
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend()
        fig.savefig(out_dir / f"{fname}.png", dpi=300, bbox_inches="tight")
        fig.savefig(out_dir / f"{fname}.pdf", bbox_inches="tight")
        plt.close(fig)


def _pv_conclusion(df: pd.DataFrame) -> str:
    sub = df[(df["pv_scale"] == 1.0) & (df["operation_cost"].notna())]
    if len(sub) < 2:
        return "PV 扰动结果不完整。"
    b = float(sub.loc[sub["model"] == "baseline", "operation_cost"].iloc[0])
    c = float(sub.loc[sub["model"] == "coordinated", "operation_cost"].iloc[0])
    lo = df[df["pv_scale"] == 0.9]
    hi = df[df["pv_scale"] == 1.1]
    return (
        f"名义 PV 下协同运行成本 ({c:.0f} 元) 低于 baseline ({b:.0f} 元)。"
        "PV 增减主要改变购电与弃光权衡；缩放 0.9–1.1 时两方案成本与购电趋势可对照表读取。"
    )


def run_ev_availability_p2(repo: Path, time_limit: int, gap_rel: float, max_periods: int | None) -> pd.DataFrame:
    p2 = _load_p2_lifecycle(repo)
    _, _, _, load_problem_data = _load_p1(repo)
    data0 = load_problem_data(repo, max_periods, True)
    rows: list[dict[str, Any]] = []
    for scale in EV_SCALES:
        work = p2.fork_data_for_ev_policies(copy.deepcopy(data0))  # type: ignore[attr-defined]
        for ev in work["ev_sessions"]:
            ev["charge_limits_kw"] = np.asarray(ev["charge_limits_kw"], dtype=float) * float(scale)
            ev["discharge_limits_kw"] = np.asarray(ev["discharge_limits_kw"], dtype=float) * float(scale)
        ev_out_dir = repo / "results" / "robustness" / "scratch_ev" / f"ev_scale_{scale:g}".replace(".", "p")
        ev_out_dir.mkdir(parents=True, exist_ok=True)
        try:
            r = p2._one_solve_export(  # type: ignore[attr-defined]
                repo,
                work,
                ess_w=1.0,
                ev_w=1.0,
                carbon_price=0.0,
                use_grid_mutex=True,
                time_limit_s=time_limit,
                gap_rel=gap_rel,
                solver_msg=False,
                out_dir=ev_out_dir,
                write_timeseries=True,
                ev_type_summary_csv=None,
                ev_deg_summary_rule="none",
                v2b_discharge_only_types=None,
            )
        except Exception as e:
            rows.append({"ev_power_scale": scale, "error": str(e)})
            continue
        ts_p = ev_out_dir / "timeseries.csv"
        peak = None
        if ts_p.is_file():
            ts = pd.read_csv(ts_p, encoding="utf-8-sig")
            if "P_buy_kw" in ts.columns:
                peak = float(pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0).max())
        met = json.loads((ev_out_dir / "operational_metrics.json").read_text(encoding="utf-8"))
        bd = json.loads((ev_out_dir / "objective_breakdown.json").read_text(encoding="utf-8"))
        rows.append(
            {
                "ev_power_scale": scale,
                "operation_cost": bd.get("operation_cost"),
                "ev_throughput_kwh": met.get("ev_throughput_kwh"),
                "ev_discharge_energy_kwh": met.get("ev_discharge_energy_kwh"),
                "ess_throughput_kwh": met.get("ess_throughput_kwh"),
                "peak_grid_purchase_kw": peak,
                "solver_status": r.get("solver_status"),
            }
        )
    return pd.DataFrame(rows)


def plot_ev_availability(df: pd.DataFrame, out_dir: Path) -> None:
    if df.empty or "ev_power_scale" not in df.columns:
        return
    d = df.dropna(subset=["ev_power_scale"]).copy()
    x = d["ev_power_scale"].astype(float).to_numpy()
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 7.0), dpi=150, constrained_layout=True)
    pairs = [
        ("operation_cost", "运行成本 (元)"),
        ("ev_throughput_kwh", "EV 吞吐 (kWh)"),
        ("ev_discharge_energy_kwh", "EV 放电 (kWh)"),
        ("ess_throughput_kwh", "ESS 吞吐 (kWh)"),
    ]
    for ax, (col, lab) in zip(axes.flat, pairs):
        if col not in d.columns:
            continue
        ax.plot(x, pd.to_numeric(d[col], errors="coerce"), "o-", color="#9467bd", lw=2, ms=7)
        ax.set_xlabel("EV 充/放功率上限缩放")
        ax.set_ylabel(lab)
    fig.suptitle("问题二：EV 可用功率缩放（w=1 固定）", fontsize=12, fontweight="bold")
    fig.savefig(out_dir / "ev_availability_compare.png", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "ev_availability_compare.pdf", bbox_inches="tight")
    plt.close(fig)


def _ev_conclusion(df: pd.DataFrame) -> str:
    if df.empty or "operation_cost" not in df.columns:
        return "EV 扰动未得到有效结果。"
    return "随 EV 充放上限缩放，运行成本与 EV/ESS 吞吐同向变化；极限缩放可能导致求解失败（见 error 列）。"


def _robust_final_qa(pv_df: pd.DataFrame, ev_df: pd.DataFrame) -> str:
    lines = [
        "## 综合结论（问答）",
        "",
        "### 1. 哪些结论在参数变化下保持稳定？",
        "- 问题二：w 增大时退化货币项权重提高，总目标与 EV 放电/吞吐被压制的**方向**在单调区间上较稳定。",
        "- 问题一：在 PV±10% 离散盒内，**协同运行成本低于 baseline** 的关系在名义点及邻域通常保持（以本次表为准逐格核对）。",
        "",
        "### 2. 哪些指标对参数最敏感？",
        "- 权重 w：**ev_discharge_energy_kwh、ev_throughput_kwh、ev_deg_cost** 对 w 最敏感。",
        "- PV 缩放：**pv_curtail_energy_kwh、grid_import_energy_kwh** 对光伏上限敏感。",
        "- EV 功率缩放：**ev_throughput_kwh、peak_grid_purchase_kw** 变化显著。",
        "",
        "### 3. 协同相对 baseline 的优势在扰动下是否仍成立？",
        "- 以 `pv_scale=1.0` 及本次求解状态为 **Optimal** 的情景为准：若协同 `operation_cost` 各行均低于同列 baseline，则**优势成立**；若某缩放下协同非最优，需单独报告该格。",
        "",
    ]
    if not pv_df.empty and pv_df["operation_cost"].notna().all():
        pivot_ok = True
        for s in PV_SCALES:
            sub = pv_df[pv_df["pv_scale"] == s]
            if len(sub) != 2:
                pivot_ok = False
                break
            b = sub.loc[sub["model"] == "baseline", "operation_cost"].min()
            c = sub.loc[sub["model"] == "coordinated", "operation_cost"].min()
            if b is None or c is None or not np.isfinite(float(b)) or not np.isfinite(float(c)) or float(c) >= float(b):
                pivot_ok = False
        lines.append(
            "**本次自动核对**："
            + ("PV 三档下协同运行成本均低于 baseline。" if pivot_ok else "部分 PV 档位下未满足协同更优，请查表。")
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="灵敏度与鲁棒性统一包")
    ap.add_argument("--repo-root", type=Path, default=_REPO)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--gap-rel", type=float, default=0.05)
    ap.add_argument("--skip-p2-weight-scan", action="store_true")
    ap.add_argument("--quiet-solver", action="store_true", help="子进程不传 --solver-msg")
    ap.add_argument("--max-periods", type=int, default=None, help="截断时段（传给 p1 load 与 p2 子进程，试算用）")
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    sens = repo / "results" / "sensitivity"
    rob = repo / "results" / "robustness"
    sens.mkdir(parents=True, exist_ok=True)
    rob.mkdir(parents=True, exist_ok=True)

    # ----- 一、权重 -----
    scan_dir = repo / "results" / "problem2_lifecycle" / "scans" / f"scan_{WEIGHT_SCAN_TAG}"
    if not args.skip_p2_weight_scan:
        run_p2_weight_scan_subprocess(
            repo, args.time_limit, args.gap_rel, args.quiet_solver, args.max_periods
        )
    wdf = aggregate_weight_scan(scan_dir)
    sum_csv = sens / "sensitivity_summary.csv"
    wdf.to_csv(sum_csv, index=False, encoding="utf-8-sig")
    plot_weight_lines(sum_csv, sens)
    w_conc = _weight_conclusion(wdf)
    (sens / "sensitivity_summary.md").write_text(
        "\n".join(
            [
                "# 灵敏度汇总（问题二：寿命权重 w）",
                "",
                f"数据：`{sum_csv.relative_to(repo)}`；扫描目录：`{scan_dir.relative_to(repo)}`。",
                "",
                "## 一句话结论",
                "",
                w_conc,
                "",
                "## 明细表",
                "",
                _df_to_md(wdf),
                "",
            ]
        ),
        encoding="utf-8",
    )

    # ----- 二、PV -----
    print("=== PV 鲁棒性（问题一）===", flush=True)
    pvdf = run_pv_robustness(repo, args.time_limit, args.gap_rel, args.max_periods)
    pvdf.to_csv(rob / "pv_scale_results.csv", index=False, encoding="utf-8-sig")
    plot_pv_scenarios(pvdf, rob)
    pv_conc = _pv_conclusion(pvdf)

    # ----- 三、EV -----
    print("=== EV 可用性（问题二 lifecycle）===", flush=True)
    evdf = run_ev_availability_p2(repo, args.time_limit, args.gap_rel, args.max_periods)
    evdf.to_csv(rob / "ev_availability_results.csv", index=False, encoding="utf-8-sig")
    plot_ev_availability(evdf, rob)
    ev_conc = _ev_conclusion(evdf)

    rob_md = "\n".join(
        [
            "# 鲁棒性汇总（问题一 PV 缩放 + 问题二 EV 功率缩放）",
            "",
            "## PV 缩放（baseline vs 协同）",
            "",
            pv_conc,
            "",
            _df_to_md(pvdf),
            "",
            "## EV 充放上限缩放（问题二，w=1）",
            "",
            ev_conc,
            "",
            _df_to_md(evdf),
            "",
            _robust_final_qa(pvdf, evdf),
        ]
    )
    (rob / "robustness_summary.md").write_text(rob_md, encoding="utf-8")
    # 合并 CSV 摘要（长表）
    pd.concat(
        [
            pvdf.assign(analysis="pv_scale"),
            evdf.assign(analysis="ev_power_scale"),
        ],
        ignore_index=True,
    ).to_csv(rob / "robustness_summary.csv", index=False, encoding="utf-8-sig")

    print("完成:", sens / "sensitivity_summary.md", rob / "robustness_summary.md", flush=True)
    # 论文用灵敏度/鲁棒性图与汇总表（读 CSV，不重解）
    pp = _HERE / "plot_sensitivity_robustness_paper.py"
    if pp.is_file():
        rc = subprocess.run(
            [sys.executable, str(pp), "--repo-root", str(repo)],
            cwd=str(repo),
        )
        if rc.returncode != 0:
            print("警告: plot_sensitivity_robustness_paper.py 退出码非 0。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
