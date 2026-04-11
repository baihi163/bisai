"""
问题1「协同调度」1.1 原型（PuLP + CBC）—— 在 1.0 基础上加入 EV 充放电项（会话时间窗 + 净能量下界）。

定位（必读）：
- 本脚本仍为 **简化原型**，用于 **PuLP 快速试验**；**非** 问题1 最终主模型。
- EV 采用 **净能量不等式**（到站至离站净充入 ≥ 需求差），**未** 实现与 `coordinated_model.py` 完全一致的逐时段 SOC 递推与离站时刻对齐。
- **正式主模型**仍以 `src/problem1/coordinated_model.py` 与 `docs/problem1_coordinated_model.md` 为准。

数据：默认使用 `ev_sessions_model_ready.csv`（arrival_slot / departure_slot 为 1-based，离站 slot 不含在停车内）。

详见：docs/problem1_simplified_vs_full_model.md、code/python/problem_1/README_problem1_prototype.md

运行（仓库根目录）:
    python code/python/problem_1/p_1_1.py --max-periods 96
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


def _read_series_csv(path: Path, column: str) -> np.ndarray:
    df = pd.read_csv(path)
    if column not in df.columns:
        raise KeyError(f"{path} 缺少列 {column}")
    return df[column].to_numpy(dtype=float)


def _max_net_charge_kwh(
    n_steps: int, dt_h: float, eta_ch: float, p_ch_max_kw: float
) -> float:
    """
    停车时段内、恒以最大功率充电且无放电时，电池侧净增能量上界（kWh）。
    与约束 sum(eta_ch*P_ch - P_dis/eta_dis)*dt >= e_need 在 P_dis=0、P_ch<=p_max 时一致。
    """
    return float(n_steps) * dt_h * eta_ch * p_ch_max_kw


def _build_ev_sessions_for_horizon(
    df_ev: pd.DataFrame,
    n_periods: int,
    dt_hours: float,
    *,
    skip_infeasible: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    由 `ev_sessions_model_ready.csv` 构造会话列表。

    停车时段（与主模型一致）：slot_id 满足 arrival_slot <= slot < departure_slot，
    对应 period 索引 t = slot_id - 1，且 0 <= t < n_periods。

    若某会话 **净能量需求 e_need** 大于 **物理上可充入上界**（停留步数 × dt × η_ch × P_ch_max），
    则单独加入该 EV 约束会使 **整体模型不可行**。当 skip_infeasible=True 时跳过并记入 skipped。
    """
    sessions: list[dict] = []
    skipped: list[dict] = []
    eta_ch_def = 0.95
    for _, row in df_ev.iterrows():
        arr = int(row["arrival_slot"])
        dep = int(row["departure_slot"])
        if dep <= arr:
            continue
        # 裁剪到 [1, n_periods] 内的停车 slot
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

        e0 = float(row["initial_energy_kwh"])
        e_req = float(row["required_energy_at_departure_kwh"])
        e_need = e_req - e0  # 净能量需求（到站→离站）

        p_ch_max_kw = float(row["max_charge_power_kw"])
        k = len(park_ts)
        max_net = _max_net_charge_kwh(k, dt_hours, eta_ch_def, p_ch_max_kw)

        if e_need > max_net + 1e-3:
            rec = {
                "session_id": str(row["session_id"]),
                "e_need_kwh": round(e_need, 3),
                "max_net_charge_kwh": round(max_net, 3),
                "dwell_steps": k,
                "p_ch_max_kw": p_ch_max_kw,
                "reason": "e_need 超过停留期间恒功率充电净入上界（数据与功率/时间窗矛盾）",
            }
            if skip_infeasible:
                skipped.append(rec)
                continue
        sessions.append(
            {
                "session_id": str(row["session_id"]),
                "park_ts": sorted(set(park_ts)),
                "e_need_kwh": e_need,
                "p_ch_max_kw": p_ch_max_kw,
                "p_dis_max_kw": p_dis,
                "v2b": v2b,
                "eta_ch": 0.95,
                "eta_dis": 0.95,
                "e_cap_kwh": float(row["battery_capacity_kwh"]),
            }
        )
    return sessions, skipped


