# -*- coding: utf-8 -*-
r"""
问题2 兼顾运行成本与电池寿命损耗的协同调度模型 (Lifecycle Coordinated Model)

功能概要
--------
- 运行成本 + 可调权重的 ESS/EV 吞吐退化成本；
- 购售电互斥、V2B 会话内充放互斥（与问题 1 口径对齐）；
- 单点求解 / 对角权重扫描、目标分项与运行指标导出（CSV/JSON）；
- 可选：读 ``problem2_ev_type_summary.csv`` 按车型覆盖/缩放 ``deg_cost``；可选仅指定车型允许 V2B 放电。

已知建模近似与改进方向（评审收口）
--------------------------------
1. **寿命损耗线性化**：ESS/EV 目标项为「吞吐功率 × 线性单价」近似（``deg_cost`` / ESS 退化系数），
   未引入循环深度、温度、DOD 分布等非线性老化；论文中应明确为保守上界或一阶经济惩罚项。
2. **建筑柔性「恢复」**：``E_backlog`` 为移峰未用电量的 backlog；``P_recover`` 以 ``rebound_factor`` 折减
   计入 backlog 清偿（与问题 1 一致）。若正文难解释，可在附录给出状态方程与 ``rebound_factor`` 含义。
3. **MILP 规模与 CBC**：时段数 ×（二元互斥 + EV 在网键）影响分支定界压力；全周 + 多扫描点建议
   ``--gap-rel 0.02~0.05``、``--scan-no-timeseries`` 或 ``--max-periods`` 截断试算后再全模型。
4. **充电桩并发**：本脚本未纳入问题 1.5 的桩数并发 0-1 族；若与现场严格一致需后续移植。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pulp

# 复用问题1：将 problem_1 置于 path 最前
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_PROBLEM1_DIR = (_HERE.parent / "problem_1").resolve()
if _PROBLEM1_DIR.is_dir() and str(_PROBLEM1_DIR) not in sys.path:
    sys.path.insert(0, str(_PROBLEM1_DIR))

try:
    import objective_reconciliation as obr
    from p_1_5_ultimate import extract_solution_timeseries, load_problem_data
except ImportError as exc:
    print(
        "无法导入问题1模块（objective_reconciliation / p_1_5_ultimate）。\n"
        f"  期望目录存在: {_PROBLEM1_DIR}\n"
        f"  原始错误: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from p_2_ev_type_policy import (
        apply_deg_cost_from_type_summary,
        fork_data_for_ev_policies,
        load_type_summary_deg_map,
        restrict_v2b_discharge_to_types,
    )
except ImportError as exc:
    print(f"无法导入 p_2_ev_type_policy: {exc}", file=sys.stderr)
    sys.exit(1)

# 与 objective_reconciliation / p_1_5_ultimate 一致
PENALTY_CURTAIL = obr.PENALTY_CURTAIL
PENALTY_SHIFT = obr.PENALTY_SHIFT


def _utc_run_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def validate_cli_args(args: argparse.Namespace) -> int | None:
    """返回 None 表示通过；否则为退出码。"""
    if args.gap_rel <= 0 or args.gap_rel > 1.0:
        print("--gap-rel 应在 (0, 1] 内，例如 0.01~0.05。", file=sys.stderr)
        return 1
    if args.time_limit <= 0:
        print("--time-limit 须为正整数（秒）。", file=sys.stderr)
        return 1
    if args.ess_deg_weight < 0 or args.ev_deg_weight < 0:
        print("警告: 退化权重为负将改变目标凸性含义，请确认是有意为之。", file=sys.stderr)
    return None


def warn_heavy_model_instance(data: dict[str, Any], args: argparse.Namespace) -> None:
    """数据加载后提示规模与求解建议（不写 stderr 为错误）。"""
    n = int(data["n"])
    n_ev = len(data.get("ev_sessions", []))
    use_gm = not args.no_grid_mutex
    n_bin_grid = n if use_gm else 0
    # 粗略：每在网 V2B 时段一个 U_ev（上界）
    n_ev_bin = 0
    for ev in data.get("ev_sessions", []):
        if int(ev.get("v2b_allowed", 0)):
            n_ev_bin += len(ev.get("park_ts", []))
    if n > 500 and args.gap_rel < 0.02:
        print(
            f"提示: 时段数 n={n} 较大且 gap_rel={args.gap_rel} 偏紧，CBC 可能耗时；"
            f"可试 --gap-rel 0.03 或先 --max-periods 截断。",
            file=sys.stderr,
        )
    if n_ev > 0:
        print(
            f"模型规模提示: n={n}, EV 会话数={n_ev}, 约 U_grid={n_bin_grid} + U_ess={n} + U_ev≈{n_ev_bin} 个二进制变量量级。",
            file=sys.stderr,
        )


def ensure_problem2_layout(base: Path) -> None:
    """创建 results/problem2_lifecycle 下建议子目录。"""
    for sub in ("single_run", "scans", "figures", "tables"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def status_label(prob: pulp.LpProblem) -> str:
    return str(pulp.LpStatus.get(prob.status, prob.status))


def solution_is_usable(prob: pulp.LpProblem) -> bool:
    """
    若 CBC 在 gap 内停止，PuLP 常仍为 Optimal；若为其它状态但目标值可读，
    仍允许导出（便于论文记录次优可行解）。
    """
    st = prob.status
    if st == pulp.LpStatusOptimal:
        return True
    if st in (pulp.LpStatusInfeasible, pulp.LpStatusUnbounded):
        return False
    try:
        v = pulp.value(prob.objective)
        return v is not None and np.isfinite(float(v))
    except Exception:
        return False


def _matrix_col_to_ev_index(matrix_col: str) -> int:
    s = str(matrix_col).strip()
    if s.lower().startswith("ev_"):
        return int(s.split("_", 1)[1])
    raise ValueError(f"无法解析 matrix_col: {matrix_col!r}")


def enrich_ev_sessions_with_ev_type(repo_root: Path, ev_sessions: list[dict[str, Any]]) -> None:
    """
    从 final_model_inputs 的 EV 会话表合并车型字段（不修改 load_problem_data，保持兼容）。
    列名兼容：ev_type / vehicle_type / type。
    """
    inputs_dir = repo_root / "data" / "processed" / "final_model_inputs"
    candidates = [
        inputs_dir / "ev_sessions_model_ready.csv",
        inputs_dir / "ev_sessions_indexed.csv",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    type_col: str | None = None
    if path is not None:
        df = pd.read_csv(path, nrows=0)
        for c in df.columns:
            cl = c.lower()
            if cl in ("ev_type", "vehicle_type", "type"):
                type_col = c
                break
        if type_col is not None:
            df = pd.read_csv(path, usecols=["ev_index", type_col])
            idx_to_type = dict(zip(df["ev_index"].astype(int), df[type_col].astype(str)))

            def _norm_type(raw: str) -> str:
                t = str(raw).strip()
                if not t or t.lower() == "nan":
                    return "unknown"
                if t.lower() == "suv":
                    return "SUV"
                return t

            for ev in ev_sessions:
                try:
                    k = _matrix_col_to_ev_index(str(ev.get("matrix_col", "")))
                except (ValueError, KeyError, TypeError):
                    ev["ev_type"] = "unknown"
                    continue
                raw = idx_to_type.get(k, "unknown")
                ev["ev_type"] = _norm_type(raw)
            return

    for ev in ev_sessions:
        ev.setdefault("ev_type", "unknown")


def build_and_solve_p2(
    data: dict[str, Any],
    *,
    carbon_price: float = 0.0,
    ess_deg_weight: float = 1.0,
    ev_deg_weight: float = 1.0,
    use_grid_mutex: bool = True,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
    solver_msg: bool = True,
) -> tuple[pulp.LpProblem, float | None, dict[str, Any] | None]:
    """构建并求解问题2 MILP；solve_ctx 在存在可用解时返回（未必仅 Optimal）。"""
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    ess, buildings, ev_sessions = data["ess"], data["building_blocks"], data["ev_sessions"]

    prob = pulp.LpProblem("Microgrid_Problem2_Lifecycle", pulp.LpMinimize)

    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_pv_use = pulp.LpVariable.dicts("P_pv_use", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)
    U_grid_buy = pulp.LpVariable.dicts("U_grid_buy", T, cat=pulp.LpBinary) if use_grid_mutex else None

    BT = [(b["name"], t) for b in buildings for t in T]
    P_shift_out = pulp.LpVariable.dicts("P_shift_out", BT, lowBound=0)
    P_recover = pulp.LpVariable.dicts("P_recover", BT, lowBound=0)
    P_shed = pulp.LpVariable.dicts("P_shed", BT, lowBound=0)
    E_backlog = pulp.LpVariable.dicts("E_backlog", BT, lowBound=0)

    ev_keys: list[tuple[int, int]] = []
    ev_keys_by_t: dict[int, list[tuple[int, int]]] = defaultdict(list)
    ev_ts_by_i: dict[int, list[int]] = {}
    for i, ev in enumerate(ev_sessions):
        ev_ts_by_i[i] = sorted(ev["park_ts"])
        for t in ev_ts_by_i[i]:
            key = (i, t)
            ev_keys.append(key)
            ev_keys_by_t[t].append(key)

    if ev_keys:
        P_ev_ch = pulp.LpVariable.dicts("P_ev_ch", ev_keys, lowBound=0)
        P_ev_dis = pulp.LpVariable.dicts("P_ev_dis", ev_keys, lowBound=0)
        E_ev = pulp.LpVariable.dicts("E_ev", ev_keys, lowBound=0)
    else:
        P_ev_ch, P_ev_dis, E_ev = {}, {}, {}

    # 仅对允许 V2B 的 (i,t) 引入充放互斥二进制变量
    ev_mutex_keys: list[tuple[int, int]] = []
    for i, ev in enumerate(ev_sessions):
        if not int(ev.get("v2b_allowed", 0)):
            continue
        for t in ev_ts_by_i[i]:
            ev_mutex_keys.append((i, t))
    U_ev_ch: dict[tuple[int, int], Any] = {}
    if ev_mutex_keys:
        U_ev_ch = pulp.LpVariable.dicts("U_ev_ch", ev_mutex_keys, cat=pulp.LpBinary)

    obj_terms: list[Any] = []
    for t in T:
        obj_terms.append(data["buy_price"][t] * P_buy[t] * dt)
        obj_terms.append(-data["sell_price"][t] * P_sell[t] * dt)
        obj_terms.append(carbon_price * data["grid_carbon"][t] * P_buy[t] * dt)
        obj_terms.append(PENALTY_CURTAIL * (data["pv_upper"][t] - P_pv_use[t]) * dt)
        # ESS 退化：与 EV 相同为线性吞吐惩罚（半周转 dt/2），权重 ess_deg_weight。
        ess_deg_cost = float(ess["degradation_cost_cny_per_kwh"]) * float(ess_deg_weight)
        obj_terms.append(ess_deg_cost * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2)

    for b in buildings:
        for t in T:
            obj_terms.append(PENALTY_SHIFT * (P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)]) * dt)
            obj_terms.append(b["penalty_not_served"] * P_shed[(b["name"], t)] * dt)

    # EV 退化：会话级线性吞吐单价 × 权重（半周转计权 dt/2）；非循环老化模型。
    for i, ev in enumerate(ev_sessions):
        ev_deg_cost = float(ev["deg_cost"]) * float(ev_deg_weight)
        for t in ev_ts_by_i[i]:
            if ev_keys:
                obj_terms.append(ev_deg_cost * (P_ev_ch[(i, t)] + P_ev_dis[(i, t)]) * dt / 2)

    prob += pulp.lpSum(obj_terms)

    for t in T:
        served_load = pulp.lpSum(
            b["load"][t] - P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)] - P_shed[(b["name"], t)]
            for b in buildings
        )
        ev_ch_t = pulp.lpSum(P_ev_ch[k] for k in ev_keys_by_t[t]) if ev_keys_by_t[t] else 0
        ev_dis_t = pulp.lpSum(P_ev_dis[k] for k in ev_keys_by_t[t]) if ev_keys_by_t[t] else 0

        prob += P_pv_use[t] + P_buy[t] + P_ess_dis[t] + ev_dis_t == served_load + P_sell[t] + P_ess_ch[t] + ev_ch_t, f"Bal_{t}"
        prob += P_pv_use[t] <= data["pv_upper"][t]

        if use_grid_mutex and U_grid_buy is not None:
            prob += P_buy[t] <= data["p_imp_max"][t] * U_grid_buy[t]
            prob += P_sell[t] <= data["p_exp_max"][t] * (1 - U_grid_buy[t])
        else:
            prob += P_buy[t] <= data["p_imp_max"][t]
            prob += P_sell[t] <= data["p_exp_max"][t]

        prob += P_ess_ch[t] <= ess["max_charge_power_kw"] * U_ess_ch[t]
        prob += P_ess_dis[t] <= ess["max_discharge_power_kw"] * (1 - U_ess_ch[t])
        if t == 0:
            prob += E_ess[t] == ess["initial_energy_kwh"] + (
                ess["charge_efficiency"] * P_ess_ch[t] - P_ess_dis[t] / ess["discharge_efficiency"]
            ) * dt
        else:
            prob += E_ess[t] == E_ess[t - 1] + (
                ess["charge_efficiency"] * P_ess_ch[t] - P_ess_dis[t] / ess["discharge_efficiency"]
            ) * dt
        prob += E_ess[t] >= ess["min_energy_kwh"]
        prob += E_ess[t] <= ess["max_energy_kwh"]

    prob += E_ess[n - 1] >= ess["initial_energy_kwh"], "Terminal_SOC"

    # --- 建筑柔性（与 p_1_5_ultimate 同源）---
    # flex_cap：本时段可中断/可移部分的上界（与不可中断负荷比例有关）。
    # P_shift_out：从「等效基线负荷」中移出的功率（削填）；P_shed：削减；P_recover：回补功率。
    # E_backlog：尚未被 P_recover「清偿」的移出能量累积（kWh）；恢复项进入 backlog 时除以 rebound_factor，
    #   表示每 kW 的 P_recover 在一个时段内只清偿 1/rebound_factor 的 backlog（反弹越慢，rebound_factor 越大）。
    # 周期末 E_backlog=0：移出的负荷须在视界内被恢复机制消化，避免无限拖欠。
    for b in buildings:
        name = b["name"]
        rf = float(b["rebound_factor"])
        if rf < 1.0:
            raise ValueError(f"建筑块 {name!r} 的 rebound_factor={rf} < 1，与 backlog 动力学不兼容。")
        for t in T:
            flex_cap = max(0.0, (1 - b["noninterruptible_share"]) * b["load"][t])
            prob += P_shift_out[(name, t)] <= min(b["max_shiftable_kw"], flex_cap)
            prob += P_shed[(name, t)] <= min(b["max_sheddable_kw"], flex_cap)
            prob += P_shift_out[(name, t)] + P_shed[(name, t)] <= flex_cap
            prob += P_recover[(name, t)] <= rf * b["max_shiftable_kw"]
            if t == 0:
                prob += E_backlog[(name, t)] == P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / rf
            else:
                prob += E_backlog[(name, t)] == E_backlog[(name, t - 1)] + P_shift_out[(name, t)] * dt - P_recover[
                    (name, t)
                ] * dt / rf
        prob += E_backlog[(name, n - 1)] == 0

    for i, ev in enumerate(ev_sessions):
        ts = ev_ts_by_i[i]
        if not ts or not ev_keys:
            continue
        for pos, t in enumerate(ts):
            ch_lim = float(ev["charge_limits_kw"][t])
            dis_lim = float(ev["discharge_limits_kw"][t])
            v2b = int(ev.get("v2b_allowed", 0))

            if v2b and (i, t) in U_ev_ch:
                prob += P_ev_ch[(i, t)] <= ch_lim * U_ev_ch[(i, t)]
                prob += P_ev_dis[(i, t)] <= dis_lim * (1 - U_ev_ch[(i, t)])
            else:
                prob += P_ev_dis[(i, t)] == 0
                prob += P_ev_ch[(i, t)] <= ch_lim

            if pos == 0:
                prob += E_ev[(i, t)] == ev["initial_energy_kwh"] + (
                    ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]
                ) * dt
            else:
                prev_t = ts[pos - 1]
                if t != prev_t + 1:
                    raise ValueError(
                        f"EV {ev.get('session_id', i)} 在站时段非连续 (t={t}, prev={prev_t})，与 SOC 递推不兼容。"
                    )
                prob += E_ev[(i, t)] == E_ev[(i, prev_t)] + (
                    ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]
                ) * dt

            prob += E_ev[(i, t)] >= 0
            prob += E_ev[(i, t)] <= ev["battery_capacity_kwh"]
        prob += E_ev[(i, ts[-1])] >= ev["required_energy_kwh"]

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=solver_msg)
    prob.solve(solver)

    obj_val: float | None = None
    if solution_is_usable(prob):
        try:
            v = pulp.value(prob.objective)
            obj_val = float(v) if v is not None else None
        except (TypeError, ValueError):
            obj_val = None

    solve_ctx: dict[str, Any] | None = None
    if solution_is_usable(prob):
        solve_ctx = {
            "carbon_price": float(carbon_price),
            "PENALTY_CURTAIL": float(PENALTY_CURTAIL),
            "PENALTY_SHIFT": float(PENALTY_SHIFT),
            "ess_deg_weight": float(ess_deg_weight),
            "ev_deg_weight": float(ev_deg_weight),
            "use_grid_mutex": bool(use_grid_mutex),
            "P_buy": P_buy,
            "P_sell": P_sell,
            "P_pv_use": P_pv_use,
            "P_ess_ch": P_ess_ch,
            "P_ess_dis": P_ess_dis,
            "P_shift_out": P_shift_out,
            "P_recover": P_recover,
            "P_shed": P_shed,
            "P_ev_ch": P_ev_ch,
            "P_ev_dis": P_ev_dis,
            "ev_keys_by_t": ev_keys_by_t,
            "ev_ts_by_i": ev_ts_by_i,
            "ev_sessions": ev_sessions,
            "buildings": buildings,
            "ess": ess,
        }
    return prob, obj_val, solve_ctx


def compute_objective_breakdown(
    prob: pulp.LpProblem,
    data: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, float]:
    """
    按当前问题2目标系数重算分项，应与 pulp 目标值一致（数值误差 < 1e-4 量级）。
    """
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    ess = ctx["ess"]
    buildings: list[dict[str, Any]] = ctx["buildings"]
    ev_sessions: list[dict[str, Any]] = ctx["ev_sessions"]
    ev_ts_by_i: dict[int, list[int]] = ctx["ev_ts_by_i"]
    w_ess = float(ctx["ess_deg_weight"])
    w_ev = float(ctx["ev_deg_weight"])
    cprice = float(ctx["carbon_price"])

    grid_import_cost = 0.0
    grid_export_revenue = 0.0
    carbon_cost = 0.0
    pv_curtail_penalty = 0.0
    ess_degradation_cost = 0.0
    for t in T:
        pb = obr.var_float(ctx["P_buy"][t])
        ps = obr.var_float(ctx["P_sell"][t])
        ppu = obr.var_float(ctx["P_pv_use"][t])
        grid_import_cost += float(data["buy_price"][t]) * pb * dt
        grid_export_revenue += float(data["sell_price"][t]) * ps * dt
        carbon_cost += cprice * float(data["grid_carbon"][t]) * pb * dt
        pv_curtail_penalty += float(PENALTY_CURTAIL) * (float(data["pv_upper"][t]) - ppu) * dt
        pch = obr.var_float(ctx["P_ess_ch"][t])
        pdi = obr.var_float(ctx["P_ess_dis"][t])
        ess_degradation_cost += float(ess["degradation_cost_cny_per_kwh"]) * w_ess * (pch + pdi) * dt / 2

    building_shift_penalty = 0.0
    load_shed_penalty = 0.0
    for b in buildings:
        name = b["name"]
        for t in T:
            key = (name, t)
            building_shift_penalty += float(PENALTY_SHIFT) * (
                obr.var_float(ctx["P_shift_out"][key]) + obr.var_float(ctx["P_recover"][key])
            ) * dt
            load_shed_penalty += float(b["penalty_not_served"]) * obr.var_float(ctx["P_shed"][key]) * dt

    ev_degradation_cost = 0.0
    P_ev_ch = ctx["P_ev_ch"]
    P_ev_dis = ctx["P_ev_dis"]
    for i, ev in enumerate(ev_sessions):
        for t in ev_ts_by_i.get(i, []):
            k = (i, t)
            if k in P_ev_ch:
                ev_degradation_cost += float(ev["deg_cost"]) * w_ev * (
                    obr.var_float(P_ev_ch[k]) + obr.var_float(P_ev_dis[k])
                ) * dt / 2

    operation_cost = (
        grid_import_cost
        - grid_export_revenue
        + carbon_cost
        + pv_curtail_penalty
        + building_shift_penalty
        + load_shed_penalty
    )
    objective_recomputed = (
        operation_cost + ess_degradation_cost + ev_degradation_cost
    )
    try:
        objective_from_solver = float(pulp.value(prob.objective))
    except Exception:
        objective_from_solver = float("nan")

    return {
        "grid_import_cost": grid_import_cost,
        "grid_export_revenue": grid_export_revenue,
        "carbon_cost": carbon_cost,
        "pv_curtail_penalty": pv_curtail_penalty,
        "building_shift_penalty": building_shift_penalty,
        "load_shed_penalty": load_shed_penalty,
        "ess_degradation_cost": ess_degradation_cost,
        "ev_degradation_cost": ev_degradation_cost,
        "operation_cost": operation_cost,
        "objective_from_solver": objective_from_solver,
        "objective_recomputed": objective_recomputed,
        "objective_abs_gap": abs(objective_from_solver - objective_recomputed)
        if np.isfinite(objective_from_solver) and np.isfinite(objective_recomputed)
        else float("nan"),
    }


def compute_operational_metrics(data: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """能量/功率积分类运行指标（未单独建模支路功率则标注未启用）。"""
    n = data["n"]
    dt = data["delta_t"]
    T = range(n)

    grid_import_energy = sum(obr.var_float(ctx["P_buy"][t]) * dt for t in T)
    grid_export_energy = sum(obr.var_float(ctx["P_sell"][t]) * dt for t in T)
    pv_curtail_energy = sum(max(0.0, float(data["pv_upper"][t]) - obr.var_float(ctx["P_pv_use"][t])) * dt for t in T)

    ess_e_ch = sum(obr.var_float(ctx["P_ess_ch"][t]) * dt for t in T)
    ess_e_dis = sum(obr.var_float(ctx["P_ess_dis"][t]) * dt for t in T)
    ess_throughput = sum(
        (obr.var_float(ctx["P_ess_ch"][t]) + obr.var_float(ctx["P_ess_dis"][t])) * dt / 2 for t in T
    )

    ev_e_ch = 0.0
    ev_e_dis = 0.0
    P_ev_ch, P_ev_dis = ctx["P_ev_ch"], ctx["P_ev_dis"]
    for i, _ev in enumerate(ctx["ev_sessions"]):
        for t in ctx["ev_ts_by_i"].get(i, []):
            k = (i, t)
            if k not in P_ev_ch:
                continue
            ev_e_ch += obr.var_float(P_ev_ch[k]) * dt
            ev_e_dis += obr.var_float(P_ev_dis[k]) * dt
    ev_throughput = (ev_e_ch + ev_e_dis) / 2.0

    # 未供电量：本模型仅通过 P_shed 表示削减量（kWh），非拓扑潮流不可达
    unserved_model_note = (
        "当前目标含削减惩罚 P_shed（kWh 当量），无独立‘潮流不可达未供电’变量；"
        "若需支路未供电需扩展网络约束。"
    )
    load_shed_energy = 0.0
    for b in ctx["buildings"]:
        name = b["name"]
        for t in T:
            load_shed_energy += obr.var_float(ctx["P_shed"][(name, t)]) * dt

    return {
        "grid_import_energy_kwh": grid_import_energy,
        "grid_export_energy_kwh": grid_export_energy,
        "pv_curtail_energy_kwh": pv_curtail_energy,
        "ess_charge_energy_kwh": ess_e_ch,
        "ess_discharge_energy_kwh": ess_e_dis,
        "ess_throughput_kwh": ess_throughput,
        "ev_charge_energy_kwh": ev_e_ch,
        "ev_discharge_energy_kwh": ev_e_dis,
        "ev_throughput_kwh": ev_throughput,
        "load_shed_energy_kwh": load_shed_energy,
        "unserved_energy_note": unserved_model_note,
    }


def compute_ev_type_summary(
    data: dict[str, Any],
    ctx: dict[str, Any],
) -> pd.DataFrame:
    """按车型汇总充放、吞吐、退化货币量及 V2B 相关统计。"""
    dt = data["delta_t"]
    w_ev = float(ctx["ev_deg_weight"])
    P_ev_ch, P_ev_dis = ctx["P_ev_ch"], ctx["P_ev_dis"]
    ev_ts_by_i = ctx["ev_ts_by_i"]
    rows: list[dict[str, Any]] = []

    by_type: dict[str, list[int]] = defaultdict(list)
    for i, ev in enumerate(ctx["ev_sessions"]):
        et = str(ev.get("ev_type", "unknown"))
        by_type[et].append(i)

    for et, indices in sorted(by_type.items(), key=lambda x: x[0]):
        total_ch = 0.0
        total_dis = 0.0
        deg_cny = 0.0
        n_sess = len(indices)
        n_v2b_allowed = 0
        n_v2b_active = 0
        for i in indices:
            ev = ctx["ev_sessions"][i]
            if int(ev.get("v2b_allowed", 0)):
                n_v2b_allowed += 1
            any_dis = False
            for t in ev_ts_by_i.get(i, []):
                k = (i, t)
                if k not in P_ev_ch:
                    continue
                pch = obr.var_float(P_ev_ch[k])
                pdi = obr.var_float(P_ev_dis[k])
                total_ch += pch * dt
                total_dis += pdi * dt
                deg_cny += float(ev["deg_cost"]) * w_ev * (pch + pdi) * dt / 2
                if pdi > 1e-6:
                    any_dis = True
            if any_dis:
                n_v2b_active += 1
        throughput = (total_ch + total_dis) / 2.0
        v2b_allowed_share = (n_v2b_allowed / n_sess) if n_sess else 0.0
        rows.append(
            {
                "ev_type": et,
                "session_count": n_sess,
                "v2b_allowed_sessions": n_v2b_allowed,
                "v2b_active_sessions_discharge": n_v2b_active,
                "v2b_allowed_share": v2b_allowed_share,
                "total_charge_energy_kwh": total_ch,
                "total_discharge_energy_kwh": total_dis,
                "total_throughput_kwh": throughput,
                "total_ev_degradation_cost_cny": deg_cny,
            }
        )
    return pd.DataFrame(rows)


def _json_safe_numbers(d: dict[str, float]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for k, v in d.items():
        if isinstance(v, float) and not math.isfinite(v):
            out[k] = None
        else:
            out[k] = float(v) if isinstance(v, (int, float)) else None
    return out


def export_objective_breakdown_json_csv(out_dir: Path, breakdown: dict[str, float]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p_json = out_dir / "objective_breakdown.json"
    p_csv = out_dir / "objective_breakdown.csv"
    p_json.write_text(json.dumps(_json_safe_numbers(breakdown), indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(
        [{"metric": k, "value_yuan": float(v)} for k, v in breakdown.items()],
    ).to_csv(p_csv, index=False, encoding="utf-8-sig")
    return p_json, p_csv


def export_operational_metrics_json_csv(out_dir: Path, metrics: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p_json = out_dir / "operational_metrics.json"
    p_csv = out_dir / "operational_metrics.csv"
    p_json.write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    rows = []
    for k, v in metrics.items():
        rows.append({"metric": k, "value": v if isinstance(v, str) else float(v)})
    pd.DataFrame(rows).to_csv(p_csv, index=False, encoding="utf-8-sig")
    return p_json, p_csv


def export_ev_type_summary_json_csv(out_dir: Path, df: pd.DataFrame) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p_json = out_dir / "ev_type_summary.json"
    p_csv = out_dir / "ev_type_summary.csv"
    df.to_csv(p_csv, index=False, encoding="utf-8-sig")
    df.to_json(p_json, orient="records", force_ascii=False, indent=2)
    return p_json, p_csv


def export_results_single_run(
    *,
    out_dir: Path,
    data: dict[str, Any],
    prob: pulp.LpProblem,
    ctx: dict[str, Any],
    breakdown: dict[str, float],
    metrics: dict[str, Any],
    ev_type_df: pd.DataFrame,
    ts_df: pd.DataFrame | None,
    meta: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    export_objective_breakdown_json_csv(out_dir, breakdown)
    export_operational_metrics_json_csv(out_dir, metrics)
    export_ev_type_summary_json_csv(out_dir, ev_type_df)
    meta_path = out_dir / "run_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if ts_df is not None:
        ts_df.to_csv(out_dir / "timeseries.csv", index=False, encoding="utf-8-sig")


def _one_solve_export(
    repo_root: Path,
    data: dict[str, Any],
    *,
    ess_w: float,
    ev_w: float,
    carbon_price: float,
    use_grid_mutex: bool,
    time_limit_s: int,
    gap_rel: float,
    solver_msg: bool,
    out_dir: Path,
    write_timeseries: bool,
    ev_type_summary_csv: Path | None = None,
    ev_deg_summary_rule: str = "none",
    v2b_discharge_only_types: str | None = None,
) -> dict[str, Any]:
    """单次求解 + 导出；返回扫描表一行字典。"""
    work = fork_data_for_ev_policies(data)
    enrich_ev_sessions_with_ev_type(repo_root, work["ev_sessions"])

    if ev_type_summary_csv is not None and ev_deg_summary_rule not in ("none", ""):
        deg_map = load_type_summary_deg_map(ev_type_summary_csv.resolve())
        apply_deg_cost_from_type_summary(work["ev_sessions"], deg_map, rule=ev_deg_summary_rule)
        print(
            f"已应用车型汇总退化规则: csv={ev_type_summary_csv.name}, rule={ev_deg_summary_rule}",
            file=sys.stderr,
        )

    if v2b_discharge_only_types:
        allowed = {x.strip() for x in v2b_discharge_only_types.split(",") if x.strip()}
        if allowed:
            restrict_v2b_discharge_to_types(work["ev_sessions"], allowed)
            print(f"已限制可放电/V2B 车型为: {sorted(allowed)}", file=sys.stderr)

    prob, obj, ctx = build_and_solve_p2(
        work,
        carbon_price=carbon_price,
        ess_deg_weight=ess_w,
        ev_deg_weight=ev_w,
        use_grid_mutex=use_grid_mutex,
        time_limit_s=time_limit_s,
        gap_rel=gap_rel,
        solver_msg=solver_msg,
    )
    st_label = status_label(prob)
    print(f"求解状态: {prob.status} ({st_label})")

    if not solution_is_usable(prob) or ctx is None:
        print("无可行解或无法读取目标值，跳过导出。", file=sys.stderr)
        return {
            "ess_deg_weight": ess_w,
            "ev_deg_weight": ev_w,
            "solver_status": st_label,
            "objective_total": None,
            "error": "no_usable_solution",
        }

    breakdown = compute_objective_breakdown(prob, work, ctx)
    metrics = compute_operational_metrics(work, ctx)
    ev_df = compute_ev_type_summary(work, ctx)
    ts_df = extract_solution_timeseries(work, ctx) if write_timeseries else None

    meta = {
        "ess_deg_weight": ess_w,
        "ev_deg_weight": ev_w,
        "carbon_price": carbon_price,
        "use_grid_mutex": use_grid_mutex,
        "solver_status": st_label,
        "timestamp_utc": _utc_run_tag(),
        "ev_type_summary_csv": str(ev_type_summary_csv.resolve()) if ev_type_summary_csv else None,
        "ev_deg_summary_rule": ev_deg_summary_rule,
        "v2b_discharge_only_types": v2b_discharge_only_types,
    }
    export_results_single_run(
        out_dir=out_dir,
        data=work,
        prob=prob,
        ctx=ctx,
        breakdown=breakdown,
        metrics=metrics,
        ev_type_df=ev_df,
        ts_df=ts_df,
        meta=meta,
    )

    print("--- 目标分项（元，重算）---")
    for k in (
        "grid_import_cost",
        "grid_export_revenue",
        "carbon_cost",
        "pv_curtail_penalty",
        "building_shift_penalty",
        "load_shed_penalty",
        "ess_degradation_cost",
        "ev_degradation_cost",
        "operation_cost",
        "objective_from_solver",
        "objective_recomputed",
        "objective_abs_gap",
    ):
        v = breakdown.get(k)
        if isinstance(v, (int, float)) and np.isfinite(float(v)):
            print(f"  {k}: {float(v):.6f}")
        else:
            print(f"  {k}: {v}")
    print("--- 运行指标 ---")
    for k, v in metrics.items():
        if k == "unserved_energy_note":
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {float(v):.6f}")

    return {
        "ess_deg_weight": ess_w,
        "ev_deg_weight": ev_w,
        "solver_status": st_label,
        "objective_total": breakdown.get("objective_from_solver"),
        "objective_recomputed": breakdown.get("objective_recomputed"),
        "operation_cost": breakdown.get("operation_cost"),
        "ess_deg_cost": breakdown.get("ess_degradation_cost"),
        "ev_deg_cost": breakdown.get("ev_degradation_cost"),
        "ess_throughput": metrics.get("ess_throughput_kwh"),
        "ev_throughput": metrics.get("ev_throughput_kwh"),
        "grid_import_energy": metrics.get("grid_import_energy_kwh"),
        "grid_export_energy": metrics.get("grid_export_energy_kwh"),
        "pv_curtail_energy": metrics.get("pv_curtail_energy_kwh"),
    }


def main(argv: list[str] | None = None) -> int:
    epilog = r"""
