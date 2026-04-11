"""
问题 1：协同 MILP 与 baseline 的「目标分项」统一对账与对比输出。

- 与 `p_1_5_ultimate.build_and_solve` 中目标函数各项系数、正负号一致；
- baseline 无 PuLP 目标时：`objective_affine_constant=0`，`objective_from_solver` 取与重算一致的等价总成本；
- 金额单位：元。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import pulp

# 须与 p_1_5_ultimate.build_and_solve 中定义一致
PENALTY_CURTAIL = 0.5
PENALTY_SHIFT = 0.02

# (CSV/Markdown 行名, dict 键)
COST_ITEM_ROWS: list[tuple[str, str]] = [
    ("Grid import cost", "grid_import_cost"),
    ("Grid export revenue", "grid_export_revenue"),
    ("PV curtailment penalty", "pv_curtail_penalty"),
    ("Load shed penalty", "load_shed_penalty"),
    ("Building shift penalty", "building_shift_penalty"),
    ("ESS degradation cost", "ess_degradation_cost"),
    ("EV degradation cost", "ev_degradation_cost"),
    ("Carbon cost", "carbon_cost"),
    ("Objective affine constant", "objective_affine_constant"),
    ("Objective from solver", "objective_from_solver"),
    ("Objective recomputed from solution", "objective_recomputed_from_solution"),
    ("Objective shown in CBC log style", "objective_cbc_log_style"),
]


def var_float(x: pulp.LpVariable) -> float:
    v = x.varValue
    return float(v) if v is not None else 0.0


def summarize_coordinated_costs(prob: pulp.LpProblem, data: dict[str, Any], ctx: dict[str, Any]) -> dict[str, float]:
    """协同模型：分项 + pulp.value(prob.objective) + 仿射常数与 CBC 风格目标。"""
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    carbon_price = float(ctx["carbon_price"])
    ess = ctx["ess"]
    buildings: list[dict[str, Any]] = ctx["buildings"]
    ev_sessions: list[dict[str, Any]] = ctx["ev_sessions"]
    ev_ts_by_i: dict[int, list[int]] = ctx["ev_ts_by_i"]

    P_buy = ctx["P_buy"]
    P_sell = ctx["P_sell"]
    P_pv_use = ctx["P_pv_use"]
    P_ess_ch = ctx["P_ess_ch"]
    P_ess_dis = ctx["P_ess_dis"]
    P_shift_out = ctx["P_shift_out"]
    P_recover = ctx["P_recover"]
    P_shed = ctx["P_shed"]
    P_ev_ch = ctx["P_ev_ch"]
    P_ev_dis = ctx["P_ev_dis"]

    grid_import_cost = 0.0
    grid_export_revenue = 0.0
    carbon_cost = 0.0
    pv_curtail_penalty = 0.0
    ess_degradation_cost = 0.0
    for t in T:
        pb, psell, ppu = var_float(P_buy[t]), var_float(P_sell[t]), var_float(P_pv_use[t])
        grid_import_cost += float(data["buy_price"][t]) * pb * dt
        grid_export_revenue += float(data["sell_price"][t]) * psell * dt
        carbon_cost += carbon_price * float(data["grid_carbon"][t]) * pb * dt
        pv_curtail_penalty += PENALTY_CURTAIL * (float(data["pv_upper"][t]) - ppu) * dt
        ess_degradation_cost += float(ess["degradation_cost_cny_per_kwh"]) * (
            var_float(P_ess_ch[t]) + var_float(P_ess_dis[t])
        ) * dt / 2

    building_shift_penalty = 0.0
    load_shed_penalty = 0.0
    for b in buildings:
        name = b["name"]
        for t in T:
            key = (name, t)
            building_shift_penalty += PENALTY_SHIFT * (var_float(P_shift_out[key]) + var_float(P_recover[key])) * dt
            load_shed_penalty += float(b["penalty_not_served"]) * var_float(P_shed[key]) * dt

    ev_degradation_cost = 0.0
    for i, ev in enumerate(ev_sessions):
        for t in ev_ts_by_i.get(i, []):
            k = (i, t)
            if k in P_ev_ch:
                ev_degradation_cost += float(ev["deg_cost"]) * (
                    var_float(P_ev_ch[k]) + var_float(P_ev_dis[k])
                ) * dt / 2

    objective_recomputed_from_solution = (
        grid_import_cost
        - grid_export_revenue
        + carbon_cost
        + pv_curtail_penalty
        + ess_degradation_cost
        + building_shift_penalty
        + load_shed_penalty
        + ev_degradation_cost
    )

    objective_from_solver = float(pulp.value(prob.objective))
    affine_const = float(getattr(prob.objective, "constant", 0.0) or 0.0)
    objective_cbc_log_style = objective_from_solver - affine_const

    return {
        "grid_import_cost": grid_import_cost,
        "grid_export_revenue": grid_export_revenue,
        "pv_curtail_penalty": pv_curtail_penalty,
        "load_shed_penalty": load_shed_penalty,
        "building_shift_penalty": building_shift_penalty,
        "ess_degradation_cost": ess_degradation_cost,
        "ev_degradation_cost": ev_degradation_cost,
        "carbon_cost": carbon_cost,
        "objective_from_solver": objective_from_solver,
        "objective_affine_constant": affine_const,
        "objective_cbc_log_style": objective_cbc_log_style,
        "objective_recomputed_from_solution": objective_recomputed_from_solution,
    }


def costs_dict_to_reconciliation_df(costs: Mapping[str, float], *, decimals: int = 6) -> pd.DataFrame:
    rows = []
    for label, key in COST_ITEM_ROWS:
        rows.append({"cost_item": label, "value_yuan": round(float(costs[key]), decimals)})
    return pd.DataFrame(rows)


def write_reconciliation_csv(path: Path, costs: Mapping[str, float], *, decimals: int = 6) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    costs_dict_to_reconciliation_df(costs, decimals=decimals).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_cost_comparison_csv_md(
    coordinated: Mapping[str, float],
    baseline: Mapping[str, float],
    *,
    csv_path: Path,
    md_path: Path,
    decimals: int = 6,
) -> tuple[Path, Path]:
    """生成协同 vs baseline 对比表（delta = baseline − coordinated）。"""
    rows = []
    for label, key in COST_ITEM_ROWS:
        c = float(coordinated[key])
        b = float(baseline[key])
        delta = b - c
        if abs(b) < 1e-12:
            ratio_str = "NA"
        else:
            ratio_str = f"{(b - c) / b:.{decimals}f}"
        rows.append(
            {
                "cost_item": label,
                "coordinated_model_yuan": round(c, decimals),
                "baseline_yuan": round(b, decimals),
                "delta_baseline_minus_coordinated_yuan": round(delta, decimals),
                "improvement_ratio": ratio_str,
            }
        )
    df = pd.DataFrame(rows)
    csv_path = csv_path.resolve()
    md_path = md_path.resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    lines = [
        "# 协同模型 vs baseline：全周成本分项对比（正式版）",
        "",
        "本表基于 **672 个 15 min 时段** 的完整优化 horizon 与 baseline 仿真结果汇总，"
        "非 `max-periods` 截断的演示算例。若某侧 CSV 由短 horizon 生成，请勿与本文标题混用。",
        "",
        "## 论文中目标函数取值",
        "",
        "- **协同模型**：论文中的「最优目标函数值」应采用 **Objective from solver**（即 `pulp.value(prob.objective)`，"
        "含 PuLP 目标仿射表达式中的 **Objective affine constant** 项）。",
        "- **CBC 控制台**：`Objective value` 可能 **不含** 仿射常数项，仅用于与 **Objective shown in CBC log style** 对照调试。",
        "- **baseline**：无 MILP；表中 **Objective from solver** 与 **Objective recomputed from solution** 均取"
        "与协同模型 **同一分项口径** 加总得到的等价总成本（affine constant 恒为 0）。"
        "该项可与 baseline KPI 中仅含「购电−售电」的 `total_cost_cny` 不同，后者不含退化/弃光惩罚/未供电惩罚等。",
        "",
        "## 符号约定",
        "",
        "- **Grid export revenue** 列为正值表示售电收入；重算总目标时按 **减项** 处理（与 MILP 中 `-sell·P·Δt` 一致）。",
        "- **delta_baseline_minus_coordinated_yuan** = baseline − coordinated（正值表示 baseline 更高、协同更优）。",
        "- **improvement_ratio** = (baseline − coordinated) / baseline；baseline 分项为 0 时记 **NA**（避免除零）。",
        "- **Load shed penalty（baseline）**：非协同仿真仅有聚合 `unmet_load_kw`，无分建筑削减；"
        "为与协同分项对齐，按 `flexible_load_params_clean.csv` 中 **penalty_cny_per_kwh_not_served 的最大值** 乘以未供电量折算，"
        "不改变 baseline 既有 `total_cost_cny`（仅购售电）定义。",
        "",
        "## 分项对比表",
        "",
        "| cost_item | coordinated_model_yuan | baseline_yuan | delta_baseline_minus_coordinated_yuan | improvement_ratio |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['cost_item']} | {r['coordinated_model_yuan']} | {r['baseline_yuan']} | "
            f"{r['delta_baseline_minus_coordinated_yuan']} | {r['improvement_ratio']} |"
        )
    coord_total = float(coordinated["objective_from_solver"])
    base_total = float(baseline["objective_from_solver"])
    delta_t = base_total - coord_total
    ratio_t = "NA" if abs(base_total) < 1e-12 else f"{(delta_t / base_total):.{decimals}f}"
    lines.extend(
        [
            "",
            "## 简要结论（模板，可按结果改写）",
            "",
            f"- 全周等价总成本（分项重算口径）：协同 **{coord_total:.{decimals}f} 元**，baseline **{base_total:.{decimals}f} 元**，"
            f"差值 baseline−协同 **{delta_t:.{decimals}f} 元**，相对改善率 **{ratio_t}**（以 baseline 为分母）。",
            "- 主要贡献项：请对照表中 `delta_baseline_minus_coordinated_yuan` 绝对值较大的行"
            "（如购电成本、弃光惩罚、未供电惩罚、退化成本等）撰写机理分析。",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, md_path


def try_write_fullweek_comparison(repo_root: Path) -> tuple[Path, Path] | None:
    """若两侧全周对账 CSV 均存在，则写出对比表。"""
    root = repo_root.resolve()
    p_c = root / "results" / "tables" / "objective_reconciliation_fullweek.csv"
    p_b = root / "results" / "tables" / "objective_reconciliation_baseline_fullweek.csv"
    if not p_c.is_file() or not p_b.is_file():
        return None
    dc = pd.read_csv(p_c)
    db = pd.read_csv(p_b)
    coord = {str(r["cost_item"]): float(r["value_yuan"]) for _, r in dc.iterrows()}
    base = {str(r["cost_item"]): float(r["value_yuan"]) for _, r in db.iterrows()}
    # 转回内部键
    key_by_label = {label: key for label, key in COST_ITEM_ROWS}
    coord_k = {key_by_label[k]: v for k, v in coord.items()}
    base_k = {key_by_label[k]: v for k, v in base.items()}
    out_csv = root / "results" / "tables" / "objective_cost_comparison_fullweek.csv"
    out_md = root / "results" / "tables" / "objective_cost_comparison_fullweek.md"
    return write_cost_comparison_csv_md(coord_k, base_k, csv_path=out_csv, md_path=out_md)


def appendix_rows_zh(costs: Mapping[str, float], *, decimals: int = 4) -> pd.DataFrame:
    """附录用两列表（项 / 数值（元）），与历史脚本列名兼容。"""
    rows = []
    for label, key in COST_ITEM_ROWS:
        rows.append({"项": label, "数值（元）": f"{float(costs[key]):.{decimals}f}"})
    return pd.DataFrame(rows)


def write_appendix_reconciliation_files(
    costs: Mapping[str, float],
    *,
    csv_path: Path,
    md_path: Path,
    decimals: int = 4,
) -> tuple[Path, Path]:
    df = appendix_rows_zh(costs, decimals=decimals)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    lines = [
        "# 目标函数分项对账表（附录 / 补充材料）",
        "",
        "分项口径见 `objective_reconciliation.py` 与 `p_1_5_ultimate` 目标函数定义。",
        "",
        "| 项 | 数值（元） |",
        "| --- | ---: |",
    ]
    for _, r in df.iterrows():
        item = str(r["项"]).replace("|", "\\|")
        val = str(r["数值（元）"])
        lines.append(f"| {item} | {val} |")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path.resolve(), md_path.resolve()