def load_problem_data(
    root: Path,
    max_periods: int | None = None,
    *,
    skip_infeasible_ev: bool = True,
) -> dict:
    """读取时序、储能、柔性及 EV 会话（与仓库 processed 数据对齐）。"""
    load_csv = root / "data/processed/final_model_inputs/load_profile.csv"
    pv_csv = root / "data/processed/final_model_inputs/pv_profile.csv"
    price_csv = root / "data/processed/price_profile.csv"
    grid_csv = root / "data/processed/grid_limits.csv"
    ess_json = root / "data/processed/final_model_inputs/ess_params.json"
    flex_csv = root / "data/processed/final_model_inputs/flexible_load_params_clean.csv"
    ev_csv = root / "data/processed/final_model_inputs/ev_sessions_model_ready.csv"

    df_load = pd.read_csv(load_csv)
    n = len(df_load)
    if max_periods is not None:
        n = min(n, int(max_periods))
        df_load = df_load.iloc[:n].copy()

    if "total_native_load_kw" in df_load.columns:
        load_power = df_load["total_native_load_kw"].to_numpy(dtype=float)
    else:
        sub = [c for c in df_load.columns if c.endswith("_kw") and c != "slot_id"]
        if not sub:
            raise ValueError("负荷文件需含 total_native_load_kw 或 *_kw 列")
        load_power = df_load[sub].sum(axis=1).to_numpy(dtype=float)

    pv_power = _read_series_csv(pv_csv, "pv_available_kw")[:n]
    buy_price = _read_series_csv(price_csv, "grid_buy_price_cny_per_kwh")[:n]
    sell_price = _read_series_csv(price_csv, "grid_sell_price_cny_per_kwh")[:n]
    p_imp_max = _read_series_csv(grid_csv, "grid_import_limit_kw")[:n]
    p_exp_max = _read_series_csv(grid_csv, "grid_export_limit_kw")[:n]

    with open(ess_json, "r", encoding="utf-8") as f:
        ess_raw = json.load(f)

    dt_h = float(ess_raw.get("time_step_hours", 0.25))

    df_flex = pd.read_csv(flex_csv)
    shift_cap_kw = float(df_flex["max_shiftable_kw"].sum()) if len(df_flex) else 200.0

    df_ev = pd.read_csv(ev_csv)
    ev_sessions, ev_skipped = _build_ev_sessions_for_horizon(
        df_ev, n, dt_h, skip_infeasible=skip_infeasible_ev
    )

    ess = {
        "E0_kwh": float(ess_raw["initial_energy_kwh"]),
        "E_min_kwh": float(ess_raw["min_energy_kwh"]),
        "E_max_kwh": float(ess_raw["max_energy_kwh"]),
        "P_ch_max_kw": float(ess_raw["max_charge_power_kw"]),
        "P_dis_max_kw": float(ess_raw["max_discharge_power_kw"]),
        "eta_ch": float(ess_raw["charge_efficiency"]),
        "eta_dis": float(ess_raw["discharge_efficiency"]),
    }

    assert len(load_power) == n == len(pv_power) == len(buy_price)

    return {
        "n": n,
        "delta_t": dt_h,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pv_power": pv_power,
        "load_power": load_power,
        "p_imp_max": p_imp_max,
        "p_exp_max": p_exp_max,
        "shift_cap_kw": shift_cap_kw,
        "ess": ess,
        "ev_sessions": ev_sessions,
        "ev_sessions_skipped": ev_skipped,
    }