关键参数与数据列（便于论文写「符号—数据」对照）
  carbon_price          乘 buy 功率与 timeseries 中 grid_carbon_kg_per_kwh → 碳项（元）
  ess_deg_weight        乘 ESS 基元退化单价 ess.degradation_cost_cny_per_kwh
  ev_deg_weight         乘各会话 ev.deg_cost（吞吐退化，元/kWh 半周转）
  rebound_factor        建筑 CSV：恢复功率对 backlog 的清偿效率（≥1，越大反弹越慢）
  noninterruptible_share 可移位/可削减负荷比例上界来源

大规模 / 权重扫描减负
  --scan-no-timeseries    扫描时不写每个 w 子目录下的 timeseries.csv（I/O 与磁盘明显减轻）
  --gap-rel 0.02~0.05     全周 + 多 w 时可略放 gap 换时间；正式表可仍用 0.01

示例
  python p_2_lifecycle_coordinated.py.code.py --max-periods 672 --gap-rel 0.03 --run-tag dev
  python p_2_lifecycle_coordinated.py.code.py --scan-weights 0 0.5 1 --scan-no-timeseries --gap-rel 0.04
"""
    parser = argparse.ArgumentParser(
        description="问题2：兼顾寿命损耗的协同调度（正式实验版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    g = parser.add_argument_group("目标与退化权重")
    g.add_argument("--ess-deg-weight", type=float, default=1.0, help="ESS 退化成本权重 λ_ESS（乘基元退化单价）")
    g.add_argument("--ev-deg-weight", type=float, default=1.0, help="EV 退化成本权重 λ_EV（乘各会话 deg_cost）")
    g.add_argument("--carbon-price", type=float, default=0.0, help="碳价 σ（元/kg 等），购电功率×碳强度×σ")

    g = parser.add_argument_group("数据与电网建模")
    g.add_argument("--no-grid-mutex", action="store_true", help="关闭购售电互斥（消融用）")
    g.add_argument("--max-periods", type=int, default=None, help="截断时段数 T（传给 load_problem_data）")
    g.add_argument("--no-skip-infeasible-ev", action="store_true", help="不跳过不可行 EV（传给 load_problem_data）")

    g = parser.add_argument_group("求解器 CBC")
    g.add_argument("--time-limit", type=int, default=600, help="时间上限（秒）")
    g.add_argument("--gap-rel", type=float, default=0.01, help="相对最优间隙（建议大模型 0.02~0.05）")
    g.add_argument("--solver-msg", action="store_true", help="打印 CBC 日志")
    g = parser.add_argument_group("输出与扫描")
    g.add_argument(
        "--results-dir",
        type=Path,
        default=_REPO_ROOT / "results" / "problem2_lifecycle",
        help="结果根目录（其下 single_run / scans / figures / tables）",
    )
    g.add_argument("--run-tag", type=str, default=None, help="单次或扫描子目录名（默认 UTC 时间戳）")
    g.add_argument(
        "--scan-weights",
        type=float,
        nargs="*",
        default=None,
        help="对角权重扫描：每组 w 同时作为 ess_deg_weight 与 ev_deg_weight，例如: --scan-weights 0 0.5 1 2",
    )
    g.add_argument(
        "--scan-no-timeseries",
        action="store_true",
        help="权重扫描时不写出各 w 子目录的 timeseries.csv（减轻磁盘与 I/O，汇总表仍生成）",
    )
    g = parser.add_argument_group("异质性 / 消融实验（可选）")
    g.add_argument(
        "--ev-type-summary-csv",
        type=Path,
        default=None,
        help="problem2_ev_type_summary.csv 路径；与 --ev-deg-summary-rule 联用",
    )
    g.add_argument(
        "--ev-deg-summary-rule",
        choices=["none", "override_mean", "scale_to_type_mean"],
        default="none",
        help="none=用会话表原 deg_cost；override_mean=按车型用表中均值覆盖；scale_to_type_mean=按车型把本会话样本均值对齐到表均值",
    )
    g.add_argument(
        "--v2b-discharge-only-types",
        type=str,
        default=None,
        help="逗号分隔车型（compact/sedan/SUV），仅这些车保留放电与 V2B；其余强制仅充电",
    )
    args = parser.parse_args(argv)

    bad = validate_cli_args(args)
    if bad is not None:
        return bad

    if args.ev_deg_summary_rule != "none":
        if args.ev_type_summary_csv is None:
            print("使用 --ev-deg-summary-rule 时必须同时指定 --ev-type-summary-csv", file=sys.stderr)
            return 1
        sc = args.ev_type_summary_csv.expanduser().resolve()
        if not sc.is_file():
            print(f"汇总表不存在: {sc}", file=sys.stderr)
            return 1
        args.ev_type_summary_csv = sc

    base = args.results_dir.resolve()
    ensure_problem2_layout(base)
    run_tag = args.run_tag or _utc_run_tag()

    try:
        data = load_problem_data(
            _REPO_ROOT,
            args.max_periods,
            skip_infeasible=not args.no_skip_infeasible_ev,
        )
    except FileNotFoundError as e:
        print(f"数据文件缺失: {e}", file=sys.stderr)
        return 1
    except (KeyError, ValueError) as e:
        print(f"数据校验失败: {e}", file=sys.stderr)
        return 1

    warn_heavy_model_instance(data, args)

    use_mutex = not args.no_grid_mutex
    summary_csv: Path | None = args.ev_type_summary_csv
    ev_rule = args.ev_deg_summary_rule
    v2b_only = args.v2b_discharge_only_types

    if args.scan_weights is not None and len(args.scan_weights) > 0:
        scan_dir = base / "scans" / f"scan_{run_tag}"
        scan_dir.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        for w in args.scan_weights:
            sub = scan_dir / f"w_{w:g}".replace(".", "p")
            sub.mkdir(parents=True, exist_ok=True)
            print(f"\n=== 扫描权重 w={w} -> {sub} ===")
            try:
                row = _one_solve_export(
                    _REPO_ROOT,
                    data,
                    ess_w=float(w),
                    ev_w=float(w),
                    carbon_price=args.carbon_price,
                    use_grid_mutex=use_mutex,
                    time_limit_s=args.time_limit,
                    gap_rel=args.gap_rel,
                    solver_msg=args.solver_msg,
                    out_dir=sub,
                    write_timeseries=not args.scan_no_timeseries,
                    ev_type_summary_csv=summary_csv,
                    ev_deg_summary_rule=ev_rule,
                    v2b_discharge_only_types=v2b_only,
                )
            except Exception as exc:
                print(f"权重 w={w} 求解失败: {exc}", file=sys.stderr)
                row = {
                    "ess_deg_weight": float(w),
                    "ev_deg_weight": float(w),
                    "solver_status": "error",
                    "objective_total": None,
                    "error": str(exc),
                }
            rows.append(row)
        df_scan = pd.DataFrame(rows)
        csv_path = scan_dir / "weight_scan_summary.csv"
        json_path = scan_dir / "weight_scan_summary.json"
        df_scan.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df_scan.to_json(json_path, orient="records", force_ascii=False, indent=2)
        tbl = base / "tables"
        tbl.mkdir(parents=True, exist_ok=True)
        tbl_csv = tbl / f"weight_scan_summary_{run_tag}.csv"
        df_scan.to_csv(tbl_csv, index=False, encoding="utf-8-sig")
        # 与全仓习惯一致：同时在 results/tables 留一份，便于与 problem2_ev_type_summary 等并列查看
        pub_tables = _REPO_ROOT / "results" / "tables"
        pub_tables.mkdir(parents=True, exist_ok=True)
        pub_copy = pub_tables / f"problem2_weight_scan_{run_tag}.csv"
        df_scan.to_csv(pub_copy, index=False, encoding="utf-8-sig")
        pub_json = pub_tables / f"problem2_weight_scan_{run_tag}.json"
        df_scan.to_json(pub_json, orient="records", force_ascii=False, indent=2)
        print(f"\n权重扫描汇总: {csv_path}")
        print(f"已同步: {pub_copy.resolve()}")
        print(f"已同步: {pub_json.resolve()}")
        n_ok = sum(1 for r in rows if r.get("objective_total") is not None)
        if n_ok == 0:
            print("所有扫描点均失败。", file=sys.stderr)
            return 1
        return 0

    out_dir = base / "single_run" / run_tag
    print(f"=== 问题2 单次求解 -> {out_dir} ===")
    try:
        row = _one_solve_export(
            _REPO_ROOT,
            data,
            ess_w=args.ess_deg_weight,
            ev_w=args.ev_deg_weight,
            carbon_price=args.carbon_price,
            use_grid_mutex=use_mutex,
            time_limit_s=args.time_limit,
            gap_rel=args.gap_rel,
            solver_msg=args.solver_msg,
            out_dir=out_dir,
            write_timeseries=True,
            ev_type_summary_csv=summary_csv,
            ev_deg_summary_rule=ev_rule,
            v2b_discharge_only_types=v2b_only,
        )
    except Exception as e:
        print(f"建模或求解过程异常: {e}", file=sys.stderr)
        return 1

    if not isinstance(row, dict) or row.get("objective_total") is None:
        return 1

    tbl = base / "tables"
    tbl.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(tbl / f"single_run_{run_tag}.csv", index=False, encoding="utf-8-sig")
    print(f"完成。主输出目录: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
