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

# (CSV 中 cost_item 英文键名, dict 内键) — CSV 保持英文以便程序读取
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

# 论文展示用中文名称（与 CSV 中英文 cost_item 一一对应）
COST_ITEM_LABEL_ZH: dict[str, str] = {
    "Grid import cost": "电网购电成本",
    "Grid export revenue": "电网售电收益",
    "PV curtailment penalty": "光伏弃电惩罚成本",
    "Load shed penalty": "未供电惩罚成本",
    "Building shift penalty": "建筑柔性调节补偿成本",
    "ESS degradation cost": "储能退化成本",
    "EV degradation cost": "电动汽车电池退化成本",
    "Carbon cost": "碳排放成本",
    "Objective affine constant": "目标函数常数项",
    "Objective from solver": "最优目标函数值",
    "Objective recomputed from solution": "解后重算目标值",
    "Objective shown in CBC log style": "按 CBC 日志口径的目标值",
}


def cost_item_label_zh(english_label: str) -> str:
    return COST_ITEM_LABEL_ZH.get(english_label, english_label)


def _ratio_display(baseline_val: float, coord_val: float, *, decimals: int) -> str:
    """相对改善率展示：基线为 0 时无意义。"""
    if abs(baseline_val) < 1e-12:
        return "—"
    return f"{(baseline_val - coord_val) / baseline_val:.{decimals}f}"


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


