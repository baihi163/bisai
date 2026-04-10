# -*- coding: utf-8 -*-
"""
问题1：非协同调度基准（规则型仿真，非全局优化）。

唯一入口：从仓库根目录执行
  python code/python/baseline/run_baseline_noncooperative.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# run_baseline_noncooperative.py -> baseline -> python -> code -> 仓库根
ROOT = Path(__file__).resolve().parents[3]
INPUT_DIR = ROOT / "data" / "processed" / "final_model_inputs"
OUT_DIR = ROOT / "results" / "problem1_baseline"
INPUT_VALIDATION_REPORT = OUT_DIR / "baseline_input_validation_report.md"

# EV 交流侧充电功率 → 电池储能增量效率（车载充电机 AC–DC 典型值，文献/工程常用约 0.90–0.95；
# 输入数据未提供实测曲线，本 baseline 取中值 0.92 以保证物理一致性与可复现性。）
EV_CHARGE_EFFICIENCY = 0.92

# 储能高价放电：购电价不低于全周购电价样本的该分位数时允许放电（默认 0.8 = 最贵约 20% 时段）。
ESS_DISCHARGE_PRICE_QUANTILE = 0.8


def _resolve_input_dir() -> Path:
    if INPUT_DIR.is_dir():
        return INPUT_DIR
    alt = ROOT / "data" / "processed"
    if alt.is_dir():
        return alt
    raise FileNotFoundError(f"未找到输入目录: {INPUT_DIR}")


def load_inputs(base: Path | None = None) -> dict[str, Any]:
    """读取 final_model_inputs（或等价目录）下的标准文件。"""
    d = base or _resolve_input_dir()

    def req(name: str) -> Path:
        p = d / name
        if not p.exists():
            raise FileNotFoundError(f"缺少必需文件: {p}")
        return p

    load = pd.read_csv(req("load_profile.csv"))
    pv = pd.read_csv(req("pv_profile.csv"))
    price = pd.read_csv(req("price_profile.csv"))
    grid = pd.read_csv(req("grid_limits.csv"))
    ess_path = req("ess_params.json")
    ess = json.loads(ess_path.read_text(encoding="utf-8"))

    ev_sessions = pd.read_csv(req("ev_sessions_model_ready.csv"), keep_default_na=False)
    av = pd.read_csv(req("ev_availability_matrix.csv"))
    p_ch = pd.read_csv(req("ev_charge_power_limit_matrix_kw.csv"))
    p_dis = pd.read_csv(req("ev_discharge_power_limit_matrix_kw.csv"))

    for name, df in [
        ("load_profile", load),
        ("pv_profile", pv),
        ("price_profile", price),
        ("grid_limits", grid),
    ]:
        if len(df) != 672:
            raise ValueError(f"{name} 行数应为 672，实际 {len(df)}")

    ts = pd.to_datetime(load["timestamp"])
    if not ts.equals(pd.to_datetime(pv["timestamp"])):
        raise ValueError("load 与 pv 时间戳不一致")

    # ESS 建模用字段（缺省则报错，不虚构）
    need_ess = [
        "energy_capacity_kwh",
        "initial_energy_kwh",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "charge_efficiency",
        "discharge_efficiency",
        "min_energy_kwh",
        "max_energy_kwh",
        "time_step_hours",
    ]
    missing = [k for k in need_ess if ess.get(k) is None]
    if missing:
        raise ValueError(f"ess_params.json 缺少数值字段: {missing}")

    dt = float(ess["time_step_hours"])
    if abs(dt - 0.25) > 1e-6:
        raise ValueError(f"本脚本按 0.25h 步长编写，当前 time_step_hours={dt}")

    n_ev = len(ev_sessions)
    ev_cols = [c for c in av.columns if c.startswith("ev_")]
    if len(ev_cols) != n_ev:
        raise ValueError(f"EV 矩阵列数 {len(ev_cols)} 与 ev_sessions 行数 {n_ev} 不一致")

    avail = av[ev_cols].to_numpy(dtype=np.float64)
    p_ch_mat = p_ch[ev_cols].to_numpy(dtype=np.float64)
    p_dis_mat = p_dis[ev_cols].to_numpy(dtype=np.float64)

    return {
        "dir": d,
        "load": load,
        "pv": pv,
        "price": price,
        "grid": grid,
        "ess": ess,
        "ev_sessions": ev_sessions,
        "avail": avail,
        "p_ch_mat": p_ch_mat,
        "p_dis_mat": p_dis_mat,
        "dt_hours": dt,
        "n_ev": n_ev,
        "n_slots": 672,
        "ev_charge_efficiency": float(EV_CHARGE_EFFICIENCY),
    }


def _high_price_mask(
    buy_prices: np.ndarray, quantile: float = ESS_DISCHARGE_PRICE_QUANTILE
) -> np.ndarray:
    """
    高价放电时段：购电价不低于全周购电价样本的给定分位数（默认 0.8，即约最贵 20% 时段）。
    规则型、非优化；若全周电价相同，分位阈值等于该常数，所有时段均视为「高价区间」（与分位定义一致）。
    """
    x = buy_prices.astype(np.float64)
    thr = float(np.quantile(x, quantile))
    return x >= thr - 1e-9


def collect_input_validation_issues(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """
    输入合法性检查。返回 (errors, warnings)，errors 表示应中止仿真的问题，warnings 为提示性项。
    """
    errors: list[str] = []
    warnings: list[str] = []
    ev_df = data["ev_sessions"]
    ess = data["ess"]
    avail = data["avail"]
    p_ch_mat = data["p_ch_mat"]
    p_dis_mat = data["p_dis_mat"]
    T, n_ev = avail.shape

    if p_ch_mat.shape != (T, n_ev):
        errors.append(f"充电功率矩阵形状 {p_ch_mat.shape} 与 availability {(T, n_ev)} 不一致。")
    if p_dis_mat.shape != (T, n_ev):
        errors.append(f"放电功率矩阵形状 {p_dis_mat.shape} 与 availability {(T, n_ev)} 不一致。")
    if avail.shape[0] != data["n_slots"]:
        errors.append(f"availability 行数 {avail.shape[0]} 与 n_slots {data['n_slots']} 不一致。")

    bad_ch = np.where(p_ch_mat < -1e-9)
    if bad_ch[0].size:
        errors.append(
            f"充电功率矩阵存在负值：共 {bad_ch[0].size} 处，示例 (t,j)=({int(bad_ch[0][0])},{int(bad_ch[1][0])})。"
        )

    bad_dis = np.where(p_dis_mat < -1e-9)
    if bad_dis[0].size:
        errors.append(
            f"放电功率矩阵存在负值：共 {bad_dis[0].size} 处，示例 (t,j)=({int(bad_dis[0][0])},{int(bad_dis[1][0])})。"
        )

    # availability 与功率矩阵：非连接时段功率应为 0（兼容性）
    eps = 1e-6
    mask_off = avail < 0.5
    if np.any(p_ch_mat[mask_off] > eps):
        n = int(np.sum(p_ch_mat[mask_off] > eps))
        warnings.append(f"未连接时段存在非零充电功率上限（共 {n} 个元素），仿真仍按可用性截断，建议核对数据。")
    if np.any(p_dis_mat[mask_off] > eps):
        n = int(np.sum(p_dis_mat[mask_off] > eps))
        warnings.append(f"未连接时段存在非零放电功率上限（共 {n} 个元素），baseline 不向电网放电，建议核对数据。")

    avail_bad = (avail < -1e-6) | (avail > 1.0 + 1e-6)
    if np.any(avail_bad):
        warnings.append("availability 矩阵存在明显超出 [0,1] 的值，将按 >0.5 视为连接处理。")

    for j in range(n_ev):
        row = ev_df.iloc[j]
        cap = float(row["battery_capacity_kwh"])
        e0 = float(row["initial_energy_kwh"])
        req = float(row["required_energy_at_departure_kwh"])
        md = float(row["max_discharge_power_kw"])
        v2b = int(row.get("v2b_allowed", 0))

        if cap <= 0:
            errors.append(f"EV {j + 1} (ev_index={row.get('ev_index', j + 1)}): battery_capacity_kwh 须为正。")
        if e0 < -1e-9 or e0 > cap + 1e-6:
            errors.append(
                f"EV {j + 1}: initial_energy_kwh={e0} 超出 [0, capacity={cap}]。"
            )
        if req < -1e-9 or req > cap + 1e-6:
            errors.append(
                f"EV {j + 1}: required_energy_at_departure_kwh={req} 超出 [0, capacity={cap}]。"
            )
        if req < e0 - 1e-6:
            warnings.append(
                f"EV {j + 1}: 离站目标电量 ({req}) 低于初始电量 ({e0})，到站即充规则下该车本时段不充电。"
            )

        dep_s = int(row["departure_slot"])
        if dep_s < 1 or dep_s > data["n_slots"]:
            errors.append(
                f"EV {j + 1}: departure_slot={dep_s} 超出仿真范围 [1, {data['n_slots']}]。"
            )

        if v2b == 0 and md > 1e-6:
            warnings.append(
                f"EV {j + 1}: v2b_allowed=0 但 max_discharge_power_kw={md}>0，与「不允许 V2B」语义略不一致（baseline 仍不启用放电）。"
            )
        if v2b == 0:
            dmax = float(np.max(p_dis_mat[:, j]))
            if dmax > 1e-3:
                warnings.append(
                    f"EV {j + 1}: v2b_allowed=0 但放电功率上限矩阵列最大值为 {dmax:.4g} kW，建议与策略一致化为 0。"
                )

    e_min = float(ess["min_energy_kwh"])
    e_max = float(ess["max_energy_kwh"])
    e_ini = float(ess["initial_energy_kwh"])
    if e_min > e_max + 1e-9:
        errors.append("ess_params: min_energy_kwh 大于 max_energy_kwh。")
    if e_ini < e_min - 1e-6 or e_ini > e_max + 1e-6:
        errors.append(f"ess_params: initial_energy_kwh={e_ini} 超出 [{e_min}, {e_max}]。")

    return errors, warnings


def write_input_validation_report(
    path: Path, errors: list[str], warnings: list[str], data: dict[str, Any] | None = None
) -> None:
    lines: list[str] = [
        "# Baseline 输入数据合法性检查报告",
        "",
        "由 `code/python/baseline/run_baseline_noncooperative.py` 在每次仿真前生成。",
        "",
    ]
    if data is not None:
        lines.append(f"- 输入目录: `{data.get('dir', '')}`")
        lines.append(f"- EV 充电效率假设: `ev_charge_efficiency = {EV_CHARGE_EFFICIENCY}`（见 `baseline_readme.md`）")
        lines.append(f"- 储能高价分位: `ESS_DISCHARGE_PRICE_QUANTILE = {ESS_DISCHARGE_PRICE_QUANTILE}`")
        lines.append("")
    if errors:
        lines.append("## 错误（须修正输入后重新运行）")
        lines.append("")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")
    else:
        lines.append("## 错误")
        lines.append("")
        lines.append("- 无。")
        lines.append("")
    lines.append("## 警告")
    lines.append("")
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- 无。")
    lines.append("")
    lines.append("---")
    lines.append("*本报告为规则型 baseline 的数据门禁，不改变非协同定位。*")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def simulate_ev_baseline(
    ev_e: np.ndarray,
    ev_req: np.ndarray,
    ev_cap: np.ndarray,
    avail_row: np.ndarray,
    p_ch_row: np.ndarray,
    dt_h: float,
    eta_ev: float,
) -> np.ndarray:
    """
    到站即充：已连接且电量未达离站要求时，按交流侧限制功率充电；无 V2B。
    p[j] 为交流侧充电功率 (kW)；电池能量增量 ΔE = η_ev · p · Δt。
    """
    n = len(ev_e)
    eta = float(eta_ev)
    if eta <= 0:
        raise ValueError("eta_ev 须为正。")
    p = np.zeros(n, dtype=np.float64)
    for j in range(n):
        if avail_row[j] < 0.5:
            continue
        if ev_e[j] >= ev_req[j] - 1e-9:
            continue
        headroom_req = max(0.0, (ev_req[j] - ev_e[j]) / (eta * dt_h))
        headroom_cap = max(0.0, (ev_cap[j] - ev_e[j]) / (eta * dt_h))
        p[j] = min(p_ch_row[j], headroom_req, headroom_cap)
    return p


def simulate_ess_rule(
    e_ess: float,
    deficit_kw: float,
    surplus_pv_kw: float,
    _buy_price: float,
    is_high: bool,
    ess: dict,
    dt_h: float,
) -> tuple[float, float, float]:
    """
    返回 (ess_dis_kw, ess_ch_kw, e_ess_new)。
    规则：仅在有剩余光伏时交流侧充电；仅在高价区间（购电价分位阈值以上）且有缺口时放电；其它静置。
    充电/放电均受功率与能量界约束，效率为 JSON 单向效率。
    """
    eta_c = float(ess["charge_efficiency"])
    eta_d = float(ess["discharge_efficiency"])
    p_ch_max = float(ess["max_charge_power_kw"])
    p_dis_max = float(ess["max_discharge_power_kw"])
    e_min = float(ess["min_energy_kwh"])
    e_max = float(ess["max_energy_kwh"])

    ess_dis = 0.0
    ess_ch = 0.0
    e = e_ess

    if is_high and deficit_kw > 1e-9 and e > e_min + 1e-9:
        p_cap_soc = (e - e_min) * eta_d / dt_h
        ess_dis = float(min(p_dis_max, p_cap_soc, deficit_kw))
        e -= (ess_dis * dt_h) / eta_d

    if surplus_pv_kw > 1e-9 and e < e_max - 1e-9:
        p_cap_soc = (e_max - e) / (eta_c * dt_h)
        ess_ch = float(min(p_ch_max, surplus_pv_kw, p_cap_soc))
        e += ess_ch * eta_c * dt_h

    e = float(np.clip(e, e_min, e_max))
    return ess_dis, ess_ch, e


def run_baseline(data: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    dt = data["dt_hours"]
    T = data["n_slots"]
    load_df = data["load"]
    pv_df = data["pv"]
    price_df = data["price"]
    grid_df = data["grid"]
    ess = data["ess"]
    ev_df = data["ev_sessions"]
    avail = data["avail"]
    p_ch_mat = data["p_ch_mat"]
    n_ev = data["n_ev"]
    eta_ev = float(data["ev_charge_efficiency"])

    L = load_df["total_native_load_kw"].to_numpy(dtype=np.float64)
    pv_av = pv_df["pv_available_kw"].to_numpy(dtype=np.float64)
    buy = price_df["grid_buy_price_cny_per_kwh"].to_numpy(dtype=np.float64)
    sell = price_df["grid_sell_price_cny_per_kwh"].to_numpy(dtype=np.float64)
    g_imp_lim = grid_df["grid_import_limit_kw"].to_numpy(dtype=np.float64)
    g_exp_lim = grid_df["grid_export_limit_kw"].to_numpy(dtype=np.float64)
    slot_id = load_df["slot_id"].to_numpy(dtype=np.int64)
    ts = load_df["timestamp"].astype(str)

    high_mask = _high_price_mask(buy)

    ev_e = ev_df["initial_energy_kwh"].to_numpy(dtype=np.float64).copy()
    ev_req = ev_df["required_energy_at_departure_kwh"].to_numpy(dtype=np.float64)
    ev_cap = ev_df["battery_capacity_kwh"].to_numpy(dtype=np.float64)
    dep_slot = ev_df["departure_slot"].to_numpy(dtype=np.int64)
    dep_ts = ev_df["departure_time"].astype(str).to_numpy()

    e_ess = float(ess["initial_energy_kwh"])

    energy_at_departure = np.full(n_ev, np.nan, dtype=np.float64)

    rows: list[dict[str, Any]] = []

    for t in range(T):
        a_row = avail[t]
        pch_row = p_ch_mat[t]
        p_ev = simulate_ev_baseline(ev_e, ev_req, ev_cap, a_row, pch_row, dt, eta_ev)
        ev_sum_p = float(p_ev.sum())
        D = float(L[t] + ev_sum_p)

        pv_a = float(pv_av[t])
        pv_local = min(pv_a, D)
        net_before_ess = float(D - pv_local)
        deficit = net_before_ess
        surplus = pv_a - pv_local

        is_h = bool(high_mask[t])
        ess_dis, ess_ch, e_ess = simulate_ess_rule(
            e_ess, deficit, surplus, float(buy[t]), is_h, ess, dt
        )
        deficit -= ess_dis
        net_after_ess = float(max(0.0, deficit))

        g_imp = float(min(g_imp_lim[t], max(0.0, deficit)))
        deficit -= g_imp
        unmet = float(max(0.0, deficit))

        surplus_after = surplus - ess_ch
        g_exp = float(min(g_exp_lim[t], max(0.0, surplus_after)))
        surplus_after -= g_exp
        curt = float(max(0.0, surplus_after))

        ev_e = ev_e + eta_ev * p_ev * dt

        sid = int(slot_id[t])
        for j in range(n_ev):
            if sid == int(dep_slot[j]):
                energy_at_departure[j] = float(ev_e[j])

        rows.append(
            {
                "timestamp": ts[t],
                "slot_id": sid,
                "native_load_kw": L[t],
                "ev_total_charge_kw": ev_sum_p,
                "ev_total_discharge_kw": 0.0,
                "total_load_with_ev_kw": D,
                "pv_available_kw": pv_a,
                "pv_used_locally_kw": pv_local,
                "pv_to_ess_kw": ess_ch,
                "pv_export_kw": g_exp,
                "pv_curtailed_kw": curt,
                "ess_charge_kw": ess_ch,
                "ess_discharge_kw": ess_dis,
                "ess_energy_kwh": e_ess,
                "grid_import_kw": g_imp,
                "grid_export_kw": g_exp,
                "unmet_load_kw": unmet,
                "net_load_before_ess_kw": net_before_ess,
                "net_load_after_ess_kw": net_after_ess,
                "residual_demand_after_pv_kw": net_before_ess,
                "residual_demand_after_ess_kw": net_after_ess,
                "buy_price": buy[t],
                "sell_price": sell[t],
            }
        )

    ts_df = pd.DataFrame(rows)

    connected_slots = avail.sum(axis=0).astype(int)
    final_e = ev_e.copy()
    ev_rows = []
    for j in range(n_ev):
        e_dep = energy_at_departure[j]
        if math.isnan(e_dep):
            e_dep = float(final_e[j])
        req_j = float(ev_req[j])
        met_dep = e_dep >= req_j - 1e-6
        ratio = float(e_dep / req_j) if req_j > 1e-12 else float("nan")
        ev_rows.append(
            {
                "ev_index": int(ev_df.iloc[j]["ev_index"]),
                "session_id": ev_df.iloc[j]["session_id"],
                "departure_timestamp": dep_ts[j],
                "initial_energy_kwh": float(ev_df.iloc[j]["initial_energy_kwh"]),
                "required_energy_at_departure_kwh": req_j,
                "final_energy_at_departure_kwh": float(e_dep),
                "demand_met_flag_at_departure": bool(met_dep),
                "energy_completion_ratio": ratio,
                "demand_met_flag": bool(met_dep),
                "charged_energy_kwh": float(final_e[j] - float(ev_df.iloc[j]["initial_energy_kwh"])),
                "connected_slots": int(connected_slots[j]),
            }
        )
    ev_out = pd.DataFrame(ev_rows)

    kpis = summarize_kpis(ts_df, ev_out, pv_av, dt)
    return ts_df, ev_out, kpis


def summarize_kpis(
    ts_df: pd.DataFrame,
    ev_out: pd.DataFrame,
    pv_available: np.ndarray,
    dt_h: float,
) -> dict[str, Any]:
    imp_kwh = (ts_df["grid_import_kw"] * dt_h).sum()
    exp_kwh = (ts_df["grid_export_kw"] * dt_h).sum()
    curt_kwh = (ts_df["pv_curtailed_kw"] * dt_h).sum()
    cost = float(
        (ts_df["grid_import_kw"] * ts_df["buy_price"] * dt_h).sum()
        - (ts_df["grid_export_kw"] * ts_df["sell_price"] * dt_h).sum()
    )
    pv_avail_kwh = float(np.sum(pv_available * dt_h))
    # 消纳率：未弃光能量占可用光伏能量之比（含上网）
    pv_util = float(1.0 - curt_kwh / pv_avail_kwh) if pv_avail_kwh > 1e-9 else float("nan")

    ev_met_rate = float(ev_out["demand_met_flag"].mean()) if len(ev_out) else float("nan")
    peak_imp = float(ts_df["grid_import_kw"].max())
    unmet_kwh = float((ts_df["unmet_load_kw"] * dt_h).sum())
    ess_ch_t = float((ts_df["ess_charge_kw"] * dt_h).sum())
    ess_dis_t = float((ts_df["ess_discharge_kw"] * dt_h).sum())

    ev_ch_kwh = float((ts_df["ev_total_charge_kw"] * dt_h).sum())
    pv_loc_kwh = float((ts_df["pv_used_locally_kw"] * dt_h).sum())
    pv_ess_kwh = float((ts_df["pv_to_ess_kw"] * dt_h).sum())
    sell_rev = float((ts_df["grid_export_kw"] * ts_df["sell_price"] * dt_h).sum())
    avg_g_imp = float(ts_df["grid_import_kw"].mean())
    ess_e = ts_df["ess_energy_kwh"].to_numpy(dtype=np.float64)
    ess_min = float(np.min(ess_e))
    ess_max = float(np.max(ess_e))
    ratios = pd.to_numeric(ev_out["energy_completion_ratio"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    ev_avg_ratio = float(ratios.mean()) if len(ratios) else float("nan")
    unmet_slots = int((ts_df["unmet_load_kw"].to_numpy(dtype=np.float64) > 1e-6).sum())

    pv_util_out = None if math.isnan(pv_util) else round(pv_util, 6)
    ev_ratio_out = None if math.isnan(ev_avg_ratio) else round(ev_avg_ratio, 6)

    return {
        "total_grid_import_kwh": round(imp_kwh, 4),
        "total_grid_export_kwh": round(exp_kwh, 4),
        "total_pv_curtailed_kwh": round(curt_kwh, 4),
        "total_cost_cny": round(cost, 4),
        "pv_utilization_rate": pv_util_out,
        "ev_demand_met_rate": round(ev_met_rate, 6),
        "peak_grid_import_kw": round(peak_imp, 4),
        "total_unmet_load_kwh": round(unmet_kwh, 4),
        "ess_total_charge_throughput_kwh": round(ess_ch_t, 4),
        "ess_total_discharge_throughput_kwh": round(ess_dis_t, 4),
        "total_ev_charge_kwh": round(ev_ch_kwh, 4),
        "total_pv_used_locally_kwh": round(pv_loc_kwh, 4),
        "total_pv_to_ess_kwh": round(pv_ess_kwh, 4),
        "total_sell_revenue_cny": round(sell_rev, 4),
        "average_grid_import_kw": round(avg_g_imp, 4),
        "ess_min_energy_kwh": round(ess_min, 4),
        "ess_max_energy_kwh": round(ess_max, 4),
        "ev_average_completion_ratio": ev_ratio_out,
        "unmet_load_slots_count": unmet_slots,
    }


def write_readme(path: Path) -> None:
    text = f"""# 问题1 非协同调度基准（baseline）

