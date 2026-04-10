"""B题数据预处理脚本：清洗原始数据并产出建模输入文件。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
LOG_DIR = ROOT / "results" / "logs"

TIME_INDEX = pd.date_range(
    "2025-07-14 00:00:00",
    "2025-07-20 23:45:00",
    freq="15min",
)


def _is_non_empty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _safe_write_csv(df: pd.DataFrame, path: Path, logs: List[str]) -> None:
    if _is_non_empty(path):
        logs.append(f"- SKIP(非空已存在): `{path.as_posix()}`")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logs.append(f"- WRITE: `{path.as_posix()}`")


def _safe_write_json(obj: Dict, path: Path, logs: List[str]) -> None:
    if _is_non_empty(path):
        logs.append(f"- SKIP(非空已存在): `{path.as_posix()}`")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logs.append(f"- WRITE: `{path.as_posix()}`")


def _safe_write_text(text: str, path: Path, logs: List[str]) -> None:
    if _is_non_empty(path):
        logs.append(f"- SKIP(非空已存在): `{path.as_posix()}`")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logs.append(f"- WRITE: `{path.as_posix()}`")


def _load_raw() -> Dict[str, pd.DataFrame]:
    files = {
        "timeseries_15min.csv": pd.read_csv(RAW_DIR / "timeseries_15min.csv"),
        "asset_parameters.csv": pd.read_csv(RAW_DIR / "asset_parameters.csv"),
        "ev_sessions.csv": pd.read_csv(RAW_DIR / "ev_sessions.csv"),
        "flexible_load_parameters.csv": pd.read_csv(RAW_DIR / "flexible_load_parameters.csv"),
        "daily_summary.csv": pd.read_csv(RAW_DIR / "daily_summary.csv"),
        "ev_summary_stats.csv": pd.read_csv(RAW_DIR / "ev_summary_stats.csv"),
        "scenario_notes.csv": pd.read_csv(RAW_DIR / "scenario_notes.csv"),
    }
    return files


def _check_timeseries(ts: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    issues: List[str] = []
    ts = ts.copy()
    ts["timestamp"] = pd.to_datetime(ts["timestamp"], errors="coerce")
    ts = ts.dropna(subset=["timestamp"]).sort_values("timestamp")
    ts = ts.drop_duplicates(subset=["timestamp"], keep="first")

    ts = ts.set_index("timestamp").reindex(TIME_INDEX)
    missing_rows = ts.index[ts.isna().all(axis=1)].size
    if missing_rows:
        issues.append(f"- timeseries 缺失整行时段: {missing_rows}")

    # 线性插值仅用于数值列，边界用前后填充。
    num_cols = ts.select_dtypes(include=["number"]).columns
    ts[num_cols] = ts[num_cols].interpolate(limit_direction="both")
    ts[num_cols] = ts[num_cols].ffill().bfill()
    ts = ts.reset_index().rename(columns={"index": "timestamp"})
    return ts, issues


def _split_timeseries(ts: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    base = pd.DataFrame({"timestamp": ts["timestamp"]})
    outputs = {
        "load_profile.csv": pd.concat(
            [
                base,
                ts[
                    [
                        "office_building_kw",
                        "wet_lab_kw",
                        "teaching_center_kw",
                        "total_native_load_kw",
                    ]
                ],
            ],
            axis=1,
        ),
        "pv_profile.csv": pd.concat([base, ts[["pv_available_kw"]]], axis=1),
        "price_profile.csv": pd.concat(
            [base, ts[["grid_buy_price_cny_per_kwh", "grid_sell_price_cny_per_kwh"]]],
            axis=1,
        ),
        "carbon_profile.csv": pd.concat([base, ts[["grid_carbon_kg_per_kwh"]]], axis=1),
        "grid_limits.csv": pd.concat(
            [base, ts[["grid_import_limit_kw", "grid_export_limit_kw"]]],
            axis=1,
        ),
    }
    return outputs


def _extract_ess_params(asset_df: pd.DataFrame) -> Dict:
    amap = dict(zip(asset_df["parameter"], asset_df["value"]))
    keys = {
        "energy_capacity_kwh": "stationary_battery_energy_capacity_kwh",
        "p_charge_max_kw": "stationary_battery_max_charge_power_kw",
        "p_discharge_max_kw": "stationary_battery_max_discharge_power_kw",
        "eta_charge": "stationary_battery_charge_efficiency",
        "eta_discharge": "stationary_battery_discharge_efficiency",
        "soc_init_kwh": "stationary_battery_initial_energy_kwh",
        "delta_t_hours": "default_time_step_hours",
    }
    ess = {k: float(amap.get(v)) for k, v in keys.items() if v in amap}

    cap = ess.get("energy_capacity_kwh")
    min_e = amap.get("stationary_battery_min_energy_kwh")
    max_e = amap.get("stationary_battery_max_energy_kwh")
    if cap and cap > 0:
        if min_e is not None:
            ess["soc_min_frac"] = float(min_e) / float(cap)
        if max_e is not None:
            ess["soc_max_frac"] = float(max_e) / float(cap)
    return ess


def _clean_ev_sessions(ev: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    issues: List[str] = []
    ev = ev.copy()
    ev["arrival_time"] = pd.to_datetime(ev["arrival_time"], errors="coerce")
    ev["departure_time"] = pd.to_datetime(ev["departure_time"], errors="coerce")
    ev = ev.dropna(subset=["session_id", "arrival_time", "departure_time"])
    ev = ev.drop_duplicates(subset=["session_id"], keep="first")

    ev = ev[ev["departure_time"] > ev["arrival_time"]].copy()

    for col in [
        "battery_capacity_kwh",
        "initial_energy_kwh",
        "required_energy_at_departure_kwh",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "degradation_cost_cny_per_kwh_throughput",
    ]:
        ev[col] = pd.to_numeric(ev[col], errors="coerce")

    ev["v2b_allowed"] = pd.to_numeric(ev["v2b_allowed"], errors="coerce").fillna(0).astype(int)
    ev["v2b_allowed"] = ev["v2b_allowed"].clip(lower=0, upper=1)

    # 电量边界修正到 [0, capacity]，离站需求不低于初始电量。
    ev["initial_energy_kwh"] = ev["initial_energy_kwh"].clip(lower=0)
    ev["battery_capacity_kwh"] = ev["battery_capacity_kwh"].clip(lower=0)
    ev["initial_energy_kwh"] = ev[["initial_energy_kwh", "battery_capacity_kwh"]].min(axis=1)
    ev["required_energy_at_departure_kwh"] = ev["required_energy_at_departure_kwh"].clip(lower=0)
    ev["required_energy_at_departure_kwh"] = ev[
        ["required_energy_at_departure_kwh", "battery_capacity_kwh"]
    ].min(axis=1)
    ev["required_energy_at_departure_kwh"] = ev[
        ["required_energy_at_departure_kwh", "initial_energy_kwh"]
    ].max(axis=1)

    ev["max_charge_power_kw"] = ev["max_charge_power_kw"].clip(lower=0)
    ev["max_discharge_power_kw"] = ev["max_discharge_power_kw"].clip(lower=0)
    ev.loc[ev["v2b_allowed"] == 0, "max_discharge_power_kw"] = 0

    # 对齐到 15 分钟时段边界：到站向上取整，离站向下取整。
    ev["arrival_slot"] = ev["arrival_time"].dt.ceil("15min")
    ev["departure_slot"] = ev["departure_time"].dt.floor("15min")
    ev = ev[ev["departure_slot"] > ev["arrival_slot"]].copy()

    outside = ((ev["arrival_slot"] > TIME_INDEX.max()) | (ev["departure_slot"] < TIME_INDEX.min())).sum()
    if outside:
        issues.append(f"- EV 会话超出周范围数量: {int(outside)}")

    ev = ev.sort_values(["arrival_slot", "departure_slot", "session_id"]).reset_index(drop=True)
    return ev, issues


def _aggregate_ev(ev: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DataFrame({"timestamp": TIME_INDEX})

    online_count = []
    p_ev_ch_max_kw = []
    p_ev_dis_max_kw = []

    for t in TIME_INDEX:
        online = ev[(ev["arrival_slot"] <= t) & (t < ev["departure_slot"])]
        online_count.append(int(len(online)))
        p_ev_ch_max_kw.append(float(online["max_charge_power_kw"].sum()))
        p_ev_dis_max_kw.append(float(online["max_discharge_power_kw"].sum()))

    inflow = (
        ev.groupby("arrival_slot")["initial_energy_kwh"]
        .sum()
        .reindex(TIME_INDEX, fill_value=0.0)
        .rename("e_ev_init_inflow_kwh")
    )
    outflow = (
        ev.groupby("departure_slot")["required_energy_at_departure_kwh"]
        .sum()
        .reindex(TIME_INDEX, fill_value=0.0)
        .rename("e_ev_req_outflow_kwh")
    )

    agg = idx.copy()
    agg["online_count"] = online_count
    agg["p_ev_ch_max_kw"] = p_ev_ch_max_kw
    agg["p_ev_dis_max_kw"] = p_ev_dis_max_kw
    agg["e_ev_init_inflow_kwh"] = inflow.values
    agg["e_ev_req_outflow_kwh"] = outflow.values
    return agg


def _clean_flexible_params(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    num_cols = [
        "noninterruptible_share",
        "max_shiftable_kw",
        "max_sheddable_kw",
        "rebound_factor",
        "penalty_cny_per_kwh_not_served",
    ]
    for c in num_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["load_block"] + num_cols).drop_duplicates(subset=["load_block"], keep="first")
    out["noninterruptible_share"] = out["noninterruptible_share"].clip(lower=0, upper=1)
    out["max_shiftable_kw"] = out["max_shiftable_kw"].clip(lower=0)
    out["max_sheddable_kw"] = out["max_sheddable_kw"].clip(lower=0)
    out["rebound_factor"] = out["rebound_factor"].clip(lower=1.0)
    out["penalty_cny_per_kwh_not_served"] = out["penalty_cny_per_kwh_not_served"].clip(lower=0)
    return out.reset_index(drop=True)


def main() -> None:
    logs: List[str] = []
    dq: List[str] = ["# 数据质量检查报告", "", "## 输入文件检查"]
    missing = []

    required = [
        "timeseries_15min.csv",
        "asset_parameters.csv",
        "ev_sessions.csv",
        "flexible_load_parameters.csv",
        "daily_summary.csv",
        "ev_summary_stats.csv",
        "scenario_notes.csv",
        "README.txt",
    ]
    for f in required:
        fp = RAW_DIR / f
        if not fp.exists():
            missing.append(f)
        else:
            dq.append(f"- OK: `{fp.as_posix()}`")

    if missing:
        raise FileNotFoundError(f"缺失原始文件: {missing}")

    raw = _load_raw()
    ts_fixed, ts_issues = _check_timeseries(raw["timeseries_15min.csv"])
    ev_clean, ev_issues = _clean_ev_sessions(raw["ev_sessions.csv"])
    ev_agg = _aggregate_ev(ev_clean)
    flx = _clean_flexible_params(raw["flexible_load_parameters.csv"])
    ess = _extract_ess_params(raw["asset_parameters.csv"])

    outputs = _split_timeseries(ts_fixed)
    for name, df in outputs.items():
        _safe_write_csv(df, PROCESSED_DIR / name, logs)

    _safe_write_json(ess, PROCESSED_DIR / "ess_params.json", logs)
    _safe_write_csv(ev_clean, PROCESSED_DIR / "ev_sessions_clean.csv", logs)
    _safe_write_csv(ev_agg, PROCESSED_DIR / "ev_aggregate_profile.csv", logs)
    _safe_write_csv(flx, PROCESSED_DIR / "flexible_load_params.csv", logs)

    dq.extend(["", "## 结构与一致性检查"])
    dq.append(f"- 统一时段总数: {len(TIME_INDEX)}（预期 672）")
    dq.append(f"- timeseries 处理后行数: {len(ts_fixed)}")
    dq.append(f"- EV 清洗后会话数: {len(ev_clean)}")
    dq.append(f"- EV 聚合后行数: {len(ev_agg)}")
    dq.append(f"- 柔性负荷参数条数: {len(flx)}")
    if ts_issues or ev_issues:
        dq.append("")
        dq.append("## 风险提示")
        dq.extend(ts_issues + ev_issues)
    else:
        dq.append("")
        dq.append("## 风险提示")
        dq.append("- 未发现显著结构性异常。")

    dq.extend(["", "## 输出文件写入情况"])
    dq.extend(logs if logs else ["- 无输出动作。"])

    _safe_write_text("\n".join(dq) + "\n", LOG_DIR / "data_quality_report.md", logs=[])
    print("Preprocess done.")


if __name__ == "__main__":
    main()
