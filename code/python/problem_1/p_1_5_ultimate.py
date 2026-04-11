"""
问题1 园区微电网协同调度 — 1.5 终极融合版 (Ultimate Edition)

融合了 1.2 与 1.4 版本的全部优势：
1. 真降维优化：仅在 EV 在站时段创建变量，极大加速求解。
2. 矩阵驱动：支持时变的 EV 可用性、充放电功率上限矩阵。
3. 多区块柔性负荷：精细化建模建筑负荷的平移、恢复、削减与能量反弹。
4. 基础设施约束：加入充电桩并发数、V2G 双向桩数量的 0-1 整数约束。
5. 碳排放经济性：引入电网时变碳排放因子与碳价。
6. 详尽的 KPI 与不可行 EV 剔除报告。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pulp

import objective_reconciliation as obr

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

# =========================
# 1. 数据读取与解析
# =========================

def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少文件: {path}")
    return pd.read_csv(path)

def _pick_existing(base: Path, candidates: list[str], *, required: bool = True) -> Path | None:
    for name in candidates:
        path = base / name
        if path.is_file():
            return path
    if required:
        raise FileNotFoundError(f"缺少文件，候选项: {candidates}")
    return None

def _parse_parameter_table(df: pd.DataFrame) -> dict[str, float]:
    if not {"parameter", "value"}.issubset(df.columns):
        raise KeyError("asset 表需包含 parameter, value 列")
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        key = str(row["parameter"]).strip()
        try:
            out[key] = float(row["value"])
        except (TypeError, ValueError):
            continue
    return out


def _matrix_col_to_ev_index(col: str) -> int:
    c = str(col).strip()
    if not c.startswith("ev_"):
        raise ValueError(f"无法解析 EV 矩阵列名: {col}")
    return int(c.split("_", 1)[1])


def load_problem_data(base_dir: str | Path, max_periods: int | None = None, skip_infeasible: bool = True) -> dict[str, Any]:
    base = Path(base_dir).resolve()
    inputs_dir = base / "data" / "processed" / "final_model_inputs"
    proc_dir = base / "data" / "processed"
    if not inputs_dir.is_dir():
        raise FileNotFoundError(f"缺少目录: {inputs_dir}")

    # 读取核心时序数据
    df_ts = _read_csv(_pick_existing(inputs_dir, ["timeslot_parameters.csv", "timeseries_15min.csv", "load_profile.csv"]))
    n = len(df_ts)
    if max_periods is not None:
        n = min(n, int(max_periods))
        df_ts = df_ts.iloc[:n].copy()

    timestamps = (
        df_ts["timestamp"].astype(str).tolist()
        if "timestamp" in df_ts.columns
        else [f"t{t + 1:03d}" for t in range(n)]
    )

    asset_csv = base / "data" / "raw" / "asset_parameters.csv"
    asset: dict[str, float] = {}
    if asset_csv.is_file():
        asset = _parse_parameter_table(_read_csv(asset_csv))
    with open(inputs_dir / "ess_params.json", "r", encoding="utf-8") as f:
        ess_json = json.load(f)
    dt = float(ess_json.get("time_step_hours", asset.get("default_time_step_hours", 0.25)))

    df_flex = _read_csv(
        _pick_existing(
            inputs_dir,
            [
                "flexible_load_parameters_normalized.csv",
                "flexible_load_parameters.csv",
                "flexible_load_params_clean.csv",
            ],
        )
    )
    df_ev = _read_csv(_pick_existing(inputs_dir, ["ev_sessions_indexed.csv", "ev_sessions_model_ready.csv"]))
    if "ev_index" not in df_ev.columns:
        raise KeyError("ev_sessions 表需含 ev_index 列以与矩阵 ev_k 对齐")

    df_av = _read_csv(inputs_dir / "ev_availability_matrix.csv").iloc[:n]
    df_ch = _read_csv(inputs_dir / "ev_charge_power_limit_matrix_kw.csv").iloc[:n]
    df_dis = _read_csv(inputs_dir / "ev_discharge_power_limit_matrix_kw.csv").iloc[:n]

    ev_ids_matrix = [c for c in df_av.columns if c not in ("slot_id", "timestamp")]
    matrix_indices = [_matrix_col_to_ev_index(c) for c in ev_ids_matrix]
    df_ev = df_ev.sort_values("ev_index").reset_index(drop=True)
    ev_index_series = df_ev["ev_index"].astype(int)
    if set(ev_index_series.tolist()) != set(matrix_indices):
        raise ValueError("ev_sessions 的 ev_index 与矩阵列 ev_k 集合不一致")
    df_ev = df_ev.set_index(ev_index_series).loc[matrix_indices].reset_index(drop=True)
    
    # 柔性负荷区块解析
    building_blocks: list[dict[str, Any]] = []
    for _, row in df_flex.iterrows():
        block = str(row.get("load_block", "total_native")).strip()
        load_col = f"{block}_kw" if f"{block}_kw" in df_ts.columns else "total_native_load_kw"
        if load_col not in df_ts.columns:
            raise KeyError(f"时序表缺少负荷列: {load_col}")
        building_blocks.append(
            {
                "name": block,
                "load": df_ts[load_col].to_numpy(dtype=float),
                "noninterruptible_share": float(row.get("noninterruptible_share", 0.8)),
                "max_shiftable_kw": float(row.get("max_shiftable_kw", 200.0)),
                "max_sheddable_kw": float(row.get("max_sheddable_kw", 50.0)),
                "rebound_factor": max(1.0, float(row.get("rebound_factor", 1.2))),
                "penalty_not_served": float(row.get("penalty_cny_per_kwh_not_served", 50.0)),
            }
        )
    total_native = np.sum([b["load"] for b in building_blocks], axis=0)

    # EV 矩阵处理与可行性校验（矩阵列 ev_k 对应 ev_index=k；截断 horizon 用 CSV 到离与矩阵求交）
    av_mat = np.where(df_av[ev_ids_matrix].to_numpy(dtype=float) > 0.5, 1.0, 0.0)
    ch_mat = df_ch[ev_ids_matrix].to_numpy(dtype=float) * av_mat
    dis_mat = df_dis[ev_ids_matrix].to_numpy(dtype=float) * av_mat

    ev_sessions: list[dict[str, Any]] = []
    ev_skipped: list[dict[str, Any]] = []
    for j in range(len(df_ev)):
        row = df_ev.iloc[j]
        matrix_col = ev_ids_matrix[j]
        sid = str(row["session_id"])
        cap = float(row["battery_capacity_kwh"])
        e_init = float(row["initial_energy_kwh"])
        e_req = float(row["required_energy_at_departure_kwh"])
        v2b = int(row.get("v2b_allowed", 1))
        eta_ch = float(row.get("charge_efficiency", 0.95))
        eta_dis = float(row.get("discharge_efficiency", 0.95))

        if not v2b:
            dis_mat[:, j] = 0.0

        park_from_csv: list[int] = []
        if "arrival_slot" in df_ev.columns and "departure_slot" in df_ev.columns:
            arr = int(row["arrival_slot"])
            dep = int(row["departure_slot"])
            if dep > arr:
                arr_c = max(1, arr)
                dep_c = min(dep, n + 1)
                for slot in range(arr_c, dep_c):
                    t = slot - 1
                    if 0 <= t < n:
                        park_from_csv.append(t)
        if not park_from_csv:
            ev_skipped.append({"session_id": sid, "reason": "session_outside_selected_horizon"})
            continue

        park_ts = [t for t in park_from_csv if av_mat[t, j] > 0.5]
        if not park_ts:
            ev_skipped.append({"session_id": sid, "reason": "no_matrix_availability_during_declared_parking"})
            continue

        max_gain = float((ch_mat[park_ts, j] * eta_ch * dt).sum())

        ereq_model = float(e_req)
        if "arrival_slot" in df_ev.columns and "departure_slot" in df_ev.columns:
            arr0 = max(1, int(row["arrival_slot"]))
            dep0 = int(row["departure_slot"])
            full_dwell = max(1, dep0 - arr0)
            last_csv_t = dep0 - 2
            if park_ts[-1] < last_csv_t and full_dwell > 0:
                frac = len(park_ts) / float(full_dwell)
                ereq_model = float(e_init) + (float(e_req) - float(e_init)) * min(1.0, frac)

        if e_init - cap > 1e-6:
            ev_skipped.append({"session_id": sid, "reason": "initial_energy_exceeds_capacity"})
            continue
        if ereq_model - cap > 1e-6:
            if skip_infeasible:
                ev_skipped.append({"session_id": sid, "reason": "required_energy_exceeds_capacity"})
                continue
        if ereq_model - e_init > max_gain + 1e-3 and skip_infeasible:
            ev_skipped.append(
                {
                    "session_id": sid,
                    "reason": "required_increment_exceeds_slot_charge_upper_bound",
                    "req_gain": round(ereq_model - e_init, 3),
                    "max_gain": round(max_gain, 3),
                }
            )
            continue

        ev_sessions.append(
            {
                "index": len(ev_sessions),
                "matrix_col": matrix_col,
                "session_id": sid,
                "battery_capacity_kwh": cap,
                "initial_energy_kwh": e_init,
                "required_energy_kwh": ereq_model,
                "eta_ch": eta_ch,
                "eta_dis": eta_dis,
                "deg_cost": float(row.get("degradation_cost_cny_per_kwh_throughput", 0.02)),
                "park_ts": park_ts,
                "charge_limits_kw": ch_mat[:, j].copy(),
                "discharge_limits_kw": dis_mat[:, j].copy(),
                "v2b_allowed": v2b,
            }
        )

    if ev_sessions:
        keep_idx = [ev_ids_matrix.index(ev["matrix_col"]) for ev in ev_sessions]
        av_mat = av_mat[:, keep_idx]
        ch_mat = ch_mat[:, keep_idx]
        dis_mat = dis_mat[:, keep_idx]
        for k, ev in enumerate(ev_sessions):
            ev["charge_limits_kw"] = ch_mat[:, k].copy()
            ev["discharge_limits_kw"] = dis_mat[:, k].copy()
    else:
        av_mat = np.zeros((n, 0))
        ch_mat = np.zeros((n, 0))
        dis_mat = np.zeros((n, 0))

    price_csv = _read_csv(proc_dir / "price_profile.csv").iloc[:n]
    grid_csv = _read_csv(proc_dir / "grid_limits.csv").iloc[:n]
    pv_csv = _read_csv(inputs_dir / "pv_profile.csv").iloc[:n]
    pv_upper = pv_csv["pv_available_kw"].to_numpy(dtype=float)
    pv_cap = float(asset.get("pv_inverter_limit_kw", float(np.max(pv_upper)) if len(pv_upper) else 0.0))
    pv_upper = np.minimum(pv_upper, pv_cap)

    grid_carbon = df_ts["grid_carbon_kg_per_kwh"].to_numpy(dtype=float) if "grid_carbon_kg_per_kwh" in df_ts.columns else np.zeros(n, dtype=float)

    ess_deg = float(
        asset.get(
            "stationary_battery_degradation_cost_cny_per_kwh_throughput",
            ess_json.get("degradation_cost_cny_per_kwh", 0.02),
        )
    )

    return {
        "n": n,
        "delta_t": dt,
        "timestamps": timestamps,
        "buy_price": price_csv["grid_buy_price_cny_per_kwh"].to_numpy(dtype=float),
        "sell_price": price_csv["grid_sell_price_cny_per_kwh"].to_numpy(dtype=float),
        "grid_carbon": grid_carbon,
        "pv_upper": pv_upper,
        "p_imp_max": grid_csv["grid_import_limit_kw"].to_numpy(dtype=float),
        "p_exp_max": grid_csv["grid_export_limit_kw"].to_numpy(dtype=float),
        "building_blocks": building_blocks,
        "total_native_load": total_native,
        "ess": {
            "initial_energy_kwh": float(ess_json["initial_energy_kwh"]),
            "min_energy_kwh": float(ess_json["min_energy_kwh"]),
            "max_energy_kwh": float(ess_json["max_energy_kwh"]),
            "max_charge_power_kw": float(ess_json["max_charge_power_kw"]),
            "max_discharge_power_kw": float(ess_json["max_discharge_power_kw"]),
            "charge_efficiency": float(ess_json["charge_efficiency"]),
            "discharge_efficiency": float(ess_json["discharge_efficiency"]),
            "degradation_cost_cny_per_kwh": ess_deg,
        },
        "ev_assets": {
            "bidirectional_charger_count": int(round(asset.get("ev_bidirectional_charger_count", 0))),
            "unidirectional_charger_count": int(round(asset.get("ev_unidirectional_charger_count", 0))),
            "max_simultaneous_ev_connections": int(round(asset.get("max_simultaneous_ev_connections", 0))),
        },
        "ev_sessions": ev_sessions,
        "ev_skipped": ev_skipped,
    }

# =========================
# 2. 核心优化模型构建
# =========================

def build_and_solve(
    data: dict,
    *,
    carbon_price: float = 0.0,
    use_grid_mutex: bool = True,
    enforce_ev_limit: bool = True,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
    solver_msg: bool = True,
) -> tuple[pulp.LpProblem, float | None, dict[str, Any] | None]:
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    ess, buildings, ev_sessions = data["ess"], data["building_blocks"], data["ev_sessions"]

    prob = pulp.LpProblem("Microgrid_Ultimate_1_5", pulp.LpMinimize)

    # 全局变量
    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_pv_use = pulp.LpVariable.dicts("P_pv_use", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)
    U_grid_buy = pulp.LpVariable.dicts("U_grid_buy", T, cat=pulp.LpBinary) if use_grid_mutex else None

    # 建筑柔性负荷变量
    BT = [(b["name"], t) for b in buildings for t in T]
    P_shift_out = pulp.LpVariable.dicts("P_shift_out", BT, lowBound=0)
    P_recover = pulp.LpVariable.dicts("P_recover", BT, lowBound=0)
    P_shed = pulp.LpVariable.dicts("P_shed", BT, lowBound=0)
    E_backlog = pulp.LpVariable.dicts("E_backlog", BT, lowBound=0)

    # EV 真降维稀疏变量
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
        Y_ev_conn = pulp.LpVariable.dicts("Y_ev_conn", ev_keys, cat=pulp.LpBinary) if enforce_ev_limit else None
        Y_ev_dis = pulp.LpVariable.dicts("Y_ev_dis", ev_keys, cat=pulp.LpBinary) if enforce_ev_limit else None
    else:
        P_ev_ch = {}
        P_ev_dis = {}
        E_ev = {}
        Y_ev_conn = None
        Y_ev_dis = None

    # 目标函数：购电 - 售电 + 碳排放 + 弃光惩罚 + 储能退化 + 负荷惩罚 + EV退化
    PENALTY_CURTAIL = 0.5
    PENALTY_SHIFT = 0.02

    obj_terms = []
    for t in T:
        obj_terms.append(data["buy_price"][t] * P_buy[t] * dt)
        obj_terms.append(-data["sell_price"][t] * P_sell[t] * dt)
        obj_terms.append(carbon_price * data["grid_carbon"][t] * P_buy[t] * dt)
        obj_terms.append(PENALTY_CURTAIL * (data["pv_upper"][t] - P_pv_use[t]) * dt)
        obj_terms.append(ess["degradation_cost_cny_per_kwh"] * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2)

    for b in buildings:
        for t in T:
            obj_terms.append(PENALTY_SHIFT * (P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)]) * dt)
            obj_terms.append(b["penalty_not_served"] * P_shed[(b["name"], t)] * dt)

    for i, ev in enumerate(ev_sessions):
        for t in ev_ts_by_i[i]:
            if ev_keys:
                obj_terms.append(ev["deg_cost"] * (P_ev_ch[(i, t)] + P_ev_dis[(i, t)]) * dt / 2)

    prob += pulp.lpSum(obj_terms)

    # 约束条件
    for t in T:
        served_load = pulp.lpSum(b["load"][t] - P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)] - P_shed[(b["name"], t)] for b in buildings)
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
            prob += E_ess[t] == ess["initial_energy_kwh"] + (ess["charge_efficiency"] * P_ess_ch[t] - P_ess_dis[t] / ess["discharge_efficiency"]) * dt
        else:
            prob += E_ess[t] == E_ess[t-1] + (ess["charge_efficiency"] * P_ess_ch[t] - P_ess_dis[t] / ess["discharge_efficiency"]) * dt
        prob += E_ess[t] >= ess["min_energy_kwh"]
        prob += E_ess[t] <= ess["max_energy_kwh"]

    prob += E_ess[n - 1] >= ess["initial_energy_kwh"], "Terminal_SOC"

    # 建筑柔性负荷约束
    for b in buildings:
        name = b["name"]
        for t in T:
            flex_cap = max(0.0, (1 - b["noninterruptible_share"]) * b["load"][t])
            prob += P_shift_out[(name, t)] <= min(b["max_shiftable_kw"], flex_cap)
            prob += P_shed[(name, t)] <= min(b["max_sheddable_kw"], flex_cap)
            prob += P_shift_out[(name, t)] + P_shed[(name, t)] <= flex_cap
            prob += P_recover[(name, t)] <= float(b["rebound_factor"]) * b["max_shiftable_kw"]
            
            if t == 0:
                prob += E_backlog[(name, t)] == P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / b["rebound_factor"]
            else:
                prob += E_backlog[(name, t)] == E_backlog[(name, t-1)] + P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / b["rebound_factor"]
        prob += E_backlog[(name, n - 1)] == 0

    # EV 矩阵约束与并发约束
    for i, ev in enumerate(ev_sessions):
        ts = ev_ts_by_i[i]
        if not ts or not ev_keys:
            continue
        for pos, t in enumerate(ts):
            if enforce_ev_limit and Y_ev_conn is not None and Y_ev_dis is not None:
                prob += Y_ev_dis[(i, t)] <= Y_ev_conn[(i, t)]
                prob += P_ev_ch[(i, t)] <= ev["charge_limits_kw"][t] * (Y_ev_conn[(i, t)] - Y_ev_dis[(i, t)])
                if ev["discharge_limits_kw"][t] > 0 and ev["v2b_allowed"]:
                    prob += P_ev_dis[(i, t)] <= ev["discharge_limits_kw"][t] * Y_ev_dis[(i, t)]
                else:
                    prob += Y_ev_dis[(i, t)] == 0
                    prob += P_ev_dis[(i, t)] == 0
            else:
                prob += P_ev_ch[(i, t)] <= ev["charge_limits_kw"][t]
                if ev["v2b_allowed"]:
                    prob += P_ev_dis[(i, t)] <= ev["discharge_limits_kw"][t]
                else:
                    prob += P_ev_dis[(i, t)] == 0

            if pos == 0:
                prob += E_ev[(i, t)] == ev["initial_energy_kwh"] + (
                    ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]
                ) * dt
            else:
                prev_t = ts[pos - 1]
                if t != prev_t + 1:
                    raise ValueError(
                        f"EV {ev['session_id']} 在站时段非连续 (t={t}, prev={prev_t})，与 SOC 递推不兼容。"
                    )
                prob += E_ev[(i, t)] == E_ev[(i, prev_t)] + (
                    ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]
                ) * dt

            prob += E_ev[(i, t)] >= 0
            prob += E_ev[(i, t)] <= ev["battery_capacity_kwh"]

        prob += E_ev[(i, ts[-1])] >= ev["required_energy_kwh"]

    if enforce_ev_limit and ev_keys and Y_ev_conn is not None:
        conn_cap = int(data["ev_assets"].get("max_simultaneous_ev_connections", 0))
        bidir_cap = int(data["ev_assets"].get("bidirectional_charger_count", 0))
        uni_cap = int(data["ev_assets"].get("unidirectional_charger_count", 0))
        if conn_cap <= 0:
            conn_cap = bidir_cap + uni_cap
        if conn_cap <= 0:
            conn_cap = max(1, len(ev_sessions))
        for t in T:
            if ev_keys_by_t[t]:
                prob += pulp.lpSum(Y_ev_conn[k] for k in ev_keys_by_t[t]) <= conn_cap
                if bidir_cap > 0:
                    prob += pulp.lpSum(Y_ev_dis[k] for k in ev_keys_by_t[t]) <= bidir_cap

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=solver_msg)
    try:
        prob.solve(solver)
    except Exception as exc:
        raise RuntimeError(f"CBC 求解失败: {exc}") from exc

    obj_val: float | None = None
    if prob.status == pulp.LpStatusOptimal:
        try:
            v = pulp.value(prob.objective)
            obj_val = float(v) if v is not None else None
        except (TypeError, ValueError):
            obj_val = None

    solve_ctx: dict[str, Any] | None = None
    if prob.status == pulp.LpStatusOptimal:
        solve_ctx = {
            "carbon_price": carbon_price,
            "PENALTY_CURTAIL": PENALTY_CURTAIL,
            "PENALTY_SHIFT": PENALTY_SHIFT,
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


def extract_solution_timeseries(data: dict[str, Any], ctx: dict[str, Any]) -> pd.DataFrame:
    """将最优解导出为与事件分析模块对齐的 15min 时序表（不改变优化模型，仅后处理）。"""
    n = data["n"]
    dt = data["delta_t"]
    buildings: list[dict[str, Any]] = ctx["buildings"]
    ev_keys_by_t: dict[int, list[tuple[int, int]]] = ctx["ev_keys_by_t"]

    rows: list[dict[str, Any]] = []
    for t in range(n):
        p_ev_dis = sum(obr.var_float(ctx["P_ev_dis"][k]) for k in ev_keys_by_t.get(t, []))
        p_ev_ch = sum(obr.var_float(ctx["P_ev_ch"][k]) for k in ev_keys_by_t.get(t, []))
        p_shift = p_rec = p_shed = 0.0
        for b in buildings:
            name = b["name"]
            key = (name, t)
            p_shift += obr.var_float(ctx["P_shift_out"][key])
            p_rec += obr.var_float(ctx["P_recover"][key])
            p_shed += obr.var_float(ctx["P_shed"][key])
        p_pv = obr.var_float(ctx["P_pv_use"][t])
        pv_up = float(data["pv_upper"][t])
        rows.append(
            {
                "timestamp": data["timestamps"][t],
                "P_buy_kw": obr.var_float(ctx["P_buy"][t]),
                "P_sell_kw": obr.var_float(ctx["P_sell"][t]),
                "P_ess_dis_kw": obr.var_float(ctx["P_ess_dis"][t]),
                "P_ess_ch_kw": obr.var_float(ctx["P_ess_ch"][t]),
                "P_ev_dis_total_kw": p_ev_dis,
                "P_ev_ch_total_kw": p_ev_ch,
                "P_shift_out_total_kw": p_shift,
                "P_recover_total_kw": p_rec,
                "building_flex_power_kw": p_shift + p_rec,
                "P_shed_total_kw": p_shed,
                "P_pv_use_kw": p_pv,
                "pv_upper_kw": pv_up,
                "pv_curtail_kw": max(0.0, pv_up - p_pv),
                "delta_t_h": dt,
            }
        )
    return pd.DataFrame(rows)


# =========================
# 3. 主函数
# =========================

def main() -> int:
    parser = argparse.ArgumentParser(description="1.5 终极融合版")
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument("--no-grid-mutex", action="store_true")
    parser.add_argument("--no-ev-limit", action="store_true")
    parser.add_argument("--no-skip-infeasible-ev", action="store_true")
    parser.add_argument("--quiet-cbc", action="store_true")
    parser.add_argument("--time-limit", type=int, default=600, help="CBC 时间上限（秒）")
    parser.add_argument("--gap-rel", type=float, default=0.01, help="CBC 相对最优间隙")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="最优解时序 CSV 输出目录（默认: <repo>/results/problem1_ultimate）",
    )
    parser.add_argument(
        "--no-event-analysis",
        action="store_true",
        help="关闭特殊事件后处理（不写时序表与 event_response_summary）",
    )
    parser.add_argument(
        "--event-summary-csv",
        type=Path,
        default=None,
        help="event_response_summary.csv 路径（默认: <repo>/results/tables/event_response_summary.csv）",
    )
    parser.add_argument(
        "--event-methodology-md",
        type=Path,
        default=None,
        help="方法说明 Markdown 路径（默认: <repo>/docs/problem1_special_event_implicit_modeling.md）",
    )
    parser.add_argument(
        "--no-reconciliation-export",
        action="store_true",
        help="不写出附录目标对账表（CSV/Markdown）",
    )
    parser.add_argument(
        "--reconciliation-csv",
        type=Path,
        default=None,
        help="附录对账表 CSV（默认: <repo>/results/tables/objective_reconciliation_appendix.csv）",
    )
    parser.add_argument(
        "--reconciliation-md",
        type=Path,
        default=None,
        help="附录对账表 Markdown（默认: <repo>/results/tables/objective_reconciliation_appendix.md）",
    )
    args = parser.parse_args()

    print("正在加载 1.5 终极融合版模型数据...", file=sys.stderr)
    try:
        data = load_problem_data(
            _REPO_ROOT,
            args.max_periods,
            skip_infeasible=not args.no_skip_infeasible_ev,
        )
    except (FileNotFoundError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"数据加载失败: {exc}", file=sys.stderr)
        return 2

    print(
        f"数据加载完毕: T={data['n']} | EV建模={len(data['ev_sessions'])} | EV剔除={len(data['ev_skipped'])}",
        file=sys.stderr,
    )
    if data["ev_skipped"]:
        print(f"已剔除 EV session 数: {len(data['ev_skipped'])}", file=sys.stderr)

    print("正在构建并求解 MILP ...", file=sys.stderr)
    try:
        prob, obj, solve_ctx = build_and_solve(
            data,
            use_grid_mutex=not args.no_grid_mutex,
            enforce_ev_limit=not args.no_ev_limit,
            time_limit_s=args.time_limit,
            gap_rel=args.gap_rel,
            solver_msg=not args.quiet_cbc,
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"建模或求解失败: {exc}", file=sys.stderr)
        return 2

    try:
        st = pulp.LpStatus[prob.status]
    except (KeyError, IndexError, TypeError):
        st = str(prob.status)
    print(f"求解状态: {st}")
    if obj is not None and solve_ctx is not None:
        print(f"最优目标函数值（PuLP / 完整仿射目标）: {obj:.4f} 元")
        bd = obr.summarize_coordinated_costs(prob, data, solve_ctx)
        ac = bd["objective_affine_constant"]
        print(
            f"CBC 控制台 Objective value 常与之差一个仿射常数项（本模型约 {ac:.4f} 元）: "
            f"pulp.value - constant = {bd['objective_cbc_log_style']:.4f} 元"
        )
        print("—— 分项成本对账（与模型目标同口径，元）——")
        for k in (
            "grid_import_cost",
            "grid_export_revenue",
            "pv_curtail_penalty",
            "load_shed_penalty",
            "building_shift_penalty",
            "ess_degradation_cost",
            "ev_degradation_cost",
            "carbon_cost",
        ):
            print(f"  {k}: {bd[k]:.4f}")
        print(f"  objective_from_solver: {bd['objective_from_solver']:.4f}")
        print(f"  objective_recomputed_from_solution: {bd['objective_recomputed_from_solution']:.4f}")
        print(f"  objective_affine_constant (PuLP): {bd['objective_affine_constant']:.4f}")

        if not args.no_reconciliation_export:
            n_horizon = int(data["n"])
            tables_dir = (_REPO_ROOT / "results" / "tables").resolve()
            if n_horizon == 672:
                fw = tables_dir / "objective_reconciliation_fullweek.csv"
                obr.write_reconciliation_csv(fw, bd, decimals=6)
                print(f"全周正式对账: {fw}", file=sys.stderr)
                cmp_out = obr.try_write_fullweek_comparison(_REPO_ROOT)
                if cmp_out:
                    print(f"全周对比表: {cmp_out[0]}", file=sys.stderr)
                    print(f"全周对比说明: {cmp_out[1]}", file=sys.stderr)
            else:
                print(
                    f"提示: T={n_horizon}≠672，未写入 objective_reconciliation_fullweek.csv（请全周求解后再比对）。",
                    file=sys.stderr,
                )
            rec_csv = (
                args.reconciliation_csv.resolve()
                if args.reconciliation_csv is not None
                else (tables_dir / "objective_reconciliation_appendix.csv").resolve()
            )
            rec_md = (
                args.reconciliation_md.resolve()
                if args.reconciliation_md is not None
                else (tables_dir / "objective_reconciliation_appendix.md").resolve()
            )
            c_out, m_out = obr.write_appendix_reconciliation_files(bd, csv_path=rec_csv, md_path=rec_md)
            print(f"附录目标对账表: {c_out}", file=sys.stderr)
            print(f"附录目标对账表（Markdown）: {m_out}", file=sys.stderr)

        if not args.no_event_analysis:
            results_dir = (
                args.results_dir.resolve()
                if args.results_dir is not None
                else (_REPO_ROOT / "results" / "problem1_ultimate").resolve()
            )
            results_dir.mkdir(parents=True, exist_ok=True)
            ts_path = results_dir / "p_1_5_timeseries.csv"
            ts_df = extract_solution_timeseries(data, solve_ctx)
            ts_df.to_csv(ts_path, index=False, encoding="utf-8-sig")
            print(f"已写出最优解时序: {ts_path}", file=sys.stderr)

            era_path = _HERE / "event_response_analysis.py"
            spec = importlib.util.spec_from_file_location("event_response_analysis", era_path)
            if spec is None or spec.loader is None:
                print("无法加载 event_response_analysis.py，跳过事件汇总。", file=sys.stderr)
                return 0
            era = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(era)
            summary_csv = (
                args.event_summary_csv.resolve()
                if args.event_summary_csv is not None
                else (_REPO_ROOT / "results" / "tables" / "event_response_summary.csv").resolve()
            )
            methodology_md = (
                args.event_methodology_md.resolve()
                if args.event_methodology_md is not None
                else (_REPO_ROOT / "docs" / "problem1_special_event_implicit_modeling.md").resolve()
            )
            try:
                out_csv, out_md = era.run_event_response_pipeline(
                    repo_root=_REPO_ROOT,
                    timeseries_df=ts_df,
                    summary_csv=summary_csv,
                    methodology_md=methodology_md,
                    delta_t_hours=float(data["delta_t"]),
                )
                print(f"特殊事件响应汇总: {out_csv}", file=sys.stderr)
                print(f"方法说明: {out_md}", file=sys.stderr)
            except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
                print(f"事件响应分析失败（时序已保存）: {exc}", file=sys.stderr)
        return 0
    print("未能得到最优解。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())