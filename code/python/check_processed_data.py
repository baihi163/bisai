"""核查 data/processed 预处理产物是否可直接用于建模。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
LOG_DIR = ROOT / "results" / "logs"

EXPECTED_ROWS = 672
TIME_START = pd.Timestamp("2025-07-14 00:00:00")
TIME_END = pd.Timestamp("2025-07-20 23:45:00")


def red(text: str) -> str:
    return f"\033[31m{text}\033[0m"


def _choose_report_path() -> Path:
    base = LOG_DIR / "processed_data_check.md"
    if base.exists() and base.stat().st_size > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return LOG_DIR / f"processed_data_check_{ts}.md"
    return base


def _read_csv(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺失文件: {path.as_posix()}")
    return pd.read_csv(path)


def _require_columns(df: pd.DataFrame, cols: List[str]) -> List[str]:
    return [c for c in cols if c not in df.columns]


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _choose_report_path()

    fatal: List[str] = []
    warn: List[str] = []
    ok: List[str] = []

    seq_files = [
        "load_profile.csv",
        "pv_profile.csv",
        "price_profile.csv",
        "carbon_profile.csv",
        "grid_limits.csv",
        "ev_aggregate_profile.csv",
    ]

    # 1/2 时序行数和 timestamp
    dfs = {}
    for name in seq_files:
        df = _read_csv(name)
        dfs[name] = df
        if len(df) == EXPECTED_ROWS:
            ok.append(f"{name}: 行数为 {EXPECTED_ROWS}")
        else:
            fatal.append(f"{name}: 行数异常，当前 {len(df)}，预期 {EXPECTED_ROWS}")

        if "timestamp" in df.columns:
            ok.append(f"{name}: 包含 timestamp")
        else:
            fatal.append(f"{name}: 缺少 timestamp 列")

    # 时间轴范围与重复
    for name, df in dfs.items():
        if "timestamp" not in df.columns:
            continue
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        if ts.isna().any():
            fatal.append(f"{name}: timestamp 存在无法解析值")
            continue
        if ts.duplicated().any():
            fatal.append(f"{name}: timestamp 存在重复")
        if ts.min() != TIME_START or ts.max() != TIME_END:
            warn.append(f"{name}: 时间范围 {ts.min()} ~ {ts.max()}，期望 {TIME_START} ~ {TIME_END}")

    # 3 load_profile 非负
    load_df = dfs["load_profile.csv"]
    load_cols = [c for c in load_df.columns if c != "timestamp"]
    missing = _require_columns(
        load_df,
        ["office_building_kw", "wet_lab_kw", "teaching_center_kw", "total_native_load_kw"],
    )
    if missing:
        fatal.append(f"load_profile.csv: 缺少字段 {missing}")
    if load_cols:
        neg_cnt = int((load_df[load_cols] < 0).sum().sum())
        if neg_cnt == 0:
            ok.append("load_profile.csv: 负荷均非负")
        else:
            fatal.append(f"load_profile.csv: 发现 {neg_cnt} 个负值负荷")

    # 4 pv_profile 非负 + 夜间近零
    pv_df = dfs["pv_profile.csv"]
    miss_pv = _require_columns(pv_df, ["timestamp", "pv_available_kw"])
    if miss_pv:
        fatal.append(f"pv_profile.csv: 缺少字段 {miss_pv}")
    else:
        pv_neg = int((pv_df["pv_available_kw"] < 0).sum())
        if pv_neg == 0:
            ok.append("pv_profile.csv: 光伏非负")
        else:
            fatal.append(f"pv_profile.csv: 存在 {pv_neg} 条负光伏")

        ts = pd.to_datetime(pv_df["timestamp"], errors="coerce")
        night = pv_df[(ts.dt.hour < 6) | (ts.dt.hour >= 20)]
        night_nonzero = int((night["pv_available_kw"] > 1e-3).sum())
        ratio = night_nonzero / max(len(night), 1)
        if ratio <= 0.05:
            ok.append(f"pv_profile.csv: 夜间基本为0（非零占比 {ratio:.2%}）")
        else:
            warn.append(f"pv_profile.csv: 夜间非零偏多（非零占比 {ratio:.2%}）")

    # 5 price profile
    price_df = dfs["price_profile.csv"]
    miss_price = _require_columns(
        price_df,
        ["grid_buy_price_cny_per_kwh", "grid_sell_price_cny_per_kwh"],
    )
    if miss_price:
        fatal.append(f"price_profile.csv: 缺少字段 {miss_price}")
    else:
        buy = price_df["grid_buy_price_cny_per_kwh"]
        sell = price_df["grid_sell_price_cny_per_kwh"]
        if buy.isna().any() or sell.isna().any():
            fatal.append("price_profile.csv: 购/售电价存在缺失")
        else:
            ok.append("price_profile.csv: 购/售电价字段完整")
        bad = int((sell > buy).sum())
        if bad == 0:
            ok.append("price_profile.csv: 售电价不高于购电价")
        else:
            fatal.append(f"price_profile.csv: 发现 {bad} 条售电价高于购电价")

    # 6 carbon
    carbon_df = dfs["carbon_profile.csv"]
    miss_c = _require_columns(carbon_df, ["grid_carbon_kg_per_kwh"])
    if miss_c:
        fatal.append(f"carbon_profile.csv: 缺少字段 {miss_c}")
    else:
        bad = int((carbon_df["grid_carbon_kg_per_kwh"] < 0).sum())
        if bad == 0:
            ok.append("carbon_profile.csv: 碳排因子非负")
        else:
            fatal.append(f"carbon_profile.csv: 存在 {bad} 条负碳排因子")

    # 7 grid limits
    grid_df = dfs["grid_limits.csv"]
    miss_g = _require_columns(grid_df, ["grid_import_limit_kw", "grid_export_limit_kw"])
    if miss_g:
        fatal.append(f"grid_limits.csv: 缺少字段 {miss_g}")
    else:
        neg = int((grid_df[["grid_import_limit_kw", "grid_export_limit_kw"]] < 0).sum().sum())
        if neg == 0:
            ok.append("grid_limits.csv: 购/售电功率上限存在且非负")
        else:
            fatal.append(f"grid_limits.csv: 存在 {neg} 个负功率上限")

    # 8 ess params
    ess_path = PROCESSED_DIR / "ess_params.json"
    if not ess_path.exists():
        fatal.append("ess_params.json: 文件缺失")
    else:
        ess = json.loads(ess_path.read_text(encoding="utf-8"))
        required_keys = [
            "energy_capacity_kwh",
            "soc_init_kwh",
            "p_charge_max_kw",
            "p_discharge_max_kw",
            "eta_charge",
            "eta_discharge",
            "soc_min_frac",
            "soc_max_frac",
        ]
        missing_keys = [k for k in required_keys if k not in ess]
        if missing_keys:
            fatal.append(f"ess_params.json: 缺少关键字段 {missing_keys}")
        else:
            ok.append("ess_params.json: 关键字段完整")

    # 9 ev sessions clean
    ev_df = _read_csv("ev_sessions_clean.csv")
    ev_missing = _require_columns(
        ev_df,
        [
            "arrival_slot",
            "departure_slot",
            "initial_energy_kwh",
            "required_energy_at_departure_kwh",
            "battery_capacity_kwh",
            "v2b_allowed",
            "max_discharge_power_kw",
        ],
    )
    if ev_missing:
        fatal.append(f"ev_sessions_clean.csv: 缺少字段 {ev_missing}")
    else:
        arr = pd.to_datetime(ev_df["arrival_slot"], errors="coerce")
        dep = pd.to_datetime(ev_df["departure_slot"], errors="coerce")
        seq_bad = int((dep <= arr).sum())
        if seq_bad == 0:
            ok.append("ev_sessions_clean.csv: 时间顺序正确")
        else:
            fatal.append(f"ev_sessions_clean.csv: 发现 {seq_bad} 条时间顺序错误")

        over_cap = int(
            (
                (ev_df["initial_energy_kwh"] > ev_df["battery_capacity_kwh"])
                | (ev_df["required_energy_at_departure_kwh"] > ev_df["battery_capacity_kwh"])
            ).sum()
        )
        if over_cap == 0:
            ok.append("ev_sessions_clean.csv: 能量未超过电池容量")
        else:
            fatal.append(f"ev_sessions_clean.csv: 发现 {over_cap} 条能量超过容量")

        v2b_bad = int(((ev_df["v2b_allowed"] == 0) & (ev_df["max_discharge_power_kw"] > 0)).sum())
        if v2b_bad == 0:
            ok.append("ev_sessions_clean.csv: V2B 一致性通过")
        else:
            fatal.append(f"ev_sessions_clean.csv: 发现 {v2b_bad} 条 V2B 不一致")

    # 10 ev aggregate non-negative
    ev_agg_df = dfs["ev_aggregate_profile.csv"]
    miss_agg = _require_columns(ev_agg_df, ["online_count", "p_ev_ch_max_kw", "p_ev_dis_max_kw"])
    if miss_agg:
        fatal.append(f"ev_aggregate_profile.csv: 缺少字段 {miss_agg}")
    else:
        bad = int((ev_agg_df[["online_count", "p_ev_ch_max_kw", "p_ev_dis_max_kw"]] < 0).sum().sum())
        if bad == 0:
            ok.append("ev_aggregate_profile.csv: 关键聚合字段均非负")
        else:
            fatal.append(f"ev_aggregate_profile.csv: 发现 {bad} 个负值")

    # 11 flexible load params
    flx_df = _read_csv("flexible_load_params.csv")
    flx_required = [
        "load_block",
        "noninterruptible_share",
        "max_shiftable_kw",
        "max_sheddable_kw",
        "rebound_factor",
        "penalty_cny_per_kwh_not_served",
    ]
    miss_flx = _require_columns(flx_df, flx_required)
    if miss_flx:
        fatal.append(f"flexible_load_params.csv: 缺少字段 {miss_flx}")
    else:
        if flx_df[flx_required].isna().sum().sum() == 0:
            ok.append("flexible_load_params.csv: 关键参数无缺失")
        else:
            fatal.append("flexible_load_params.csv: 存在关键参数缺失")

    # markdown report
    lines: List[str] = []
    lines.append("# Processed Data Check")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 数据目录: `{PROCESSED_DIR.as_posix()}`")
    lines.append("")
    lines.append("## 严重问题（Fatal）")
    if fatal:
        for x in fatal:
            lines.append(f"- <span style='color:red'>🔴 {x}</span>")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 警告（Warning）")
    if warn:
        lines.extend([f"- 🟠 {x}" for x in warn])
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 通过项（OK）")
    if ok:
        lines.extend([f"- ✅ {x}" for x in ok])
    else:
        lines.append("- 无")
    lines.append("")
    lines.append(
        f"## 总结\n- Fatal: {len(fatal)}\n- Warning: {len(warn)}\n- OK: {len(ok)}"
    )
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    # terminal summary
    summary = f"Check done | Fatal={len(fatal)} Warning={len(warn)} OK={len(ok)} | Report={report_path.as_posix()}"
    if fatal:
        print(red(summary))
        print(red("存在严重问题，请先修复后再进入建模。"))
    else:
        print(summary)
        if warn:
            print("存在警告项，建议复核。")
        else:
            print("全部关键校验通过，可用于后续建模。")


if __name__ == "__main__":
    main()
