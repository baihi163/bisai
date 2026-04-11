# -*- coding: utf-8 -*-
"""
【遗留脚本】若需与论文「全时段调度总表」一致的
`problem1_baseline_dispatch_windows.{csv,json}`（相邻相似段合并 + 状态摘要），
请优先运行 ``build_dispatch_timeseries_tables.py``；本脚本仍可按「分项 category」
输出多行窗口，但会**覆盖**同名 windows 文件，请勿与上述脚本交替使用。

从问题一协调优化与非协同基线的时序结果中，提炼「具体调度时段」窗口，
供论文结果分析（削峰填谷、ESS/EV/购电/光伏/柔性等）。

数据来源（不重写原模型）：
- 问题一：`results/problem1_ultimate/p_1_5_timeseries.csv`
  合并 `data/processed/final_model_inputs/load_profile.csv`（原生负荷）、
  `data/processed/price_profile.csv`（购电价）。
- 基线：`results/problem1_baseline/baseline_timeseries_results.csv`
  （已含 native_load_kw、buy_price 等）。

输出：
- `results/tables/problem1_baseline_dispatch_windows.csv`
- `results/tables/problem1_baseline_dispatch_windows.json`

启发式说明（可写入论文方法脚注）：
- 「主要充/放电时段」：功率超过全列最大值的 5% 且 >0.5 kW 的连续时段块，
  按块内能量（kW×Δt）降序取前若干条。
- 「负荷/电价/购电高峰」：不低于各自全序列 80 分位数的连续块，取能量或时长前列。
- 「削峰/填谷」为基于可观测量的规则化标注，非反事实最优分解。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

EPS_KW = 0.5
FRAC_OF_MAX = 0.05
TOP_K_BLOCKS = 8
PCT_HIGH = 80.0
PCT_LOW = 20.0


@dataclass
class WindowRow:
    model: str
    category: str
    window_start: str
    window_end: str
    n_slots: int
    energy_kwh: float | None
    mean_power_kw: float | None
    peak_power_kw: float | None
    note: str


def _contiguous_blocks(mask: np.ndarray) -> list[tuple[int, int]]:
    n = len(mask)
    out: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        out.append((i, j - 1))
        i = j
    return out


def _block_stats(
    df: pd.DataFrame,
    lo: int,
    hi: int,
    p_col: str,
    dt_col: str,
) -> tuple[float, float, float, float]:
    sl = df.iloc[lo : hi + 1]
    dt = float(sl[dt_col].iloc[0]) if dt_col in sl.columns else 0.25
    p = pd.to_numeric(sl[p_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    energy = float((p * dt).sum())
    mean_p = float(p.mean()) if len(p) else 0.0
    peak_p = float(p.max()) if len(p) else 0.0
    return energy, mean_p, peak_p, dt


def _threshold_from_series(s: pd.Series) -> float:
    v = pd.to_numeric(s, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    mx = float(np.max(v)) if len(v) else 0.0
    return max(EPS_KW, FRAC_OF_MAX * mx)


def top_blocks_by_energy(
    df: pd.DataFrame,
    power_col: str,
    dt_col: str,
    k: int = TOP_K_BLOCKS,
) -> list[tuple[int, int, float]]:
    thr = _threshold_from_series(df[power_col])
    mask = (pd.to_numeric(df[power_col], errors="coerce").fillna(0.0) > thr).to_numpy()
    blocks = _contiguous_blocks(mask)
    scored: list[tuple[int, int, float]] = []
    for lo, hi in blocks:
        e, _, _, _ = _block_stats(df, lo, hi, power_col, dt_col)
        scored.append((lo, hi, e))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]


def pct_high_blocks(
    df: pd.DataFrame,
    col: str,
    dt_col: str,
    pct: float = PCT_HIGH,
    k: int = TOP_K_BLOCKS,
) -> list[tuple[int, int, float]]:
    s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    thr = float(np.percentile(s.to_numpy(dtype=float), pct))
    mask = (s.to_numpy(dtype=float) >= thr).astype(bool)
    blocks = _contiguous_blocks(mask)
    scored = []
    for lo, hi in blocks:
        e, _, _, _ = _block_stats(df, lo, hi, col, dt_col)
        scored.append((lo, hi, e))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]


def pct_low_blocks(
    df: pd.DataFrame,
    col: str,
    dt_col: str,
    pct: float = PCT_LOW,
    k: int = TOP_K_BLOCKS,
) -> list[tuple[int, int, float]]:
    s = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    thr = float(np.percentile(s.to_numpy(dtype=float), pct))
    mask = (s.to_numpy(dtype=float) <= thr).astype(bool)
    blocks = _contiguous_blocks(mask)
    scored = []
    for lo, hi in blocks:
        e, _, _, _ = _block_stats(df, lo, hi, col, dt_col)
        scored.append((lo, hi, e))
    return scored[:k]


def blocks_where_positive(df: pd.DataFrame, col: str, dt_col: str, k: int = TOP_K_BLOCKS) -> list[tuple[int, int, float]]:
    mask = (pd.to_numeric(df[col], errors="coerce").fillna(0.0) > EPS_KW).to_numpy()
    blocks = _contiguous_blocks(mask)
    scored = []
    for lo, hi in blocks:
        e, _, _, _ = _block_stats(df, lo, hi, col, dt_col)
        scored.append((lo, hi, e))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]


def _ts_col(df: pd.DataFrame, lo: int, hi: int) -> tuple[str, str]:
    ts = df["timestamp"].astype(str)
    return str(ts.iloc[lo]), str(ts.iloc[hi])


def rows_from_blocks(
    model: str,
    category: str,
    df: pd.DataFrame,
    blocks: list[tuple[int, int, float]],
    power_col: str,
    dt_col: str,
    note: str,
) -> list[WindowRow]:
    rows: list[WindowRow] = []
    for rank, (lo, hi, e) in enumerate(blocks, start=1):
        _, mean_p, peak_p, _ = _block_stats(df, lo, hi, power_col, dt_col)
        t0, t1 = _ts_col(df, lo, hi)
        rows.append(
            WindowRow(
                model=model,
                category=category,
                window_start=t0,
                window_end=t1,
                n_slots=hi - lo + 1,
                energy_kwh=round(e, 4),
                mean_power_kw=round(mean_p, 4),
                peak_power_kw=round(peak_p, 4),
                note=f"{note} (块序号 {rank})",
            )
        )
    return rows


def load_problem1(repo: Path) -> pd.DataFrame:
    ts = repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
    if not ts.is_file():
        raise FileNotFoundError(ts)
    df = pd.read_csv(ts, encoding="utf-8-sig")
    if "delta_t_h" not in df.columns:
        df["delta_t_h"] = 0.25

    load_p = repo / "data" / "processed" / "final_model_inputs" / "load_profile.csv"
    price_p = repo / "data" / "processed" / "price_profile.csv"
    if load_p.is_file():
        ld = pd.read_csv(load_p, encoding="utf-8-sig")
        key = "timestamp" if "timestamp" in ld.columns else ld.columns[0]
        if "total_native_load_kw" in ld.columns:
            df = df.merge(ld[[key, "total_native_load_kw"]], left_on="timestamp", right_on=key, how="left")
            if key != "timestamp":
                df.drop(columns=[key], errors="ignore", inplace=True)
    else:
        df["total_native_load_kw"] = np.nan

    if price_p.is_file():
        pr = pd.read_csv(price_p, encoding="utf-8-sig")
        key = "timestamp" if "timestamp" in pr.columns else pr.columns[0]
        col_buy = "grid_buy_price_cny_per_kwh" if "grid_buy_price_cny_per_kwh" in pr.columns else None
        if col_buy is None and "buy_price" in pr.columns:
            col_buy = "buy_price"
        if col_buy:
            df = df.merge(pr[[key, col_buy]], left_on="timestamp", right_on=key, how="left")
            df.rename(columns={col_buy: "buy_price_yuan_per_kwh"}, inplace=True)
            if key != "timestamp":
                df.drop(columns=[key], errors="ignore", inplace=True)
    else:
        df["buy_price_yuan_per_kwh"] = np.nan

    return df


def load_baseline(repo: Path) -> pd.DataFrame:
    aligned = repo / "results" / "problem1_baseline" / "baseline_timeseries_aligned.csv"
    raw = repo / "results" / "problem1_baseline" / "baseline_timeseries_results.csv"
    if aligned.is_file():
        df = pd.read_csv(aligned, encoding="utf-8-sig")
    elif raw.is_file():
        df = pd.read_csv(raw, encoding="utf-8-sig")
    else:
        raise FileNotFoundError(raw)
    if "delta_t_h" not in df.columns:
        df["delta_t_h"] = 0.25
    # 统一列名供后续逻辑
    rename = {
        "grid_import_kw": "grid_import_kw",
        "ess_charge_kw": "ess_charge_kw",
        "ess_discharge_kw": "ess_discharge_kw",
        "ev_charge_kw": "ev_charge_kw",
        "ev_discharge_kw": "ev_discharge_kw",
    }
    if "P_buy_kw" in df.columns:
        pass
    elif "grid_import_kw" in df.columns:
        df.rename(
            columns={
                "grid_import_kw": "grid_import_kw",
            },
            inplace=True,
        )
    if "native_load_kw" not in df.columns and "total_native_load_kw" in df.columns:
        df.rename(columns={"total_native_load_kw": "native_load_kw"}, inplace=True)
    if "buy_price" not in df.columns and "price_buy_yuan_per_kwh" in df.columns:
        df.rename(columns={"price_buy_yuan_per_kwh": "buy_price"}, inplace=True)
    if "pv_available_kw" not in df.columns and "pv_upper_kw" in df.columns:
        df.rename(columns={"pv_upper_kw": "pv_available_kw"}, inplace=True)
    if "pv_curtailed_kw" not in df.columns and "pv_curtail_kw" in df.columns:
        df.rename(columns={"pv_curtail_kw": "pv_curtailed_kw"}, inplace=True)
    # raw 文件列名
    if "ev_total_charge_kw" in df.columns and "ev_charge_kw" not in df.columns:
        df.rename(columns={"ev_total_charge_kw": "ev_charge_kw"}, inplace=True)
    if "ev_total_discharge_kw" in df.columns and "ev_discharge_kw" not in df.columns:
        df.rename(columns={"ev_total_discharge_kw": "ev_discharge_kw"}, inplace=True)
    return df


def collect_p1_windows(df: pd.DataFrame) -> list[WindowRow]:
    dt = "delta_t_h"
    rows: list[WindowRow] = []
    if df["total_native_load_kw"].notna().any():
        bl = pct_high_blocks(df, "total_native_load_kw", dt, PCT_HIGH)
        rows += rows_from_blocks("problem1", "load_peak_p80", df, bl, "total_native_load_kw", dt, "原生负荷≥P80")
    if df["buy_price_yuan_per_kwh"].notna().any() and df["buy_price_yuan_per_kwh"].nunique() > 1:
        bp = pct_high_blocks(df, "buy_price_yuan_per_kwh", dt, PCT_HIGH)
        rows += rows_from_blocks("problem1", "price_peak_p80", df, bp, "buy_price_yuan_per_kwh", dt, "购电价≥P80")
    else:
        rows.append(
            WindowRow(
                "problem1",
                "price_peak_p80",
                "-",
                "-",
                0,
                None,
                None,
                None,
                "购电价在合并列上近似常数，未形成分位高峰窗口",
            )
        )

    rows += rows_from_blocks(
        "problem1",
        "ess_charge_main",
        df,
        top_blocks_by_energy(df, "P_ess_ch_kw", dt),
        "P_ess_ch_kw",
        dt,
        "储能充电主力段",
    )
    rows += rows_from_blocks(
        "problem1",
        "ess_discharge_main",
        df,
        top_blocks_by_energy(df, "P_ess_dis_kw", dt),
        "P_ess_dis_kw",
        dt,
        "储能放电主力段",
    )
    rows += rows_from_blocks(
        "problem1",
        "ev_charge_main",
        df,
        top_blocks_by_energy(df, "P_ev_ch_total_kw", dt),
        "P_ev_ch_total_kw",
        dt,
        "EV总充电主力段",
    )
    rows += rows_from_blocks(
        "problem1",
        "ev_discharge_main",
        df,
        top_blocks_by_energy(df, "P_ev_dis_total_kw", dt),
        "P_ev_dis_total_kw",
        dt,
        "EV总放电主力段",
    )
    rows += rows_from_blocks(
        "problem1",
        "grid_import_peak_p80",
        df,
        pct_high_blocks(df, "P_buy_kw", dt, PCT_HIGH),
        "P_buy_kw",
        dt,
        "购电功率≥P80",
    )
    rows += rows_from_blocks(
        "problem1",
        "pv_high_output_p80",
        df,
        pct_high_blocks(df, "pv_upper_kw", dt, PCT_HIGH),
        "pv_upper_kw",
        dt,
        "光伏可发上限≥P80",
    )
    cur = blocks_where_positive(df, "pv_curtail_kw", dt, k=TOP_K_BLOCKS)
    if cur:
        rows += rows_from_blocks("problem1", "pv_curtail_positive", df, cur, "pv_curtail_kw", dt, "弃光>阈值")
    else:
        rows.append(
            WindowRow(
                "problem1",
                "pv_curtail_positive",
                "-",
                "-",
                0,
                0.0,
                0.0,
                0.0,
                "全周无显著弃光功率",
            )
        )

    sh = blocks_where_positive(df, "P_shift_out_total_kw", dt, k=TOP_K_BLOCKS)
    if sh:
        rows += rows_from_blocks("problem1", "building_shift_out", df, sh, "P_shift_out_total_kw", dt, "建筑移位出力")
    else:
        rows.append(
            WindowRow(
                "problem1",
                "building_shift_out",
                "-",
                "-",
                0,
                None,
                None,
                None,
                "无显著建筑移位出力段",
            )
        )
    rec = blocks_where_positive(df, "P_recover_total_kw", dt, k=TOP_K_BLOCKS)
    if rec:
        rows += rows_from_blocks("problem1", "building_recover", df, rec, "P_recover_total_kw", dt, "建筑恢复功率")
    else:
        rows.append(
            WindowRow(
                "problem1",
                "building_recover",
                "-",
                "-",
                0,
                None,
                None,
                None,
                "无显著建筑恢复段",
            )
        )

    # 策略层：削峰 = 高负荷且（储能放+EV放+移位>阈值）
    load_hi = (
        pd.to_numeric(df["total_native_load_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        >= np.percentile(
            pd.to_numeric(df["total_native_load_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float),
            PCT_HIGH,
        )
    )
    flex_dis = (
        pd.to_numeric(df["P_ess_dis_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["P_ev_dis_total_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["P_shift_out_total_kw"], errors="coerce").fillna(0.0)
    ).to_numpy(dtype=float) > EPS_KW
    mask = load_hi & flex_dis
    blocks = _contiguous_blocks(mask)
    scored = sorted(
        ((_block_stats(df, lo, hi, "P_buy_kw", dt)[0], lo, hi) for lo, hi in blocks), reverse=True
    )[:TOP_K_BLOCKS]
    for rank, (_, lo, hi) in enumerate(scored, 1):
        e, mean_p, peak_p, _ = _block_stats(df, lo, hi, "P_buy_kw", dt)
        t0, t1 = _ts_col(df, lo, hi)
        rows.append(
            WindowRow(
                "problem1",
                "strategy_peak_shaving",
                t0,
                t1,
                hi - lo + 1,
                round(e, 4),
                round(mean_p, 4),
                round(peak_p, 4),
                f"高负荷∩(ESS放+EV放+移位)>0 的削峰代理段 (块序号 {rank})",
            )
        )

    price_lo = (
        pd.to_numeric(df["buy_price_yuan_per_kwh"], errors="coerce").fillna(np.inf).to_numpy(dtype=float)
        <= np.percentile(
            pd.to_numeric(df["buy_price_yuan_per_kwh"], errors="coerce").fillna(np.nan).dropna(),
            PCT_LOW,
        )
        if df["buy_price_yuan_per_kwh"].notna().any()
        else np.zeros(len(df), dtype=bool)
    )
    charge_lo = (
        pd.to_numeric(df["P_ess_ch_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["P_ev_ch_total_kw"], errors="coerce").fillna(0.0)
    ).to_numpy(dtype=float) > EPS_KW
    pv_hi = pd.to_numeric(df["pv_upper_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float) > EPS_KW
    mask_v = (price_lo & charge_lo) | (pv_hi & (pd.to_numeric(df["P_ess_ch_kw"], errors="coerce").fillna(0.0) > EPS_KW))
    blocks_v = _contiguous_blocks(mask_v)

    def _p1_pair_energy(lo: int, hi: int) -> float:
        sl = df.iloc[lo : hi + 1]
        d = float(sl[dt].iloc[0])
        a = pd.to_numeric(sl["P_ess_ch_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        b = pd.to_numeric(sl["P_ev_ch_total_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        return float(((a + b) * d).sum())

    scored_v = sorted(((_p1_pair_energy(lo, hi), lo, hi) for lo, hi in blocks_v), reverse=True)[:TOP_K_BLOCKS]
    for rank, (_, lo, hi) in enumerate(scored_v, 1):
        e = _p1_pair_energy(lo, hi)
        sl = df.iloc[lo : hi + 1]
        comb = (
            pd.to_numeric(sl["P_ess_ch_kw"], errors="coerce").fillna(0.0)
            + pd.to_numeric(sl["P_ev_ch_total_kw"], errors="coerce").fillna(0.0)
        ).to_numpy(dtype=float)
        mean_p = float(comb.mean())
        peak_p = float(comb.max())
        t0, t1 = _ts_col(df, lo, hi)
        rows.append(
            WindowRow(
                "problem1",
                "strategy_valley_filling",
                t0,
                t1,
                hi - lo + 1,
                round(e, 4),
                round(mean_p, 4),
                round(peak_p, 4),
                f"(低价∩(ESS+EV)充)或(有光伏∩ESS充) 的填谷代理段；能量为ESS+EV充电合计 (块序号 {rank})",
            )
        )

    return rows


def collect_baseline_windows(df: pd.DataFrame) -> list[WindowRow]:
    dt = "delta_t_h"
    rows: list[WindowRow] = []
    load_col = "native_load_kw" if "native_load_kw" in df.columns else "total_load_with_ev_kw"
    bl = pct_high_blocks(df, load_col, dt, PCT_HIGH)
    rows += rows_from_blocks("baseline", "load_peak_p80", df, bl, load_col, dt, f"{load_col}≥P80")

    if "buy_price" in df.columns and df["buy_price"].nunique() > 1:
        bp = pct_high_blocks(df, "buy_price", dt, PCT_HIGH)
        rows += rows_from_blocks("baseline", "price_peak_p80", df, bp, "buy_price", dt, "购电价≥P80")
    else:
        rows.append(
            WindowRow(
                "baseline",
                "price_peak_p80",
                "-",
                "-",
                0,
                None,
                None,
                None,
                "购电价离散度不足，未按P80划分高峰",
            )
        )

    ess_ch_blocks = top_blocks_by_energy(df, "ess_charge_kw", dt)
    if ess_ch_blocks:
        rows += rows_from_blocks(
            "baseline",
            "ess_charge_main",
            df,
            ess_ch_blocks,
            "ess_charge_kw",
            dt,
            "储能充电主力段",
        )
    else:
        rows.append(
            WindowRow(
                "baseline",
                "ess_charge_main",
                "-",
                "-",
                0,
                0.0,
                0.0,
                0.0,
                "全周 ess_charge_kw 未超过阈值，无剩余光伏充电窗口（与基线规则一致）",
            )
        )
    rows += rows_from_blocks(
        "baseline",
        "ess_discharge_main",
        df,
        top_blocks_by_energy(df, "ess_discharge_kw", dt),
        "ess_discharge_kw",
        dt,
        "储能放电主力段",
    )
    rows += rows_from_blocks(
        "baseline",
        "ev_charge_main",
        df,
        top_blocks_by_energy(df, "ev_charge_kw", dt),
        "ev_charge_kw",
        dt,
        "EV充电主力段",
    )
    evd = top_blocks_by_energy(df, "ev_discharge_kw", dt)
    if any(df["ev_discharge_kw"].fillna(0) > EPS_KW):
        rows += rows_from_blocks("baseline", "ev_discharge_main", df, evd, "ev_discharge_kw", dt, "EV放电主力段")
    else:
        rows.append(
            WindowRow(
                "baseline",
                "ev_discharge_main",
                "-",
                "-",
                0,
                0.0,
                0.0,
                0.0,
                "基线无V2B，EV放电功率恒为0",
            )
        )

    rows += rows_from_blocks(
        "baseline",
        "grid_import_peak_p80",
        df,
        pct_high_blocks(df, "grid_import_kw", dt, PCT_HIGH),
        "grid_import_kw",
        dt,
        "购电功率≥P80",
    )
    pvcol = "pv_available_kw" if "pv_available_kw" in df.columns else "pv_upper_kw"
    rows += rows_from_blocks(
        "baseline",
        "pv_high_output_p80",
        df,
        pct_high_blocks(df, pvcol, dt, PCT_HIGH),
        pvcol,
        dt,
        "光伏可发≥P80",
    )
    curcol = "pv_curtailed_kw" if "pv_curtailed_kw" in df.columns else "pv_curtail_kw"
    cur = blocks_where_positive(df, curcol, dt, k=TOP_K_BLOCKS)
    if cur:
        rows += rows_from_blocks("baseline", "pv_curtail_positive", df, cur, curcol, dt, "弃光>阈值")
    else:
        rows.append(
            WindowRow(
                "baseline",
                "pv_curtail_positive",
                "-",
                "-",
                0,
                0.0,
                0.0,
                0.0,
                "全周无显著弃光功率",
            )
        )

    rows.append(
        WindowRow(
            "baseline",
            "building_shift_out",
            "-",
            "-",
            0,
            None,
            None,
            None,
            "基线 readme：建筑柔性调节量为0",
        )
    )
    rows.append(
        WindowRow(
            "baseline",
            "building_recover",
            "-",
            "-",
            0,
            None,
            None,
            None,
            "基线无建筑恢复列",
        )
    )

    load_hi = (
        pd.to_numeric(df[load_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        >= np.percentile(pd.to_numeric(df[load_col], errors="coerce").fillna(0.0), PCT_HIGH)
    )
    flex_dis = (pd.to_numeric(df["ess_discharge_kw"], errors="coerce").fillna(0.0)).to_numpy(dtype=float) > EPS_KW
    mask = load_hi & flex_dis
    blocks = _contiguous_blocks(mask)
    scored = sorted(
        ((_block_stats(df, lo, hi, "grid_import_kw", dt)[0], lo, hi) for lo, hi in blocks), reverse=True
    )[:TOP_K_BLOCKS]
    for rank, (_, lo, hi) in enumerate(scored, 1):
        e, mean_p, peak_p, _ = _block_stats(df, lo, hi, "grid_import_kw", dt)
        t0, t1 = _ts_col(df, lo, hi)
        rows.append(
            WindowRow(
                "baseline",
                "strategy_peak_shaving",
                t0,
                t1,
                hi - lo + 1,
                round(e, 4),
                round(mean_p, 4),
                round(peak_p, 4),
                f"高负荷∩ESS放电 的削峰代理段（基线无EV放/建筑移位）(块序号 {rank})",
            )
        )

    if "buy_price" in df.columns and df["buy_price"].nunique() > 1:
        price_lo = (
            pd.to_numeric(df["buy_price"], errors="coerce").fillna(np.inf).to_numpy(dtype=float)
            <= np.percentile(pd.to_numeric(df["buy_price"], errors="coerce").dropna(), PCT_LOW)
        )
    else:
        price_lo = np.ones(len(df), dtype=bool)
    charge_lo = (
        pd.to_numeric(df["ess_charge_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["ev_charge_kw"], errors="coerce").fillna(0.0)
    ).to_numpy(dtype=float) > EPS_KW
    pv_hi = pd.to_numeric(df[pvcol], errors="coerce").fillna(0.0).to_numpy(dtype=float) > EPS_KW
    mask_v = (price_lo & charge_lo) | (pv_hi & (pd.to_numeric(df["ess_charge_kw"], errors="coerce").fillna(0.0) > EPS_KW))
    blocks_v = _contiguous_blocks(mask_v)

    def _pair_energy(lo: int, hi: int) -> float:
        sl = df.iloc[lo : hi + 1]
        d = float(sl[dt].iloc[0])
        a = pd.to_numeric(sl["ess_charge_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        b = pd.to_numeric(sl["ev_charge_kw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        return float(((a + b) * d).sum())

    scored_v = sorted(((_pair_energy(lo, hi), lo, hi) for lo, hi in blocks_v), reverse=True)[:TOP_K_BLOCKS]
    for rank, (_, lo, hi) in enumerate(scored_v, 1):
        e = _pair_energy(lo, hi)
        sl = df.iloc[lo : hi + 1]
        d = float(sl[dt].iloc[0])
        comb = (
            pd.to_numeric(sl["ess_charge_kw"], errors="coerce").fillna(0.0)
            + pd.to_numeric(sl["ev_charge_kw"], errors="coerce").fillna(0.0)
        ).to_numpy(dtype=float)
        mean_p = float(comb.mean())
        peak_p = float(comb.max())
        t0, t1 = _ts_col(df, lo, hi)
        rows.append(
            WindowRow(
                "baseline",
                "strategy_valley_filling",
                t0,
                t1,
                hi - lo + 1,
                round(e, 4),
                round(mean_p, 4),
                round(peak_p, 4),
                f"(低价∩(ESS+EV)充)或(有光伏∩ESS充) 的填谷代理段；表内能量为ESS+EV充电合计 (块序号 {rank})",
            )
        )

    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="提炼 problem1 / baseline 调度时段窗口")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    out_dir = repo / "results" / "tables"
    out_csv = out_dir / "problem1_baseline_dispatch_windows.csv"
    out_json = out_dir / "problem1_baseline_dispatch_windows.json"

    try:
        p1 = load_problem1(repo)
        bl = load_baseline(repo)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    all_rows = collect_p1_windows(p1) + collect_baseline_windows(bl)
    out_dir.mkdir(parents=True, exist_ok=True)
    dfp = pd.DataFrame([asdict(r) for r in all_rows])
    dfp.to_csv(out_csv, index=False, encoding="utf-8-sig", na_rep="null")
    out_json.write_text(json.dumps([asdict(r) for r in all_rows], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out_csv} （{len(all_rows)} 行）")
    print(f"已写入 {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
