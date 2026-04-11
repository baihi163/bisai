"""
问题1 园区微电网协同调度 — 矩阵版升级 (p_1_4_matrix_upgrade)

在 PuLP + CBC 上融合以下能力（相对 p_1_2_final 的增量）：
- EV 可用性 / 充放电功率上界由时段矩阵给出（ev_availability_matrix 等）；
- EV 稀疏变量 + 逐时电量 E_ev；充放电与并网互斥用二进制 Y_ev_conn / Y_ev_dis 建模；
- 可选 EV 同时并网数、双向桩数上界（来自 asset_parameters）；
- 建筑分块柔性：移出 / 回补 / 削减 + 能量 backlog 递推与周期末清零；
- 显式光伏利用功率 P_pv_use 与弃光（目标中惩罚未利用光伏）；
- 可选购电碳排放成本；EV / 储能退化成本进入目标。

数据默认从仓库 ``data/processed/final_model_inputs`` 与 ``data/processed`` 读取，
矩阵列名 ``ev_k`` 与 ``ev_sessions_model_ready.csv`` 的 ``ev_index=k`` 对齐。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pulp
except ImportError as exc:  # pragma: no cover
    raise ImportError("未找到 pulp。请先安装：pip install pulp") from exc

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少文件: {path}")
    return pd.read_csv(path)


def _parse_asset_table(path: Path) -> dict[str, float]:
    df = _read_csv(path)
    if not {"parameter", "value"}.issubset(df.columns):
        raise KeyError(f"{path} 需包含 parameter, value 列")
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        key = str(row["parameter"]).strip()
        try:
            out[key] = float(row["value"])
        except (TypeError, ValueError):
            continue
    return out


def _read_ev_matrix(path: Path) -> tuple[pd.DataFrame, list[str]]:
    df = _read_csv(path)
    if not {"slot_id", "timestamp"}.issubset(df.columns):
        raise KeyError(f"{path.name} 需包含 slot_id, timestamp 列")
    ev_cols = [c for c in df.columns if c not in ("slot_id", "timestamp")]
    if not ev_cols:
        raise ValueError(f"{path.name} 不含 EV 列")
    return df, ev_cols


def _matrix_col_to_index(col: str) -> int:
    col = str(col).strip()
    if not col.startswith("ev_"):
        raise ValueError(f"无法解析 EV 矩阵列名: {col}")
    return int(col.split("_", 1)[1])


def _lp_status_name(status: int) -> str:
    try:
        return str(pulp.LpStatus[status])
    except (KeyError, IndexError, TypeError):
        return str(status)


def _var_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        x = v.value()
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError, AttributeError):
        return 0.0


def load_problem_data(
    root: Path,
    max_periods: int | None = None,
    *,
    skip_infeasible_ev: bool = True,
) -> dict[str, Any]:
    """从数维杯仓库标准路径加载矩阵版问题数据。"""
    base_in = root / "data" / "processed" / "final_model_inputs"
    base_proc = root / "data" / "processed"

    load_csv = base_in / "load_profile.csv"
    pv_csv = base_in / "pv_profile.csv"
    flex_csv = base_in / "flexible_load_params_clean.csv"
    ess_json = base_in / "ess_params.json"
    ev_csv = base_in / "ev_sessions_model_ready.csv"
    av_csv = base_in / "ev_availability_matrix.csv"
    ch_csv = base_in / "ev_charge_power_limit_matrix_kw.csv"
    dis_csv = base_in / "ev_discharge_power_limit_matrix_kw.csv"
    price_csv = base_proc / "price_profile.csv"
    grid_csv = base_proc / "grid_limits.csv"
    asset_csv = root / "data" / "raw" / "asset_parameters.csv"

    df_load = _read_csv(load_csv)
    n = len(df_load)
    if max_periods is not None:
        n = min(n, int(max_periods))
        df_load = df_load.iloc[:n].copy()

    timestamps = pd.to_datetime(df_load["timestamp"], errors="coerce")
    pv_upper = _read_csv(pv_csv)["pv_available_kw"].to_numpy(dtype=float)[:n]
    buy_price = _read_csv(price_csv)["grid_buy_price_cny_per_kwh"].to_numpy(dtype=float)[:n]
    sell_price = _read_csv(price_csv)["grid_sell_price_cny_per_kwh"].to_numpy(dtype=float)[:n]
    p_imp_max = _read_csv(grid_csv)["grid_import_limit_kw"].to_numpy(dtype=float)[:n]
    p_exp_max = _read_csv(grid_csv)["grid_export_limit_kw"].to_numpy(dtype=float)[:n]

    with open(ess_json, "r", encoding="utf-8") as f:
        ess_json = json.load(f)
    asset = _parse_asset_table(asset_csv)
    dt = float(ess_json.get("time_step_hours", asset.get("default_time_step_hours", 0.25)))
    pv_cap = float(asset.get("pv_inverter_limit_kw", np.max(pv_upper) if len(pv_upper) else 0.0))
    pv_upper = np.minimum(pv_upper, pv_cap)

    df_flex = _read_csv(flex_csv)
    need_flex = {
        "load_block",
        "noninterruptible_share",
        "max_shiftable_kw",
        "max_sheddable_kw",
        "rebound_factor",
        "penalty_cny_per_kwh_not_served",
    }
    miss_f = need_flex - set(df_flex.columns)
    if miss_f:
        raise KeyError(f"{flex_csv.name} 缺少列: {sorted(miss_f)}")

    building_blocks: list[dict[str, Any]] = []
    for _, row in df_flex.iterrows():
        block = str(row["load_block"]).strip()
        load_col = f"{block}_kw"
        if load_col not in df_load.columns:
            raise KeyError(f"{load_csv.name} 缺少建筑负荷列: {load_col}")
        building_blocks.append(
            {
                "name": block,
                "load": df_load[load_col].to_numpy(dtype=float),
                "noninterruptible_share": float(row["noninterruptible_share"]),
                "max_shiftable_kw": float(row["max_shiftable_kw"]),
                "max_sheddable_kw": float(row["max_sheddable_kw"]),
                "rebound_factor": float(row["rebound_factor"]),
                "penalty_not_served": float(row["penalty_cny_per_kwh_not_served"]),
            }
        )

    total_native = np.sum([b["load"] for b in building_blocks], axis=0)

    df_ev = _read_csv(ev_csv).sort_values("ev_index").reset_index(drop=True)
    need_ev = {
        "session_id",
        "battery_capacity_kwh",
        "initial_energy_kwh",
        "required_energy_at_departure_kwh",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "v2b_allowed",
        "degradation_cost_cny_per_kwh_throughput",
    }
    miss_ev = need_ev - set(df_ev.columns)
    if miss_ev:
        raise KeyError(f"{ev_csv.name} 缺少列: {sorted(miss_ev)}")

    df_av, av_cols = _read_ev_matrix(av_csv)
    df_ch, ch_cols = _read_ev_matrix(ch_csv)
    df_dis, dis_cols = _read_ev_matrix(dis_csv)
    df_av = df_av.iloc[:n].copy()
    df_ch = df_ch.iloc[:n].copy()
    df_dis = df_dis.iloc[:n].copy()

    if av_cols != ch_cols or av_cols != dis_cols:
        raise ValueError("三个 EV 矩阵的列名或顺序不一致")

    ev_ids_matrix = av_cols
    try:
        matrix_indices = [_matrix_col_to_index(c) for c in ev_ids_matrix]
    except ValueError as exc:
        raise ValueError("EV 矩阵列名须为 ev_1, ev_2, … 形式") from exc

    ev_index_series = df_ev["ev_index"].astype(int)
    if set(ev_index_series.tolist()) != set(matrix_indices):
        raise ValueError(
            "ev_sessions 的 ev_index 集合与矩阵列 ev_k 不一致。"
            f"矩阵: {len(matrix_indices)} 列 | 表: {len(ev_index_series)} 行"
        )
    df_ev = df_ev.set_index(ev_index_series).loc[matrix_indices].reset_index(drop=True)

    av_mat = df_av[ev_ids_matrix].to_numpy(dtype=float)
    ch_mat = df_ch[ev_ids_matrix].to_numpy(dtype=float)
    dis_mat = df_dis[ev_ids_matrix].to_numpy(dtype=float)
    av_mat = np.where(av_mat > 0.5, 1.0, 0.0)
    ch_mat = ch_mat * av_mat
    dis_mat = dis_mat * av_mat

    eta_ev_default = 0.95
    ev_sessions: list[dict[str, Any]] = []
    ev_skipped: list[dict[str, Any]] = []

    for i, row in df_ev.iterrows():
        sid = str(row["session_id"])
        matrix_col = ev_ids_matrix[i]
        cap = float(row["battery_capacity_kwh"])
        e_init = float(row["initial_energy_kwh"])
        e_req = float(row["required_energy_at_departure_kwh"])
        v2b_allowed = int(row["v2b_allowed"])
        eta_ch = (
            float(row["charge_efficiency"])
            if "charge_efficiency" in df_ev.columns and pd.notna(row.get("charge_efficiency"))
            else eta_ev_default
        )
        eta_dis = (
            float(row["discharge_efficiency"])
            if "discharge_efficiency" in df_ev.columns and pd.notna(row.get("discharge_efficiency"))
            else eta_ev_default
        )

        if not v2b_allowed:
            dis_mat[:, i] = 0.0

        # 与 p_1_2 一致：先到离时段与所选 horizon 求交，再与矩阵可用性求交，避免 --max-periods 截断误判
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
            ev_skipped.append(
                {
                    "session_id": sid,
                    "matrix_col": matrix_col,
                    "reason": "session_outside_selected_horizon",
                }
            )
            continue

        park_ts = [t for t in park_from_csv if av_mat[t, i] > 0.5]
        if not park_ts:
            ev_skipped.append(
                {
                    "session_id": sid,
                    "matrix_col": matrix_col,
                    "reason": "no_matrix_availability_during_declared_parking",
                }
            )
            continue

        max_gain = float((ch_mat[park_ts, i] * eta_ch * dt).sum())

        ereq_model = float(e_req)
        if "arrival_slot" in df_ev.columns and "departure_slot" in df_ev.columns:
            arr0 = max(1, int(row["arrival_slot"]))
            dep0 = int(row["departure_slot"])
            full_dwell = max(1, dep0 - arr0)
            last_csv_t = dep0 - 2
            if park_ts[-1] < last_csv_t and full_dwell > 0:
                frac = len(park_ts) / float(full_dwell)
                ereq_model = float(e_init) + (float(e_req) - float(e_init)) * min(1.0, frac)

        reason = None
        if e_init < -1e-9 or e_req < -1e-9 or cap < -1e-9:
            reason = "negative_energy_value"
        elif e_init - cap > 1e-6:
            reason = "initial_energy_exceeds_capacity"
        elif ereq_model - cap > 1e-6:
            reason = "required_energy_exceeds_capacity"
        elif ereq_model - e_init - max_gain > 1e-6:
            reason = "required_increment_exceeds_slot_charge_upper_bound"

        if reason is not None:
            rec = {
                "session_id": sid,
                "matrix_col": matrix_col,
                "reason": reason,
                "initial_kwh": round(e_init, 4),
                "required_kwh_csv": round(e_req, 4),
                "required_kwh_modeled": round(ereq_model, 4),
                "capacity_kwh": round(cap, 4),
                "max_chargeable_gain_kwh": round(max_gain, 4),
            }
            if skip_infeasible_ev:
                ev_skipped.append(rec)
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
                "deg_cost": float(row["degradation_cost_cny_per_kwh_throughput"]),
                "park_ts": park_ts,
                "charge_limits_kw": ch_mat[:, i].copy(),
                "discharge_limits_kw": dis_mat[:, i].copy(),
                "v2b_allowed": int(v2b_allowed),
            }
        )

    kept_ids = [ev["session_id"] for ev in ev_sessions]
    if kept_ids:
        keep_idx = [ev_ids_matrix.index(ev["matrix_col"]) for ev in ev_sessions]
        av_mat = av_mat[:, keep_idx]
        ch_mat = ch_mat[:, keep_idx]
        dis_mat = dis_mat[:, keep_idx]
    else:
        av_mat = np.zeros((n, 0))
        ch_mat = np.zeros((n, 0))
        dis_mat = np.zeros((n, 0))

    ess_deg = float(
        asset.get(
            "stationary_battery_degradation_cost_cny_per_kwh_throughput",
            ess_json.get("degradation_cost_cny_per_kwh", 0.02),
        )
    )

    return {
        "base_dir": base_in,
        "n": n,
        "delta_t": dt,
        "timestamps": timestamps,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "grid_carbon": np.zeros(n, dtype=float),
        "pv_upper": pv_upper,
        "p_imp_max": p_imp_max,
        "p_exp_max": p_exp_max,
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
        "ev_ids": kept_ids,
        "ev_availability": av_mat,
        "ev_charge_limit": ch_mat,
        "ev_discharge_limit": dis_mat,
    }


def build_and_solve(
    data: dict[str, Any],
    *,
    carbon_price_cny_per_kg: float = 0.0,
    pv_curtail_penalty_cny_per_kwh: float = 0.5,
    shift_penalty_cny_per_kwh: float = 0.02,
    use_grid_mutex: bool = True,
    enforce_ev_connection_limit: bool = True,
    gap_rel: float = 0.01,
    time_limit_s: int = 600,
    solver_msg: bool = True,
) -> tuple[pulp.LpProblem, pd.DataFrame, dict[str, Any]]:
    n = data["n"]
    if n < 1:
        raise ValueError("时段数 n 必须 >= 1")
    T = range(n)
    dt = float(data["delta_t"])
    ess = data["ess"]
    buildings = data["building_blocks"]
    ev_sessions = data["ev_sessions"]

    prob = pulp.LpProblem("CampusMicrogrid_EV_Building_CoDispatch_MatrixUpgrade", pulp.LpMinimize)

    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_pv_use = pulp.LpVariable.dicts("P_pv_use", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)
    U_grid_buy = (
        pulp.LpVariable.dicts("U_grid_buy", T, cat=pulp.LpBinary) if use_grid_mutex else None
    )

    block_names = [b["name"] for b in buildings]
    BT = [(b, t) for b in block_names for t in T]
    P_shift_out = pulp.LpVariable.dicts("P_shift_out", BT, lowBound=0)
    P_recover = pulp.LpVariable.dicts("P_recover", BT, lowBound=0)
    P_shed = pulp.LpVariable.dicts("P_shed", BT, lowBound=0)
    E_backlog = pulp.LpVariable.dicts("E_backlog", BT, lowBound=0)

    ev_keys: list[tuple[int, int]] = []
    ev_keys_by_t: dict[int, list[tuple[int, int]]] = defaultdict(list)
    ev_ts_by_i: dict[int, list[int]] = {}
    for i, ev in enumerate(ev_sessions):
        ts = sorted(ev["park_ts"])
        ev_ts_by_i[i] = ts
        for t in ts:
            key = (i, t)
            ev_keys.append(key)
            ev_keys_by_t[t].append(key)

    if ev_keys:
        P_ev_ch = pulp.LpVariable.dicts("P_ev_ch", ev_keys, lowBound=0)
        P_ev_dis = pulp.LpVariable.dicts("P_ev_dis", ev_keys, lowBound=0)
        E_ev = pulp.LpVariable.dicts("E_ev", ev_keys, lowBound=0)
        Y_ev_conn = pulp.LpVariable.dicts("Y_ev_conn", ev_keys, cat=pulp.LpBinary)
        Y_ev_dis = pulp.LpVariable.dicts("Y_ev_dis", ev_keys, cat=pulp.LpBinary)
    else:
        P_ev_ch = {}
        P_ev_dis = {}
        E_ev = {}
        Y_ev_conn = {}
        Y_ev_dis = {}

    obj_terms: list[Any] = []
    for t in T:
        obj_terms.append(data["buy_price"][t] * P_buy[t] * dt)
        obj_terms.append(-data["sell_price"][t] * P_sell[t] * dt)
        obj_terms.append(carbon_price_cny_per_kg * data["grid_carbon"][t] * P_buy[t] * dt)
        obj_terms.append(pv_curtail_penalty_cny_per_kwh * (data["pv_upper"][t] - P_pv_use[t]) * dt)
        obj_terms.append(float(ess["degradation_cost_cny_per_kwh"]) * (P_ess_ch[t] + P_ess_dis[t]) * dt / 2.0)

    for b in buildings:
        name = b["name"]
        pen = float(b["penalty_not_served"])
        for t in T:
            obj_terms.append(shift_penalty_cny_per_kwh * (P_shift_out[(name, t)] + P_recover[(name, t)]) * dt)
            obj_terms.append(pen * P_shed[(name, t)] * dt)

    for i, ev in enumerate(ev_sessions):
        deg = float(ev["deg_cost"])
        for t in ev_ts_by_i[i]:
            obj_terms.append(deg * (P_ev_ch[(i, t)] + P_ev_dis[(i, t)]) * dt / 2.0)

    prob += pulp.lpSum(obj_terms)

    for t in T:
        total_served_load = pulp.lpSum(
            b["load"][t] - P_shift_out[(b["name"], t)] + P_recover[(b["name"], t)] - P_shed[(b["name"], t)]
            for b in buildings
        )
        keys_t = ev_keys_by_t.get(t, [])
        total_ev_ch = pulp.lpSum(P_ev_ch[key] for key in keys_t) if keys_t else 0
        total_ev_dis = pulp.lpSum(P_ev_dis[key] for key in keys_t) if keys_t else 0

        prob += (
            P_pv_use[t] + P_buy[t] + P_ess_dis[t] + total_ev_dis
            == total_served_load + P_sell[t] + P_ess_ch[t] + total_ev_ch
        ), f"Power_Balance_{t}"

        prob += P_pv_use[t] <= data["pv_upper"][t], f"PV_Use_UB_{t}"
        prob += P_buy[t] <= data["p_imp_max"][t], f"Grid_Import_UB_{t}"
        prob += P_sell[t] <= data["p_exp_max"][t], f"Grid_Export_UB_{t}"

        if use_grid_mutex and U_grid_buy is not None:
            prob += P_buy[t] <= data["p_imp_max"][t] * U_grid_buy[t], f"Grid_Buy_Mutex_{t}"
            prob += P_sell[t] <= data["p_exp_max"][t] * (1 - U_grid_buy[t]), f"Grid_Sell_Mutex_{t}"

        prob += P_ess_ch[t] <= float(ess["max_charge_power_kw"]) * U_ess_ch[t], f"ESS_Ch_Mutex_{t}"
        prob += P_ess_dis[t] <= float(ess["max_discharge_power_kw"]) * (1 - U_ess_ch[t]), f"ESS_Dis_Mutex_{t}"

        eta_ch_ess = float(ess["charge_efficiency"])
        eta_dis_ess = float(ess["discharge_efficiency"])
        if t == 0:
            prob += (
                E_ess[t]
                == float(ess["initial_energy_kwh"])
                + (eta_ch_ess * P_ess_ch[t] - P_ess_dis[t] / eta_dis_ess) * dt
            ), f"ESS_SOC_{t}"
        else:
            prob += (
                E_ess[t]
                == E_ess[t - 1] + (eta_ch_ess * P_ess_ch[t] - P_ess_dis[t] / eta_dis_ess) * dt
            ), f"ESS_SOC_{t}"

        prob += E_ess[t] >= float(ess["min_energy_kwh"]), f"ESS_E_Min_{t}"
        prob += E_ess[t] <= float(ess["max_energy_kwh"]), f"ESS_E_Max_{t}"

    prob += E_ess[n - 1] >= float(ess["initial_energy_kwh"]), "ESS_Terminal_SOC"

    for b in buildings:
        name = b["name"]
        load = b["load"]
        nonint = float(b["noninterruptible_share"])
        max_shift = float(b["max_shiftable_kw"])
        max_shed = float(b["max_sheddable_kw"])
        rebound = max(1.0, float(b["rebound_factor"]))

        for t in T:
            flex_cap = max(0.0, (1.0 - nonint) * float(load[t]))
            prob += P_shift_out[(name, t)] <= min(max_shift, flex_cap), f"{name}_ShiftOut_UB_{t}"
            prob += P_shed[(name, t)] <= min(max_shed, flex_cap), f"{name}_Shed_UB_{t}"
            prob += P_shift_out[(name, t)] + P_shed[(name, t)] <= flex_cap, f"{name}_FlexShare_UB_{t}"
            prob += P_recover[(name, t)] <= rebound * max_shift, f"{name}_Recover_UB_{t}"
            prob += (
                load[t] - P_shift_out[(name, t)] + P_recover[(name, t)] - P_shed[(name, t)] >= 0
            ), f"{name}_ServedNonNegative_{t}"

            if t == 0:
                prob += (
                    E_backlog[(name, t)]
                    == P_shift_out[(name, t)] * dt - P_recover[(name, t)] * dt / rebound
                ), f"{name}_Backlog_{t}"
            else:
                prob += (
                    E_backlog[(name, t)]
                    == E_backlog[(name, t - 1)]
                    + P_shift_out[(name, t)] * dt
                    - P_recover[(name, t)] * dt / rebound
                ), f"{name}_Backlog_{t}"

        prob += E_backlog[(name, n - 1)] == 0, f"{name}_Backlog_End"

    total_conn_cap = int(data["ev_assets"].get("max_simultaneous_ev_connections", 0))
    bidir_cap = int(data["ev_assets"].get("ev_bidirectional_charger_count", 0))
    uni_cap = int(data["ev_assets"].get("ev_unidirectional_charger_count", 0))
    if total_conn_cap <= 0:
        total_conn_cap = bidir_cap + uni_cap
    if total_conn_cap <= 0:
        total_conn_cap = max(1, len(ev_sessions))

    for i, ev in enumerate(ev_sessions):
        ts = ev_ts_by_i[i]
        for pos, t in enumerate(ts):
            ch_lim = float(ev["charge_limits_kw"][t])
            dis_lim = float(ev["discharge_limits_kw"][t])

            prob += Y_ev_dis[(i, t)] <= Y_ev_conn[(i, t)], f"EV_{i}_DisSubsetConn_{t}"
            prob += P_ev_ch[(i, t)] <= ch_lim * (Y_ev_conn[(i, t)] - Y_ev_dis[(i, t)]), f"EV_{i}_Ch_UB_{t}"

            if dis_lim > 1e-9 and ev["v2b_allowed"]:
                prob += P_ev_dis[(i, t)] <= dis_lim * Y_ev_dis[(i, t)], f"EV_{i}_Dis_UB_{t}"
            else:
                prob += Y_ev_dis[(i, t)] == 0, f"EV_{i}_NoDisFlag_{t}"
                prob += P_ev_dis[(i, t)] == 0, f"EV_{i}_NoDisPow_{t}"

            if pos == 0:
                prob += (
                    E_ev[(i, t)]
                    == ev["initial_energy_kwh"]
                    + (ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]) * dt
                ), f"EV_{i}_SOC_{t}"
            else:
                prev_t = ts[pos - 1]
                if t != prev_t + 1:
                    raise ValueError(
                        f"EV {ev['session_id']} 在站时段非连续 (t={t}, prev={prev_t})，"
                        "矩阵可用性存在空洞，需预处理或扩展 SOC 递推。"
                    )
                prob += (
                    E_ev[(i, t)]
                    == E_ev[(i, prev_t)]
                    + (ev["eta_ch"] * P_ev_ch[(i, t)] - P_ev_dis[(i, t)] / ev["eta_dis"]) * dt
                ), f"EV_{i}_SOC_{t}"

            prob += E_ev[(i, t)] >= 0, f"EV_{i}_SOC_Min_{t}"
            prob += E_ev[(i, t)] <= ev["battery_capacity_kwh"], f"EV_{i}_SOC_Max_{t}"

        prob += E_ev[(i, ts[-1])] >= ev["required_energy_kwh"], f"EV_{i}_DepartureReq"

    if enforce_ev_connection_limit and ev_keys:
        for t in T:
            keys_t = ev_keys_by_t.get(t, [])
            if not keys_t:
                continue
            prob += pulp.lpSum(Y_ev_conn[key] for key in keys_t) <= total_conn_cap, f"EV_TotalConn_{t}"
            if bidir_cap > 0:
                prob += pulp.lpSum(Y_ev_dis[key] for key in keys_t) <= bidir_cap, f"EV_BidirCap_{t}"

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=solver_msg)
    try:
        prob.solve(solver)
    except Exception as exc:
        raise RuntimeError(f"CBC 求解调用失败: {exc}") from exc

    status_name = _lp_status_name(prob.status)
    objective_value: float | None = None
    if prob.status == pulp.LpStatusOptimal:
        try:
            v = pulp.value(prob.objective)
            objective_value = float(v) if v is not None else None
        except (TypeError, ValueError):
            objective_value = None

    out: dict[str, Any] = {
        "timestamp": pd.DatetimeIndex(data["timestamps"]).astype(str),
        "native_total_load_kw": data["total_native_load"],
        "P_pv_use_kw": [_var_float(P_pv_use[t]) for t in T],
        "P_pv_curtail_kw": [float(data["pv_upper"][t]) - _var_float(P_pv_use[t]) for t in T],
        "P_buy_kw": [_var_float(P_buy[t]) for t in T],
        "P_sell_kw": [_var_float(P_sell[t]) for t in T],
        "P_ess_ch_kw": [_var_float(P_ess_ch[t]) for t in T],
        "P_ess_dis_kw": [_var_float(P_ess_dis[t]) for t in T],
        "E_ess_kwh": [_var_float(E_ess[t]) for t in T],
        "buy_price_cny_per_kwh": data["buy_price"],
        "sell_price_cny_per_kwh": data["sell_price"],
        "grid_carbon_kg_per_kwh": data["grid_carbon"],
    }

    for b in buildings:
        name = b["name"]
        out[f"{name}_native_kw"] = b["load"]
        out[f"{name}_shift_out_kw"] = [_var_float(P_shift_out[(name, t)]) for t in T]
        out[f"{name}_recover_kw"] = [_var_float(P_recover[(name, t)]) for t in T]
        out[f"{name}_shed_kw"] = [_var_float(P_shed[(name, t)]) for t in T]
        out[f"{name}_backlog_kwh"] = [_var_float(E_backlog[(name, t)]) for t in T]
        out[f"{name}_served_kw"] = [
            float(b["load"][t])
            - _var_float(P_shift_out[(name, t)])
            + _var_float(P_recover[(name, t)])
            - _var_float(P_shed[(name, t)])
            for t in T
        ]

    P_ev_ch_total = []
    P_ev_dis_total = []
    EV_conn_total = []
    EV_dis_active_total = []
    for t in T:
        keys_t = ev_keys_by_t.get(t, [])
        P_ev_ch_total.append(sum(_var_float(P_ev_ch.get(k)) for k in keys_t))
        P_ev_dis_total.append(sum(_var_float(P_ev_dis.get(k)) for k in keys_t))
        EV_conn_total.append(
            sum(int(round(_var_float(Y_ev_conn.get(k)))) for k in keys_t) if keys_t else 0
        )
        EV_dis_active_total.append(
            sum(int(round(_var_float(Y_ev_dis.get(k)))) for k in keys_t) if keys_t else 0
        )

    out["P_ev_ch_total_kw"] = P_ev_ch_total
    out["P_ev_dis_total_kw"] = P_ev_dis_total
    out["EV_connected_count"] = EV_conn_total
    out["EV_discharging_count"] = EV_dis_active_total

    df_out = pd.DataFrame(out)

    ev_summary = []
    for i, ev in enumerate(ev_sessions):
        ts = ev_ts_by_i[i]
        if not ts:
            continue
        delivered = ev["initial_energy_kwh"]
        for t in ts:
            delivered += (
                ev["eta_ch"] * _var_float(P_ev_ch.get((i, t)))
                - _var_float(P_ev_dis.get((i, t))) / ev["eta_dis"]
            ) * dt
        ev_summary.append(
            {
                "session_id": ev["session_id"],
                "matrix_col": ev["matrix_col"],
                "arrival_slot": ts[0] + 1,
                "departure_slot_model": ts[-1] + 1,
                "initial_energy_kwh": round(ev["initial_energy_kwh"], 4),
                "required_energy_kwh": round(ev["required_energy_kwh"], 4),
                "final_energy_kwh": round(delivered, 4),
                "energy_margin_kwh": round(delivered - ev["required_energy_kwh"], 4),
            }
        )

    kpis: dict[str, Any] = {
        "solver_status": status_name,
        "objective_value_cny": None if objective_value is None else round(objective_value, 4),
        "n_periods": int(n),
        "delta_t_h": dt,
        "num_building_blocks": len(buildings),
        "num_ev_sessions_modeled": len(ev_sessions),
        "num_ev_sessions_skipped": len(data["ev_skipped"]),
        "total_native_load_kwh": round(float(df_out["native_total_load_kw"].sum() * dt), 4),
        "total_grid_import_kwh": round(float(df_out["P_buy_kw"].sum() * dt), 4),
        "total_grid_export_kwh": round(float(df_out["P_sell_kw"].sum() * dt), 4),
        "total_pv_used_kwh": round(float(df_out["P_pv_use_kw"].sum() * dt), 4),
        "total_pv_curtailed_kwh": round(float(df_out["P_pv_curtail_kw"].sum() * dt), 4),
        "total_ess_charge_kwh": round(float(df_out["P_ess_ch_kw"].sum() * dt), 4),
        "total_ess_discharge_kwh": round(float(df_out["P_ess_dis_kw"].sum() * dt), 4),
        "total_ev_charge_kwh": round(float(df_out["P_ev_ch_total_kw"].sum() * dt), 4),
        "total_ev_discharge_kwh": round(float(df_out["P_ev_dis_total_kw"].sum() * dt), 4),
        "peak_grid_import_kw": round(float(df_out["P_buy_kw"].max()), 4),
        "peak_grid_export_kw": round(float(df_out["P_sell_kw"].max()), 4),
        "peak_ev_charge_kw": round(float(df_out["P_ev_ch_total_kw"].max()), 4),
        "peak_ev_discharge_kw": round(float(df_out["P_ev_dis_total_kw"].max()), 4),
        "peak_ev_connected_count": int(df_out["EV_connected_count"].max()),
        "peak_ev_discharging_count": int(df_out["EV_discharging_count"].max()),
        "total_grid_carbon_kg": round(
            float((df_out["P_buy_kw"] * df_out["grid_carbon_kg_per_kwh"] * dt).sum()),
            4,
        ),
    }

    for b in buildings:
        name = b["name"]
        kpis[f"{name}_shed_kwh"] = round(float(df_out[f"{name}_shed_kw"].sum() * dt), 4)
        kpis[f"{name}_shift_out_kwh"] = round(float(df_out[f"{name}_shift_out_kw"].sum() * dt), 4)
        kpis[f"{name}_recover_kwh"] = round(float(df_out[f"{name}_recover_kw"].sum() * dt), 4)

    extras: dict[str, Any] = {
        "kpis": kpis,
        "ev_skipped": data["ev_skipped"],
        "ev_summary": ev_summary,
    }
    return prob, df_out, extras


def main() -> int:
    parser = argparse.ArgumentParser(description="问题1 矩阵版 EV-建筑-园区协同 (PuLP+CBC)")
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument(
        "--no-skip-infeasible-ev",
        action="store_true",
        help="保留不可行 EV（易导致 CBC 不可行）",
    )
    parser.add_argument("--time-limit", type=int, default=600)
    parser.add_argument("--gap-rel", type=float, default=0.01)
    parser.add_argument("--carbon-price", type=float, default=0.0, help="购电碳成本（元/kg）")
    parser.add_argument("--no-grid-mutex", action="store_true")
    parser.add_argument("--no-ev-connection-limit", action="store_true")
    parser.add_argument("--quiet-cbc", action="store_true")
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
            f"[EV] 剔除 session: {len(ev_skipped)} | 原因统计: {by_reason}",
            file=sys.stderr,
        )

    print(
        f"加载完成: T={data['n']} | buildings={len(data['building_blocks'])} | "
        f"EV_modeled={len(data['ev_sessions'])} | EV_skipped={len(ev_skipped)}",
        file=sys.stderr,
    )

    try:
        prob, df_out, extras = build_and_solve(
            data,
            carbon_price_cny_per_kg=args.carbon_price,
            use_grid_mutex=not args.no_grid_mutex,
            enforce_ev_connection_limit=not args.no_ev_connection_limit,
            gap_rel=args.gap_rel,
            time_limit_s=args.time_limit,
            solver_msg=not args.quiet_cbc,
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"建模或求解失败: {exc}", file=sys.stderr)
        return 2

    print(f"求解状态: {extras['kpis']['solver_status']}")

    out_dir = root / "results" / "problem1_matrix_upgrade"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        ts_path = out_dir / "p_1_4_matrix_upgrade_timeseries.csv"
        kpi_path = out_dir / "p_1_4_matrix_upgrade_kpis.json"
        skipped_path = out_dir / "p_1_4_matrix_upgrade_ev_skipped.json"
        evsum_path = out_dir / "p_1_4_matrix_upgrade_ev_summary.csv"

        df_out.to_csv(ts_path, index=False, encoding="utf-8-sig")
        kpi_path.write_text(json.dumps(extras["kpis"], ensure_ascii=False, indent=2), encoding="utf-8")
        skipped_path.write_text(json.dumps(extras["ev_skipped"], ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(extras["ev_summary"]).to_csv(evsum_path, index=False, encoding="utf-8-sig")

        print(f"已写出时序结果: {ts_path}")
        print(f"已写出 KPI: {kpi_path}")
        print(f"已写出 EV 跳过记录: {skipped_path}")
        print(f"已写出 EV 会话摘要: {evsum_path}")
    except OSError as exc:
        print(f"写出失败: {exc}", file=sys.stderr)
        return 2

    if extras["kpis"]["objective_value_cny"] is not None:
        print(f"目标值: {extras['kpis']['objective_value_cny']:.4f} 元")
        return 0

    print("未得到有效目标值，请检查求解状态。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
