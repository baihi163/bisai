# -*- coding: utf-8 -*-
"""
问题2 兼顾运行成本与电池寿命损耗的协同调度模型（优化版）

改进点：
1. 支持 ESS 终端 SOC 严格等于 / 宽松大于模式；
2. 支持 EV 最小安全 SOC 比例；
3. 建筑恢复功率加入轻微惩罚；
4. 增强求解元数据导出（状态、耗时、目标一致性）；
5. 保持与问题1接口兼容，保留单次求解与权重扫描能力。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pulp

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
        f"期望目录: {_PROBLEM1_DIR}\n"
        f"原始错误: {exc}",
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
except ImportError:

    def fork_data_for_ev_policies(data: dict[str, Any]) -> dict[str, Any]:
        out = dict(data)
        new_ev: list[dict[str, Any]] = []
        for ev in data["ev_sessions"]:
            e = dict(ev)
            e["charge_limits_kw"] = np.asarray(ev["charge_limits_kw"], dtype=float).copy()
            e["discharge_limits_kw"] = np.asarray(ev["discharge_limits_kw"], dtype=float).copy()
            new_ev.append(e)
        out["ev_sessions"] = new_ev
        return out

    def _ev_type_policy_missing(*_a: Any, **_k: Any) -> Any:
        raise ImportError(
            "EV 异质性策略需要同目录下的 p_2_ev_type_policy 模块（apply_deg_cost_from_type_summary 等）。"
        )

    apply_deg_cost_from_type_summary = _ev_type_policy_missing  # type: ignore[misc, assignment]
    load_type_summary_deg_map = _ev_type_policy_missing  # type: ignore[misc, assignment]
    restrict_v2b_discharge_to_types = _ev_type_policy_missing  # type: ignore[misc, assignment]

PENALTY_CURTAIL = obr.PENALTY_CURTAIL
PENALTY_SHIFT = obr.PENALTY_SHIFT


def _utc_run_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_problem2_layout(base: Path) -> None:
    for sub in ("single_run", "scans", "figures", "tables"):
        (base / sub).mkdir(parents=True, exist_ok=True)


def status_label(prob: pulp.LpProblem) -> str:
    return str(pulp.LpStatus.get(prob.status, prob.status))


def solution_is_usable(prob: pulp.LpProblem) -> bool:
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
    inputs_dir = repo_root / "data" / "processed" / "final_model_inputs"
    candidates = [
        inputs_dir / "ev_sessions_model_ready.csv",
        inputs_dir / "ev_sessions_indexed.csv",
    ]
    path = next((p for p in candidates if p.is_file()), None)

    type_col = None
    if path is not None:
        df0 = pd.read_csv(path, nrows=0)
        for c in df0.columns:
            if c.lower() in ("ev_type", "vehicle_type", "type"):
                type_col = c
                break
        if type_col is not None:
            df = pd.read_csv(path, usecols=["ev_index", type_col])
            idx_to_type = dict(zip(df["ev_index"].astype(int), df[type_col].astype(str)))

            def _norm_type(raw: str) -> str:
                t = str(raw).strip()
                if not t or t.lower() == "nan":
                    return "unknown"
                return "SUV" if t.lower() == "suv" else t

            for ev in ev_sessions:
                try:
                    k = _matrix_col_to_ev_index(str(ev.get("matrix_col", "")))
                    ev["ev_type"] = _norm_type(idx_to_type.get(k, "unknown"))
                except Exception:
                    ev["ev_type"] = "unknown"
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
    ess_terminal_mode: str = "ge",
    ev_min_soc_ratio: float = 0.0,
    recover_penalty_weight: float = 0.0,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
    solver_msg: bool = True,
) -> tuple[pulp.LpProblem, float | None, dict[str, Any] | None, dict[str, Any]]:
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    ess = data["ess"]
    buildings = data["building_blocks"]
    ev_sessions = data["ev_sessions"]

    prob = pulp.LpProblem("Microgrid_Problem2_Lifecycle_Enhanced", pulp.LpMinimize)

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

    ev_keys = []
    ev_keys_by_t = defaultdict(list)
    ev_ts_by_i = {}
    for i, ev in enumerate(ev_sessions):
        ev_ts_by_i[i] = sorted(ev["park_ts"])
        for t in ev_ts_by_i[i]:
            k = (i, t)
            ev_keys.append(k)
            ev_keys_by_t[t].append(k)

    if ev_keys:
        P_ev_ch = pulp.LpVariable.dicts("P_ev_ch", ev_keys, lowBound=0)
        P_ev_dis = pulp.LpVariable.dicts("P_ev_dis", ev_keys, lowBound=0)
        E_ev = pulp.LpVariable.dicts("E_ev", ev_keys, lowBound=0)
    else:
        P_ev_ch, P_ev_dis, E_ev = {}, {}, {}

    ev_mutex_keys = []
    for i, ev in enumerate(ev_sessions):
        if int(ev.get("v2b_allowed", 0)):
            for t in ev_ts_by_i[i]:
                ev_mutex_keys.append((i, t))
    U_ev_ch = pulp.LpVariable.dicts("U_ev_ch", ev_mutex_keys, cat=pulp.LpBinary) if ev_mutex_keys else {}

    obj_terms = []

    ess_deg_cost_coef = float(ess["degradation_cost_cny_per_kwh"]) * float(ess_deg_weight)

    for t in T:
        obj_terms.append(data["buy_price"][t] * P_buy[t] * dt)
        obj_terms.append(-data["sell_price"][t] * P_sell[t] * dt)
        obj_terms.append(carbon_price * data["grid_carbon"][t] * P_buy[t] * dt)
        obj_terms.append(PENALTY_CURTAIL * (data["pv_upper"][t] - P_pv_use[t]) * dt)
        obj_terms.append(ess_deg_cost_coef * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2)

    for b in buildings:
        for t in T:
            key = (b["name"], t)
            obj_terms.append(PENALTY_SHIFT * (P_shift_out[key] + P_recover[key]) * dt)
            obj_terms.append(recover_penalty_weight * P_recover[key] * dt)
            obj_terms.append(b["penalty_not_served"] * P_shed[key] * dt)

    if ev_keys:
        for i, ev in enumerate(ev_sessions):
            ev_deg_coef = float(ev["deg_cost"]) * float(ev_deg_weight)
            for t in ev_ts_by_i[i]:
                obj_terms.append(ev_deg_coef * (P_ev_ch[(i, t)] + P_ev_dis[(i, t)]) * dt / 2)

    prob += pulp.lpSum(obj_terms)

    for t in T:
        served_load = pulp.lpSum(
            b["load"][t] - P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)] - P_shed[(b["name"], t)]
            for b in buildings
        )
        ev_ch_t = pulp.lpSum(P_ev_ch[k] for k in ev_keys_by_t[t]) if ev_keys_by_t[t] else 0
        ev_dis_t = pulp.lpSum(P_ev_dis[k] for k in ev_keys_by_t[t]) if ev_keys_by_t[t] else 0

        prob += (
            P_pv_use[t] + P_buy[t] + P_ess_dis[t] + ev_dis_t
            == served_load + P_sell[t] + P_ess_ch[t] + ev_ch_t
        ), f"Bal_{t}"

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

    if ess_terminal_mode == "eq":
        prob += E_ess[n - 1] == ess["initial_energy_kwh"], "Terminal_SOC_EQ"
    else:
        prob += E_ess[n - 1] >= ess["initial_energy_kwh"], "Terminal_SOC_GE"

    for b in buildings:
        name = b["name"]
        rf = float(b["rebound_factor"])
        if rf < 1.0:
            raise ValueError(f"建筑块 {name!r} rebound_factor={rf} < 1，与 backlog 动力学不兼容")
        for t in T:
            flex_cap = max(0.0, (1 - b["noninterruptible_share"]) * b["load"][t])
            prob += P_shift_out[(name, t)] <= min(b["max_shiftable_kw"], flex_cap)
            prob += P_shed[(name, t)] <= min(b["max_sheddable_kw"], flex_cap)
            prob += P_shift_out[(name, t)] + P_shed[(name, t)] <= flex_cap
            prob += P_recover[(name, t)] <= rf * b["max_shiftable_kw"]

            if t == 0:
                prob += E_backlog[(name, t)] == P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / rf
            else:
                prob += E_backlog[(name, t)] == E_backlog[(name, t - 1)] + P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / rf

        prob += E_backlog[(name, n - 1)] == 0, f"Backlog_End_{name}"

    if ev_keys:
        for i, ev in enumerate(ev_sessions):
            ts = ev_ts_by_i[i]
            if not ts:
                continue

            ev_min_energy = float(ev_min_soc_ratio) * float(ev["battery_capacity_kwh"])

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
                        raise ValueError(f"EV {ev.get('session_id', i)} 在站时段非连续：{prev_t}->{t}")
                    prob += E_ev[(i, t)] == E_ev[(i, prev_t)] + (
                        ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]
                    ) * dt

                prob += E_ev[(i, t)] >= ev_min_energy
                prob += E_ev[(i, t)] <= ev["battery_capacity_kwh"]

            prob += E_ev[(i, ts[-1])] >= ev["required_energy_kwh"]

    solve_start = time.perf_counter()
    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=solver_msg)
    prob.solve(solver)
    solve_time_s = time.perf_counter() - solve_start

    obj_val = None
    if solution_is_usable(prob):
        try:
            v = pulp.value(prob.objective)
            obj_val = float(v) if v is not None else None
        except Exception:
            obj_val = None

    solve_meta = {
        "solver_status": status_label(prob),
        "solver_code": int(prob.status),
        "solve_time_seconds": solve_time_s,
        "objective_value": obj_val,
        "ess_terminal_mode": ess_terminal_mode,
        "ev_min_soc_ratio": ev_min_soc_ratio,
        "recover_penalty_weight": recover_penalty_weight,
    }

    solve_ctx = None
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
            "solve_meta": solve_meta,
            "recover_penalty_weight": float(recover_penalty_weight),
        }

    return prob, obj_val, solve_ctx, solve_meta


def compute_objective_breakdown(prob: pulp.LpProblem, data: dict[str, Any], ctx: dict[str, Any]) -> dict[str, float]:
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    ess = ctx["ess"]
    buildings = ctx["buildings"]
    ev_sessions = ctx["ev_sessions"]
    ev_ts_by_i = ctx["ev_ts_by_i"]
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
        ess_degradation_cost += float(ess["degradation_cost_cny_per_kwh"]) * w_ess * (
            obr.var_float(ctx["P_ess_ch"][t]) + obr.var_float(ctx["P_ess_dis"][t])
        ) * dt / 2

    building_shift_penalty = 0.0
    load_shed_penalty = 0.0
    sm = ctx.get("solve_meta") or {}
    rw = float(sm.get("recover_penalty_weight", 0.0))
    recover_penalty_cost = 0.0
    for b in buildings:
        name = b["name"]
        for t in T:
            pr = obr.var_float(ctx["P_recover"][(name, t)])
            building_shift_penalty += float(PENALTY_SHIFT) * (
                obr.var_float(ctx["P_shift_out"][(name, t)]) + pr
            ) * dt
            recover_penalty_cost += rw * pr * dt
            load_shed_penalty += float(b["penalty_not_served"]) * obr.var_float(ctx["P_shed"][(name, t)]) * dt

    ev_degradation_cost = 0.0
    for i, ev in enumerate(ev_sessions):
        for t in ev_ts_by_i.get(i, []):
            k = (i, t)
            ev_degradation_cost += float(ev["deg_cost"]) * w_ev * (
                obr.var_float(ctx["P_ev_ch"][k]) + obr.var_float(ctx["P_ev_dis"][k])
            ) * dt / 2

    operation_cost = (
        grid_import_cost
        - grid_export_revenue
        + carbon_cost
        + pv_curtail_penalty
        + building_shift_penalty
        + load_shed_penalty
        + recover_penalty_cost
    )
    objective_recomputed = operation_cost + ess_degradation_cost + ev_degradation_cost

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
        "recover_penalty_cost": recover_penalty_cost,
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
    n = data["n"]
    dt = data["delta_t"]
    T = range(n)

    grid_import_energy = sum(obr.var_float(ctx["P_buy"][t]) * dt for t in T)
    grid_export_energy = sum(obr.var_float(ctx["P_sell"][t]) * dt for t in T)
    pv_curtail_energy = sum(max(0.0, float(data["pv_upper"][t]) - obr.var_float(ctx["P_pv_use"][t])) * dt for t in T)
    ess_charge_energy = sum(obr.var_float(ctx["P_ess_ch"][t]) * dt for t in T)
    ess_discharge_energy = sum(obr.var_float(ctx["P_ess_dis"][t]) * dt for t in T)
    ess_throughput = (ess_charge_energy + ess_discharge_energy) / 2

    ev_charge_energy = 0.0
    ev_discharge_energy = 0.0
    for i, _ev in enumerate(ctx["ev_sessions"]):
        for t in ctx["ev_ts_by_i"].get(i, []):
            k = (i, t)
            ev_charge_energy += obr.var_float(ctx["P_ev_ch"][k]) * dt
            ev_discharge_energy += obr.var_float(ctx["P_ev_dis"][k]) * dt
    ev_throughput = (ev_charge_energy + ev_discharge_energy) / 2

    load_shed_energy = 0.0
    for b in ctx["buildings"]:
        name = b["name"]
        for t in T:
            load_shed_energy += obr.var_float(ctx["P_shed"][(name, t)]) * dt

    return {
        "grid_import_energy_kwh": grid_import_energy,
        "grid_export_energy_kwh": grid_export_energy,
        "pv_curtail_energy_kwh": pv_curtail_energy,
        "ess_charge_energy_kwh": ess_charge_energy,
        "ess_discharge_energy_kwh": ess_discharge_energy,
        "ess_throughput_kwh": ess_throughput,
        "ev_charge_energy_kwh": ev_charge_energy,
        "ev_discharge_energy_kwh": ev_discharge_energy,
        "ev_throughput_kwh": ev_throughput,
        "load_shed_energy_kwh": load_shed_energy,
    }


def compute_ev_type_summary(data: dict[str, Any], ctx: dict[str, Any]) -> pd.DataFrame:
    dt = data["delta_t"]
    w_ev = float(ctx["ev_deg_weight"])

    by_type = defaultdict(list)
    for i, ev in enumerate(ctx["ev_sessions"]):
        by_type[str(ev.get("ev_type", "unknown"))].append(i)

    rows = []
    for et, indices in sorted(by_type.items()):
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
            for t in ctx["ev_ts_by_i"].get(i, []):
                k = (i, t)
                pch = obr.var_float(ctx["P_ev_ch"][k])
                pdi = obr.var_float(ctx["P_ev_dis"][k])
                total_ch += pch * dt
                total_dis += pdi * dt
                deg_cny += float(ev["deg_cost"]) * w_ev * (pch + pdi) * dt / 2
                if pdi > 1e-6:
                    any_dis = True
            if any_dis:
                n_v2b_active += 1

        rows.append({
            "ev_type": et,
            "session_count": n_sess,
            "v2b_allowed_sessions": n_v2b_allowed,
            "v2b_active_sessions_discharge": n_v2b_active,
            "v2b_allowed_share": n_v2b_allowed / n_sess if n_sess else 0.0,
            "total_charge_energy_kwh": total_ch,
            "total_discharge_energy_kwh": total_dis,
            "total_throughput_kwh": (total_ch + total_dis) / 2,
            "total_ev_degradation_cost_cny": deg_cny,
        })
    return pd.DataFrame(rows)


def _json_safe_numbers(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and not math.isfinite(v):
            out[k] = None
        else:
            out[k] = v
    return out


def export_bundle(out_dir: Path, breakdown: dict[str, Any], metrics: dict[str, Any], ev_type_df: pd.DataFrame,
                  meta: dict[str, Any], ts_df: pd.DataFrame | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "objective_breakdown.json").write_text(
        json.dumps(_json_safe_numbers(breakdown), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame([{"metric": k, "value": v} for k, v in breakdown.items()]).to_csv(
        out_dir / "objective_breakdown.csv", index=False, encoding="utf-8-sig"
    )

    (out_dir / "operational_metrics.json").write_text(
        json.dumps(_json_safe_numbers(metrics), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame([{"metric": k, "value": v} for k, v in metrics.items()]).to_csv(
        out_dir / "operational_metrics.csv", index=False, encoding="utf-8-sig"
    )

    ev_type_df.to_csv(out_dir / "ev_type_summary.csv", index=False, encoding="utf-8-sig")
    ev_type_df.to_json(out_dir / "ev_type_summary.json", orient="records", force_ascii=False, indent=2)

    (out_dir / "run_meta.json").write_text(
        json.dumps(_json_safe_numbers(meta), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if ts_df is not None:
        ts_df.to_csv(out_dir / "timeseries.csv", index=False, encoding="utf-8-sig")


def validate_cli_args(args: argparse.Namespace) -> int | None:
    if args.gap_rel <= 0 or args.gap_rel > 1.0:
        print("--gap-rel 应在 (0, 1] 内", file=sys.stderr)
        return 1
    if args.time_limit <= 0:
        print("--time-limit 须为正", file=sys.stderr)
        return 1
    if not (0.0 <= args.ev_min_soc_ratio <= 1.0):
        print("--ev-min-soc-ratio 应在 [0,1]", file=sys.stderr)
        return 1
    if args.recover_penalty_weight < 0:
        print("--recover-penalty-weight 不应为负", file=sys.stderr)
        return 1

    rule = getattr(args, "ev_deg_summary_rule", "none")
    csv_arg = getattr(args, "ev_type_summary_csv", None)
    if rule != "none":
        if csv_arg is None:
            print("使用 --ev-deg-summary-rule 非 none 时必须同时指定 --ev-type-summary-csv", file=sys.stderr)
            return 1
        sc = Path(csv_arg).expanduser().resolve()
        if not sc.is_file():
            print(f"汇总表不存在: {sc}", file=sys.stderr)
            return 1
        args.ev_type_summary_csv = sc
    elif csv_arg is not None:
        sc = Path(csv_arg).expanduser().resolve()
        if not sc.is_file():
            print(f"汇总表不存在: {sc}", file=sys.stderr)
            return 1
        args.ev_type_summary_csv = sc

    return None


def _one_run(
    repo_root: Path,
    data: dict[str, Any],
    *,
    ess_w: float,
    ev_w: float,
    carbon_price: float,
    use_grid_mutex: bool,
    ess_terminal_mode: str,
    ev_min_soc_ratio: float,
    recover_penalty_weight: float,
    time_limit_s: int,
    gap_rel: float,
    solver_msg: bool,
    out_dir: Path,
    write_timeseries: bool = True,
    ev_type_summary_csv: Path | None = None,
    ev_deg_summary_rule: str = "none",
    v2b_discharge_only_types: str | None = None,
) -> dict[str, Any]:
    work_data = fork_data_for_ev_policies(data)
    enrich_ev_sessions_with_ev_type(repo_root, work_data["ev_sessions"])

    if ev_type_summary_csv is not None and ev_deg_summary_rule not in ("none", ""):
        deg_map = load_type_summary_deg_map(Path(ev_type_summary_csv).resolve())
        apply_deg_cost_from_type_summary(work_data["ev_sessions"], deg_map, rule=ev_deg_summary_rule)
        print(
            f"已应用车型汇总退化规则: csv={Path(ev_type_summary_csv).name}, rule={ev_deg_summary_rule}",
            file=sys.stderr,
        )

    if v2b_discharge_only_types:
        allowed = {x.strip() for x in v2b_discharge_only_types.split(",") if x.strip()}
        if allowed:
            restrict_v2b_discharge_to_types(work_data["ev_sessions"], allowed)
            print(f"已限制可放电/V2B 车型为: {sorted(allowed)}", file=sys.stderr)

    prob, obj, ctx, solve_meta = build_and_solve_p2(
        work_data,
        carbon_price=carbon_price,
        ess_deg_weight=ess_w,
        ev_deg_weight=ev_w,
        use_grid_mutex=use_grid_mutex,
        ess_terminal_mode=ess_terminal_mode,
        ev_min_soc_ratio=ev_min_soc_ratio,
        recover_penalty_weight=recover_penalty_weight,
        time_limit_s=time_limit_s,
        gap_rel=gap_rel,
        solver_msg=solver_msg,
    )

    if not solution_is_usable(prob) or ctx is None:
        return {
            "ess_deg_weight": ess_w,
            "ev_deg_weight": ev_w,
            "solver_status": solve_meta["solver_status"],
            "objective_total": None,
            "solve_time_seconds": solve_meta["solve_time_seconds"],
            "error": "no_usable_solution",
        }

    breakdown = compute_objective_breakdown(prob, work_data, ctx)
    metrics = compute_operational_metrics(work_data, ctx)
    ev_df = compute_ev_type_summary(work_data, ctx)
    ts_df = extract_solution_timeseries(work_data, ctx) if write_timeseries else None

    meta = {
        "timestamp_utc": _utc_run_tag(),
        "carbon_price": carbon_price,
        "ess_deg_weight": ess_w,
        "ev_deg_weight": ev_w,
        "use_grid_mutex": use_grid_mutex,
        "ev_type_summary_csv": str(Path(ev_type_summary_csv).resolve()) if ev_type_summary_csv else None,
        "ev_deg_summary_rule": ev_deg_summary_rule,
        "v2b_discharge_only_types": v2b_discharge_only_types,
        **solve_meta,
    }
    export_bundle(out_dir, breakdown, metrics, ev_df, meta, ts_df)

    return {
        "ess_deg_weight": ess_w,
        "ev_deg_weight": ev_w,
        "solver_status": solve_meta["solver_status"],
        "objective_total": breakdown["objective_from_solver"],
        "objective_recomputed": breakdown["objective_recomputed"],
        "objective_abs_gap": breakdown["objective_abs_gap"],
        "operation_cost": breakdown["operation_cost"],
        "ess_deg_cost": breakdown["ess_degradation_cost"],
        "ev_deg_cost": breakdown["ev_degradation_cost"],
        "ess_throughput_kwh": metrics["ess_throughput_kwh"],
        "ev_throughput_kwh": metrics["ev_throughput_kwh"],
        "grid_import_energy_kwh": metrics["grid_import_energy_kwh"],
        "grid_export_energy_kwh": metrics["grid_export_energy_kwh"],
        "pv_curtail_energy_kwh": metrics["pv_curtail_energy_kwh"],
        "load_shed_energy_kwh": metrics["load_shed_energy_kwh"],
        "solve_time_seconds": solve_meta["solve_time_seconds"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="问题2：兼顾寿命损耗的协同调度（优化版 p2.py）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="ESS 终端: --ess-terminal-mode ge(>=初值) 或 eq(=初值)。"
        "恢复惩罚: --recover-penalty-weight>0 时对 P_recover 额外线性惩罚（与 objective 对账一致）。",
    )
    parser.add_argument("--ess-deg-weight", type=float, default=1.0)
    parser.add_argument("--ev-deg-weight", type=float, default=1.0)
    parser.add_argument("--carbon-price", type=float, default=0.0)
    parser.add_argument("--no-grid-mutex", action="store_true")
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument("--no-skip-infeasible-ev", action="store_true")
    parser.add_argument("--time-limit", type=int, default=600)
    parser.add_argument("--gap-rel", type=float, default=0.01)
    parser.add_argument("--solver-msg", action="store_true")
    parser.add_argument("--ess-terminal-mode", choices=["ge", "eq"], default="ge")
    parser.add_argument("--ev-min-soc-ratio", type=float, default=0.0)
    parser.add_argument("--recover-penalty-weight", type=float, default=0.0)
    parser.add_argument("--results-dir", type=Path, default=_REPO_ROOT / "results" / "problem2_lifecycle")
    parser.add_argument("--run-tag", type=str, default=None)
    g_scan = parser.add_argument_group("输出与扫描")
    g_scan.add_argument(
        "--scan-weights",
        type=float,
        nargs="*",
        default=None,
        help="对角权重扫描：每组 w 同时作为 ess_deg_weight 与 ev_deg_weight",
    )
    g_scan.add_argument(
        "--scan-no-timeseries",
        action="store_true",
        help="权重扫描时不写各 w 子目录 timeseries.csv",
    )
    g_ev = parser.add_argument_group("异质性 / 消融实验（可选）")
    g_ev.add_argument(
        "--ev-type-summary-csv",
        type=Path,
        default=None,
        help="problem2_ev_type_summary.csv；与 --ev-deg-summary-rule 联用",
    )
    g_ev.add_argument(
        "--ev-deg-summary-rule",
        choices=["none", "override_mean", "scale_to_type_mean"],
        default="none",
        help="none=会话原 deg_cost；override_mean=按车型表均值覆盖；scale_to_type_mean=按车型对齐样本均值",
    )
    g_ev.add_argument(
        "--v2b-discharge-only-types",
        type=str,
        default=None,
        help="逗号分隔车型（如 compact,sedan,SUV），仅这些车保留放电与 V2B",
    )
    args = parser.parse_args(argv)

    bad = validate_cli_args(args)
    if bad is not None:
        return bad

    base = args.results_dir.resolve()
    ensure_problem2_layout(base)
    run_tag = args.run_tag or _utc_run_tag()

    try:
        data = load_problem_data(
            _REPO_ROOT,
            args.max_periods,
            skip_infeasible=not args.no_skip_infeasible_ev,
        )
    except Exception as e:
        print(f"数据加载失败: {e}", file=sys.stderr)
        return 1

    use_mutex = not args.no_grid_mutex

    if args.scan_weights:
        scan_dir = base / "scans" / f"scan_{run_tag}"
        scan_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for w in args.scan_weights:
            sub = scan_dir / f"w_{w:g}".replace(".", "p")
            sub.mkdir(parents=True, exist_ok=True)
            print(f"=== 扫描 w={w} ===")
            try:
                row = _one_run(
                    _REPO_ROOT,
                    data,
                    ess_w=float(w),
                    ev_w=float(w),
                    carbon_price=args.carbon_price,
                    use_grid_mutex=use_mutex,
                    ess_terminal_mode=args.ess_terminal_mode,
                    ev_min_soc_ratio=args.ev_min_soc_ratio,
                    recover_penalty_weight=args.recover_penalty_weight,
                    time_limit_s=args.time_limit,
                    gap_rel=args.gap_rel,
                    solver_msg=args.solver_msg,
                    out_dir=sub,
                    write_timeseries=not args.scan_no_timeseries,
                    ev_type_summary_csv=args.ev_type_summary_csv,
                    ev_deg_summary_rule=args.ev_deg_summary_rule,
                    v2b_discharge_only_types=args.v2b_discharge_only_types,
                )
            except Exception as exc:
                row = {
                    "ess_deg_weight": float(w),
                    "ev_deg_weight": float(w),
                    "solver_status": "error",
                    "objective_total": None,
                    "error": str(exc),
                }
            rows.append(row)

        df = pd.DataFrame(rows)
        csv_path = scan_dir / "weight_scan_summary.csv"
        json_path = scan_dir / "weight_scan_summary.json"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        df.to_json(json_path, orient="records", force_ascii=False, indent=2)
        tbl = base / "tables"
        tbl.mkdir(parents=True, exist_ok=True)
        df.to_csv(tbl / f"weight_scan_summary_{run_tag}.csv", index=False, encoding="utf-8-sig")
        pub = _REPO_ROOT / "results" / "tables"
        pub.mkdir(parents=True, exist_ok=True)
        pub_csv = pub / f"problem2_weight_scan_{run_tag}.csv"
        pub_json = pub / f"problem2_weight_scan_{run_tag}.json"
        df.to_csv(pub_csv, index=False, encoding="utf-8-sig")
        df.to_json(pub_json, orient="records", force_ascii=False, indent=2)
        print(f"扫描完成：{scan_dir}")
        print(f"已同步: {pub_csv.resolve()}")
        print(f"已同步: {pub_json.resolve()}")
        return 0

    out_dir = base / "single_run" / run_tag
    try:
        row = _one_run(
            _REPO_ROOT,
            data,
            ess_w=args.ess_deg_weight,
            ev_w=args.ev_deg_weight,
            carbon_price=args.carbon_price,
            use_grid_mutex=use_mutex,
            ess_terminal_mode=args.ess_terminal_mode,
            ev_min_soc_ratio=args.ev_min_soc_ratio,
            recover_penalty_weight=args.recover_penalty_weight,
            time_limit_s=args.time_limit,
            gap_rel=args.gap_rel,
            solver_msg=args.solver_msg,
            out_dir=out_dir,
            write_timeseries=True,
            ev_type_summary_csv=args.ev_type_summary_csv,
            ev_deg_summary_rule=args.ev_deg_summary_rule,
            v2b_discharge_only_types=args.v2b_discharge_only_types,
        )
    except Exception as e:
        print(f"求解失败: {e}", file=sys.stderr)
        return 1

    if row.get("objective_total") is None:
        return 1

    pd.DataFrame([row]).to_csv(base / "tables" / f"single_run_{run_tag}.csv", index=False, encoding="utf-8-sig")
    print(f"完成，输出目录：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