def build_and_solve_1_1(
    data: dict,
    *,
    penalty_shed_cny_per_kwh: float = 50.0,
    penalty_curt_cny_per_kwh: float = 0.5,
    use_ess_mutex: bool = True,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
) -> tuple[pulp.LpProblem, dict, float | None]:
    """
    PuLP 模型：单母线平衡含 EV 聚合充放电 + 固定储能 SOC + 移峰/削减。

    功率平衡（与论文形式一致，EV 按会话求和）:
        (pv - curt) + P_buy + P_ess_dis + sum_i P_ev_dis,i
        = P_load + P_shift - P_shed + P_sell + P_ess_ch + sum_i P_ev_ch,i

    EV：仅在停车时段允许非零功率；净能量（简化）:
        sum_{t in park} (eta_ch*P_ch - P_dis/eta_dis)*dt >= e_need_kwh
    """
    n = data["n"]
    dt = data["delta_t"]
    T = range(n)
    ev_list = data["ev_sessions"]
    V = len(ev_list)

    prob = pulp.LpProblem("Microgrid_PuLP_Synergy_v1_1", pulp.LpMinimize)

    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    P_shift = pulp.LpVariable.dicts(
        "P_shift", T, lowBound=-data["shift_cap_kw"], upBound=data["shift_cap_kw"]
    )
    P_shed = pulp.LpVariable.dicts("P_shed", T, lowBound=0)
    P_curtail = pulp.LpVariable.dicts("P_curtail", T, lowBound=0)

    U_ess_ch = None
    if use_ess_mutex:
        U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)

    # EV: 仅对 (i,t) 建变量；非停车时段在约束中固定为 0
    P_ev_ch: dict[tuple[int, int], pulp.LpVariable] = {}
    P_ev_dis: dict[tuple[int, int], pulp.LpVariable] = {}
    park_set: list[set[int]] = []
    for i, ev in enumerate(ev_list):
        park = set(ev["park_ts"])
        park_set.append(park)
        for t in T:
            P_ev_ch[i, t] = pulp.LpVariable(f"P_ev_ch_{i}_{t}", lowBound=0)
            P_ev_dis[i, t] = pulp.LpVariable(f"P_ev_dis_{i}_{t}", lowBound=0)

    ess = data["ess"]
    eta_ec = ess["eta_ch"]
    eta_ed = ess["eta_dis"]

    prob += pulp.lpSum(
        data["buy_price"][t] * P_buy[t] * dt
        - data["sell_price"][t] * P_sell[t] * dt
        + penalty_curt_cny_per_kwh * P_curtail[t] * dt
        + penalty_shed_cny_per_kwh * P_shed[t] * dt
        for t in T
    )

    steps_per_day = max(1, int(round(24.0 / dt)))

    for i, ev in enumerate(ev_list):
        park = park_set[i]
        eta_v_ch = ev["eta_ch"]
        eta_v_dis = ev["eta_dis"]
        for t in T:
            if t not in park:
                prob += P_ev_ch[i, t] == 0, f"EV{i}_ch_off_{t}"
                prob += P_ev_dis[i, t] == 0, f"EV{i}_dis_off_{t}"
            else:
                prob += P_ev_ch[i, t] <= ev["p_ch_max_kw"], f"EV{i}_ch_cap_{t}"
                if ev["v2b"] and ev["p_dis_max_kw"] > 0:
                    prob += P_ev_dis[i, t] <= ev["p_dis_max_kw"], f"EV{i}_dis_cap_{t}"
                else:
                    prob += P_ev_dis[i, t] == 0, f"EV{i}_no_v2b_{t}"

        prob += (
            pulp.lpSum(
                (eta_v_ch * P_ev_ch[i, t] - P_ev_dis[i, t] / eta_v_dis) * dt
                for t in park
            )
            >= ev["e_need_kwh"]
        ), f"EV{i}_net_energy"

    for t in T:
        total_ev_ch = (
            pulp.lpSum(P_ev_ch[i, t] for i in range(V))
            if V
            else 0
        )
        total_ev_dis = (
            pulp.lpSum(P_ev_dis[i, t] for i in range(V))
            if V
            else 0
        )

        pv_net = data["pv_power"][t] - P_curtail[t]
        prob += (
            pv_net + P_buy[t] + P_ess_dis[t] + total_ev_dis
            == data["load_power"][t] + P_shift[t] - P_shed[t] + P_sell[t] + P_ess_ch[t] + total_ev_ch
        ), f"Power_Balance_{t}"

        prob += P_curtail[t] <= data["pv_power"][t], f"Curtail_UB_{t}"
        prob += P_buy[t] <= data["p_imp_max"][t], f"Import_Cap_{t}"
        prob += P_sell[t] <= data["p_exp_max"][t], f"Export_Cap_{t}"
        prob += P_shed[t] <= data["load_power"][t] + data["shift_cap_kw"], f"Shed_UB_{t}"

        if use_ess_mutex and U_ess_ch is not None:
            prob += P_ess_ch[t] <= ess["P_ch_max_kw"] * U_ess_ch[t], f"ESS_ch_bm_{t}"
            prob += P_ess_dis[t] <= ess["P_dis_max_kw"] * (1 - U_ess_ch[t]), f"ESS_dis_bm_{t}"
        else:
            prob += P_ess_ch[t] <= ess["P_ch_max_kw"], f"ESS_ch_cap_{t}"
            prob += P_ess_dis[t] <= ess["P_dis_max_kw"], f"ESS_dis_cap_{t}"

        if t == 0:
            prob += (
                E_ess[t]
                == ess["E0_kwh"]
                + (eta_ec * P_ess_ch[t] - P_ess_dis[t] / eta_ed) * dt
            ), f"ESS_SOC_{t}"
        else:
            prob += (
                E_ess[t]
                == E_ess[t - 1]
                + (eta_ec * P_ess_ch[t] - P_ess_dis[t] / eta_ed) * dt
            ), f"ESS_SOC_{t}"
        prob += E_ess[t] >= ess["E_min_kwh"], f"ESS_Emin_{t}"
        prob += E_ess[t] <= ess["E_max_kwh"], f"ESS_Emax_{t}"

    n_days = int(np.ceil(n / steps_per_day))
    for day in range(n_days):
        start_t = day * steps_per_day
        end_t = min((day + 1) * steps_per_day, n)
        if start_t >= n:
            break
        prob += (
            pulp.lpSum(P_shift[t] for t in range(start_t, end_t)) == 0
        ), f"Daily_Shift_{day}"

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=True)
    prob.solve(solver)

    obj_val = None
    if prob.status == pulp.LpStatusOptimal:
        obj_val = float(pulp.value(prob.objective))

    out: dict = {
        "P_buy": [float(P_buy[t].value() or 0) for t in T],
        "P_sell": [float(P_sell[t].value() or 0) for t in T],
        "P_ess_ch": [float(P_ess_ch[t].value() or 0) for t in T],
        "P_ess_dis": [float(P_ess_dis[t].value() or 0) for t in T],
        "E_ess": [float(E_ess[t].value() or 0) for t in T],
        "P_shift": [float(P_shift[t].value() or 0) for t in T],
        "P_shed": [float(P_shed[t].value() or 0) for t in T],
        "P_curtail": [float(P_curtail[t].value() or 0) for t in T],
    }
    if V:
        out["P_ev_ch_sum"] = [
            float(sum(P_ev_ch[i, t].value() or 0 for i in range(V))) for t in T
        ]
        out["P_ev_dis_sum"] = [
            float(sum(P_ev_dis[i, t].value() or 0 for i in range(V))) for t in T
        ]
    else:
        out["P_ev_ch_sum"] = [0.0] * n
        out["P_ev_dis_sum"] = [0.0] * n

    return prob, out, obj_val


