"""问题1：确定性协同调度（Python + PuLP）代码框架。

说明：
- 时间尺度：7天 * 96 = 672 个15分钟时段
- 目标：总运行成本最小（购电成本 - 售电收益 + 削减惩罚 + 平移惩罚 + 弃光惩罚）
- 本脚本偏“可运行框架”，便于后续逐步细化参数和约束。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pulp as pl


# -----------------------------
# 1) 路径与基础参数
# -----------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
OUT_DIR = ROOT / "results" / "exports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DT = 0.25  # 小时（15分钟）
N_EXPECTED = 672

# 可按论文设定调整的惩罚系数（元/kWh）
SHIFT_PENALTY = 0.15
CURTAIL_PENALTY = 0.08


def load_inputs() -> dict:
    """读取建模输入文件并做基础校验。"""
    load = pd.read_csv(DATA_DIR / "load_profile.csv")
    pv = pd.read_csv(DATA_DIR / "pv_profile.csv")
    price = pd.read_csv(DATA_DIR / "price_profile.csv")
    grid = pd.read_csv(DATA_DIR / "grid_limits.csv")
    carbon = pd.read_csv(DATA_DIR / "carbon_profile.csv")
    ev = pd.read_csv(DATA_DIR / "ev_aggregate_profile.csv")
    flex = pd.read_csv(DATA_DIR / "flexible_load_params.csv")
    ess = json.loads((DATA_DIR / "ess_params.json").read_text(encoding="utf-8"))

    for name, df in {
        "load_profile": load,
        "pv_profile": pv,
        "price_profile": price,
        "grid_limits": grid,
        "carbon_profile": carbon,
        "ev_aggregate_profile": ev,
    }.items():
        if len(df) != N_EXPECTED:
            raise ValueError(f"{name} 行数为 {len(df)}，预期 {N_EXPECTED}")

    return {
        "load": load,
        "pv": pv,
        "price": price,
        "grid": grid,
        "carbon": carbon,
        "ev": ev,
        "flex": flex,
        "ess": ess,
    }


def build_and_solve(data: dict) -> tuple[pl.LpProblem, dict]:
    """建立并求解确定性协同调度模型。"""
    load = data["load"]
    pv = data["pv"]
    price = data["price"]
    grid = data["grid"]
    ev = data["ev"]
    flex = data["flex"]
    ess = data["ess"]

    # 时间集合
    T = range(N_EXPECTED)
    blocks = flex["load_block"].tolist()

    # 原生负荷按块取值（列名映射）
    block_to_col = {
        "office_building": "office_building_kw",
        "wet_lab": "wet_lab_kw",
        "teaching_center": "teaching_center_kw",
    }
    native_total = load["total_native_load_kw"].to_dict()

    # 柔性参数字典
    noninterruptible = dict(zip(flex["load_block"], flex["noninterruptible_share"]))
    max_shift = dict(zip(flex["load_block"], flex["max_shiftable_kw"]))
    max_shed = dict(zip(flex["load_block"], flex["max_sheddable_kw"]))
    rebound = dict(zip(flex["load_block"], flex["rebound_factor"]))
    shed_penalty = dict(zip(flex["load_block"], flex["penalty_cny_per_kwh_not_served"]))

    # EV聚合能量上界（用累计净流入构造一个保守上界）
    cum_net = (ev["e_ev_init_inflow_kwh"] - ev["e_ev_req_outflow_kwh"]).cumsum()
    ev_energy_cap = float(max(cum_net.max(), 0.0) + ev["e_ev_init_inflow_kwh"].max() + 1e-6)

    # --------------- 建模 ---------------
    model = pl.LpProblem("Problem1_Deterministic_Dispatch", pl.LpMinimize)

    # 2) 决策变量
    p_buy = pl.LpVariable.dicts("p_grid_buy_kw", T, lowBound=0)
    p_sell = pl.LpVariable.dicts("p_grid_sell_kw", T, lowBound=0)

    p_ess_ch = pl.LpVariable.dicts("p_ess_ch_kw", T, lowBound=0)
    p_ess_dis = pl.LpVariable.dicts("p_ess_dis_kw", T, lowBound=0)
    e_ess = pl.LpVariable.dicts(
        "e_ess_kwh",
        T,
        lowBound=ess["soc_min_frac"] * ess["energy_capacity_kwh"],
        upBound=ess["soc_max_frac"] * ess["energy_capacity_kwh"],
    )

    p_ev_ch = pl.LpVariable.dicts("p_ev_ch_kw", T, lowBound=0)
    p_ev_dis = pl.LpVariable.dicts("p_ev_dis_kw", T, lowBound=0)
    e_ev = pl.LpVariable.dicts("e_ev_kwh", T, lowBound=0, upBound=ev_energy_cap)

    # 柔性负荷：平移“出/入”与削减（按块）
    shift_out = pl.LpVariable.dicts("shift_out_kw", ((b, t) for b in blocks for t in T), lowBound=0)
    shift_in = pl.LpVariable.dicts("shift_in_kw", ((b, t) for b in blocks for t in T), lowBound=0)
    shed = pl.LpVariable.dicts("shed_kw", ((b, t) for b in blocks for t in T), lowBound=0)

    # 光伏利用与弃光
    p_pv_use = pl.LpVariable.dicts("p_pv_use_kw", T, lowBound=0)
    p_pv_curt = pl.LpVariable.dicts("p_pv_curt_kw", T, lowBound=0)

    # 3) 目标函数
    total_cost = pl.lpSum(
        price.loc[t, "grid_buy_price_cny_per_kwh"] * p_buy[t] * DT
        - price.loc[t, "grid_sell_price_cny_per_kwh"] * p_sell[t] * DT
        + CURTAIL_PENALTY * p_pv_curt[t] * DT
        for t in T
    )
    total_cost += pl.lpSum(
        shed_penalty[b] * shed[(b, t)] * DT
        + SHIFT_PENALTY * (shift_out[(b, t)] + shift_in[(b, t)]) * DT
        for b in blocks
        for t in T
    )
    model += total_cost, "total_operating_cost"

    # 4) 约束
    for t in T:
        # 光伏分解约束：利用 + 弃光 = 可用出力
        model += p_pv_use[t] + p_pv_curt[t] == pv.loc[t, "pv_available_kw"], f"pv_split_{t}"

        # 电网上限约束
        model += p_buy[t] <= grid.loc[t, "grid_import_limit_kw"], f"grid_buy_limit_{t}"
        model += p_sell[t] <= grid.loc[t, "grid_export_limit_kw"], f"grid_sell_limit_{t}"

        # ESS 功率上限
        model += p_ess_ch[t] <= ess["p_charge_max_kw"], f"ess_ch_limit_{t}"
        model += p_ess_dis[t] <= ess["p_discharge_max_kw"], f"ess_dis_limit_{t}"

        # EV 聚合功率上限
        model += p_ev_ch[t] <= ev.loc[t, "p_ev_ch_max_kw"], f"ev_ch_limit_{t}"
        model += p_ev_dis[t] <= ev.loc[t, "p_ev_dis_max_kw"], f"ev_dis_limit_{t}"

        # 柔性负荷约束（按块）
        for b in blocks:
            base_col = block_to_col[b]
            base_load = float(load.loc[t, base_col])

            model += shift_out[(b, t)] <= max_shift[b], f"shift_out_limit_{b}_{t}"
            model += shift_in[(b, t)] <= max_shift[b], f"shift_in_limit_{b}_{t}"
            model += shed[(b, t)] <= max_shed[b], f"shed_limit_cap_{b}_{t}"
            model += shed[(b, t)] <= (1 - noninterruptible[b]) * base_load, f"shed_rigid_bound_{b}_{t}"

        # 功率平衡约束
        # 供给侧：电网净购电 + 光伏利用 + 储能放电 + EV放电
        supply = p_buy[t] - p_sell[t] + p_pv_use[t] + p_ess_dis[t] + p_ev_dis[t]

        # 需求侧：原生负荷 + 储能充电 + EV充电 + 负荷平移净流入 - 削减
        flex_adjust = pl.lpSum(shift_in[(b, t)] - shift_out[(b, t)] - shed[(b, t)] for b in blocks)
        demand = native_total[t] + p_ess_ch[t] + p_ev_ch[t] + flex_adjust
        model += supply == demand, f"power_balance_{t}"

    # ESS 能量状态方程
    for t in T:
        if t == 0:
            model += (
                e_ess[t]
                == ess["soc_init_kwh"]
                + ess["eta_charge"] * p_ess_ch[t] * DT
                - (p_ess_dis[t] * DT) / ess["eta_discharge"]
            ), "ess_energy_init"
        else:
            model += (
                e_ess[t]
                == e_ess[t - 1]
                + ess["eta_charge"] * p_ess_ch[t] * DT
                - (p_ess_dis[t] * DT) / ess["eta_discharge"]
            ), f"ess_energy_{t}"

    # EV 聚合能量状态方程（考虑会话净流入/净流出）
    eta_ev_ch = 0.95
    eta_ev_dis = 0.95
    for t in T:
        inflow = float(ev.loc[t, "e_ev_init_inflow_kwh"])
        outflow = float(ev.loc[t, "e_ev_req_outflow_kwh"])
        if t == 0:
            model += (
                e_ev[t]
                == inflow
                + eta_ev_ch * p_ev_ch[t] * DT
                - (p_ev_dis[t] * DT) / eta_ev_dis
                - outflow
            ), "ev_energy_init"
        else:
            model += (
                e_ev[t]
                == e_ev[t - 1]
                + inflow
                + eta_ev_ch * p_ev_ch[t] * DT
                - (p_ev_dis[t] * DT) / eta_ev_dis
                - outflow
            ), f"ev_energy_{t}"

    # 柔性负荷“总量平移守恒 + 反弹”约束（按块）
    for b in blocks:
        model += (
            pl.lpSum(shift_in[(b, t)] for t in T)
            == rebound[b] * pl.lpSum(shift_out[(b, t)] for t in T)
        ), f"shift_rebound_{b}"

    # 5) 求解
    solver = pl.PULP_CBC_CMD(msg=True)
    model.solve(solver)

    # 输出关键结果
    status = pl.LpStatus[model.status]
    obj = pl.value(model.objective)
    summary = {"status": status, "objective_cny": obj}

    dispatch = pd.DataFrame(
        {
            "timestamp": load["timestamp"],
            "p_grid_buy_kw": [pl.value(p_buy[t]) for t in T],
            "p_grid_sell_kw": [pl.value(p_sell[t]) for t in T],
            "p_ess_ch_kw": [pl.value(p_ess_ch[t]) for t in T],
            "p_ess_dis_kw": [pl.value(p_ess_dis[t]) for t in T],
            "e_ess_kwh": [pl.value(e_ess[t]) for t in T],
            "p_ev_ch_kw": [pl.value(p_ev_ch[t]) for t in T],
            "p_ev_dis_kw": [pl.value(p_ev_dis[t]) for t in T],
            "e_ev_kwh": [pl.value(e_ev[t]) for t in T],
            "p_pv_use_kw": [pl.value(p_pv_use[t]) for t in T],
            "p_pv_curt_kw": [pl.value(p_pv_curt[t]) for t in T],
        }
    )

    # 按块输出柔性调节
    for b in blocks:
        dispatch[f"{b}_shift_in_kw"] = [pl.value(shift_in[(b, t)]) for t in T]
        dispatch[f"{b}_shift_out_kw"] = [pl.value(shift_out[(b, t)]) for t in T]
        dispatch[f"{b}_shed_kw"] = [pl.value(shed[(b, t)]) for t in T]

    return model, {"summary": summary, "dispatch": dispatch}


def main() -> None:
    data = load_inputs()
    _, results = build_and_solve(data)

    # 保存结果
    summary_path = OUT_DIR / "problem1_dispatch_summary.json"
    dispatch_path = OUT_DIR / "problem1_dispatch_timeseries.csv"
    summary_path.write_text(json.dumps(results["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    results["dispatch"].to_csv(dispatch_path, index=False, encoding="utf-8-sig")

    print("问题1确定性协同调度求解完成。")
    print(f"状态: {results['summary']['status']}")
    print(f"目标值(元): {results['summary']['objective_cny']}")
    print(f"摘要文件: {summary_path.as_posix()}")
    print(f"时序文件: {dispatch_path.as_posix()}")


if __name__ == "__main__":
    main()
