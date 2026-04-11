"""
问题1 确定性协同调度主模型 — Gurobi 建模（对应 docs/problem1_coordinated_model.md）。

包含：系统功率平衡（§7.6）、光伏弃光（§7.5）、固定储能（§7.2）、EV 会话（§7.3）、
建筑柔性（§7.1）、电网购售（§7.4）、总运行成本目标（§6）。

非 baseline：全时域联合优化，EV 为会话级且仅 V2B 可放电；建筑为原生负荷 + 柔性调整量。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from . import config
from .data_loader import CoordinatedInputData, build_ev_chi_matrix

try:
    import gurobipy as gp
    from gurobipy import GRB
except ImportError:  # pragma: no cover - 环境无 Gurobi 时仍允许导入包做类型检查
    gp = None  # type: ignore
    GRB = None  # type: ignore


@dataclass
class CoordinatedModelArtifacts:
    """求解后保留的变量句柄与模型引用，供导出器抽取结果。"""

    model: Any
    n_periods: int
    n_buildings: int
    n_ev: int
    delta_t: float
    # 时段级
    P_imp: Any
    P_exp: Any
    P_ch_ess: Any
    P_dis_ess: Any
    E_ess: Any
    P_curt: Any
    P_uns: Any
    delta_flex: Any
    # EV
    P_ev_ch: Any
    P_ev_dis: Any
    E_ev: Any
    chi: np.ndarray
    # 可选二进制
    u_ess: Any | None
    u_grid: Any | None
    # 柔性绝对值线性化辅助（若使用）
    flex_abs: Any | None


def build_gurobi_model(data: CoordinatedInputData) -> tuple[Any, CoordinatedModelArtifacts]:
    """
    构建并返回 (gurobi.Model, CoordinatedModelArtifacts)。

    Args:
        data: 已由 data_loader 校验的输入。

    Returns:
        model, artifacts
    """
    if gp is None:
        raise ImportError("未安装 gurobipy。请安装 Gurobi 并在许可环境下运行；或改用 Pyomo 版本。")

    n = data.n_periods
    B = len(data.building_ids)
    V = len(data.ev_sessions)
    dt = float(data.delta_t_hours)

    m = gp.Model("problem1_coordinated_dispatch")

    chi, t_first, t_last_park = build_ev_chi_matrix(n, data.ev_sessions)

    # ------------------------------------------------------------------
    # §5 决策变量 — 电网、储能、弃光、缺电
    # ------------------------------------------------------------------
    P_imp = m.addVars(n, lb=0.0, name="P_imp")
    P_exp = m.addVars(n, lb=0.0, name="P_exp")
    P_ch_ess = m.addVars(n, lb=0.0, name="P_ch_ess")
    P_dis_ess = m.addVars(n, lb=0.0, name="P_dis_ess")
    E_ess = m.addVars(n, lb=0.0, name="E_ess")
    P_curt = m.addVars(n, lb=0.0, name="P_curt")
    if config.ENABLE_UNSERVED_LOAD:
        P_uns = m.addVars(n, lb=0.0, name="P_uns")
    else:
        P_uns = m.addVars(n, lb=0.0, ub=0.0, name="P_uns")

    # ------------------------------------------------------------------
    # §5 建筑柔性调整量 ΔP_{b,t}
    # ------------------------------------------------------------------
    delta_flex: dict[tuple[int, int], Any] = {}
    flex_abs: dict[tuple[int, int], Any] | None = {} if config.FLEX_COST_MODE == "abs_linear" else None
    for b in range(B):
        fl = data.buildings_flex[b]
        for t in range(n):
            delta_flex[b, t] = m.addVar(
                lb=fl.flex_lower_kw,
                ub=fl.flex_upper_kw,
                name=f"delta_flex_{b}_{t}",
            )
            if flex_abs is not None:
                flex_abs[b, t] = m.addVar(lb=0.0, name=f"flex_abs_{b}_{t}")

    # ------------------------------------------------------------------
    # §5 EV 会话级充放电与能量状态
    # ------------------------------------------------------------------
    P_ev_ch = m.addVars(V, n, lb=0.0, name="P_ev_ch")
    P_ev_dis = m.addVars(V, n, lb=0.0, name="P_ev_dis")
    E_ev = m.addVars(V, n, lb=0.0, name="E_ev")

    # ------------------------------------------------------------------
    # 可选 0-1：储能充放电互斥、购售电互斥（§7.2 / §7.4）
    # ------------------------------------------------------------------
    u_ess = None
    if config.ENABLE_ESS_CHARGE_DISCHARGE_MUTEX:
        u_ess = m.addVars(n, vtype=GRB.BINARY, name="u_ess")
    u_grid = None
    if config.ENABLE_GRID_IMPORT_EXPORT_MUTEX:
        u_grid = m.addVars(n, vtype=GRB.BINARY, name="u_grid")

    ess = data.ess
    eta_ch = ess.charge_efficiency
    eta_dis = ess.discharge_efficiency

    # ==================================================================
    # §7.5 光伏弃光上下界
    # ==================================================================
    for t in range(n):
        m.addConstr(P_curt[t] <= data.pv_available_kw[t], name=f"curtail_ub_{t}")

    # ==================================================================
    # §7.2 固定储能：功率界、SOC 递推、能量边界、可选互斥
    # ==================================================================
    for t in range(n):
        m.addConstr(P_ch_ess[t] <= ess.max_charge_power_kw, name=f"ess_ch_cap_{t}")
        m.addConstr(P_dis_ess[t] <= ess.max_discharge_power_kw, name=f"ess_dis_cap_{t}")
        if u_ess is not None:
            m.addConstr(P_ch_ess[t] <= u_ess[t] * ess.max_charge_power_kw, name=f"ess_ch_mutex_{t}")
            m.addConstr(
                P_dis_ess[t] <= (1.0 - u_ess[t]) * ess.max_discharge_power_kw,
                name=f"ess_dis_mutex_{t}",
            )

    for t in range(n):
        if t == 0:
            m.addConstr(
                E_ess[t]
                == ess.initial_energy_kwh
                + eta_ch * P_ch_ess[t] * dt
                - (1.0 / eta_dis) * P_dis_ess[t] * dt,
                name=f"ess_dyn_{t}",
            )
        else:
            m.addConstr(
                E_ess[t]
                == E_ess[t - 1]
                + eta_ch * P_ch_ess[t] * dt
                - (1.0 / eta_dis) * P_dis_ess[t] * dt,
                name=f"ess_dyn_{t}",
            )
        m.addConstr(E_ess[t] >= ess.min_energy_kwh, name=f"ess_e_lb_{t}")
        m.addConstr(E_ess[t] <= ess.max_energy_kwh, name=f"ess_e_ub_{t}")

    # ==================================================================
    # §7.3 EV：停车窗口、V2B、功率界、能量递推、到站/离站能量
    # ==================================================================
    for v in range(V):
        s = data.ev_sessions[v]
        eta_ev_ch = s.eta_charge
        eta_ev_dis = s.eta_discharge
        for t in range(n):
            m.addConstr(
                P_ev_ch[v, t] <= chi[v, t] * s.P_charge_max_kw,
                name=f"ev_ch_ub_{v}_{t}",
            )
            m.addConstr(
                P_ev_dis[v, t] <= chi[v, t] * s.P_discharge_max_kw,
                name=f"ev_dis_ub_{v}_{t}",
            )
            if not s.v2b_allowed:
                m.addConstr(P_ev_dis[v, t] == 0.0, name=f"ev_no_v2b_{v}_{t}")

        t0 = int(t_first[v])
        # 到站能量：若首段停车在 t0>0，则未到站前能量保持 E_arr（χ=0 ⇒ P=0 ⇒ 状态不变）
        if t0 > 0:
            m.addConstr(E_ev[v, 0] == s.E_arrival_kwh, name=f"ev_pre_arrival_{v}")
        else:
            # t0==0：周期起始即在站，段末能量由到站能量与首时段充放电决定
            m.addConstr(
                E_ev[v, 0]
                == s.E_arrival_kwh
                + eta_ev_ch * P_ev_ch[v, 0] * dt
                - (1.0 / eta_ev_dis) * P_ev_dis[v, 0] * dt,
                name=f"ev_first_slot_{v}",
            )
        for t in range(1, n):
            m.addConstr(
                E_ev[v, t]
                == E_ev[v, t - 1]
                + eta_ev_ch * P_ev_ch[v, t] * dt
                - (1.0 / eta_ev_dis) * P_ev_dis[v, t] * dt,
                name=f"ev_dyn_{v}_{t}",
            )
        for t in range(n):
            m.addConstr(E_ev[v, t] <= s.E_max_kwh + 1e-6, name=f"ev_e_cap_{v}_{t}")
            m.addConstr(E_ev[v, t] >= 0.0, name=f"ev_e_lb_{v}_{t}")

        t_end = int(t_last_park[v])
        m.addConstr(E_ev[v, t_end] >= s.E_required_departure_kwh, name=f"ev_dep_req_{v}")

    # ==================================================================
    # §7.1 建筑柔性：盒约束、可选爬坡、|ΔP| 线性化或二次代价
    # ==================================================================
    if config.FLEX_COST_MODE == "abs_linear" and flex_abs is not None:
        for b in range(B):
            for t in range(n):
                df = delta_flex[b, t]
                fa = flex_abs[b, t]
                m.addGenConstrAbs(fa, df, name=f"flex_abs_{b}_{t}")
    if config.FLEX_RAMP_LIMIT_KW is not None:
        r = float(config.FLEX_RAMP_LIMIT_KW)
        for b in range(B):
            for t in range(1, n):
                m.addConstr(
                    delta_flex[b, t] - delta_flex[b, t - 1] <= r,
                    name=f"flex_ramp_up_{b}_{t}",
                )
                m.addConstr(
                    delta_flex[b, t - 1] - delta_flex[b, t] <= r,
                    name=f"flex_ramp_dn_{b}_{t}",
                )

    if config.ENABLE_FLEX_ENERGY_NEUTRAL:
        m.addConstr(
            gp.quicksum(delta_flex[b, t] for b in range(B) for t in range(n)) * dt == 0,
            name="flex_energy_neutral",
        )

    # ==================================================================
    # §7.4 电网购售电：上下界与可选互斥
    # ==================================================================
    for t in range(n):
        m.addConstr(P_imp[t] <= data.grid_import_limit_kw[t], name=f"imp_cap_{t}")
        m.addConstr(P_exp[t] <= data.grid_export_limit_kw[t], name=f"exp_cap_{t}")
        if u_grid is not None:
            m.addConstr(
                P_imp[t] <= u_grid[t] * data.grid_import_limit_kw[t],
                name=f"imp_mutex_{t}",
            )
            m.addConstr(
                P_exp[t] <= (1.0 - u_grid[t]) * data.grid_export_limit_kw[t],
                name=f"exp_mutex_{t}",
            )

    # ==================================================================
    # §7.6 系统有功功率平衡（单母线）
    # P_imp + (P_pv - P_curt) + P_dis_ess + Σ P_ev_dis
    #   = P_exp + P_ch_ess + Σ P_ev_ch + Σ P_bld + P_uns
    # ==================================================================
    for t in range(n):
        pv_net = data.pv_available_kw[t] - P_curt[t]
        bld_sum = gp.quicksum(
            data.load_base_kw[b, t] + delta_flex[b, t] for b in range(B)
        )
        ev_ch_sum = gp.quicksum(P_ev_ch[v, t] for v in range(V))
        ev_dis_sum = gp.quicksum(P_ev_dis[v, t] for v in range(V))
        m.addConstr(
            P_imp[t] + pv_net + P_dis_ess[t] + ev_dis_sum
            == P_exp[t] + P_ch_ess[t] + ev_ch_sum + bld_sum + P_uns[t],
            name=f"power_balance_{t}",
        )

    # ==================================================================
    # §6 目标函数：总运行成本最小
    # ==================================================================
    obj = gp.LinExpr()
    for t in range(n):
        buy = float(data.price_buy_cny_per_kwh[t])
        sell = float(data.price_sell_cny_per_kwh[t])
        c_curt = float(data.curtailment_penalty_cny_per_kwh[t])
        c_uns = float(data.unserved_penalty_cny_per_kwh[t])
        obj += buy * P_imp[t] * dt
        obj -= sell * P_exp[t] * dt
        obj += c_curt * P_curt[t] * dt
        obj += c_uns * P_uns[t] * dt
        if config.FLEX_COST_MODE == "abs_linear" and flex_abs is not None:
            for b in range(B):
                c_f = data.buildings_flex[b].penalty_cny_per_kw
                obj += c_f * flex_abs[b, t] * dt
        elif config.FLEX_COST_MODE == "quadratic":
            for b in range(B):
                c_f = data.buildings_flex[b].penalty_cny_per_kw
                df = delta_flex[b, t]
                obj += c_f * df * df * dt

    if config.ENABLE_DEGRADATION_COST_IN_OBJECTIVE:
        # TODO 问题2：EV 吞吐退化成本 Σ_v Σ_t c_deg_v * (P_ch + P_dis) * dt
        pass

    m.setObjective(obj, GRB.MINIMIZE)

    art = CoordinatedModelArtifacts(
        model=m,
        n_periods=n,
        n_buildings=B,
        n_ev=V,
        delta_t=dt,
        P_imp=P_imp,
        P_exp=P_exp,
        P_ch_ess=P_ch_ess,
        P_dis_ess=P_dis_ess,
        E_ess=E_ess,
        P_curt=P_curt,
        P_uns=P_uns,
        delta_flex=delta_flex,
        P_ev_ch=P_ev_ch,
        P_ev_dis=P_ev_dis,
        E_ev=E_ev,
        chi=chi,
        u_ess=u_ess,
        u_grid=u_grid,
        flex_abs=flex_abs if config.FLEX_COST_MODE == "abs_linear" else None,
    )
    return m, art


def apply_gurobi_params(model: Any) -> None:
    """写入 config.GUROBI_PARAMS。"""
    if gp is None:
        return
    for k, v in config.GUROBI_PARAMS.items():
        model.setParam(k, v)


def solve_model(model: Any) -> None:
    """调用 optimize()。"""
    model.optimize()


def write_iis(model: Any, path: str) -> None:
    """若不可行，计算 IIS 并写入 .ilp 文件。"""
    if gp is None:
        return
    model.computeIIS()
    model.write(path)