def main() -> int:
    parser = argparse.ArgumentParser(description="问题1 协同调度 1.1 原型（PuLP+EV）")
    parser.add_argument("--max-periods", type=int, default=None)
    parser.add_argument("--no-ess-mutex", action="store_true")
    parser.add_argument("--time-limit", type=int, default=600)
    parser.add_argument(
        "--no-skip-infeasible-ev",
        action="store_true",
        help="不跳过「净能量需求超过可充上界」的 EV 会话（模型通常会整体不可行，仅用于排查）",
    )
    args = parser.parse_args()

    root = _REPO_ROOT
    if not (root / "data").is_dir():
        print(f"错误：未找到数据目录，推断根目录: {root}", file=sys.stderr)
        return 2

    data = load_problem_data(
        root,
        max_periods=args.max_periods,
        skip_infeasible_ev=not args.no_skip_infeasible_ev,
    )
    skipped = data.get("ev_sessions_skipped") or []
    if skipped:
        print(
            "提示：以下 EV 会话在现有功率/停留时间下 **物理不可行**（已跳过，否则 MILP 不可行）：",
            file=sys.stderr,
        )
        for s in skipped:
            print(
                f"  - {s['session_id']}: e_need={s['e_need_kwh']} kWh > "
                f"max_net_charge≈{s['max_net_charge_kwh']} kWh "
                f"(dwell={s['dwell_steps']} 步, P_ch_max={s['p_ch_max_kw']} kW)",
                file=sys.stderr,
            )
        print(
            "说明：附件中到站电量、离站需求、停留时长与 max_charge_power 可能不一致；"
            "正式建模应清洗数据或放宽为软约束。使用 --no-skip-infeasible-ev 可强制保留（通常仍不可行）。",
            file=sys.stderr,
        )

    print(f"T={data['n']}, dt={data['delta_t']} h, EV 会话数={len(data['ev_sessions'])}")

    prob, results, obj = build_and_solve_1_1(
        data,
        use_ess_mutex=not args.no_ess_mutex,
        time_limit_s=args.time_limit,
    )

    print(f"求解状态: {pulp.LpStatus[prob.status]}")
    if obj is not None:
        print(f"最小总成本: {obj:.2f} 元")
        out_dir = root / "results" / "problem1_pulp"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "p_1_1_timeseries.csv"
        pd.DataFrame(results).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"已写出: {out_csv}")
    else:
        print("未得到最优解。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
