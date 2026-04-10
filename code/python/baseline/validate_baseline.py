# -*- coding: utf-8 -*-
"""
baseline 非协同仿真结果核查（不修改仿真逻辑，仅读输出与输入做一致性校验）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "results" / "problem1_baseline"
REPORT_PATH = OUT_DIR / "baseline_validation_report.md"
EPS = 1e-6


def _load_baseline_module():
    path = Path(__file__).resolve().parent / "run_baseline_noncooperative.py"
    spec = importlib.util.spec_from_file_location("baseline_run", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def replay_ev_total_charge(data: dict) -> np.ndarray:
    """按与主程序相同的到站即充规则回放各时段 EV 总充电功率。"""
    dt = data["dt_hours"]
    T = data["n_slots"]
    avail = data["avail"]
    p_ch_mat = data["p_ch_mat"]
    ev_df = data["ev_sessions"]
    ev_e = ev_df["initial_energy_kwh"].to_numpy(dtype=np.float64).copy()
    ev_req = ev_df["required_energy_at_departure_kwh"].to_numpy(dtype=np.float64)
    ev_cap = ev_df["battery_capacity_kwh"].to_numpy(dtype=np.float64)
    eta_ev = float(data.get("ev_charge_efficiency", 1.0))
    mod = _load_baseline_module()
    sim_ev = mod.simulate_ev_baseline
    out = np.zeros(T, dtype=np.float64)
    for t in range(T):
        p_ev = sim_ev(ev_e, ev_req, ev_cap, avail[t], p_ch_mat[t], dt, eta_ev)
        out[t] = float(p_ev.sum())
        ev_e = ev_e + eta_ev * p_ev * dt
    return out


def validate_all() -> tuple[str, dict]:
    mod = _load_baseline_module()
    ts_path = OUT_DIR / "baseline_timeseries_results.csv"
    kpi_path = OUT_DIR / "baseline_kpi_summary.json"
    if not ts_path.exists():
        raise FileNotFoundError(f"缺少仿真输出: {ts_path}")
    if not kpi_path.exists():
        raise FileNotFoundError(f"缺少 KPI 文件: {kpi_path}")

    ts = pd.read_csv(ts_path)
    kpi = json.loads(kpi_path.read_text(encoding="utf-8"))
    data = mod.load_inputs()

    dt = data["dt_hours"]
    load_in = data["load"]["total_native_load_kw"].to_numpy(dtype=np.float64)
    g_lim = data["grid"]["grid_import_limit_kw"].to_numpy(dtype=np.float64)
    buy = data["price"]["grid_buy_price_cny_per_kwh"].to_numpy(dtype=np.float64)

    lines: list[str] = []
    lines.append("# Baseline 非协同仿真 — 结果核查报告")
    lines.append("")
    lines.append("本报告由 `code/python/baseline/validate_baseline.py` 根据仿真输出与 `final_model_inputs` 自动生成。")
    lines.append("")
    inv = OUT_DIR / "baseline_input_validation_report.md"
    if inv.exists():
        lines.append(f"输入合法性预检见：`{inv.name}`（由主脚本在仿真前生成）。")
        lines.append("")

    # --- 1. EV 到站即充、不可放电 ---
    ev_dis = ts["ev_total_discharge_kw"].to_numpy(dtype=np.float64)
    ok_no_v2b = bool(np.all(np.abs(ev_dis) < EPS))
    replay = replay_ev_total_charge(data)
    sim_ev = ts["ev_total_charge_kw"].to_numpy(dtype=np.float64)
    ev_ch_match = bool(np.all(np.abs(replay - sim_ev) < 1e-3))
    lines.append("## 1. EV：到站即充、不向园区放电")
    lines.append("")
    lines.append(f"- **ev_total_discharge_kw 全为 0**：{'通过' if ok_no_v2b else '未通过'}（容差 {EPS}）。")
    lines.append(
        f"- **各时段总充电功率与规则回放一致**：{'通过' if ev_ch_match else '未通过'}（与输入矩阵/会话重放 `simulate_ev_baseline` 逐时段比对，容差 1e-3 kW）。"
    )
    if not ev_ch_match:
        diff = np.abs(replay - sim_ev)
        lines.append(f"  - 最大绝对偏差：{float(diff.max()):.6f} kW，首个不一致 slot_id：{int(ts.loc[diff.argmax(), 'slot_id'])}。")
    lines.append("")

    # --- 2. 建筑负荷未调节 ---
    native = ts["native_load_kw"].to_numpy(dtype=np.float64)
    ok_load = bool(np.all(np.abs(native - load_in) < 1e-3))
    lines.append("## 2. 建筑负荷未参与调节")
    lines.append("")
    lines.append(
        f"- **native_load_kw 与输入 `total_native_load_kw` 逐时段一致**：{'通过' if ok_load else '未通过'}（容差 1e-3 kW）。"
    )
    lines.append("")

    # --- 3. 储能规则一致性（非全局优化：行为与声明规则一致）---
    high = mod._high_price_mask(buy)
    pv_a = ts["pv_available_kw"].to_numpy(float)
    pv_l = ts["pv_used_locally_kw"].to_numpy(float)
    D = ts["total_load_with_ev_kw"].to_numpy(float)
    ess_ch = ts["ess_charge_kw"].to_numpy(float)
    ess_dis = ts["ess_discharge_kw"].to_numpy(float)
    pv_ess = ts["pv_to_ess_kw"].to_numpy(float)

    ok_pv_ess_link = bool(np.all(np.abs(pv_ess - ess_ch) < 1e-3))
    viol_dis = []
    viol_ch = []
    for i in range(len(ts)):
        if ess_dis[i] > EPS:
            bad = False
            if not high[i]:
                bad = True
            if not (D[i] > pv_l[i] + 1e-3):
                bad = True
            if bad:
                viol_dis.append(int(ts.iloc[i]["slot_id"]))
        if ess_ch[i] > EPS:
            if not (pv_a[i] > pv_l[i] + 1e-3):
                viol_ch.append(int(ts.iloc[i]["slot_id"]))
    ok_ess_dis_rule = len(viol_dis) == 0
    ok_ess_ch_rule = len(viol_ch) == 0

    lines.append("## 3. 储能：与声明规则一致（非全局优化）")
    lines.append("")
    lines.append(
        "- **说明**：无法从数值结果单独「证明」未做全局优化；此处校验输出是否与**已实现的规则**一致。"
    )
    lines.append(f"- **pv_to_ess_kw 与 ess_charge_kw 一致（光伏充电路径）**：{'通过' if ok_pv_ess_link else '未通过'}。")
    lines.append(
        f"- **放电仅出现在购电高价区间（分位阈值以上）且存在本地缺口**（`total_load_with_ev > pv_used_locally`）：{'通过' if ok_ess_dis_rule else '未通过'}。"
    )
    if viol_dis:
        lines.append(f"  - 异常 slot_id（去重前可能重复列出）示例：{sorted(set(viol_dis))[:20]}")
    lines.append(
        f"- **充电仅在有剩余光伏时**（`pv_available > pv_used_locally`）：{'通过' if ok_ess_ch_rule else '未通过'}。"
    )
    if viol_ch:
        lines.append(f"  - 异常 slot_id 示例：{sorted(set(viol_ch))[:20]}")
    lines.append("")

    # --- 4. 购电上限 ---
    g_imp = ts["grid_import_kw"].to_numpy(float)
    ok_grid = bool(np.all(g_imp <= g_lim + 1e-3))
    lines.append("## 4. 电网购电功率上限")
    lines.append("")
    lines.append(f"- **grid_import_kw ≤ grid_import_limit_kw（输入）**：{'通过' if ok_grid else '未通过'}。")
    if not ok_grid:
        bad = np.where(g_imp > g_lim + 1e-3)[0]
        lines.append(f"  - 越限行数：{len(bad)}，示例 slot_id：{ts.iloc[bad[:10]]['slot_id'].tolist()}。")
    lines.append("")

    # --- 5. unmet ---
    unmet = ts["unmet_load_kw"].to_numpy(float)
    unmet_kwh = float((unmet * dt).sum())
    pos = unmet > EPS
    n_pos = int(pos.sum())
    lines.append("## 5. 未供能缺口 unmet_load_kw")
    lines.append("")
    lines.append(f"- **全周折算电量**（∑ unmet×Δt）：{unmet_kwh:.4f} kWh。")
    lines.append(f"- **unmet > 0 的时段数**：{n_pos}。")
    if n_pos > 0:
        sub = ts.loc[pos, ["slot_id", "timestamp", "unmet_load_kw"]].head(30)
        lines.append("- **出现时段（节选）**：")
        lines.append("")
        lines.append("| slot_id | timestamp | unmet_load_kw |")
        lines.append("|---------|-----------|---------------|")
        for _, r in sub.iterrows():
            lines.append(f"| {int(r['slot_id'])} | {r['timestamp']} | {r['unmet_load_kw']} |")
        lines.append("")
    lines.append("")

    # --- 6. 光伏分配 ---
    pv_exp = ts["pv_export_kw"].to_numpy(float)
    pv_curt = ts["pv_curtailed_kw"].to_numpy(float)
    balance = pv_l + pv_ess + pv_exp + pv_curt - pv_a
    ok_balance = bool(np.all(np.abs(balance) < 1e-2))
    lines.append("## 6. 光伏分配：本地 → 储能 → 售电 → 弃光")
    lines.append("")
    lines.append(
        f"- **功率平衡**：`pv_used_locally + pv_to_ess + pv_export + pv_curtailed = pv_available`：{'通过' if ok_balance else '未通过'}（容差 0.02 kW）。"
    )
    ok_local = bool(np.all(np.abs(pv_l - np.minimum(pv_a, D)) < 1e-2))
    lines.append(
        f"- **本地消纳**：`pv_used_locally = min(pv_available, total_load_with_ev)`：{'通过' if ok_local else '未通过'}。"
    )
    surplus_after_local = pv_a - pv_l
    surplus_after_ess = surplus_after_local - pv_ess
    exp_lim_arr = data["grid"]["grid_export_limit_kw"].to_numpy(dtype=np.float64)
    ok_export_order = True
    viol_curt: list[int] = []
    for i in range(len(ts)):
        lim = float(exp_lim_arr[i])
        sae = float(surplus_after_ess[i])
        gexp_exp = min(lim, max(0.0, sae))
        curt_exp = max(0.0, sae - gexp_exp)
        if abs(pv_exp[i] - gexp_exp) > 1e-2 or abs(pv_curt[i] - curt_exp) > 1e-2:
            ok_export_order = False
            viol_curt.append(int(ts.iloc[i]["slot_id"]))
    viol_curt = sorted(set(viol_curt))[:15]
    lines.append(
        f"- **剩余光伏先上网（受出口限）再弃光**：与逐时段公式一致：{'通过' if ok_export_order else '未通过'}。"
    )
    if viol_curt:
        lines.append(f"  - 不一致 slot_id 示例：{viol_curt}")
    lines.append("")

    # --- 7. KPI ---
    lines.append("## 7. 主要 KPI 汇总与含义")
    lines.append("")
    kpi_rows = [
        ("total_grid_import_kwh", "全周从电网购入的有功电量（kWh）。"),
        ("total_grid_export_kwh", "全周向电网送出的有功电量（kWh）。"),
        ("total_pv_curtailed_kwh", "全周弃光电量（kWh）。"),
        ("total_cost_cny", "购电成本减售电收入的近似总费用（元）。"),
        ("pv_utilization_rate", "光伏利用程度：1 − 弃光电量/可发电量（见 baseline 说明）。"),
        ("ev_demand_met_rate", "离站能量需求达标的车辆比例。"),
        ("peak_grid_import_kw", "单时段最大购电功率（kW）。"),
        ("total_unmet_load_kwh", "购电达上限后仍不足的缺电量折算（kWh）。"),
        ("ess_total_charge_throughput_kwh", "储能交流侧充电能量累计（kWh）。"),
        ("ess_total_discharge_throughput_kwh", "储能交流侧放电能量累计（kWh）。"),
        ("total_ev_charge_kwh", "EV 交流侧充电电量累计（kWh）。"),
        ("total_pv_used_locally_kwh", "光伏本地直接消纳电量（kWh）。"),
        ("total_pv_to_ess_kwh", "光伏充入储能的电量（kWh）。"),
        ("total_sell_revenue_cny", "售电收入（元，∑ 上网功率×售电价×Δt）。"),
        ("average_grid_import_kw", "全时段平均购电功率（kW）。"),
        ("ess_min_energy_kwh", "储能 SOC 轨迹最小值（kWh）。"),
        ("ess_max_energy_kwh", "储能 SOC 轨迹最大值（kWh）。"),
        ("ev_average_completion_ratio", "EV 离站能量完成比（均值）。"),
        ("unmet_load_slots_count", "存在未供能缺口的时段数。"),
    ]
    lines.append("| KPI | 数值 | 含义 |")
    lines.append("|-----|------|------|")
    for key, desc in kpi_rows:
        v = kpi.get(key, "")
        lines.append(f"| `{key}` | {v} | {desc} |")
    lines.append("")

    all_ok = (
        ok_no_v2b
        and ev_ch_match
        and ok_load
        and ok_pv_ess_link
        and ok_ess_dis_rule
        and ok_ess_ch_rule
        and ok_grid
        and ok_balance
        and ok_local
        and ok_export_order
    )
    lines.append("## 总判定")
    lines.append("")
    lines.append("**全部数值核查项通过。**" if all_ok else "**存在未通过项，请见上文各节。**")
    lines.append("")

    summary = {
        "all_ok": all_ok,
        "total_cost_cny": kpi.get("total_cost_cny"),
        "pv_utilization_rate": kpi.get("pv_utilization_rate"),
        "ev_demand_met_rate": kpi.get("ev_demand_met_rate"),
        "peak_grid_import_kw": kpi.get("peak_grid_import_kw"),
        "total_unmet_load_kwh": kpi.get("total_unmet_load_kwh"),
        "unmet_slots": n_pos,
    }

    return "\n".join(lines), summary


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body, s = validate_all()
    REPORT_PATH.write_text(body, encoding="utf-8")

    print("=== baseline 验证完成 ===")
    print(f"报告: {REPORT_PATH}")
    print(f"总成本 (元): {s['total_cost_cny']}")
    print(f"光伏利用率: {s['pv_utilization_rate']}")
    print(f"EV 需求满足率: {s['ev_demand_met_rate']}")
    print(f"峰值购电功率 (kW): {s['peak_grid_import_kw']}")
    print(f"未供能总量 (kWh): {s['total_unmet_load_kwh']}")
    print(f"unmet>0 时段数: {s['unmet_slots']}")
    print(f"核查总判定: {'全部通过' if s['all_ok'] else '存在未通过项'}")


if __name__ == "__main__":
    main()