## 策略说明

1. **建筑负荷**：仅使用 `total_native_load_kw`，柔性负荷调节量为 0。
2. **电动汽车**：到站即充——在连接时段内若电量未达离站目标，则按交流侧功率
   `min(最大充电功率上限, 目标与容量约束折算后的需求功率)` 充电；电池侧能量
   **ΔE = η_ev × P_ac × Δt**，其中 **η_ev = {EV_CHARGE_EFFICIENCY}**（见下「假设」）。
   **不向园区放电（无 V2B）**；不考虑电价与光伏余量；未达标会话仅标记，不中断仿真。
3. **固定储能**：
   - 仅使用**剩余光伏**（满足负荷与 EV 后的交流剩余）以效率 `charge_efficiency` 充电；
   - 当购电价落入**全周高价区间**——即不低于购电价样本的 **{ESS_DISCHARGE_PRICE_QUANTILE:.2f} 分位数**（约最贵 **{(1 - ESS_DISCHARGE_PRICE_QUANTILE) * 100:.0f}%** 时段）——且存在功率缺口时，按效率 `discharge_efficiency` 放电以降低购电；
   - 其余时段静置（不从电网充电）。
4. **光伏**：优先供本地（负荷+EV 充电）；剩余依次用于储能充电、上网（受出口上限）、弃光。
5. **电网**：缺口购电受进口上限约束；不足部分记为 `unmet_load_kw`，仿真继续。

