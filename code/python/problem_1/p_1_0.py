"""
问题1「协同调度」简化原型模型（PuLP + CBC）—— 非最终主模型。

定位说明（请务必阅读）：
- 本脚本为 **简化原型**，用于 **快速验证数据通路、功率平衡与轻量 MILP 求解**（CBC，无需 Gurobi）。
- **不含电动车（EV）显式决策变量与会话约束**；建筑侧为 **总负荷 + 聚合移峰/削减**，非论文中的多栋分项柔性 + 完整形式。
- **问题1 正式主模型**（与 `docs/problem1_coordinated_model.md` 严格对应、含 EV 会话与 V2B 等）仍以：
      src/problem1/coordinated_model.py
  为准；赛题答卷、完整经济性对比与 baseline 对照应以该主模型与 `run_coordinated.py` 为主。
- 勿将本文件作为「问题1 最终交付代码」的唯一代表。

数据与运行：从仓库 `data/processed/` 读取电价、光伏、负荷、电网限额与储能参数。

运行（在仓库根目录）:
    python code/python/problem_1/p_1_0.py
    python code/python/problem_1/p_1_0.py --max-periods 96

详见：docs/problem1_simplified_vs_full_model.md、code/python/problem_1/README_problem1_prototype.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

# ---------------------------------------------------------------------------
# 路径：本文件 -> code/python/problem_1 -> code/python -> code -> 仓库根
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]


def _read_series_csv(path: Path, column: str) -> np.ndarray:
    df = pd.read_csv(path)
    if column not in df.columns:
        raise KeyError(f"{path} 缺少列 {column}")
    return df[column].to_numpy(dtype=float)


def load_problem_data(
    root: Path,
    max_periods: int | None = None,
) -> dict:
    """
    为「简化原型」读取与 `src/problem1` 一致的默认数据路径，返回长度 T 的字典。

    仅聚合总负荷与柔性上界，不含 EV 会话表。正式主模型使用 `data_loader.load_coordinated_inputs`。

    Returns:
        dict 含 buy_price, sell_price, pv_power, load_power, p_imp_max, p_exp_max,
        ess 参数字典，以及实际 T。
    """
    load_csv = root / "data/processed/final_model_inputs/load_profile.csv"
    pv_csv = root / "data/processed/final_model_inputs/pv_profile.csv"
    price_csv = root / "data/processed/price_profile.csv"
    grid_csv = root / "data/processed/grid_limits.csv"
    ess_json = root / "data/processed/final_model_inputs/ess_params.json"
    flex_csv = root / "data/processed/final_model_inputs/flexible_load_params_clean.csv"

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
        ess = json.load(f)

    # 聚合柔性：各建筑 max_shiftable 之和，作为 |P_shift| 保守上界（可改）
    df_flex = pd.read_csv(flex_csv)
    shift_cap_kw = float(df_flex["max_shiftable_kw"].sum()) if len(df_flex) else 200.0

    assert len(load_power) == n == len(pv_power) == len(buy_price)
    return {
        "n": n,
        "delta_t": float(ess.get("time_step_hours", 0.25)),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pv_power": pv_power,
        "load_power": load_power,
        "p_imp_max": p_imp_max,
        "p_exp_max": p_exp_max,
        "shift_cap_kw": shift_cap_kw,
        "ess": {
            "E0_kwh": float(ess["initial_energy_kwh"]),
            "E_min_kwh": float(ess["min_energy_kwh"]),
            "E_max_kwh": float(ess["max_energy_kwh"]),
            "P_ch_max_kw": float(ess["max_charge_power_kw"]),
            "P_dis_max_kw": float(ess["max_discharge_power_kw"]),
            "eta_ch": float(ess["charge_efficiency"]),
            "eta_dis": float(ess["discharge_efficiency"]),
        },
    }


def build_and_solve(
    data: dict,
    *,
    penalty_shed_cny_per_kwh: float = 50.0,
    penalty_curt_cny_per_kwh: float = 0.5,
    use_ess_mutex: bool = True,
    time_limit_s: int = 600,
    gap_rel: float = 0.01,
) -> tuple[pulp.LpProblem, dict, float | None]:
    """
    构建「简化原型」PuLP 模型并求解（非问题1正式主模型）。

    功率平衡（单母线，无 EV 显式项）:
        (pv - curtail) + P_buy + P_ess_dis
        = P_load + P_shift - P_shed + P_sell + P_ess_ch

    其中 P_shift 为相对基准负荷的转移量（可正可负）；P_shed 为削减（非负），
    日内 sum(P_shift) 按 96 步为一天归零。
    """
    n = data["n"]
    T = range(n)
    dt = data["delta_t"]
    buy_price = data["buy_price"]
    sell_price = data["sell_price"]
    pv_power = data["pv_power"]
    load_power = data["load_power"]
    p_imp_max = data["p_imp_max"]
    p_exp_max = data["p_exp_max"]
    shift_cap = data["shift_cap_kw"]
    ess = data["ess"]

    prob = pulp.LpProblem("Microgrid_PuLP_Synergy", pulp.LpMinimize)

    P_buy = pulp.LpVariable.dicts("P_buy", T, lowBound=0)
    P_sell = pulp.LpVariable.dicts("P_sell", T, lowBound=0)
    P_ess_ch = pulp.LpVariable.dicts("P_ess_ch", T, lowBound=0)
    P_ess_dis = pulp.LpVariable.dicts("P_ess_dis", T, lowBound=0)
    E_ess = pulp.LpVariable.dicts("E_ess", T, lowBound=0)
    P_shift = pulp.LpVariable.dicts("P_shift", T, lowBound=-shift_cap, upBound=shift_cap)
    P_shed = pulp.LpVariable.dicts("P_shed", T, lowBound=0)
    P_curtail = pulp.LpVariable.dicts("P_curtail", T, lowBound=0)

    U_ess_ch = None
    if use_ess_mutex:
        # 每时段一个二进制：1=充电模式，0=放电模式（互斥）
        U_ess_ch = pulp.LpVariable.dicts("U_ess_ch", T, cat=pulp.LpBinary)

    eta_ch = ess["eta_ch"]
    eta_dis = ess["eta_dis"]
    P_ch_max = ess["P_ch_max_kw"]
    P_dis_max = ess["P_dis_max_kw"]

    # 目标：购电 - 售电 + 弃光惩罚 + 削减惩罚
    prob += pulp.lpSum(
        buy_price[t] * P_buy[t] * dt
        - sell_price[t] * P_sell[t] * dt
        + penalty_curt_cny_per_kwh * P_curtail[t] * dt
        + penalty_shed_cny_per_kwh * P_shed[t] * dt
        for t in T
    )

    steps_per_day = max(1, int(round(24.0 / dt)))

    for t in T:
        pv_net = pv_power[t] - P_curtail[t]
        prob += (
            pv_net + P_buy[t] + P_ess_dis[t]
            == load_power[t] + P_shift[t] - P_shed[t] + P_sell[t] + P_ess_ch[t]
        ), f"Power_Balance_{t}"

        prob += P_curtail[t] <= pv_power[t], f"Curtail_UB_{t}"
        prob += P_buy[t] <= p_imp_max[t], f"Import_Cap_{t}"
        prob += P_sell[t] <= p_exp_max[t], f"Export_Cap_{t}"
        # 削减量不超过名义负荷量级（保守上界，避免与移峰耦合过紧）
        prob += P_shed[t] <= load_power[t] + shift_cap, f"Shed_UB_{t}"

        if use_ess_mutex and U_ess_ch is not None:
            prob += P_ess_ch[t] <= P_ch_max * U_ess_ch[t], f"ESS_Ch_BigM_{t}"
            prob += P_ess_dis[t] <= P_dis_max * (1 - U_ess_ch[t]), f"ESS_Dis_BigM_{t}"
        else:
            prob += P_ess_ch[t] <= P_ch_max, f"ESS_Ch_Cap_{t}"
            prob += P_ess_dis[t] <= P_dis_max, f"ESS_Dis_Cap_{t}"

        if t == 0:
            prob += (
                E_ess[t]
                == ess["E0_kwh"]
                + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
            ), f"ESS_SOC_{t}"
        else:
            prob += (
                E_ess[t]
                == E_ess[t - 1]
                + (eta_ch * P_ess_ch[t] - P_ess_dis[t] / eta_dis) * dt
            ), f"ESS_SOC_{t}"

        prob += E_ess[t] >= ess["E_min_kwh"], f"ESS_E_Min_{t}"
        prob += E_ess[t] <= ess["E_max_kwh"], f"ESS_E_Max_{t}"

    # 日内转移守恒：每天 sum(P_shift)=0
    n_days = int(np.ceil(n / steps_per_day))
    for day in range(n_days):
        start_t = day * steps_per_day
        end_t = min((day + 1) * steps_per_day, n)
        if start_t >= n:
            break
        prob += (
            pulp.lpSum(P_shift[t] for t in range(start_t, end_t)) == 0
        ), f"Daily_Shift_Balance_{day}"

    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=gap_rel, msg=True)
    prob.solve(solver)

    obj_val = None
    if prob.status == pulp.LpStatusOptimal:
        obj_val = float(pulp.value(prob.objective))

    results = {
        "P_buy": [float(P_buy[t].value() or 0) for t in T],
        "P_sell": [float(P_sell[t].value() or 0) for t in T],
        "P_ess_ch": [float(P_ess_ch[t].value() or 0) for t in T],
        "P_ess_dis": [float(P_ess_dis[t].value() or 0) for t in T],
        "E_ess": [float(E_ess[t].value() or 0) for t in T],
        "P_shift": [float(P_shift[t].value() or 0) for t in T],
        "P_shed": [float(P_shed[t].value() or 0) for t in T],
        "P_curtail": [float(P_curtail[t].value() or 0) for t in T],
    }
    return prob, results, obj_val


def main() -> int:
    parser = argparse.ArgumentParser(description="PuLP 微电网协同调度简化版")
    parser.add_argument("--max-periods", type=int, default=None, help="只取前 N 个时段（调试/小规模）")
    parser.add_argument("--no-ess-mutex", action="store_true", help="去掉储能充放互斥（仍为 MILP 若保留二进制；当前互斥关闭时不再添加 Big-M）")
    parser.add_argument("--time-limit", type=int, default=600)
    args = parser.parse_args()

    root = _REPO_ROOT
    if not (root / "data").is_dir():
        print(f"错误：未找到数据目录，请从仓库根运行。推断根目录: {root}", file=sys.stderr)
        return 2

    data = load_problem_data(root, max_periods=args.max_periods)
    print(f"时段数 T={data['n']}, delta_t={data['delta_t']} h")

    prob, results, obj = build_and_solve(
        data,
        use_ess_mutex=not args.no_ess_mutex,
        time_limit_s=args.time_limit,
    )

    print(f"求解状态: {pulp.LpStatus[prob.status]}")
    if obj is not None:
        print(f"最小总成本（目标函数值）: {obj:.2f} 元")
        out_dir = root / "results" / "problem1_pulp"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "p_1_0_timeseries.csv"
        pd.DataFrame(results).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"已写出: {out_csv}")
    else:
        print("未得到最优解，请检查不可行原因或增大 --time-limit。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
