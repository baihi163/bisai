# -*- coding: utf-8 -*-
"""
问题一（p_1_5_ultimate）灵敏度分析与离散鲁棒检验。

- 灵敏度：单参数扰动（购电价倍率、碳价、弃光惩罚、建筑移位线性惩罚、储能退化单价），
  观察目标值与关键运行量变化。
- 鲁棒性：负荷与光伏可用功率的联合比例扰动（离散情景盒），观察目标与购电能量的波动范围。

不改模型结构；仅通过 data 字典的可选键覆盖惩罚系数（默认与原版一致）。

输出：
  results/tables/problem1_sensitivity_oneway.csv
  results/tables/problem1_robustness_scenarios.csv
  results/tables/problem1_sensitivity_robustness_summary.md

用法：
  python code/python/analysis/run_problem1_sensitivity_robustness.py --repo-root .
  python code/python/analysis/run_problem1_sensitivity_robustness.py --repo-root . --max-periods 192 --time-limit 90
  python code/python/analysis/run_problem1_sensitivity_robustness.py --repo-root . --mode robustness-only
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pulp

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_PROB1 = _REPO / "code" / "python" / "problem_1"
if str(_PROB1) not in sys.path:
    sys.path.insert(0, str(_PROB1))

from p_1_5_ultimate import (  # noqa: E402
    build_and_solve,
    extract_solution_timeseries,
    load_problem_data,
)
import objective_reconciliation as obr  # noqa: E402


def _clone_data(base: dict[str, Any]) -> dict[str, Any]:
    d = copy.deepcopy(base)
    return d


def _recompute_total_native(d: dict[str, Any]) -> None:
    d["total_native_load"] = np.sum([b["load"] for b in d["building_blocks"]], axis=0)


def collect_metrics(
    prob: pulp.LpProblem,
    data: dict[str, Any],
    ctx: dict[str, Any] | None,
) -> dict[str, Any]:
    st = pulp.LpStatus.get(prob.status, str(prob.status))
    out: dict[str, Any] = {
        "solver_status": st,
        "objective_pulp": None,
        "objective_recomputed": None,
        "grid_import_energy_kwh": None,
        "peak_P_buy_kw": None,
        "pv_curtail_energy_kwh": None,
        "ess_charge_energy_kwh": None,
        "ess_discharge_energy_kwh": None,
    }
    if prob.status != pulp.LpStatusOptimal or ctx is None:
        return out
    costs = obr.summarize_coordinated_costs(prob, data, ctx)
    out["objective_pulp"] = costs["objective_from_solver"]
    out["objective_recomputed"] = costs["objective_recomputed_from_solution"]
    ts = extract_solution_timeseries(data, ctx)
    dt = float(data["delta_t"])
    pb = pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    curt = pd.to_numeric(ts["pv_curtail_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ech = pd.to_numeric(ts["P_ess_ch_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    edc = pd.to_numeric(ts["P_ess_dis_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    out["grid_import_energy_kwh"] = float(np.sum(pb) * dt)
    out["peak_P_buy_kw"] = float(np.max(pb)) if len(pb) else 0.0
    out["pv_curtail_energy_kwh"] = float(np.sum(curt) * dt)
    out["ess_charge_energy_kwh"] = float(np.sum(ech) * dt)
    out["ess_discharge_energy_kwh"] = float(np.sum(edc) * dt)
    return out


def run_one(
    data: dict[str, Any],
    *,
    carbon_price: float,
    use_grid_mutex: bool,
    enforce_ev_limit: bool,
    time_limit_s: int,
    gap_rel: float,
    quiet: bool,
) -> tuple[pulp.LpProblem, dict[str, Any] | None, dict[str, Any]]:
    prob, _obj, ctx = build_and_solve(
        data,
        carbon_price=carbon_price,
        use_grid_mutex=use_grid_mutex,
        enforce_ev_limit=enforce_ev_limit,
        time_limit_s=time_limit_s,
        gap_rel=gap_rel,
        solver_msg=not quiet,
    )
    m = collect_metrics(prob, data, ctx)
    return prob, ctx, m


def sensitivity_rows(
    base: dict[str, Any],
    *,
    carbon_price: float,
    use_grid_mutex: bool,
    enforce_ev_limit: bool,
    time_limit_s: int,
    gap_rel: float,
    quiet: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base_buy = np.asarray(base["buy_price"], dtype=float).copy()

    def add_row(kind: str, name: str, val: float, d: dict[str, Any], m: dict[str, Any]) -> None:
        rows.append(
            {
                "analysis": "sensitivity_oneway",
                "perturbation": kind,
                "param_name": name,
                "param_value": val,
                **m,
            }
        )

    # 名义（与默认 data 一致）
    d0 = _clone_data(base)
    prob, ctx, m = run_one(
        d0,
        carbon_price=carbon_price,
        use_grid_mutex=use_grid_mutex,
        enforce_ev_limit=enforce_ev_limit,
        time_limit_s=time_limit_s,
        gap_rel=gap_rel,
        quiet=quiet,
    )
    add_row("nominal", "baseline_nominal", 1.0, d0, m)

    # 购电价倍率
    for s in (0.95, 1.05):
        d = _clone_data(base)
        d["buy_price"] = base_buy * s
        prob, ctx, m = run_one(
            d,
            carbon_price=carbon_price,
            use_grid_mutex=use_grid_mutex,
            enforce_ev_limit=enforce_ev_limit,
            time_limit_s=time_limit_s,
            gap_rel=gap_rel,
            quiet=quiet,
        )
        add_row("buy_price_scale", "buy_price_multiplier", s, d, m)

    # 碳价
    for c in (0.05, 0.12):
        if abs(c - carbon_price) < 1e-9:
            continue
        d = _clone_data(base)
        prob, ctx, m = run_one(
            d,
            carbon_price=c,
            use_grid_mutex=use_grid_mutex,
            enforce_ev_limit=enforce_ev_limit,
            time_limit_s=time_limit_s,
            gap_rel=gap_rel,
            quiet=quiet,
        )
        add_row("carbon_price", "carbon_price_cny_per_kwh_co2", c, d, m)

    # 弃光惩罚
    for pc in (0.35, 0.75):
        d = _clone_data(base)
        d["penalty_curtail_per_kwh"] = pc
        prob, ctx, m = run_one(
            d,
            carbon_price=carbon_price,
            use_grid_mutex=use_grid_mutex,
            enforce_ev_limit=enforce_ev_limit,
            time_limit_s=time_limit_s,
            gap_rel=gap_rel,
            quiet=quiet,
        )
        add_row("penalty_curtail", "penalty_curtail_per_kwh", pc, d, m)

    # 建筑移位/恢复线性惩罚
    for ps in (0.01, 0.04):
        d = _clone_data(base)
        d["penalty_shift_linear_cny_per_kw"] = ps
        prob, ctx, m = run_one(
            d,
            carbon_price=carbon_price,
            use_grid_mutex=use_grid_mutex,
            enforce_ev_limit=enforce_ev_limit,
            time_limit_s=time_limit_s,
            gap_rel=gap_rel,
            quiet=quiet,
        )
        add_row("penalty_shift", "penalty_shift_linear_cny_per_kw", ps, d, m)

    # 储能退化单价
    base_deg = float(base["ess"]["degradation_cost_cny_per_kwh"])
    for mult in (0.5, 2.0):
        d = _clone_data(base)
        d["ess"]["degradation_cost_cny_per_kwh"] = base_deg * mult
        prob, ctx, m = run_one(
            d,
            carbon_price=carbon_price,
            use_grid_mutex=use_grid_mutex,
            enforce_ev_limit=enforce_ev_limit,
            time_limit_s=time_limit_s,
            gap_rel=gap_rel,
            quiet=quiet,
        )
        add_row("ess_degradation_scale", "ess_degradation_multiplier", mult, d, m)

    return rows


def robustness_rows(
    base: dict[str, Any],
    *,
    carbon_price: float,
    use_grid_mutex: bool,
    enforce_ev_limit: bool,
    time_limit_s: int,
    gap_rel: float,
    quiet: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    factors = (0.94, 1.0, 1.06)
    for lm in factors:
        for pm in factors:
            d = _clone_data(base)
            for b in d["building_blocks"]:
                b["load"] = np.asarray(b["load"], dtype=float) * lm
            _recompute_total_native(d)
            d["pv_upper"] = np.asarray(d["pv_upper"], dtype=float) * pm
            prob, ctx, m = run_one(
                d,
                carbon_price=carbon_price,
                use_grid_mutex=use_grid_mutex,
                enforce_ev_limit=enforce_ev_limit,
                time_limit_s=time_limit_s,
                gap_rel=gap_rel,
                quiet=quiet,
            )
            rows.append(
                {
                    "analysis": "robustness_box",
                    "load_scale": lm,
                    "pv_scale": pm,
                    **m,
                }
            )
    return rows


def write_summary_md(
    path: Path,
    sens: pd.DataFrame,
    rob: pd.DataFrame,
    *,
    max_periods: int | None,
    carbon_nominal: float,
) -> None:
    lines = [
        "# 问题一：灵敏度分析与鲁棒检验摘要",
        "",
        f"- **求解范围**：时段数 `n = {max_periods if max_periods is not None else '全序列'}`（由 `--max-periods` 控制）。",
        f"- **名义碳价**（build_and_solve）：`{carbon_nominal}` 元/kgCO₂ 当量（与主脚本一致时可传 `--carbon-price`）。",
        "",
        "## 1. 灵敏度（单参数）",
        "",
        "对购电价整体倍率、碳价、弃光惩罚、建筑柔性线性惩罚、储能退化单价分别做一步扰动，其余保持名义值。",
        "",
    ]
    if not sens.empty:
        sub = sens.dropna(subset=["objective_recomputed"])
        if len(sub):
            ref = sub.loc[sub["perturbation"] == "nominal", "objective_recomputed"]
            ref_v = float(ref.iloc[0]) if len(ref) else float("nan")
            lines.append(f"- **名义重算目标**（元）：约 `{ref_v:.2f}`（以 `perturbation=nominal` 行为准）。")
            lines.append(
                f"- **目标值范围**（元）：`{sub['objective_recomputed'].min():.2f}` ~ `{sub['objective_recomputed'].max():.2f}`。"
            )
        lines.append("")
        lines.append("完整数据见 `problem1_sensitivity_oneway.csv`。以下为预览：")
        lines.append("")
        lines.append("```")
        lines.append(sens.head(20).to_string(index=False))
        lines.append("```")
    lines.extend(["", "## 2. 鲁棒性（负荷 × 光伏离散盒）", ""])
    lines.append("对每栋建筑负荷与 `pv_upper` 同步按比例缩放，考察最优目标与购电能量的波动。")
    lines.append("")
    if not rob.empty:
        ok = rob[rob["solver_status"] == "Optimal"]
        if len(ok) and ok["objective_recomputed"].notna().any():
            o = ok["objective_recomputed"].astype(float)
            g = ok["grid_import_energy_kwh"].astype(float)
            lines.append(f"- **可行情景数**（Optimal）：{len(ok)} / {len(rob)}。")
            lines.append(
                f"- **重算目标**：均值 `{o.mean():.2f}` 元，标准差 `{o.std():.4f}`，极差 `{o.max() - o.min():.2f}` 元。"
            )
            lines.append(
                f"- **购电能量（kWh）**：均值 `{g.mean():.2f}`，极差 `{g.max() - g.min():.2f}`。"
            )
        lines.append("")
        lines.append("完整数据见 `problem1_robustness_scenarios.csv`。以下为预览：")
        lines.append("")
        lines.append("```")
        lines.append(rob.head(20).to_string(index=False))
        lines.append("```")
    lines.extend(
        [
            "",
            "## 3. 问题二补充说明",
            "",
            "退化权重对角扫描已单独由 `code/python/problem_2/run_problem2_weight_scan.py` 驱动，"
            "属于问题二的**权重灵敏度**；本脚本聚焦问题一全周协同主模型。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="问题一灵敏度与鲁棒离散扫描")
    ap.add_argument("--repo-root", type=Path, default=_REPO)
    ap.add_argument("--max-periods", type=int, default=None)
    ap.add_argument("--time-limit", type=int, default=240, help="CBC 单案时间上限（秒）")
    ap.add_argument("--gap-rel", type=float, default=0.02)
    ap.add_argument("--carbon-price", type=float, default=0.0)
    ap.add_argument("--no-grid-mutex", action="store_true")
    ap.add_argument("--no-ev-limit", action="store_true", help="关闭 EV 并发/桩数整数约束以加速")
    ap.add_argument("--quiet-cbc", action="store_true")
    ap.add_argument(
        "--mode",
        choices=("both", "sensitivity-only", "robustness-only"),
        default="both",
    )
    args = ap.parse_args()
    repo = args.repo_root.resolve()

    try:
        data = load_problem_data(
            repo,
            args.max_periods,
            skip_infeasible=True,
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 2

    use_mutex = not args.no_grid_mutex
    ev_limit = not args.no_ev_limit

    sens_list: list[dict[str, Any]] = []
    rob_list: list[dict[str, Any]] = []

    if args.mode in ("both", "sensitivity-only"):
        sens_list = sensitivity_rows(
            data,
            carbon_price=float(args.carbon_price),
            use_grid_mutex=use_mutex,
            enforce_ev_limit=ev_limit,
            time_limit_s=int(args.time_limit),
            gap_rel=float(args.gap_rel),
            quiet=bool(args.quiet_cbc),
        )
    if args.mode in ("both", "robustness-only"):
        rob_list = robustness_rows(
            data,
            carbon_price=float(args.carbon_price),
            use_grid_mutex=use_mutex,
            enforce_ev_limit=ev_limit,
            time_limit_s=int(args.time_limit),
            gap_rel=float(args.gap_rel),
            quiet=bool(args.quiet_cbc),
        )

    out_dir = repo / "results" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    sens_df = pd.DataFrame(sens_list)
    rob_df = pd.DataFrame(rob_list)
    if not sens_df.empty:
        sens_df.to_csv(out_dir / "problem1_sensitivity_oneway.csv", index=False, encoding="utf-8-sig")
        print(out_dir / "problem1_sensitivity_oneway.csv")
    if not rob_df.empty:
        rob_df.to_csv(out_dir / "problem1_robustness_scenarios.csv", index=False, encoding="utf-8-sig")
        print(out_dir / "problem1_robustness_scenarios.csv")

    md_p = out_dir / "problem1_sensitivity_robustness_summary.md"
    write_summary_md(md_p, sens_df, rob_df, max_periods=args.max_periods, carbon_nominal=float(args.carbon_price))
    print(md_p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
