# -*- coding: utf-8 -*-
"""
从问题一协调优化与非协同基线的**现有时序 CSV** 构建：
1) 统一字段的逐时段调度总表（宽表 ×2 + 可选长表）
2) 相邻相似时段合并后的「关键时段摘要」

不重写原模型；缺列通过合并 `load_profile` / `price_profile` 与简单递推补全。

输出：
- results/tables/problem1_dispatch_timeseries.csv
- results/tables/baseline_dispatch_timeseries.csv
- results/tables/problem1_baseline_dispatch_timeseries_long.csv
- results/tables/problem1_baseline_dispatch_windows.csv
- results/tables/problem1_baseline_dispatch_windows.json

字段语义（adjusted_load_kw）：
- 问题一：native_load_kw - building_shift_kw + building_recover_kw（柔性「移出/移回」对瞬时等效建筑侧需求的近似）。
- 基线：total_load_with_ev_kw（原生+EV 交流充电，无建筑柔性）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

# 与 ess_params.json 一致，用于问题一储能能量递推（若与模型内部初值不一致，仅影响展示列）
P1_ESS_E0_KWH = 600.0
P1_ESS_ETA_CH = 0.95
P1_ESS_ETA_DIS = 0.95

UNIFIED_COLS: list[str] = [
    "slot_id",
    "timestamp",
    "delta_t_h",
    "price_buy_yuan_per_kwh",
    "price_sell_yuan_per_kwh",
    "is_price_peak_slot",
    "is_price_valley_slot",
    "native_load_kw",
    "adjusted_load_kw",
    "pv_available_kw",
    "pv_use_kw",
    "pv_to_ess_kw",
    "pv_export_kw",
    "pv_curtail_kw",
    "grid_import_kw",
    "grid_export_kw",
    "ess_charge_kw",
    "ess_discharge_kw",
    "ess_energy_end_kwh",
    "ev_charge_kw",
    "ev_discharge_kw",
    "building_shift_kw",
    "building_recover_kw",
    "building_flex_net_kw",
    "load_shed_kw",
    "ev_aggregate_energy_kwh",
    "dispatch_summary_zh",
]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def _price_flags(price: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.asarray(price, dtype=float)
    hi = float(np.nanpercentile(p, 80)) if np.nanmax(p) > np.nanmin(p) else np.nanmax(p)
    lo = float(np.nanpercentile(p, 20)) if np.nanmax(p) > np.nanmin(p) else np.nanmin(p)
    is_peak = p >= hi - 1e-12
    is_valley = p <= lo + 1e-12
    return is_peak.astype(int), is_valley.astype(int)


def _ess_energy_integrate(
    p_ch: np.ndarray,
    p_dis: np.ndarray,
    dt: float,
    e0: float,
    eta_ch: float,
    eta_dis: float,
) -> np.ndarray:
    n = len(p_ch)
    e = np.zeros(n, dtype=float)
    cur = float(e0)
    for t in range(n):
        cur = cur + eta_ch * float(p_ch[t]) * dt - (float(p_dis[t]) / eta_dis) * dt
        e[t] = cur
    return e


def _dispatch_summary_zh(
    *,
    model: str,
    g_imp: float,
    g_exp: float,
    ess_c: float,
    ess_d: float,
    ev_c: float,
    ev_d: float,
    sh: float,
    rec: float,
    curt: float,
    shed: float,
    pv_u: float,
    pv_a: float,
) -> str:
    parts: list[str] = []
    if g_imp > 1.0:
        parts.append("外购电")
    if g_exp > 1.0:
        parts.append("外售电")
    if ess_c > 1.0:
        parts.append("储能充电")
    if ess_d > 1.0:
        parts.append("储能放电")
    if ev_c > 1.0:
        parts.append("EV充电")
    if ev_d > 1.0:
        parts.append("EV放电")
    if abs(sh) > 1.0:
        parts.append("建筑移位")
    if abs(rec) > 1.0:
        parts.append("建筑恢复")
    if curt > 1.0:
        parts.append("弃光")
    if shed > 1.0:
        parts.append("切负荷/未供电")
    if pv_a > 1.0 and pv_u > pv_a * 0.85:
        parts.append("光伏高消纳")
    if not parts:
        parts.append("静置/低功率")
    tag = "协同" if model == "problem1" else "基线"
    return f"【{tag}】" + "；".join(parts)


def build_problem1_table(repo: Path) -> pd.DataFrame:
    ts_path = repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
    if not ts_path.is_file():
        raise FileNotFoundError(ts_path)
    ts = _read_csv(ts_path)
    if "delta_t_h" not in ts.columns:
        ts["delta_t_h"] = 0.25
    dt = float(ts["delta_t_h"].iloc[0])

    load_p = repo / "data" / "processed" / "final_model_inputs" / "load_profile.csv"
    price_p = repo / "data" / "processed" / "price_profile.csv"
    ld = _read_csv(load_p) if load_p.is_file() else pd.DataFrame()
    pr = _read_csv(price_p) if price_p.is_file() else pd.DataFrame()

    key = "timestamp"
    if not ld.empty and "total_native_load_kw" in ld.columns:
        ts = ts.merge(ld[[key, "total_native_load_kw"]], on=key, how="left")
        ts.rename(columns={"total_native_load_kw": "native_load_kw"}, inplace=True)
    else:
        ts["native_load_kw"] = np.nan

    buy_col = None
    sell_col = None
    if not pr.empty:
        if "grid_buy_price_cny_per_kwh" in pr.columns:
            buy_col = "grid_buy_price_cny_per_kwh"
        elif "buy_price" in pr.columns:
            buy_col = "buy_price"
        if "grid_sell_price_cny_per_kwh" in pr.columns:
            sell_col = "grid_sell_price_cny_per_kwh"
        elif "sell_price" in pr.columns:
            sell_col = "sell_price"
        mcols = [key] + [c for c in [buy_col, sell_col] if c]
        ts = ts.merge(pr[mcols].drop_duplicates(key), on=key, how="left")

    ts["price_buy_yuan_per_kwh"] = ts[buy_col] if buy_col else np.nan
    ts["price_sell_yuan_per_kwh"] = ts[sell_col] if sell_col else np.nan

    pb = pd.to_numeric(ts["price_buy_yuan_per_kwh"], errors="coerce").ffill().fillna(0.0).to_numpy()
    is_pk, is_vl = _price_flags(pb)
    ts["is_price_peak_slot"] = is_pk
    ts["is_price_valley_slot"] = is_vl

    sh = pd.to_numeric(ts["P_shift_out_total_kw"], errors="coerce").fillna(0.0).to_numpy()
    rec = pd.to_numeric(ts["P_recover_total_kw"], errors="coerce").fillna(0.0).to_numpy()
    nl = pd.to_numeric(ts["native_load_kw"], errors="coerce").fillna(0.0).to_numpy()
    ts["building_shift_kw"] = sh
    ts["building_recover_kw"] = rec
    ts["building_flex_net_kw"] = sh - rec
    ts["adjusted_load_kw"] = nl - sh + rec

    ts["pv_available_kw"] = pd.to_numeric(ts["pv_upper_kw"], errors="coerce").fillna(0.0)
    ts["pv_use_kw"] = pd.to_numeric(ts["P_pv_use_kw"], errors="coerce").fillna(0.0)
    ts["pv_curtail_kw"] = pd.to_numeric(ts["pv_curtail_kw"], errors="coerce").fillna(0.0)
    ts["pv_to_ess_kw"] = 0.0
    ts["pv_export_kw"] = 0.0

    ts["grid_import_kw"] = pd.to_numeric(ts["P_buy_kw"], errors="coerce").fillna(0.0)
    ts["grid_export_kw"] = pd.to_numeric(ts["P_sell_kw"], errors="coerce").fillna(0.0)
    ts["ess_charge_kw"] = pd.to_numeric(ts["P_ess_ch_kw"], errors="coerce").fillna(0.0)
    ts["ess_discharge_kw"] = pd.to_numeric(ts["P_ess_dis_kw"], errors="coerce").fillna(0.0)
    ts["ev_charge_kw"] = pd.to_numeric(ts["P_ev_ch_total_kw"], errors="coerce").fillna(0.0)
    ts["ev_discharge_kw"] = pd.to_numeric(ts["P_ev_dis_total_kw"], errors="coerce").fillna(0.0)
    ts["load_shed_kw"] = pd.to_numeric(ts["P_shed_total_kw"], errors="coerce").fillna(0.0)

    ess_e = _ess_energy_integrate(
        ts["ess_charge_kw"].to_numpy(),
        ts["ess_discharge_kw"].to_numpy(),
        dt,
        P1_ESS_E0_KWH,
        P1_ESS_ETA_CH,
        P1_ESS_ETA_DIS,
    )
    ts["ess_energy_end_kwh"] = ess_e
    ts["ev_aggregate_energy_kwh"] = np.nan

    ts["slot_id"] = np.arange(1, len(ts) + 1, dtype=int)

    summ = []
    for i in range(len(ts)):
        summ.append(
            _dispatch_summary_zh(
                model="problem1",
                g_imp=float(ts["grid_import_kw"].iloc[i]),
                g_exp=float(ts["grid_export_kw"].iloc[i]),
                ess_c=float(ts["ess_charge_kw"].iloc[i]),
                ess_d=float(ts["ess_discharge_kw"].iloc[i]),
                ev_c=float(ts["ev_charge_kw"].iloc[i]),
                ev_d=float(ts["ev_discharge_kw"].iloc[i]),
                sh=float(ts["building_shift_kw"].iloc[i]),
                rec=float(ts["building_recover_kw"].iloc[i]),
                curt=float(ts["pv_curtail_kw"].iloc[i]),
                shed=float(ts["load_shed_kw"].iloc[i]),
                pv_u=float(ts["pv_use_kw"].iloc[i]),
                pv_a=float(ts["pv_available_kw"].iloc[i]),
            )
        )
    ts["dispatch_summary_zh"] = summ

    out = ts[[c for c in UNIFIED_COLS if c in ts.columns]].copy()
    for c in UNIFIED_COLS:
        if c not in out.columns:
            out[c] = np.nan
    return out[UNIFIED_COLS]


def build_baseline_table(repo: Path) -> pd.DataFrame:
    raw = repo / "results" / "problem1_baseline" / "baseline_timeseries_results.csv"
    if not raw.is_file():
        raise FileNotFoundError(raw)
    b = _read_csv(raw)
    b["delta_t_h"] = 0.25

    pb = pd.to_numeric(b["buy_price"], errors="coerce").fillna(0.0).to_numpy()
    is_pk, is_vl = _price_flags(pb)

    out = pd.DataFrame(
        {
            "slot_id": b["slot_id"].astype(int) if "slot_id" in b.columns else np.arange(1, len(b) + 1),
            "timestamp": b["timestamp"].astype(str),
            "delta_t_h": 0.25,
            "price_buy_yuan_per_kwh": pd.to_numeric(b["buy_price"], errors="coerce"),
            "price_sell_yuan_per_kwh": pd.to_numeric(b["sell_price"], errors="coerce"),
            "is_price_peak_slot": is_pk,
            "is_price_valley_slot": is_vl,
            "native_load_kw": pd.to_numeric(b["native_load_kw"], errors="coerce"),
            "adjusted_load_kw": pd.to_numeric(b["total_load_with_ev_kw"], errors="coerce"),
            "pv_available_kw": pd.to_numeric(b["pv_available_kw"], errors="coerce"),
            "pv_use_kw": pd.to_numeric(b["pv_used_locally_kw"], errors="coerce"),
            "pv_to_ess_kw": pd.to_numeric(b["pv_to_ess_kw"], errors="coerce"),
            "pv_export_kw": pd.to_numeric(b["pv_export_kw"], errors="coerce"),
            "pv_curtail_kw": pd.to_numeric(b["pv_curtailed_kw"], errors="coerce"),
            "grid_import_kw": pd.to_numeric(b["grid_import_kw"], errors="coerce"),
            "grid_export_kw": pd.to_numeric(b["grid_export_kw"], errors="coerce"),
            "ess_charge_kw": pd.to_numeric(b["ess_charge_kw"], errors="coerce"),
            "ess_discharge_kw": pd.to_numeric(b["ess_discharge_kw"], errors="coerce"),
            "ess_energy_end_kwh": pd.to_numeric(b["ess_energy_kwh"], errors="coerce"),
            "ev_charge_kw": pd.to_numeric(b["ev_total_charge_kw"], errors="coerce"),
            "ev_discharge_kw": pd.to_numeric(b["ev_total_discharge_kw"], errors="coerce"),
            "building_shift_kw": 0.0,
            "building_recover_kw": 0.0,
            "building_flex_net_kw": 0.0,
            "load_shed_kw": pd.to_numeric(b["unmet_load_kw"], errors="coerce"),
            "ev_aggregate_energy_kwh": np.nan,
        }
    )

    summ = []
    for i in range(len(out)):
        summ.append(
            _dispatch_summary_zh(
                model="baseline",
                g_imp=float(out["grid_import_kw"].iloc[i]),
                g_exp=float(out["grid_export_kw"].iloc[i]),
                ess_c=float(out["ess_charge_kw"].iloc[i]),
                ess_d=float(out["ess_discharge_kw"].iloc[i]),
                ev_c=float(out["ev_charge_kw"].iloc[i]),
                ev_d=float(out["ev_discharge_kw"].iloc[i]),
                sh=0.0,
                rec=0.0,
                curt=float(out["pv_curtail_kw"].iloc[i]),
                shed=float(out["load_shed_kw"].iloc[i]),
                pv_u=float(out["pv_use_kw"].iloc[i]),
                pv_a=float(out["pv_available_kw"].iloc[i]),
            )
        )
    out["dispatch_summary_zh"] = summ
    return out[UNIFIED_COLS].copy()


def _state_code_row(row: pd.Series, load_p80: float, pv_p80: float) -> int:
    nl = float(row.get("native_load_kw") or 0)
    hi_load = 2 if nl >= load_p80 - 1e-6 else 0
    pk = int(row.get("is_price_peak_slot") or 0)
    vl = int(row.get("is_price_valley_slot") or 0)
    ess_c = float(row.get("ess_charge_kw") or 0)
    ess_d = float(row.get("ess_discharge_kw") or 0)
    if ess_c > 1 and ess_d <= 1:
        em = 1
    elif ess_d > 1 and ess_c <= 1:
        em = 2
    else:
        em = 0
    ev_c = float(row.get("ev_charge_kw") or 0)
    ev_d = float(row.get("ev_discharge_kw") or 0)
    if ev_c > 1 and ev_d <= 1:
        evm = 1
    elif ev_d > 1 and ev_c <= 1:
        evm = 2
    else:
        evm = 0
    pv_a = float(row.get("pv_available_kw") or 0)
    pv_hi = 1 if pv_a >= pv_p80 - 1e-6 else 0
    return hi_load * 1000 + pk * 100 + vl * 10 + em * 3 + evm + pv_hi * 10000


def build_segment_summary(model: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    nl = pd.to_numeric(df["native_load_kw"], errors="coerce").fillna(0.0).to_numpy()
    pva = pd.to_numeric(df["pv_available_kw"], errors="coerce").fillna(0.0).to_numpy()
    load_p80 = float(np.percentile(nl, 80))
    pv_p80 = float(np.percentile(pva, 80))
    codes = []
    for _, row in df.iterrows():
        codes.append(_state_code_row(row, load_p80, pv_p80))

    rows: list[dict[str, Any]] = []
    n = len(df)
    i = 0
    while i < n:
        j = i
        while j < n and codes[j] == codes[i]:
            j += 1
        seg = df.iloc[i:j]
        t0 = str(seg["timestamp"].iloc[0])
        t1 = str(seg["timestamp"].iloc[-1])
        dt = float(seg["delta_t_h"].iloc[0])
        nh = (j - i) * dt

        m_gi = float(pd.to_numeric(seg["grid_import_kw"], errors="coerce").mean())
        m_ge = float(pd.to_numeric(seg["grid_export_kw"], errors="coerce").mean())
        m_ec = float(pd.to_numeric(seg["ess_charge_kw"], errors="coerce").mean())
        m_ed = float(pd.to_numeric(seg["ess_discharge_kw"], errors="coerce").mean())
        m_evc = float(pd.to_numeric(seg["ev_charge_kw"], errors="coerce").mean())
        m_evd = float(pd.to_numeric(seg["ev_discharge_kw"], errors="coerce").mean())
        m_nl = float(pd.to_numeric(seg["native_load_kw"], errors="coerce").mean())
        m_pv = float(pd.to_numeric(seg["pv_available_kw"], errors="coerce").mean())
        m_pb = float(pd.to_numeric(seg["price_buy_yuan_per_kwh"], errors="coerce").mean())
        pk = int(seg["is_price_peak_slot"].iloc[0])
        vl = int(seg["is_price_valley_slot"].iloc[0])

        states: list[str] = []
        if m_nl >= load_p80 * 0.98:
            states.append("高负荷")
        if m_pv > 50:
            states.append("光伏可用")
        if pk:
            states.append("峰电价")
        if vl:
            states.append("谷电价")
        if not states:
            states.append("常规")

        actions: list[str] = []
        if m_ed > 5:
            actions.append("储能放电为主")
        if m_ec > 5:
            actions.append("储能充电为主")
        if m_evc > 5:
            actions.append("EV充电为主")
        if m_evd > 5:
            actions.append("EV放电为主")
        if m_gi > 200 and m_ed < 5:
            actions.append("购电支撑为主")
        if not actions:
            actions.append("多资源低功率混合")

        purposes: list[str] = []
        if m_ed > 5 and (m_nl >= load_p80 * 0.95 or pk):
            purposes.append("削峰")
        if (m_ec > 5 or m_evc > 5) and vl:
            purposes.append("填谷/低价充电")
        if m_ec > 5 and m_pv > 30:
            purposes.append("吸纳光伏充储能")
        if model == "problem1" and float(pd.to_numeric(seg["building_shift_kw"], errors="coerce").abs().sum()) > 1:
            purposes.append("建筑负荷时间移位")
        if not purposes:
            purposes.append("维持功率平衡")

        rows.append(
            {
                "model": model,
                "segment_start": t0,
                "segment_end": t1,
                "n_slots": j - i,
                "duration_h": round(nh, 4),
                "system_state_zh": "+".join(states),
                "main_dispatch_action_zh": "；".join(actions[:3]),
                "dispatch_purpose_zh": "；".join(dict.fromkeys(purposes)),
                "mean_native_load_kw": round(m_nl, 3),
                "mean_grid_import_kw": round(m_gi, 3),
                "mean_ess_charge_kw": round(m_ec, 3),
                "mean_ess_discharge_kw": round(m_ed, 3),
                "mean_ev_charge_kw": round(m_evc, 3),
                "mean_ev_discharge_kw": round(m_evd, 3),
                "mean_pv_available_kw": round(m_pv, 3),
                "mean_price_buy": round(m_pb, 4),
            }
        )
        i = j
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="构建逐时段调度总表与关键时段摘要")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    out_dir = repo / "results" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        p1 = build_problem1_table(repo)
        bl = build_baseline_table(repo)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    p1_path = out_dir / "problem1_dispatch_timeseries.csv"
    bl_path = out_dir / "baseline_dispatch_timeseries.csv"
    long_path = out_dir / "problem1_baseline_dispatch_timeseries_long.csv"
    win_csv = out_dir / "problem1_baseline_dispatch_windows.csv"
    win_json = out_dir / "problem1_baseline_dispatch_windows.json"

    p1.to_csv(p1_path, index=False, encoding="utf-8-sig", na_rep="null")
    bl.to_csv(bl_path, index=False, encoding="utf-8-sig", na_rep="null")

    long = pd.concat(
        [
            p1.assign(model="problem1_coordinated"),
            bl.assign(model="baseline_noncooperative"),
        ],
        ignore_index=True,
    )
    long.to_csv(long_path, index=False, encoding="utf-8-sig", na_rep="null")

    seg_rows = build_segment_summary("problem1_coordinated", p1) + build_segment_summary("baseline_noncooperative", bl)
    pd.DataFrame(seg_rows).to_csv(win_csv, index=False, encoding="utf-8-sig", na_rep="null")
    win_json.write_text(json.dumps(seg_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已写入 {p1_path} ({len(p1)} 行)")
    print(f"已写入 {bl_path} ({len(bl)} 行)")
    print(f"已写入 {long_path} ({len(long)} 行)")
    print(f"已写入 {win_csv} / {win_json} ({len(seg_rows)} 段)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