## 时段内计算顺序

对每个 15 min：`EV 充电功率（交流）` → `总需求 = 原生负荷 + EV 充电` → `光伏供本地` → `高价区间则储能放电补缺口` → `购电` → `剩余光伏充储能` → `上网与弃光`。

## 输出字段（timeseries）

| 字段 | 含义 |
|------|------|
| native_load_kw | 园区原生总负荷 |
| ev_total_charge_kw | EV 总充电功率（**交流侧**，kW） |
| ev_total_discharge_kw | 基准为 0 |
| total_load_with_ev_kw | 原生负荷 + EV 充电 |
| pv_used_locally_kw | 光伏直接供负荷+EV 部分 |
| pv_to_ess_kw | 剩余光伏进储能的充电功率 |
| pv_export_kw | 再剩余经上网功率 |
| pv_curtailed_kw | 超上网上限的弃光 |
| net_load_before_ess_kw | 总需求 − 本地消纳光伏（储能动作前净需求） |
| net_load_after_ess_kw | 储能放电后的净需求（购电前） |
| residual_demand_after_pv_kw | 与 net_load_before_ess_kw 同义（表述用） |
| residual_demand_after_ess_kw | 与 net_load_after_ess_kw 同义（表述用） |
| ess_energy_kwh | **时段末**储能能量 |
| unmet_load_kw | 购电达上限后仍不足的功率缺口 |
| buy_price / sell_price | 电价（元/kWh） |

