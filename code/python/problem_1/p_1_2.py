"""
问题1 园区微电网协同调度 — 终极对齐版 (PuLP + CBC)
已对齐真实仓库路径、EV 字段 (arrival_slot)、并加入 Infeasible 自动跳过与 argparse
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少文件: {path}")
    return pd.read_csv(path)

def _read_series_csv(path: Path, column: str, n: int | None = None) -> np.ndarray:
    df = _read_csv(path)
    if column not in df.columns:
        raise KeyError(f"{path} 缺少列 {column}")
    arr = df[column].to_numpy(dtype=float)
    return arr[:n] if n is not None else arr

def load_problem_data(root: Path, max_periods: int | None = None, skip_infeasible_ev: bool = True) -> dict:
    # 路径对齐真实仓库结构
    base_inputs = root / "data" / "processed" / "final_model_inputs"
    base_processed = root / "data" / "processed"

    load_csv = base_inputs / "load_profile.csv"
    pv_csv = base_inputs / "pv_profile.csv"
    flex_csv = base_inputs / "flexible_load_params_clean.csv"
    ess_json = base_inputs / "ess_params.json"
    
    price_csv = base_processed / "price_profile.csv"
    grid_csv = base_processed / "grid_limits.csv"
    ev_csv = base_processed / "ev_sessions_model_ready.csv" # 使用 ready 版本

    df_load = _read_csv(load_csv)
    n = len(df_load)
    if max_periods is not None:
        n = min(n, int(max_periods))
        df_load = df_load.iloc[:n].copy()

    timestamps = df_load["timestamp"].astype(str).tolist() if "timestamp" in df_load.columns else [f"t{t+1:03d}" for t in range(n)]
    
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

    df_flex = _read_csv(flex_csv) if flex_csv.exists() else pd.DataFrame()
    shift_cap_kw = float(df_flex["max_shiftable_kw"].sum()) if len(df_flex) and "max_shiftable_kw" in df_flex.columns else 200.0

    # EV 数据读取与物理可行性校验
    ev_sessions = []
    if ev_csv.exists():
        df_ev = _read_csv(ev_csv)
        eta_ch = 0.95
        for _, row in df_ev.iterrows():
            # 字段对齐：arrival_slot / departure_slot
            start_idx = max(0, int(row.get('arrival_slot', 0)))
            end_idx = min(n - 1, int(row.get('departure_slot', 10)))
            
            if start_idx < n and end_idx > 0 and start_idx < end_idx:
                req_energy = float(row.get('target_energy_kwh', 20.0))
                p_ch_max = float(row.get('max_charge_kw', 7.0))
                
                # 物理可行性校验
                stay_steps = end_idx - start_idx
                max_possible_charge = stay_steps * dt * eta_ch * p_ch_max
                
                if skip_infeasible_ev and (req_energy > max_possible_charge + 1e-4):
                    print(f"⚠️ 跳过不可行 EV: {row['session_id']}, 需求 {req_energy:.2f}kWh > 极限 {max_possible_charge:.2f}kWh", file=sys.stderr)
                    continue
                
                ev_sessions.append({
                    "id": row['session_id'],
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "req_energy": req_energy,
                    "p_ch_max": p_ch_max,
                    "p_dis_max": float(row.get('max_discharge_kw', 7.0)),
                    "v2b_allowed": int(row.get('v2b_allowed', 1)),
                    "eta_ch": eta_ch, "eta_dis": 0.95
                })

    return {
        "n": n, "timestamps": timestamps, "delta_t": dt,
        "buy_price": buy_price, "sell_price": sell_price,
        "pv_power": pv_power, "load_power": load_power,
        "p_imp_max": p_imp_max, "p_exp_max": p_exp_max,
        "shift_cap_kw": shift_cap_kw, "ess": ess, "ev_sessions": ev_sessions
    }

def build_and_solve(data: dict, use_grid_mutex: bool = True, time_limit_s: int = 600):
    n, T, dt = data["n"], range(data["n"]), data["delta_t"]
    ess, shift_cap, ev_sessions = data["ess"], data["shift_cap_kw"], data["ev_sessions"]
    num_ev = len(ev_sessions)

    prob = pulp.LpProblem("Microgrid_Synergy_Final", pulp.LpMinimize)

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
    U_grid_buy = pulp.LpVariable.dicts("U_grid_buy", T, cat=pulp.LpBinary) if use_grid_mutex else None

    # 修复：使用 (i, t) 元组作为字典键
    ev_keys = [(i, t) for i in range(num_ev) for t in T]
    P_ev_ch = pulp.LpVariable.dicts("P_ev_ch", ev_keys, lowBound=0)
    P_ev_dis = pulp.LpVariable.dicts("P_ev_dis", ev_keys, lowBound=0)

    deg_cost = float(ess.get("degradation_cost_cny_per_kwh", 0.02))

    prob += pulp.lpSum(
        data["buy_price"][t] * P_buy[t] * dt
        - data["sell_price"][t] * P_sell[t] * dt
        + 0.5 * P_curtail[t] * dt
        + 50.0 * P_shed[t] * dt
        + 0.02 * (P_shift_up[t] + P_shift_down[t]) * dt
        + deg_cost * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2
        for t in T
    )

    for t in T:
        actual_shift = P_shift_up[t] - P_shift_down[t]
        total_ev_ch = pulp.lpSum(P_ev_ch[(i, t)] for i in range(num_ev))
        total_ev_dis = pulp.lpSum(P_ev_dis[(i, t)] for i in range(num_ev))

        pv_net = data["pv_power"][t] - P_curtail[t]
        prob += (
            pv_net + P_buy[t] + P_ess_dis[t] + total_ev_dis
            == data["load_power"][t] + actual_shift - P_shed[t] + P_sell[t] + P_ess_ch[t] + total_ev_ch
        ), f"Power_Balance_{t}"

        if use_grid_mutex:
            prob += P_buy[t] <= data["p_imp_max"][t] * U_grid_buy[t]
            prob += P_sell[t] <= data["p_exp_max"][t] * (1 - U_grid_buy[t])
        else:
            prob += P_buy[t] <= data["p_imp_max"][t]
            prob += P_sell[t] <= data["p_exp_max"][t]

        prob += P_ess_ch[t] <= float(ess["max_charge_power_kw"]) * U_ess_ch[t]
        prob += P_ess_dis[t] <= float(ess["max_discharge_power_kw"]) * (1 - U_ess_ch[t])
        prob += P_curtail[t] <= data["pv_power"][t]
        prob += P_shed[t] <= data["load_power"][t] + shift_cap

        eta_ch, eta_dis = float(ess["charge_efficiency"]), float(ess["discharge_efficiency"])
        if t == 0:
            prob += E_ess[t] == float(ess["initial_energy_kwh"]) + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
        else:
            prob += E_ess[t] == E_ess[t-1] + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
        prob += E_ess[t] >= float(ess["min_energy_kwh"])
        prob += E_ess[t] <= float(ess["max_energy_kwh"])

    prob += E_ess[n - 1] >= float(ess["initial_energy_kwh"]), "Terminal_SOC"

    steps_per_day = max(1, int(round(24.0 / dt)))
    for day in range(int(np.ceil(n / steps_per_day))):
        start_t, end_t = day * steps_per_day, min((day + 1) * steps_per_day, n)
        prob += pulp.lpSum(P_shift_up[t] - P_shift_down[t] for t in range(start_t, end_t)) == 0

    for i, ev in enumerate(ev_sessions):
        start, end = ev["start_idx"], ev["end_idx"]
        for t in T:
            if t < start or t >= end:
                prob += P_ev_ch[(i, t)] == 0
                prob += P_ev_dis[(i, t)] == 0
            else:
                prob += P_ev_ch[(i, t)] <= ev["p_ch_max"]
                if ev["v2b_allowed"]:
                    prob += P_ev_dis[(i, t)] <= ev["p_dis_max"]
                else:
                    prob += P_ev_dis[(i, t)] == 0
        prob += pulp.lpSum((P_ev_ch[(i, t)] * ev["eta_ch"] - P_ev_dis[(i, t)] / ev["eta_dis"]) * dt for t in range(start, end)) >= ev["req_energy"]

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=0.01, msg=True)
    prob.solve(solver)

    obj_val = float(pulp.value(prob.objective)) if prob.status == pulp.LpStatusOptimal else None

    results = {
        "timestamp": data["timestamps"],
        "P_buy": [float(P_buy[t].value() or 0) for t in T],
        "P_sell": [float(P_sell[t].value() or 0) for t in T],
        "P_ess_ch": [float(P_ess_ch[t].value() or 0) for t in T],
        "P_ess_dis": [float(P_ess_dis[t].value() or 0) for t in T],
        "E_ess": [float(E_ess[t].value() or 0) for t in T],
        "P_shift": [float((P_shift_up[t].value() or 0) - (P_shift_down[t].value() or 0)) for t in T],
        "P_shed": [float(P_shed[t].value() or 0) for t in T],
        "P_curtail": [float(P_curtail[t].value() or 0) for t in T],
        "P_ev_ch_total": [sum(float(P_ev_ch[(i, t)].value() or 0) for i in range(num_ev)) for t in T],
        "P_ev_dis_total": [sum(float(P_ev_dis[(i, t)].value() or 0) for i in range(num_ev)) for t in T],
    }
    return prob, results, obj_val

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument("--no-skip-infeasible-ev", action="store_true")
    parser.add_argument("--no-grid-mutex", action="store_true")
    args = parser.parse_args()

    data = load_problem_data(_REPO_ROOT, args.max_periods, not args.no_skip-infeasible-ev)
    prob, results, obj = build_and_solve(data, not args.no_grid_mutex)
    
    if obj is not None:
        print(f"\n✅ 求解状态: {pulp.LpStatus[prob.status]}")
        print(f"✅ 最优目标函数值: {obj:.2f} 元")
        
        out_dir = _REPO_ROOT / "results" / "problem1_pulp_enhanced"
        out_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_csv(out_dir / "p_1_2_timeseries.csv", index=False, encoding="utf-8-sig")
        print(f"✅ 结果已保存至 {out_dir}")
    else:
        print("❌ 求解失败 (Infeasible 或超时)。")

if __name__ == "__main__":
    main()
