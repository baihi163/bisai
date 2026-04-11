"""
问题1 园区微电网协同调度 — PuLP 对齐版 (p_1_2_final)

修复与优化项：
- 引入“真降维”：仅为 EV 在站时间段创建充放电变量，极大减少变量与约束数量，加速求解。
- EV 逐时电量 E_ev(i,t) 仅在在站时段建模，含初值递推、容量上界、离站最低电量（目标 SOC）。
- 提取硬编码惩罚系数，便于后续敏感性分析。
- 修复项：argparse 属性映射、EV 数据路径、EV 时段对齐等。

不可行 EV 跳过策略（默认开启，可用 --no-skip-infeasible-ev 关闭）：
- 若离站目标电量 required_energy_at_departure_kwh 超过电池容量 battery_capacity_kwh，
  或即使全程以最大充电功率充电（并受充电效率、步长限制）仍无法使末时刻电量达到目标，
  则该 session 被标记为不可行并从模型中剔除；否则 CBC 易出现整体 Infeasible。
- 剔除的 session 仍写入 ev_skipped 列表，并在 stderr 与 summary JSON 中输出统计，
  不参与功率平衡与 KPI 中的“已建模 EV”指标。
- 若 initial_energy_kwh > battery_capacity_kwh，数据自相矛盾，该 session **始终**剔除并记录。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pulp

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少文件: {path}")
    return pd.read_csv(path)


def _read_series_csv(path: Path, column: str, n: int | None = None) -> np.ndarray:
    df = _read_csv(path)
    if column not in df.columns:
        raise KeyError(f"{path} 缺少列 {column}")
    arr = df[column].to_numpy(dtype=float)
    return arr[:n] if n is not None else arr


def _max_net_charge_kwh(
    n_steps: int, dt_h: float, eta_ch: float, p_ch_max_kw: float
) -> float:
    return float(n_steps) * dt_h * eta_ch * p_ch_max_kw


def _build_ev_sessions(
    df_ev: pd.DataFrame, n_periods: int, dt_h: float, *, skip_infeasible: bool
) -> tuple[list[dict], list[dict]]:
    sessions: list[dict] = []
    skipped: list[dict] = []
    eta_def = 0.95
    for _, row in df_ev.iterrows():
        arr = int(row["arrival_slot"])
        dep = int(row["departure_slot"])
        if dep <= arr:
            continue
        arr_c = max(1, arr)
        dep_c = min(dep, n_periods + 1)
        if dep_c <= arr_c:
            continue
        park_ts: list[int] = []
        for slot in range(arr_c, dep_c):
            t = slot - 1
            if 0 <= t < n_periods:
                park_ts.append(t)
        if not park_ts:
            continue

        v2b = bool(int(row["v2b_allowed"])) if not isinstance(row["v2b_allowed"], bool) else row["v2b_allowed"]
        p_dis = float(row["max_discharge_power_kw"])
        if not v2b:
            p_dis = 0.0

        e_init = float(row["initial_energy_kwh"])
        e_req = float(row["required_energy_at_departure_kwh"])
        e_cap = float(row["battery_capacity_kwh"])
        e_need = e_req - e_init
        p_ch_max = float(row["max_charge_power_kw"])
        k = len(park_ts)
        max_net = _max_net_charge_kwh(k, dt_h, eta_def, p_ch_max)

        if e_init > e_cap + 1e-3:
            skipped.append(
                {
                    "session_id": str(row["session_id"]),
                    "reason": "initial_energy_exceeds_battery_capacity",
                    "initial_kwh": round(e_init, 3),
                    "capacity_kwh": round(e_cap, 3),
                    "dwell_steps": k,
                }
            )
            continue

        if e_req > e_cap + 1e-3:
            if skip_infeasible:
                skipped.append(
                    {
                        "session_id": str(row["session_id"]),
                        "reason": "departure_target_exceeds_battery_capacity",
                        "required_departure_kwh": round(e_req, 3),
                        "capacity_kwh": round(e_cap, 3),
                        "dwell_steps": k,
                    }
                )
                continue

        if e_need > max_net + 1e-3:
            rec = {
                "session_id": str(row["session_id"]),
                "reason": "insufficient_charging_capacity_to_reach_departure_target",
                "e_need_kwh": round(e_need, 3),
                "max_net_kwh": round(max_net, 3),
                "initial_kwh": round(e_init, 3),
                "required_departure_kwh": round(e_req, 3),
                "dwell_steps": k,
            }
            if skip_infeasible:
                skipped.append(rec)
                continue

        sessions.append(
            {
                "id": str(row["session_id"]),
                "park_ts": sorted(set(park_ts)),
                "e_initial_kwh": e_init,
                "e_required_departure_kwh": e_req,
                "e_cap_kwh": e_cap,
                "e_min_kwh": 0.0,
                "p_ch_max": p_ch_max,
                "p_dis_max": p_dis,
                "v2b_allowed": 1 if v2b else 0,
                "eta_ch": eta_def,
                "eta_dis": 0.95,
            }
        )
    return sessions, skipped


def _compute_operational_summary(
    data: dict,
    results: dict,
    obj_val: float | None,
    ev_sessions: list[dict],
    ev_gaps_kwh: list[float],
    *,
    total_ev_charge_kwh: float,
    total_ev_discharge_kwh: float,
) -> dict:
    """全时段聚合指标（能量均为 kWh，功率峰值 kW）。"""
    n = data["n"]
    dt = float(data["delta_t"])
    T = range(n)
    buy = np.asarray(results["P_buy"], dtype=float)
    sell = np.asarray(results["P_sell"], dtype=float)
    curt = np.asarray(results["P_curtail"], dtype=float)
    shed = np.asarray(results["P_shed"], dtype=float)
    pv = np.asarray(data["pv_power"], dtype=float)
    shift_net = np.asarray(results["P_shift"], dtype=float)
    shift_up = np.asarray(results.get("P_shift_up", []), dtype=float)
    shift_down = np.asarray(results.get("P_shift_down", []), dtype=float)

    total_grid_import_kwh = float(np.sum(buy) * dt)
    total_grid_export_kwh = float(np.sum(sell) * dt)
    total_pv_curtailment_kwh = float(np.sum(curt) * dt)
    total_load_shed_kwh = float(np.sum(shed) * dt)
    peak_grid_import_kw = float(np.max(buy)) if n else 0.0
    total_pv_available_kwh = float(np.sum(pv) * dt)
    pv_used_gross_kwh = float(np.sum(np.maximum(pv - curt, 0.0)) * dt)
    if total_pv_available_kwh > 1e-9:
        pv_self_utilization_rate = pv_used_gross_kwh / total_pv_available_kwh
    else:
        pv_self_utilization_rate = None

    if len(shift_up) == n and len(shift_down) == n:
        flex_gross_kwh = float(np.sum(shift_up + shift_down) * dt)
    else:
        flex_gross_kwh = float(np.sum(np.abs(shift_net)) * dt)

    modeled = len(ev_sessions)
    skipped = data.get("ev_skipped") or []
    n_skipped = len(skipped)
    n_csv_sessions = modeled + n_skipped
    if ev_gaps_kwh:
        min_gap = float(min(ev_gaps_kwh))
        n_met = sum(1 for g in ev_gaps_kwh if g >= -1e-3)
        ev_departure_target_met_rate_modeled = n_met / len(ev_gaps_kwh)
    else:
        min_gap = None
        ev_departure_target_met_rate_modeled = None

    by_reason: dict[str, int] = {}
    skipped_ids: list[str] = []
    for rec in skipped:
        r = str(rec.get("reason", "unknown"))
        by_reason[r] = by_reason.get(r, 0) + 1
        sid = rec.get("session_id")
        if sid is not None:
            skipped_ids.append(str(sid))

    return {
        "num_periods": n,
        "time_step_hours": dt,
        "total_operating_cost_cny": (
            None if obj_val is None else round(float(obj_val), 6)
        ),
        "total_grid_import_kwh": round(total_grid_import_kwh, 4),
        "total_grid_export_kwh": round(total_grid_export_kwh, 4),
        "total_pv_curtailment_kwh": round(total_pv_curtailment_kwh, 4),
        "total_load_shed_kwh": round(total_load_shed_kwh, 4),
        "peak_grid_import_kw": round(peak_grid_import_kw, 4),
        "pv_self_utilization_rate": (
            None if pv_self_utilization_rate is None else round(pv_self_utilization_rate, 6)
        ),
        "pv_self_utilization_rate_note": "sum(max(pv_t - P_curtail_t, 0) * dt) / sum(pv_t * dt)",
        "total_ev_charge_kwh": round(total_ev_charge_kwh, 4),
        "total_ev_discharge_kwh": round(total_ev_discharge_kwh, 4),
        "total_building_flex_gross_shift_kwh": round(flex_gross_kwh, 4),
        "total_building_flex_gross_shift_note": "sum((P_shift_up + P_shift_down) * dt) when available",
        "ev_sessions_modeled": modeled,
        "ev_sessions_skipped": n_skipped,
        "ev_sessions_included_fraction_of_csv": (
            round(modeled / n_csv_sessions, 6) if n_csv_sessions else None
        ),
        "ev_min_departure_soc_gap_kwh": None if min_gap is None else round(min_gap, 6),
        "ev_departure_target_met_rate_modeled": ev_departure_target_met_rate_modeled,
        "ev_demand_satisfaction_rate": ev_departure_target_met_rate_modeled,
        "ev_demand_satisfaction_rate_note": "在已建模 EV 上，末时刻电量相对离站目标的满足比例（最优解下通常为 1）",
        "ev_skip_reason_counts": by_reason,
        "ev_skipped_session_ids": skipped_ids,
    }


def load_problem_data(
    root: Path,
    max_periods: int | None = None,
    *,
    skip_infeasible_ev: bool = True,
) -> dict:
    base_inputs = root / "data" / "processed" / "final_model_inputs"
    base_processed = root / "data" / "processed"

    load_csv = base_inputs / "load_profile.csv"
    pv_csv = base_inputs / "pv_profile.csv"
    flex_csv = base_inputs / "flexible_load_params_clean.csv"
    ess_json = base_inputs / "ess_params.json"
    ev_csv = base_inputs / "ev_sessions_model_ready.csv"

    price_csv = base_processed / "price_profile.csv"
    grid_csv = base_processed / "grid_limits.csv"

    df_load = _read_csv(load_csv)
    n = len(df_load)
    if max_periods is not None:
        n = min(n, int(max_periods))
        df_load = df_load.iloc[:n].copy()

    timestamps = (
        df_load["timestamp"].astype(str).tolist()
        if "timestamp" in df_load.columns
        else [f"t{t + 1:03d}" for t in range(n)]
    )

    if "total_native_load_kw" in df_load.columns:
        load_power = df_load["total_native_load_kw"].to_numpy(dtype=float)
    else:
        sub = [c for c in df_load.columns if c.endswith("_kw") and c != "slot_id"]
        load_power = df_load[sub].sum(axis=1).to_numpy(dtype=float)

    pv_power = _read_series_csv(pv_csv, "pv_available_kw", n)
    buy_price = _read_series_csv(price_csv, "grid_buy_price_cny_per_kwh", n)
    sell_price = _read_series_csv(price_csv, "grid_sell_price_cny_per_kwh", n)
    p_imp_max = _read_series_csv(grid_csv, "grid_import_limit_kw", n)
    p_exp_max = _read_series_csv(grid_csv, "grid_export_limit_kw", n)

    with open(ess_json, "r", encoding="utf-8") as f:
        ess = json.load(f)
    dt = float(ess.get("time_step_hours", 0.25))

    df_flex = _read_csv(flex_csv) if flex_csv.is_file() else pd.DataFrame()
    shift_cap_kw = (
        float(df_flex["max_shiftable_kw"].sum())
        if len(df_flex) and "max_shiftable_kw" in df_flex.columns
        else 200.0
    )

    df_ev = _read_csv(ev_csv)
    ev_sessions, ev_skipped = _build_ev_sessions(
        df_ev, n, dt, skip_infeasible=skip_infeasible_ev
    )

    return {
        "n": n,
        "timestamps": timestamps,
        "delta_t": dt,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pv_power": pv_power,
        "load_power": load_power,
        "p_imp_max": p_imp_max,
        "p_exp_max": p_exp_max,
        "shift_cap_kw": shift_cap_kw,
        "ess": ess,
        "ev_sessions": ev_sessions,
        "ev_skipped": ev_skipped,
    }


def _var_float(v: Any) -> float:
    """安全读取 PuLP 变量值（未求解或非最优时为 None）。"""
    if v is None:
        return 0.0
    try:
        x = v.value()
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


def build_and_solve(
    data: dict,
    *,
    use_grid_mutex: bool = True,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
    cbc_msg: bool = True,
) -> tuple[pulp.LpProblem, dict, float | None, dict]:
    n = data["n"]
    if n < 1:
        raise ValueError("时段数 n 必须 >= 1，请检查负荷 CSV 或 --max-periods")
    T = range(n)
    dt = data["delta_t"]
    ess, shift_cap, ev_sessions = data["ess"], data["shift_cap_kw"], data["ev_sessions"]
    num_ev = len(ev_sessions)

    # 惩罚系数参数化 (便于后续论文敏感性分析)
    PENALTY_CURTAIL = 0.5  # 弃光惩罚
    PENALTY_SHED = 50.0    # 削负荷惩罚 (极高，保证刚性需求)
    PENALTY_SHIFT = 0.02   # 负荷转移微小惩罚 (防止震荡)

    prob = pulp.LpProblem("Microgrid_Synergy_Final", pulp.LpMinimize)

    # 1. 基础变量定义
    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    P_shed = pulp.LpVariable.dicts("P_shed", T, lowBound=0)
    P_curtail = pulp.LpVariable.dicts("P_curtail", T, lowBound=0)
    P_shift_up = pulp.LpVariable.dicts("P_shift_up", T, lowBound=0, upBound=shift_cap)
    P_shift_down = pulp.LpVariable.dicts("P_shift_down", T, lowBound=0, upBound=shift_cap)

    U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)
    U_grid_buy = (
        pulp.LpVariable.dicts("U_grid_buy", T, cat=pulp.LpBinary)
        if use_grid_mutex
        else None
    )

    # ================= 核心优化：EV 变量真降维 =================
    # 仅为车辆在站的时间步 (i, t) 创建变量
    valid_ev_keys = []
    evs_at_t = {t: [] for t in T}  # 预计算每个时间步在站的车辆索引，加速功率平衡构建
    
    for i, ev in enumerate(ev_sessions):
        for t in ev["park_ts"]:
            valid_ev_keys.append((i, t))
            evs_at_t[t].append(i)

    # 空列表时部分 PuLP 版本对 dicts 行为不一致，显式分支避免构建失败
    if valid_ev_keys:
        P_ev_ch = pulp.LpVariable.dicts("P_ev_ch", valid_ev_keys, lowBound=0)
        P_ev_dis = pulp.LpVariable.dicts("P_ev_dis", valid_ev_keys, lowBound=0)
        E_ev = pulp.LpVariable.dicts("E_ev", valid_ev_keys, lowBound=0)
    else:
        P_ev_ch = {}
        P_ev_dis = {}
        E_ev = {}
    # ===========================================================

    deg_cost = float(ess.get("degradation_cost_cny_per_kwh", 0.02))

    # 2. 目标函数
    prob += pulp.lpSum(
        data["buy_price"][t] * P_buy[t] * dt
        - data["sell_price"][t] * P_sell[t] * dt
        + PENALTY_CURTAIL * P_curtail[t] * dt
        + PENALTY_SHED * P_shed[t] * dt
        + PENALTY_SHIFT * (P_shift_up[t] + P_shift_down[t]) * dt
        + deg_cost * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2
        for t in T
    )

    # 3. 约束条件
    for t in T:
        actual_shift = P_shift_up[t] - P_shift_down[t]
        
        # 仅对当前时刻在站的 EV 进行求和
        if evs_at_t[t]:
            total_ev_ch = pulp.lpSum(P_ev_ch[(i, t)] for i in evs_at_t[t])
            total_ev_dis = pulp.lpSum(P_ev_dis[(i, t)] for i in evs_at_t[t])
        else:
            total_ev_ch = 0
            total_ev_dis = 0

        pv_net = data["pv_power"][t] - P_curtail[t]
        prob += (
            pv_net + P_buy[t] + P_ess_dis[t] + total_ev_dis
            == data["load_power"][t] + actual_shift - P_shed[t] + P_sell[t] + P_ess_ch[t] + total_ev_ch
        ), f"Power_Balance_{t}"

        if use_grid_mutex and U_grid_buy is not None:
            prob += P_buy[t] <= data["p_imp_max"][t] * U_grid_buy[t], f"Grid_buy_bm_{t}"
            prob += P_sell[t] <= data["p_exp_max"][t] * (1 - U_grid_buy[t]), f"Grid_sell_bm_{t}"
        else:
            prob += P_buy[t] <= data["p_imp_max"][t], f"Imp_cap_{t}"
            prob += P_sell[t] <= data["p_exp_max"][t], f"Exp_cap_{t}"

        prob += P_ess_ch[t] <= float(ess["max_charge_power_kw"]) * U_ess_ch[t], f"ESS_ch_bm_{t}"
        prob += P_ess_dis[t] <= float(ess["max_discharge_power_kw"]) * (1 - U_ess_ch[t]), f"ESS_dis_bm_{t}"
        prob += P_curtail[t] <= data["pv_power"][t], f"Curt_ub_{t}"
        prob += P_shed[t] <= data["load_power"][t] + shift_cap, f"Shed_ub_{t}"

        eta_ch = float(ess["charge_efficiency"])
        eta_dis = float(ess["discharge_efficiency"])
        if t == 0:
            prob += (
                E_ess[t]
                == float(ess["initial_energy_kwh"])
                + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
            ), f"ESS_soc_{t}"
        else:
            prob += (
                E_ess[t]
                == E_ess[t - 1] + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
            ), f"ESS_soc_{t}"
        prob += E_ess[t] >= float(ess["min_energy_kwh"]), f"ESS_emin_{t}"
        prob += E_ess[t] <= float(ess["max_energy_kwh"]), f"ESS_emax_{t}"

    prob += E_ess[n - 1] >= float(ess["initial_energy_kwh"]), "Terminal_SOC"

    steps_per_day = max(1, int(round(24.0 / dt)))
    for day in range(int(np.ceil(n / steps_per_day))):
        start_t = day * steps_per_day
        end_t = min((day + 1) * steps_per_day, n)
        if start_t >= n:
            break
        prob += (
            pulp.lpSum(P_shift_up[t] - P_shift_down[t] for t in range(start_t, end_t)) == 0
        ), f"Daily_shift_{day}"

    # 4. EV：功率限 + 仅在在站时段的电量状态递推、容量/下限、离站电量目标
    for i, ev in enumerate(ev_sessions):
        park_vars = sorted(t for t in ev["park_ts"] if (i, t) in P_ev_ch)
        if not park_vars:
            continue
        e0 = float(ev["e_initial_kwh"])
        ecap = float(ev["e_cap_kwh"])
        emin = float(ev["e_min_kwh"])
        ech, edis = float(ev["eta_ch"]), float(ev["eta_dis"])
        ereq = float(ev["e_required_departure_kwh"])

        for t in park_vars:
            prob += P_ev_ch[(i, t)] <= ev["p_ch_max"], f"EV{i}_ch_{t}"
            if ev["v2b_allowed"] and ev["p_dis_max"] > 0:
                prob += P_ev_dis[(i, t)] <= ev["p_dis_max"], f"EV{i}_dis_{t}"
            else:
                prob += P_ev_dis[(i, t)] == 0, f"EV{i}_nov2b_{t}"
            prob += E_ev[(i, t)] <= ecap, f"EV{i}_Emax_{t}"
            prob += E_ev[(i, t)] >= emin, f"EV{i}_Emin_{t}"

        for j, t in enumerate(park_vars):
            if j == 0:
                prob += (
                    E_ev[(i, t)]
                    == e0
                    + (ech * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / edis) * dt
                ), f"EV{i}_soc_{t}"
            else:
                t_prev = park_vars[j - 1]
                if t != t_prev + 1:
                    raise ValueError(
                        f"EV session {ev['id']} 在站时段非连续 (t={t}, t_prev={t_prev})，"
                        "需扩展递推；当前数据应为连续停靠。"
                    )
                prob += (
                    E_ev[(i, t)]
                    == E_ev[(i, t_prev)]
                    + (ech * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / edis) * dt
                ), f"EV{i}_soc_{t}"
        t_last = park_vars[-1]
        prob += E_ev[(i, t_last)] >= ereq, f"EV{i}_departure_min_energy"

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=cbc_msg)
    try:
        prob.solve(solver)
    except Exception as exc:
        raise RuntimeError(f"CBC 求解调用失败: {exc}") from exc

    obj_val: float | None = None
    if prob.status == pulp.LpStatusOptimal:
        try:
            obj_val = float(pulp.value(prob.objective))
        except (TypeError, ValueError):
            obj_val = None

    total_ev_charge_kwh = sum(_var_float(P_ev_ch[k]) for k in valid_ev_keys) * dt
    total_ev_discharge_kwh = sum(_var_float(P_ev_dis[k]) for k in valid_ev_keys) * dt

    ev_gaps_kwh: list[float] = []
    for i, ev in enumerate(ev_sessions):
        park_vars = sorted(t for t in ev["park_ts"] if (i, t) in E_ev)
        if not park_vars:
            continue
        t_last = park_vars[-1]
        e_end = _var_float(E_ev.get((i, t_last)))
        ev_gaps_kwh.append(e_end - float(ev["e_required_departure_kwh"]))

    # 提取结果（任意求解状态均写出，避免 .value() 抛错）
    results = {
        "timestamp": data["timestamps"],
        "P_buy": [_var_float(P_buy[t]) for t in T],
        "P_sell": [_var_float(P_sell[t]) for t in T],
        "P_ess_ch": [_var_float(P_ess_ch[t]) for t in T],
        "P_ess_dis": [_var_float(P_ess_dis[t]) for t in T],
        "E_ess": [_var_float(E_ess[t]) for t in T],
        "P_shift_up": [_var_float(P_shift_up[t]) for t in T],
        "P_shift_down": [_var_float(P_shift_down[t]) for t in T],
        "P_shift": [
            _var_float(P_shift_up[t]) - _var_float(P_shift_down[t]) for t in T
        ],
        "P_shed": [_var_float(P_shed[t]) for t in T],
        "P_curtail": [_var_float(P_curtail[t]) for t in T],
        "P_ev_ch_total": [
            sum(_var_float(P_ev_ch.get((i, t))) for i in evs_at_t[t])
            if evs_at_t[t]
            else 0.0
            for t in T
        ],
        "P_ev_dis_total": [
            sum(_var_float(P_ev_dis.get((i, t))) for i in evs_at_t[t])
            if evs_at_t[t]
            else 0.0
            for t in T
        ],
    }

    summary = _compute_operational_summary(
        data,
        results,
        obj_val,
        ev_sessions,
        ev_gaps_kwh,
        total_ev_charge_kwh=total_ev_charge_kwh,
        total_ev_discharge_kwh=total_ev_discharge_kwh,
    )
    return prob, results, obj_val, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="p_1_2_final PuLP 对齐版 (真降维优化版)")
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument(
        "--no-skip-infeasible-ev",
        action="store_true",
        help="保留物理不可行 EV（易导致整体不可行）",
    )
    parser.add_argument("--no-grid-mutex", action="store_true")
    parser.add_argument("--time-limit", type=int, default=600)
    parser.add_argument(
        "--quiet-cbc",
        action="store_true",
        help="关闭 CBC 控制台输出（仍求解）",
    )
    args = parser.parse_args()

    root = _REPO_ROOT
    if not (root / "data").is_dir():
        print(f"错误：未找到数据目录: {root}", file=sys.stderr)
        return 2

    try:
        data = load_problem_data(
            root,
            args.max_periods,
            skip_infeasible_ev=not args.no_skip_infeasible_ev,
        )
    except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
        print(f"数据加载失败: {exc}", file=sys.stderr)
        return 2

    ev_skipped = data.get("ev_skipped") or []
    if ev_skipped:
        by_reason: dict[str, int] = {}
        for s in ev_skipped:
            r = str(s.get("reason", "unknown"))
            by_reason[r] = by_reason.get(r, 0) + 1
        print(
            f"[EV] 已从模型剔除的 session 数: {len(ev_skipped)}；按原因: {by_reason}",
            file=sys.stderr,
        )
        for s in ev_skipped:
            sid = s.get("session_id", "?")
            reason = s.get("reason", "")
            extra = {k: v for k, v in s.items() if k not in ("session_id", "reason")}
            print(f"  - {sid} | {reason} | {extra}", file=sys.stderr)

    print(
        f"T={data['n']}, EV(建模)={len(data['ev_sessions'])}, EV(剔除)={len(ev_skipped)}",
        file=sys.stderr,
    )

    try:
        prob, results, obj, summary = build_and_solve(
            data,
            use_grid_mutex=not args.no_grid_mutex,
            time_limit_s=args.time_limit,
            cbc_msg=not args.quiet_cbc,
        )
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"建模或求解失败: {exc}", file=sys.stderr)
        return 2

    try:
        st = pulp.LpStatus[prob.status]
    except (IndexError, TypeError, KeyError):
        st = str(prob.status)
    print(f"求解状态: {st}")
    summary["solver_status"] = st

    out_dir = root / "results" / "problem1_pulp_enhanced"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "p_1_2_final_timeseries.csv"
        pd.DataFrame(results).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"已写出: {out_csv}")
        summary_path = out_dir / "p_1_2_final_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写出: {summary_path}")
    except OSError as exc:
        print(f"写出 CSV/Summary 失败: {exc}", file=sys.stderr)
        return 2

    if obj is not None:
        print(f"最优目标值: {obj:.4f} 元")
        try:
            kpis = {
                "objective_value_cny": round(obj, 4),
                "solver_status": st,
                "summary_metrics_path": "p_1_2_final_summary.json",
            }
            (out_dir / "p_1_2_final_kpis.json").write_text(
                json.dumps(kpis, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            print(f"写出 KPI 失败: {exc}", file=sys.stderr)
        return 0

    print("未得到最优解（不可行/超时等）。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