## KPI 说明

- **pv_utilization_rate**：`1 - 总弃光电量 / 总可发电量`（含本地、储能、上网，弃光以外均视为已利用）。
- **total_ev_charge_kwh**：交流侧 EV 充电电量累计。
- **ev_average_completion_ratio**：各车 `energy_completion_ratio`（离站时）的算术平均（仅对有效值）。

## 假设与局限

- **η_ev（EV_CHARGE_EFFICIENCY）**：输入未提供实测充电曲线，取 **{EV_CHARGE_EFFICIENCY}** 代表车载充电机 AC→电池的典型效率（工程文献常见约 0.90–0.95），用于统一折算交流充电功率与电池能量，保证状态方程物理一致。
- **高价区间**：由全周购电价 **{ESS_DISCHARGE_PRICE_QUANTILE:.2f} 分位**阈值确定，**非**全局优化；若全周电价完全相同，则阈值等于该常数，所有时段均落入高价区间（与分位定义一致）。
- 未建立交流潮流与损耗模型；功率瞬时平衡。
- 未考虑充电桩数量同时率等约束，仅用单车功率上限矩阵。

## 本数据周可能出现的现象

若全周每个时段均有「原生负荷 + EV 充电 ≥ 可用光伏」，则**剩余光伏为 0**，储能按规则**无法**从光伏充电（`pv_to_ess_kw` 恒为 0），仅能在高价时段放电直至触及 SOC 下界。此为数据与规则共同结果，非程序错误。

