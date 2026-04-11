# -*- coding: utf-8 -*-
"""
模型检验分析脚本（problem2 / problem1 / baseline）

设计说明
--------
1. **数据来源**
   - **p2**：``results/problem2_lifecycle/single_run/<tag>/`` 下 ``run_meta.json``、
     ``objective_breakdown.json``、``timeseries.csv``（若存在）。
   - **p1**：``results/problem1_ultimate/p_1_5_timeseries.csv`` 与
     ``results/tables/objective_reconciliation_fullweek.csv`` 或附录中文 CSV。
   - **baseline**：``results/problem1_baseline/baseline_timeseries_results.csv``（含 ``ess_energy_kwh``）、
     ``baseline_ev_session_summary.csv``、``results/tables/objective_reconciliation_baseline_fullweek.csv``。
   - **problem2 权重扫描**：``results/tables/problem2_weight_scan_*.csv``（若存在多行且含 ``ess_deg_weight``、
     ``objective_recomputed`` 等列则做趋势类检验）。

2. **检验项与 pass 语义**
   - ``pass_flag`` 取 ``pass`` / ``fail`` / ``not_applicable``；缺文件或缺列时不抛异常，对应检查记为
     ``not_applicable`` 并说明原因。
   - ``value``：主要度量（数值、计数或 JSON 可序列化标量）；无则 ``null``。
   - ``threshold``：通过准则的阈值（脚本内常量，写入表内便于论文引用）。

3. **已知局限**
   - 时序表无单车 SOC；**EV 离场**对 p2/p1 若无 ``demand_met`` 类导出则 ``not_applicable``。
   - **EV 同时充放**：聚合 ``P_ev_ch_total_kw`` / ``P_ev_dis_total_kw`` 同向为正**不能**等价于单车违反
     V2B 互斥，该项对协同模型标注为参考性说明，避免误判。

4. **输出**
   - ``results/tables/model_validation_checks.csv``
   - ``results/tables/model_validation_checks.json``
   - 控制台打印各 ``model_name/run_tag`` 的 pass / fail / n_a 计数摘要。

用法
----
  python code/python/analysis/run_model_validation_checks.py
  python code/python/analysis/run_model_validation_checks.py --repo-root D:/数维杯比赛
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

RECORD_KEYS = (
    "model_name",
    "run_tag",
    "check_name",
    "pass_flag",
    "value",
    "threshold",
    "message",
)

# --- 阈值（与论文/附录中可一同报告）---
GAP_ABS_TOL_YUAN = 0.02
EPS_GRID_KW = 1.0
EPS_ESS_KW = 0.5
SOC_BOUND_TOL_KWH = 1.0
NEG_TOL = 1e-6
SCAN_MIN_ROWS = 3
SCAN_SPEARMAN_WARN = -0.3


def _record(
    model_name: str,
    run_tag: str,
    check_name: str,
    pass_flag: str,
    value: Any,
    threshold: Any,
    message: str,
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "run_tag": run_tag,
        "check_name": check_name,
        "pass_flag": pass_flag,
        "value": value,
        "threshold": threshold,
        "message": message,
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_ess_params(repo: Path) -> dict[str, Any] | None:
    p = repo / "data" / "processed" / "final_model_inputs" / "ess_params.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _integrate_ess_energy_kwh(ts: pd.DataFrame, ess: dict[str, Any]) -> pd.Series | None:
    """由 P_ess_ch_kw / P_ess_dis_kw 递推时段末能量（与常见 SOC 递推一致）。"""
    need = ("P_ess_ch_kw", "P_ess_dis_kw", "delta_t_h")
    if not all(c in ts.columns for c in need):
        return None
    eta_ch = float(ess.get("charge_efficiency", 0.95))
    eta_dis = float(ess.get("discharge_efficiency", 0.95))
    e0 = float(ess.get("initial_energy_kwh", 0.0))
    dt = ts["delta_t_h"].to_numpy(dtype=float)
    pch = ts["P_ess_ch_kw"].to_numpy(dtype=float)
    pdi = ts["P_ess_dis_kw"].to_numpy(dtype=float)
    n = len(ts)
    e = np.zeros(n, dtype=float)
    cur = e0
    for t in range(n):
        cur = cur + eta_ch * pch[t] * dt[t] - pdi[t] / eta_dis * dt[t]
        e[t] = cur
    return pd.Series(e, index=ts.index)


def _checks_timeseries_common(
    model_name: str,
    run_tag: str,
    ts: pd.DataFrame,
    rows: list[dict[str, Any]],
    *,
    has_recover_col: bool,
) -> None:
    """购售互斥、ESS 充放互斥、非负惩罚量。"""
    if "P_buy_kw" in ts.columns and "P_sell_kw" in ts.columns:
        both = (
            (pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0) > EPS_GRID_KW)
            & (pd.to_numeric(ts["P_sell_kw"], errors="coerce").fillna(0.0) > EPS_GRID_KW)
        ).sum()
        rows.append(
            _record(
                model_name,
                run_tag,
                "no_simultaneous_grid_buy_sell_slots",
                "pass" if int(both) == 0 else "fail",
                int(both),
                f"count_slots_buy_and_sell_gt_{EPS_GRID_KW}kw",
                "购、售电功率同时大于阈值的时段数（互斥或数值应接近 0）。",
            )
        )
    else:
        rows.append(
            _record(
                model_name,
                run_tag,
                "no_simultaneous_grid_buy_sell_slots",
                "not_applicable",
                None,
                None,
                "时序缺少 P_buy_kw 或 P_sell_kw。",
            )
        )

    if "P_ess_ch_kw" in ts.columns and "P_ess_dis_kw" in ts.columns:
        both_e = (
            (pd.to_numeric(ts["P_ess_ch_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
            & (pd.to_numeric(ts["P_ess_dis_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
        ).sum()
        rows.append(
            _record(
                model_name,
                run_tag,
                "no_simultaneous_ess_charge_discharge_slots",
                "pass" if int(both_e) == 0 else "fail",
                int(both_e),
                f"count_slots_ch_and_dis_gt_{EPS_ESS_KW}kw",
                "ESS 充、放电功率同时大于阈值的时段数。",
            )
        )
    else:
        rows.append(
            _record(
                model_name,
                run_tag,
                "no_simultaneous_ess_charge_discharge_slots",
                "not_applicable",
                None,
                None,
                "时序缺少 ESS 功率列。",
            )
        )

    if "P_ev_ch_total_kw" in ts.columns and "P_ev_dis_total_kw" in ts.columns:
        both_v = (
            (pd.to_numeric(ts["P_ev_ch_total_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
            & (pd.to_numeric(ts["P_ev_dis_total_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
        ).sum()
        rows.append(
            _record(
                model_name,
                run_tag,
                "ev_fleet_ch_dis_positive_slots_reference",
                "not_applicable",
                int(both_v),
                "informational",
                "车队总充与总放同时为正可能来自不同车辆；非单车 V2B 互斥违反判据。",
            )
        )

    if "pv_curtail_kw" in ts.columns:
        mn = float(pd.to_numeric(ts["pv_curtail_kw"], errors="coerce").min())
        rows.append(
            _record(
                model_name,
                run_tag,
                "pv_curtail_non_negative",
                "pass" if mn >= -NEG_TOL else "fail",
                mn,
                f">= {-NEG_TOL}",
                "弃光功率最小值。",
            )
        )
    else:
        rows.append(
            _record(model_name, run_tag, "pv_curtail_non_negative", "not_applicable", None, None, "无 pv_curtail_kw 列。")
        )

    shed_col = "P_shed_total_kw" if "P_shed_total_kw" in ts.columns else None
    if shed_col:
        mn = float(pd.to_numeric(ts[shed_col], errors="coerce").min())
        rows.append(
            _record(
                model_name,
                run_tag,
                "load_shed_non_negative",
                "pass" if mn >= -NEG_TOL else "fail",
                mn,
                f">= {-NEG_TOL}",
                "切负荷功率最小值。",
            )
        )
    else:
        rows.append(
            _record(model_name, run_tag, "load_shed_non_negative", "not_applicable", None, None, "无切负荷列。")
        )

    if has_recover_col and "P_recover_total_kw" in ts.columns:
        mn = float(pd.to_numeric(ts["P_recover_total_kw"], errors="coerce").min())
        rows.append(
            _record(
                model_name,
                run_tag,
                "building_recover_non_negative",
                "pass" if mn >= -NEG_TOL else "fail",
                mn,
                f">= {-NEG_TOL}",
                "建筑恢复功率最小值（p2/p1 协同时序）。",
            )
        )
    else:
        rows.append(
            _record(
                model_name,
                run_tag,
                "building_recover_non_negative",
                "not_applicable",
                None,
                None,
                "无时序恢复列或非协同 baseline。",
            )
        )


def _checks_p2_run(repo: Path, run_dir: Path, rows: list[dict[str, Any]]) -> None:
    tag = run_dir.name
    meta = _read_json(run_dir / "run_meta.json")
    bd = _read_json(run_dir / "objective_breakdown.json")
    ts_path = run_dir / "timeseries.csv"

    if meta:
        st = str(meta.get("solver_status", ""))
        ok = st == "Optimal"
        rows.append(
            _record(
                "p2_lifecycle",
                tag,
                "solver_status_optimal",
                "pass" if ok else ("fail" if st else "not_applicable"),
                st or None,
                "Optimal",
                "CBC / PuLP 状态标签。",
            )
        )
    else:
        rows.append(
            _record("p2_lifecycle", tag, "solver_status_optimal", "not_applicable", None, "Optimal", "无 run_meta.json。")
        )

    if bd and "objective_abs_gap" in bd:
        gap = float(bd["objective_abs_gap"]) if bd["objective_abs_gap"] is not None and not math.isnan(float(bd["objective_abs_gap"])) else None
        if gap is not None:
            rows.append(
                _record(
                    "p2_lifecycle",
                    tag,
                    "objective_abs_gap_small",
                    "pass" if gap <= GAP_ABS_TOL_YUAN else "fail",
                    gap,
                    f"<= {GAP_ABS_TOL_YUAN}",
                    "目标重算与求解器目标绝对差（元）。",
                )
            )
        else:
            rows.append(
                _record("p2_lifecycle", tag, "objective_abs_gap_small", "not_applicable", None, None, "objective_abs_gap 非有限值。")
            )
    else:
        rows.append(
            _record("p2_lifecycle", tag, "objective_abs_gap_small", "not_applicable", None, None, "无 objective_breakdown.json 或无 objective_abs_gap。")
        )

    ess = _read_ess_params(repo)
    if ts_path.is_file() and ess:
        try:
            ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        except OSError:
            ts = pd.DataFrame()
        if len(ts) and _integrate_ess_energy_kwh(ts, ess) is not None:
            e_series = _integrate_ess_energy_kwh(ts, ess)
            assert e_series is not None
            emin = float(ess.get("min_energy_kwh", 0.0))
            emax = float(ess.get("max_energy_kwh", float("inf")))
            below = float((e_series < emin - SOC_BOUND_TOL_KWH).sum())
            above = float((e_series > emax + SOC_BOUND_TOL_KWH).sum())
            ok = below == 0 and above == 0
            rows.append(
                _record(
                    "p2_lifecycle",
                    tag,
                    "ess_energy_within_bounds",
                    "pass" if ok else "fail",
                    {"violations_below": int(below), "violations_above": int(above), "e_min": float(e_series.min()), "e_max": float(e_series.max())},
                    {"min_kwh": emin, "max_kwh": emax, "tol_kwh": SOC_BOUND_TOL_KWH},
                    "由时序功率与 ess_params 递推的 SOC 是否越界。",
                )
            )
        else:
            rows.append(
                _record("p2_lifecycle", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无法由时序递推 ESS 能量。")
            )
    else:
        rows.append(
            _record("p2_lifecycle", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无时序或 ess_params.json。")
        )

    rows.append(
        _record(
            "p2_lifecycle",
            tag,
            "ev_departure_demand_met",
            "not_applicable",
            None,
            None,
            "p2 单次目录未导出逐会话 demand_met；请用专门后处理或 baseline 对比。",
        )
    )

    if ts_path.is_file():
        try:
            ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        except OSError:
            ts = pd.DataFrame()
        if len(ts):
            _checks_timeseries_common("p2_lifecycle", tag, ts, rows, has_recover_col=True)
        else:
            for name, msg in [
                ("no_simultaneous_grid_buy_sell_slots", "时序为空。"),
                ("no_simultaneous_ess_charge_discharge_slots", "时序为空。"),
                ("ev_fleet_ch_dis_positive_slots_reference", "时序为空。"),
                ("pv_curtail_non_negative", "时序为空。"),
                ("load_shed_non_negative", "时序为空。"),
                ("building_recover_non_negative", "时序为空。"),
            ]:
                rows.append(_record("p2_lifecycle", tag, name, "not_applicable", None, None, msg))
    else:
        for name, msg in [
            ("no_simultaneous_grid_buy_sell_slots", "无 timeseries.csv。"),
            ("no_simultaneous_ess_charge_discharge_slots", "无 timeseries.csv。"),
            ("ev_fleet_ch_dis_positive_slots_reference", "无 timeseries.csv。"),
            ("pv_curtail_non_negative", "无 timeseries.csv。"),
            ("load_shed_non_negative", "无 timeseries.csv。"),
            ("building_recover_non_negative", "无 timeseries.csv。"),
        ]:
            rows.append(_record("p2_lifecycle", tag, name, "not_applicable", None, None, msg))


def _checks_p1(repo: Path, rows: list[dict[str, Any]]) -> None:
    tag = "p1_ultimate_latest"
    ts_path = repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
    rows.append(
        _record("p1_coordinated", tag, "solver_status_optimal", "not_applicable", None, None, "p1 脚本未写入求解器状态文件。")
    )

    tables = repo / "results" / "tables"
    fw = tables / "objective_reconciliation_fullweek.csv"
    ap = tables / "objective_reconciliation_appendix.csv"
    costs: dict[str, float] | None = None
    if fw.is_file():
        try:
            df = pd.read_csv(fw, encoding="utf-8-sig")
            if "cost_item" in df.columns and "value_yuan" in df.columns:
                m = {str(r["cost_item"]).strip(): float(r["value_yuan"]) for _, r in df.iterrows()}
                ofs = m.get("Objective from solver")
                ore = m.get("Objective recomputed from solution")
                if ofs is not None and ore is not None:
                    costs = {"gap": abs(float(ofs) - float(ore))}
        except (OSError, ValueError, TypeError, KeyError):
            pass
    if costs is None and ap.is_file():
        try:
            df = pd.read_csv(ap, encoding="utf-8-sig")
            c0, c1 = df.columns[0], df.columns[1]
            zh_of = "最优目标函数值"
            zh_re = "解后重算目标值"
            ofs = ore = None
            for _, r in df.iterrows():
                if str(r[c0]).strip() == zh_of:
                    ofs = float(str(r[c1]).replace(",", ""))
                if str(r[c0]).strip() == zh_re:
                    ore = float(str(r[c1]).replace(",", ""))
            if ofs is not None and ore is not None:
                costs = {"gap": abs(float(ofs) - float(ore))}
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            pass

    if costs and "gap" in costs:
        g = float(costs["gap"])
        rows.append(
            _record(
                "p1_coordinated",
                tag,
                "objective_abs_gap_small",
                "pass" if g <= GAP_ABS_TOL_YUAN else "fail",
                g,
                f"<= {GAP_ABS_TOL_YUAN}",
                "由全周或附录对账表两目标行差分。",
            )
        )
    else:
        rows.append(
            _record("p1_coordinated", tag, "objective_abs_gap_small", "not_applicable", None, None, "无法读取对账目标两行。")
        )

    ess = _read_ess_params(repo)
    if ts_path.is_file() and ess:
        try:
            ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        except OSError:
            ts = pd.DataFrame()
        if len(ts) and _integrate_ess_energy_kwh(ts, ess) is not None:
            e_series = _integrate_ess_energy_kwh(ts, ess)
            assert e_series is not None
            emin = float(ess.get("min_energy_kwh", 0.0))
            emax = float(ess.get("max_energy_kwh", float("inf")))
            below = float((e_series < emin - SOC_BOUND_TOL_KWH).sum())
            above = float((e_series > emax + SOC_BOUND_TOL_KWH).sum())
            ok = below == 0 and above == 0
            rows.append(
                _record(
                    "p1_coordinated",
                    tag,
                    "ess_energy_within_bounds",
                    "pass" if ok else "fail",
                    {"violations_below": int(below), "violations_above": int(above)},
                    {"min_kwh": emin, "max_kwh": emax},
                    "由 p1 时序递推 ESS 能量。",
                )
            )
        else:
            rows.append(
                _record("p1_coordinated", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无法递推 ESS。")
            )
    else:
        rows.append(
            _record("p1_coordinated", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无时序或 ess_params。")
        )

    rows.append(
        _record("p1_coordinated", tag, "ev_departure_demand_met", "not_applicable", None, None, "p1 未在本次导出逐会话离场标志。")
    )

    if ts_path.is_file():
        try:
            ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        except OSError:
            ts = pd.DataFrame()
        if len(ts):
            _checks_timeseries_common("p1_coordinated", tag, ts, rows, has_recover_col=True)
        else:
            for name in [
                "no_simultaneous_grid_buy_sell_slots",
                "no_simultaneous_ess_charge_discharge_slots",
                "ev_fleet_ch_dis_positive_slots_reference",
                "pv_curtail_non_negative",
                "load_shed_non_negative",
                "building_recover_non_negative",
            ]:
                rows.append(_record("p1_coordinated", tag, name, "not_applicable", None, None, "时序为空。"))
    else:
        for name in [
            "no_simultaneous_grid_buy_sell_slots",
            "no_simultaneous_ess_charge_discharge_slots",
            "ev_fleet_ch_dis_positive_slots_reference",
            "pv_curtail_non_negative",
            "load_shed_non_negative",
            "building_recover_non_negative",
        ]:
            rows.append(_record("p1_coordinated", tag, name, "not_applicable", None, None, "无 p_1_5_timeseries.csv。"))


def _checks_baseline(repo: Path, rows: list[dict[str, Any]]) -> None:
    tag = "baseline_default"
    rows.append(
        _record("baseline_noncooperative", tag, "solver_status_optimal", "not_applicable", None, None, "baseline 为规则仿真，无 MILP 状态。")
    )

    bcsv = repo / "results" / "tables" / "objective_reconciliation_baseline_fullweek.csv"
    if bcsv.is_file():
        try:
            df = pd.read_csv(bcsv, encoding="utf-8-sig")
            m = {str(r["cost_item"]).strip(): float(r["value_yuan"]) for _, r in df.iterrows()}
            ofs = m.get("Objective from solver")
            ore = m.get("Objective recomputed from solution")
            if ofs is not None and ore is not None:
                g = abs(float(ofs) - float(ore))
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "objective_abs_gap_small",
                        "pass" if g <= GAP_ABS_TOL_YUAN else "fail",
                        g,
                        f"<= {GAP_ABS_TOL_YUAN}",
                        "baseline 对账表两目标行。",
                    )
                )
            else:
                rows.append(
                    _record("baseline_noncooperative", tag, "objective_abs_gap_small", "not_applicable", None, None, "表中缺目标行。")
                )
        except (OSError, ValueError, TypeError, KeyError):
            rows.append(
                _record("baseline_noncooperative", tag, "objective_abs_gap_small", "not_applicable", None, None, "无法解析 baseline 对账 CSV。")
            )
    else:
        rows.append(
            _record("baseline_noncooperative", tag, "objective_abs_gap_small", "not_applicable", None, None, "无 baseline 全周对账表。")
        )

    ts_path = repo / "results" / "problem1_baseline" / "baseline_timeseries_results.csv"
    ess = _read_ess_params(repo)
    if ts_path.is_file() and "ess_energy_kwh" in pd.read_csv(ts_path, nrows=0).columns:
        ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        ee = pd.to_numeric(ts["ess_energy_kwh"], errors="coerce")
        if ess:
            emin = float(ess.get("min_energy_kwh", 0.0))
            emax = float(ess.get("max_energy_kwh", float("inf")))
            below = int((ee < emin - SOC_BOUND_TOL_KWH).sum())
            above = int((ee > emax + SOC_BOUND_TOL_KWH).sum())
            ok = below == 0 and above == 0
            rows.append(
                _record(
                    "baseline_noncooperative",
                    tag,
                    "ess_energy_within_bounds",
                    "pass" if ok else "fail",
                    {"violations_below": below, "violations_above": above, "e_min": float(ee.min()), "e_max": float(ee.max())},
                    {"min_kwh": emin, "max_kwh": emax},
                    "baseline 时序 ess_energy_kwh 与参数上下界。",
                )
            )
        else:
            rows.append(
                _record("baseline_noncooperative", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无 ess_params。")
            )
    else:
        rows.append(
            _record("baseline_noncooperative", tag, "ess_energy_within_bounds", "not_applicable", None, None, "无 baseline 时序或 ess_energy_kwh 列。")
        )

    ev_path = repo / "results" / "problem1_baseline" / "baseline_ev_session_summary.csv"
    if ev_path.is_file():
        try:
            ev = pd.read_csv(ev_path, encoding="utf-8-sig")
            if "demand_met_flag" in ev.columns:
                bad = int((~ev["demand_met_flag"].astype(bool)).sum())
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "ev_departure_demand_met",
                        "pass" if bad == 0 else "fail",
                        {"sessions_unmet": bad, "n_sessions": len(ev)},
                        "sessions_unmet == 0",
                        "baseline 离站需求满足标志。",
                    )
                )
            else:
                rows.append(
                    _record("baseline_noncooperative", tag, "ev_departure_demand_met", "not_applicable", None, None, "无 demand_met_flag 列。")
                )
        except OSError:
            rows.append(
                _record("baseline_noncooperative", tag, "ev_departure_demand_met", "not_applicable", None, None, "无法读取 EV 汇总表。")
            )
    else:
        rows.append(
            _record("baseline_noncooperative", tag, "ev_departure_demand_met", "not_applicable", None, None, "无 baseline_ev_session_summary.csv。")
        )

    if ts_path.is_file():
        try:
            ts = pd.read_csv(ts_path, encoding="utf-8-sig")
        except OSError:
            ts = pd.DataFrame()
        if len(ts):
            if "grid_import_kw" in ts.columns and "grid_export_kw" in ts.columns:
                both = (
                    (pd.to_numeric(ts["grid_import_kw"], errors="coerce").fillna(0.0) > EPS_GRID_KW)
                    & (pd.to_numeric(ts["grid_export_kw"], errors="coerce").fillna(0.0) > EPS_GRID_KW)
                ).sum()
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "no_simultaneous_grid_buy_sell_slots",
                        "pass" if int(both) == 0 else "fail",
                        int(both),
                        f"count_gt_{EPS_GRID_KW}kw",
                        "baseline 使用 grid_import_kw / grid_export_kw。",
                    )
                )
            if "ess_charge_kw" in ts.columns and "ess_discharge_kw" in ts.columns:
                both_e = (
                    (pd.to_numeric(ts["ess_charge_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
                    & (pd.to_numeric(ts["ess_discharge_kw"], errors="coerce").fillna(0.0) > EPS_ESS_KW)
                ).sum()
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "no_simultaneous_ess_charge_discharge_slots",
                        "pass" if int(both_e) == 0 else "fail",
                        int(both_e),
                        f"count_gt_{EPS_ESS_KW}kw",
                        "baseline ESS 同时充放。",
                    )
                )
            rows.append(
                _record(
                    "baseline_noncooperative",
                    tag,
                    "ev_fleet_ch_dis_positive_slots_reference",
                    "not_applicable",
                    None,
                    None,
                    "baseline EV 仅充电，跳过车队参考项。",
                )
            )
            if "pv_curtailed_kw" in ts.columns:
                mn = float(pd.to_numeric(ts["pv_curtailed_kw"], errors="coerce").min())
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "pv_curtail_non_negative",
                        "pass" if mn >= -NEG_TOL else "fail",
                        mn,
                        f">= {-NEG_TOL}",
                        "弃光（baseline 列名 pv_curtailed_kw）。",
                    )
                )
            if "unmet_load_kw" in ts.columns:
                mn = float(pd.to_numeric(ts["unmet_load_kw"], errors="coerce").min())
                rows.append(
                    _record(
                        "baseline_noncooperative",
                        tag,
                        "load_shed_non_negative",
                        "pass" if mn >= -NEG_TOL else "fail",
                        mn,
                        f">= {-NEG_TOL}",
                        "未供电功率非负。",
                    )
                )
            rows.append(
                _record(
                    "baseline_noncooperative",
                    tag,
                    "building_recover_non_negative",
                    "not_applicable",
                    None,
                    None,
                    "baseline 无建筑恢复列。",
                )
            )
        else:
            pass
    else:
        for name, msg in [
            ("no_simultaneous_grid_buy_sell_slots", "无 baseline 时序。"),
            ("no_simultaneous_ess_charge_discharge_slots", "无 baseline 时序。"),
        ]:
            rows.append(_record("baseline_noncooperative", tag, name, "not_applicable", None, None, msg))


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    rx = pd.Series(x).rank(method="average").to_numpy()
    ry = pd.Series(y).rank(method="average").to_numpy()
    if np.std(rx) < 1e-12 or np.std(ry) < 1e-12:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _checks_p2_weight_scans(repo: Path, rows: list[dict[str, Any]]) -> None:
    tbl = repo / "results" / "tables"
    if not tbl.is_dir():
        return
    for path in sorted(tbl.glob("problem2_weight_scan_*.csv")):
        stem = path.stem.replace("problem2_weight_scan_", "")
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
        except OSError:
            continue

        if "objective_recomputed" in df.columns:
            nan_obj = int(df["objective_recomputed"].isna().sum())
            err_st = (
                int((df["solver_status"].astype(str) == "error").sum()) if "solver_status" in df.columns else 0
            )
            bad = nan_obj + err_st
            rows.append(
                _record(
                    "p2_weight_scan",
                    stem,
                    "scan_rows_objective_finite",
                    "pass" if bad == 0 else "fail",
                    bad,
                    "error_or_nan_count == 0",
                    "扫描行中 objective_recomputed 为 NaN 或 solver_status=error 计数。",
                )
            )
        else:
            rows.append(
                _record(
                    "p2_weight_scan",
                    stem,
                    "scan_rows_objective_finite",
                    "not_applicable",
                    None,
                    None,
                    "无 objective_recomputed 列。",
                )
            )

        if len(df) < SCAN_MIN_ROWS:
            rows.append(
                _record(
                    "p2_weight_scan",
                    stem,
                    "scan_trend_ev_deg_vs_weight",
                    "not_applicable",
                    len(df),
                    f">= {SCAN_MIN_ROWS} rows",
                    "扫描行数不足，跳过 Spearman 检验。",
                )
            )
            continue
        wcol = "ess_deg_weight" if "ess_deg_weight" in df.columns else None
        evc = "ev_deg_cost" if "ev_deg_cost" in df.columns else None
        if wcol is None or evc is None:
            rows.append(
                _record(
                    "p2_weight_scan",
                    stem,
                    "scan_trend_ev_deg_vs_weight",
                    "not_applicable",
                    None,
                    None,
                    "缺少 ess_deg_weight 或 ev_deg_cost 列。",
                )
            )
            continue
        sub = df[[wcol, evc]].dropna()
        sub = sub.apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < SCAN_MIN_ROWS:
            rows.append(
                _record(
                    "p2_weight_scan",
                    stem,
                    "scan_trend_ev_deg_vs_weight",
                    "not_applicable",
                    len(sub),
                    f">= {SCAN_MIN_ROWS} valid rows",
                    "有效点不足。",
                )
            )
            continue
        rho = _spearman(sub[wcol].tolist(), sub[evc].tolist())
        if rho is None:
            flag = "not_applicable"
        elif rho >= SCAN_SPEARMAN_WARN:
            flag = "pass"
        else:
            flag = "fail"
        rows.append(
            _record(
                "p2_weight_scan",
                stem,
                "scan_trend_ev_deg_vs_weight",
                flag,
                rho,
                f"Spearman(rho) >= {SCAN_SPEARMAN_WARN}",
                "ev_deg_cost 随退化权重应总体不呈强负相关（启发式稳健性）。",
            )
        )


def collect_all(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p2_root = repo / "results" / "problem2_lifecycle" / "single_run"
    if p2_root.is_dir():
        for d in sorted(p2_root.iterdir()):
            if d.is_dir() and (
                (d / "run_meta.json").is_file() or (d / "objective_breakdown.json").is_file()
            ):
                _checks_p2_run(repo, d, rows)

    _checks_p1(repo, rows)
    _checks_baseline(repo, rows)
    _checks_p2_weight_scans(repo, rows)
    return rows


def _print_summary(rows: list[dict[str, Any]]) -> None:
    from collections import defaultdict

    cnt: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = (r["model_name"], r["run_tag"])
        cnt[key][str(r["pass_flag"])] += 1
    print("=== 模型检验摘要 ===", flush=True)
    for (mn, rt), d in sorted(cnt.items()):
        print(
            f"  [{mn} / {rt}] pass={d.get('pass', 0)} fail={d.get('fail', 0)} "
            f"not_applicable={d.get('not_applicable', 0)}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="模型检验：p2 / p1 / baseline 输出自动检查")
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--out-csv", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=None)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    out_csv = (args.out_csv or (repo / "results" / "tables" / "model_validation_checks.csv")).resolve()
    out_json = (args.out_json or (repo / "results" / "tables" / "model_validation_checks.json")).resolve()

    rows = collect_all(repo)
    if not rows:
        print("未生成任何检验记录。", file=sys.stderr)
        return 1

    def _json_safe(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: _json_safe(x) for k, x in v.items()}
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    def _csv_cell(v: Any) -> Any:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return v

    rows_json = [{k: _json_safe(r[k]) for k in RECORD_KEYS} for r in rows]
    rows_out = [{k: _csv_cell(r[k]) for k in RECORD_KEYS} for r in rows_json]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows_out).to_csv(out_csv, index=False, encoding="utf-8-sig")
    out_json.write_text(json.dumps(rows_json, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(rows)
    print(f"已写入: {out_csv}", flush=True)
    print(f"已写入: {out_json}", flush=True)
    return 0