def write_reconciliation_zh_markdown(
    md_path: Path,
    costs: Mapping[str, float],
    *,
    title: str,
    subtitle: str,
    decimals: int = 6,
) -> Path:
    """全周对账表中文 Markdown（与同名 CSV 配套，不改变 CSV 英文键名）。"""
    md_path = md_path.resolve()
    md_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        subtitle,
        "",
        "下表金额单位均为 **元**；分项定义与协同调度主模型目标函数及解后重算口径一致。",
        "",
        "| 成本项 | 金额（元） |",
        "| --- | ---: |",
    ]
    for en_label, key in COST_ITEM_ROWS:
        zh = cost_item_label_zh(en_label)
        val = round(float(costs[key]), decimals)
        lines.append(f"| {zh} | {val} |")
    lines.append("")
    lines.extend(
        [
            "## 说明",
            "",
            "协同调度模型由 PuLP/CBC 求解时，**最优目标函数值**含目标仿射表达式中的常数项（上表「目标函数常数项」）。"
            "CBC 控制台打印的 Objective value 可能不包含该常数项，故与「按 CBC 日志口径的目标值」存在固定差额；"
            "论文中报告完整目标时，应以 **最优目标函数值** 为准。",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def write_reconciliation_csv(
    path: Path,
    costs: Mapping[str, float],
    *,
    decimals: int = 6,
    zh_title: str | None = None,
    zh_subtitle: str | None = None,
) -> tuple[Path, Path | None]:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    costs_dict_to_reconciliation_df(costs, decimals=decimals).to_csv(path, index=False, encoding="utf-8-sig")
    md_path: Path | None = None
    if zh_title is not None:
        md_path = path.with_suffix(".md").resolve()
        write_reconciliation_zh_markdown(
            md_path,
            costs,
            title=zh_title,
            subtitle=zh_subtitle or "本表对应全周（672 个 15 min 时段）优化或仿真结果。",
            decimals=decimals,
        )
    return path, md_path


def write_cost_comparison_csv_md(
    coordinated: Mapping[str, float],
    baseline: Mapping[str, float],
    *,
    csv_path: Path,
    md_path: Path,
    decimals: int = 6,
) -> tuple[Path, Path]:
    """生成协同 vs baseline 对比表（delta = baseline − coordinated）；CSV 列名保持英文。"""
    rows = []
    for label, key in COST_ITEM_ROWS:
        c = float(coordinated[key])
        b = float(baseline[key])
        delta = b - c
        ratio_str = _ratio_display(b, c, decimals=decimals)
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
        "# 全周成本分项对比（协同调度 vs 基线）",
        "",
        "本表基于全周（672 个 15 min 时段）协同优化最优解与基线规则仿真结果，对目标函数各经济分项进行同一口径汇总与对比。"
        "金额单位均为 **元**。",
        "",
        "## 目标函数在论文中的写法",
        "",
        "- **协同调度模型**：正文中的「最优目标函数值」应取 **最优目标函数值**（即 PuLP 求得的完整仿射目标，含 **目标函数常数项**）。",
        "- **求解器日志**：CBC 控制台显示的数值可能不含上述常数项，故与完整最优值存在固定差额；可与 **按 CBC 日志口径的目标值** 对照，用于核对模型实现。",
        "- **基线模型**：无混合整数规划求解过程；表中 **最优目标函数值** 与 **解后重算目标值** 均按与协同模型一致的分项加总得到，常数项恒为零。"
        "需注意：基线原有 KPI 中的「总费用」若仅含购售电收支，则与本表「等价总成本」可能不一致，因本表另计退化、弃电惩罚、未供电惩罚等项。",
        "",
        "## 符号与列含义",
        "",
        "- **电网售电收益**列以正值表示售电收入；重算总目标时按 **减项** 计入（与模型中「负收益」一致）。",
        "- **差值（基线−协同）/元**：正值表示基线成本更高，即协同调度更优。",
        "- **相对改善率**：以基线分项为分母，计算（基线−协同）/基线；若基线该项为零，则相对率 **无意义**，表中记为「—」。",
        "- **未供电惩罚成本（基线）**：基线仅有聚合未供电功率，为与协同分项对齐，按柔性负荷参数表中 **未供电惩罚单价的最大值** 折算，不改变基线原有仅含购售电的核算口径。",
        "",
        "## 分项对比",
        "",
        "| 成本项 | 协同调度模型/元 | 基线模型/元 | 差值（基线−协同）/元 | 相对改善率 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for _, r in df.iterrows():
        zh = cost_item_label_zh(str(r["cost_item"]))
        ratio_md = str(r["improvement_ratio"])
        if ratio_md.upper() == "NA":
            ratio_md = "—"
        lines.append(
            f"| {zh} | {r['coordinated_model_yuan']} | {r['baseline_yuan']} | "
            f"{r['delta_baseline_minus_coordinated_yuan']} | {ratio_md} |"
        )
    coord_total = float(coordinated["objective_from_solver"])
    base_total = float(baseline["objective_from_solver"])
    delta_t = base_total - coord_total
    ratio_t = _ratio_display(base_total, coord_total, decimals=decimals)
    lines.extend(
        [
            "",
            "## 小结（可按需改写后纳入正文）",
            "",
            f"- 全周等价总成本：协同调度为 **{coord_total:.{decimals}f} 元**，基线为 **{base_total:.{decimals}f} 元**，"
            f"二者相差 **{delta_t:.{decimals}f} 元**（基线减协同）；相对改善率为 **{ratio_t}**（以基线总成本为分母）。",
            "- 机理分析建议：重点考察表中差值绝对值较大的分项（如购电成本、弃电惩罚、未供电惩罚、各类退化成本等），并与功率时序图、事件窗口图相互印证。",
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
    """附录 CSV：列名为中文「成本项」「金额（元）」，行内成本项为中文（英文键仍保留于程序逻辑）。"""
    rows = []
    for en_label, key in COST_ITEM_ROWS:
        rows.append({"成本项": cost_item_label_zh(en_label), "金额（元）": f"{float(costs[key]):.{decimals}f}"})
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
        "# 目标函数分项对账表（附录）",
        "",
        "分项定义与协同调度模型目标函数及解后重算口径一致；金额单位为元。",
        "",
        "| 成本项 | 金额（元） |",
        "| --- | ---: |",
    ]
    for _, r in df.iterrows():
        item = str(r["成本项"]).replace("|", "\\|")
        val = str(r["金额（元）"])
        lines.append(f"| {item} | {val} |")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path.resolve(), md_path.resolve()