## 输入校验

仿真前写入 `baseline_input_validation_report.md`（与脚本同输出目录），汇总矩阵维度、SOC/功率边界及 V2B 与放电矩阵一致性等检查。

---
*生成脚本：`code/python/baseline/run_baseline_noncooperative.py`*
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_inputs()
    in_errs, in_warns = collect_input_validation_issues(data)
    write_input_validation_report(INPUT_VALIDATION_REPORT, in_errs, in_warns, data)
    if in_errs:
        raise ValueError(
            "输入校验未通过，已写入 baseline_input_validation_report.md：\n"
            + "\n".join(in_errs)
        )

    ts_df, ev_df, kpis = run_baseline(data)

    ts_df.to_csv(OUT_DIR / "baseline_timeseries_results.csv", index=False, encoding="utf-8-sig")
    ev_df.to_csv(OUT_DIR / "baseline_ev_session_summary.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "baseline_kpi_summary.json").write_text(
        json.dumps(kpis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(OUT_DIR / "baseline_readme.md")

    print("=== baseline 非协同仿真完成 ===")
    print(f"输出目录: {OUT_DIR}")
    print(f"总成本 (元): {kpis['total_cost_cny']}")
    print(f"光伏消纳率: {kpis['pv_utilization_rate']}")
    print(f"EV 需求满足率: {kpis['ev_demand_met_rate']}")
    print(f"峰值购电功率 (kW): {kpis['peak_grid_import_kw']}")


if __name__ == "__main__":
    main()
