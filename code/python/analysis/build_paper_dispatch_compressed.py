# -*- coding: utf-8 -*-
"""
论文压缩展示版：基于 ``problem1_dispatch_timeseries.csv`` 与
``baseline_dispatch_timeseries.csv``（不改模型）生成：

1. paper_dispatch_key_segments.csv — 对齐时间轴的联合连续段摘要
2. paper_dispatch_capability_stats.csv — 调度能力统计（双列对比）
3. paper_typical_day_hourly.csv — 自动选取典型日并按小时聚合
4. paper_dispatch_table_placement.md — 正文/附录/补充材料建议

阈值与分段规则见脚本内常量，可在论文方法脚注中引用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

TH_ESS = 10.0
TH_EV = 5.0
TH_SHIFT = 5.0
TH_GRID = 300.0


def _read(repo: Path, name: str) -> pd.DataFrame:
    p = repo / "results" / "tables" / name
    if not p.is_file():
        raise FileNotFoundError(p)
    return pd.read_csv(p, encoding="utf-8-sig")


def _prefix_df(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = df.copy()
    out.columns = [prefix + c if c != "timestamp" else c for c in out.columns]
    return out


def _action_tag(
    ess_c: float,
    ess_d: float,
    ev_c: float,
    ev_d: float,
    shift: float,
    recover: float,
    g_imp: float,
    *,
    has_building: bool,
) -> str:
    if ess_d >= TH_ESS:
        return "储能放电为主"
    if ess_c >= TH_ESS:
        return "储能充电为主"
    if ev_d >= TH_EV:
        return "EV放电为主"
    if ev_c >= TH_EV:
        return "EV充电为主"
    if has_building and (abs(shift) >= TH_SHIFT or abs(recover) >= TH_SHIFT):
        return "建筑柔性移位/恢复"
    if g_imp >= TH_GRID:
        return "高外购电支撑"
    if g_imp > 50:
        return "外购电为主"
    return "低功率/静置"


def _action_code(tag: str) -> int:
    order = [
        "储能放电为主",
        "储能充电为主",
        "EV放电为主",
        "EV充电为主",
        "建筑柔性移位/恢复",
        "高外购电支撑",
        "外购电为主",
        "低功率/静置",
    ]
    return order.index(tag) if tag in order else 7


def _system_state(pk: int, vl: int, hi_ld: bool, hi_pv: bool) -> str:
    parts: list[str] = []
    if hi_ld:
        parts.append("高负荷")
    if hi_pv:
        parts.append("光伏可用")
    if pk:
        parts.append("峰电价")
    if vl:
        parts.append("谷电价")
    if not parts:
        parts.append("常规工况")
    return "+".join(parts)


def _purpose(pk: int, vl: int, hi_ld: bool, p1_tag: str, bl_tag: str) -> str:
    ps: list[str] = []
    if hi_ld and ("储能放电" in p1_tag or "EV放电" in p1_tag or "建筑柔性" in p1_tag):
        ps.append("协同削峰")
    if hi_ld and "储能放电" in bl_tag:
        ps.append("基线规则削峰")
    if vl and ("储能充电" in p1_tag or "EV充电" in p1_tag):
        ps.append("填谷充电")
    if vl and "EV充电" in bl_tag:
        ps.append("基线低价充电")
    if "储能充电为主" in p1_tag and not pk:
        ps.append("吸纳余电/备能")
    if not ps:
        ps.append("维持供需平衡")
    return "；".join(dict.fromkeys(ps))


def build_merged_frame(repo: Path) -> pd.DataFrame:
    p1 = _read(repo, "problem1_dispatch_timeseries.csv")
    bl = _read(repo, "baseline_dispatch_timeseries.csv")
    p1x = _prefix_df(p1, "p1_")
    blx = _prefix_df(bl, "bl_")
    m = p1x.merge(blx, on="timestamp", how="inner")
    m["delta_t_h"] = pd.to_numeric(m["p1_delta_t_h"], errors="coerce").fillna(0.25)

    nl = pd.to_numeric(m["p1_native_load_kw"], errors="coerce").fillna(0.0).to_numpy()
    p80 = float(np.percentile(nl, 80))
    pv_av = pd.to_numeric(m["p1_pv_available_kw"], errors="coerce").fillna(0.0).to_numpy()
    pv_p80 = float(np.percentile(pv_av, 80))
    nl50 = float(np.percentile(nl, 50))

    p1_actions: list[str] = []
    bl_actions: list[str] = []
    states: list[str] = []
    purposes: list[str] = []
    codes: list[int] = []

    for idx in range(len(m)):
        r = m.iloc[idx]
        pk = int(float(r.get("p1_is_price_peak_slot", 0) or 0))
        vl = int(float(r.get("p1_is_price_valley_slot", 0) or 0))
        nlv = float(r.get("p1_native_load_kw", 0) or 0)
        hi_ld = nlv >= p80 - 1e-6
        hi_pv = float(r.get("p1_pv_available_kw", 0) or 0) >= pv_p80 - 1e-6
        ld = 2 if hi_ld else (1 if nlv >= nl50 else 0)
        prc = 2 if pk else (0 if vl else 1)

        p1a = _action_tag(
            float(r.get("p1_ess_charge_kw", 0) or 0),
            float(r.get("p1_ess_discharge_kw", 0) or 0),
            float(r.get("p1_ev_charge_kw", 0) or 0),
            float(r.get("p1_ev_discharge_kw", 0) or 0),
            float(r.get("p1_building_shift_kw", 0) or 0),
            float(r.get("p1_building_recover_kw", 0) or 0),
            float(r.get("p1_grid_import_kw", 0) or 0),
            has_building=True,
        )
        bla = _action_tag(
            float(r.get("bl_ess_charge_kw", 0) or 0),
            float(r.get("bl_ess_discharge_kw", 0) or 0),
            float(r.get("bl_ev_charge_kw", 0) or 0),
            float(r.get("bl_ev_discharge_kw", 0) or 0),
            0.0,
            0.0,
            float(r.get("bl_grid_import_kw", 0) or 0),
            has_building=False,
        )
        c1 = _action_code(p1a)
        c2 = _action_code(bla)
        code = prc * 10_000 + ld * 1_000 + c1 * 10 + c2
        p1_actions.append(p1a)
        bl_actions.append(bla)
        states.append(_system_state(pk, vl, hi_ld, hi_pv))
        purposes.append(_purpose(pk, vl, hi_ld, p1a, bla))
        codes.append(code)

    m["native_load_kw"] = nl
    m["is_pk"] = pd.to_numeric(m["p1_is_price_peak_slot"], errors="coerce").fillna(0).astype(int)
    m["is_vl"] = pd.to_numeric(m["p1_is_price_valley_slot"], errors="coerce").fillna(0).astype(int)
    m["price_buy"] = pd.to_numeric(m["p1_price_buy_yuan_per_kwh"], errors="coerce")
    m["p1_grid_import_kw"] = pd.to_numeric(m["p1_grid_import_kw"], errors="coerce")
    m["bl_grid_import_kw"] = pd.to_numeric(m["bl_grid_import_kw"], errors="coerce")
    m["p1_ess_ch"] = pd.to_numeric(m["p1_ess_charge_kw"], errors="coerce")
    m["p1_ess_dis"] = pd.to_numeric(m["p1_ess_discharge_kw"], errors="coerce")
    m["bl_ess_ch"] = pd.to_numeric(m["bl_ess_charge_kw"], errors="coerce")
    m["bl_ess_dis"] = pd.to_numeric(m["bl_ess_discharge_kw"], errors="coerce")
    m["p1_ev_ch"] = pd.to_numeric(m["p1_ev_charge_kw"], errors="coerce")
    m["p1_ev_dis"] = pd.to_numeric(m["p1_ev_discharge_kw"], errors="coerce")
    m["bl_ev_ch"] = pd.to_numeric(m["bl_ev_charge_kw"], errors="coerce")
    m["bl_ev_dis"] = pd.to_numeric(m["bl_ev_discharge_kw"], errors="coerce")
    m["p1_shift"] = pd.to_numeric(m["p1_building_shift_kw"], errors="coerce")
    m["p1_recover"] = pd.to_numeric(m["p1_building_recover_kw"], errors="coerce")
    m["pv_av"] = pd.to_numeric(m["p1_pv_available_kw"], errors="coerce")

    m["p1_action_zh"] = p1_actions
    m["bl_action_zh"] = bl_actions
    m["system_state_zh"] = states
    m["purpose_zh"] = purposes
    m["joint_code"] = codes
    m["_p1_ch_sum"] = m["p1_ess_ch"].fillna(0.0) + m["p1_ev_ch"].fillna(0.0)
    m["_bl_ch_sum"] = m["bl_ess_ch"].fillna(0.0) + m["bl_ev_ch"].fillna(0.0)
    return m


def merge_joint_segments(m: pd.DataFrame) -> pd.DataFrame:
    codes = m["joint_code"].to_numpy()
    rows: list[dict[str, Any]] = []
    n = len(m)
    i = 0
    dt = float(m["delta_t_h"].iloc[0])
    while i < n:
        j = i
        while j < n and codes[j] == codes[i]:
            j += 1
        seg = m.iloc[i:j]
        rows.append(
            {
                "segment_start": str(seg["timestamp"].iloc[0]),
                "segment_end": str(seg["timestamp"].iloc[-1]),
                "duration_h": round((j - i) * dt, 4),
                "n_slots": j - i,
                "system_state_zh": str(seg["system_state_zh"].iloc[0]),
                "problem1_main_action_zh": str(seg["p1_action_zh"].iloc[0]),
                "baseline_main_action_zh": str(seg["bl_action_zh"].iloc[0]),
                "dispatch_purpose_zh": str(seg["purpose_zh"].iloc[0]),
                "mean_native_load_kw": round(float(seg["native_load_kw"].mean()), 3),
                "mean_p1_grid_import_kw": round(float(seg["p1_grid_import_kw"].mean()), 3),
                "mean_bl_grid_import_kw": round(float(seg["bl_grid_import_kw"].mean()), 3),
            }
        )
        i = j
    return pd.DataFrame(rows)


def duration_hours(mask: np.ndarray, dt: float) -> float:
    return float(np.sum(mask.astype(float) * dt))


def capability_stats(m: pd.DataFrame) -> pd.DataFrame:
    dt = float(m["delta_t_h"].iloc[0])
    p1_ec = (m["p1_ess_ch"].fillna(0.0).to_numpy() >= TH_ESS).astype(bool)
    p1_ed = (m["p1_ess_dis"].fillna(0.0).to_numpy() >= TH_ESS).astype(bool)
    p1_evc = (m["p1_ev_ch"].fillna(0.0).to_numpy() >= TH_EV).astype(bool)
    p1_evd = (m["p1_ev_dis"].fillna(0.0).to_numpy() >= TH_EV).astype(bool)
    p1_bs = (np.abs(m["p1_shift"].fillna(0.0).to_numpy()) >= TH_SHIFT).astype(bool)

    bl_ec = (m["bl_ess_ch"].fillna(0.0).to_numpy() >= TH_ESS).astype(bool)
    bl_ed = (m["bl_ess_dis"].fillna(0.0).to_numpy() >= TH_ESS).astype(bool)
    bl_evc = (m["bl_ev_ch"].fillna(0.0).to_numpy() >= TH_EV).astype(bool)
    bl_evd = (m["bl_ev_dis"].fillna(0.0).to_numpy() >= TH_EV).astype(bool)

    pk = (m["is_pk"].to_numpy() > 0.5).astype(bool)
    vl = (m["is_vl"].to_numpy() > 0.5).astype(bool)
    nl = m["native_load_kw"].to_numpy(dtype=float)
    hi = nl >= np.percentile(nl, 80)

    p1_shave = hi & (
        (m["p1_ess_dis"].fillna(0.0).to_numpy() >= TH_ESS)
        | (m["p1_ev_dis"].fillna(0.0).to_numpy() >= TH_EV)
        | (np.abs(m["p1_shift"].fillna(0.0).to_numpy()) >= TH_SHIFT)
    )
    bl_shave = hi & (m["bl_ess_dis"].fillna(0.0).to_numpy() >= TH_ESS)

    p1_valley = vl & (m["_p1_ch_sum"].to_numpy() >= TH_ESS)
    bl_valley = vl & (m["_bl_ch_sum"].to_numpy() >= TH_ESS)

    def mean_col(mask: np.ndarray, col: str) -> float | None:
        if not np.any(mask):
            return None
        return round(float(m.loc[mask, col].mean()), 3)

    return pd.DataFrame(
        [
            {
                "metric": "储能充电显著时长_h",
                "problem1": round(duration_hours(p1_ec, dt), 3),
                "baseline": round(duration_hours(bl_ec, dt), 3),
            },
            {
                "metric": "储能放电显著时长_h",
                "problem1": round(duration_hours(p1_ed, dt), 3),
                "baseline": round(duration_hours(bl_ed, dt), 3),
            },
            {
                "metric": "EV充电显著时长_h",
                "problem1": round(duration_hours(p1_evc, dt), 3),
                "baseline": round(duration_hours(bl_evc, dt), 3),
            },
            {
                "metric": "EV放电显著时长_h",
                "problem1": round(duration_hours(p1_evd, dt), 3),
                "baseline": round(duration_hours(bl_evd, dt), 3),
            },
            {
                "metric": "建筑移位显著时长_h",
                "problem1": round(duration_hours(p1_bs, dt), 3),
                "baseline": 0.0,
            },
            {
                "metric": "高价时段平均购电功率_kW",
                "problem1": mean_col(pk, "p1_grid_import_kw"),
                "baseline": mean_col(pk, "bl_grid_import_kw"),
            },
            {
                "metric": "削峰代理段平均购电功率_kW",
                "problem1": mean_col(p1_shave, "p1_grid_import_kw"),
                "baseline": mean_col(bl_shave, "bl_grid_import_kw"),
            },
            {
                "metric": "填谷代理段平均充电功率_kW_ESS+EV",
                "problem1": mean_col(p1_valley, "_p1_ch_sum"),
                "baseline": mean_col(bl_valley, "_bl_ch_sum"),
            },
        ]
    )


def pick_typical_day(m: pd.DataFrame) -> str:
    m = m.copy()
    m["date"] = pd.to_datetime(m["timestamp"]).dt.date.astype(str)
    scores: dict[str, float] = {}
    for d, g in m.groupby("date"):
        gi = g["p1_grid_import_kw"].fillna(0.0)
        ess = g["p1_ess_ch"].fillna(0.0) + g["p1_ess_dis"].fillna(0.0)
        pr = g["price_buy"].fillna(0.0)
        if float(gi.std()) < 1e-6:
            corr = 0.0
        else:
            corr = abs(float(np.corrcoef(gi.to_numpy(), pr.to_numpy())[0, 1]))
        scores[str(d)] = float(gi.std() + 0.01 * float(ess.sum()) + 50.0 * corr)
    return max(scores, key=lambda k: scores[k])


def hourly_typical_day(m: pd.DataFrame, day: str) -> pd.DataFrame:
    sub = m[pd.to_datetime(m["timestamp"]).dt.date.astype(str) == day].copy()
    sub["hour"] = pd.to_datetime(sub["timestamp"]).dt.hour
    agg = sub.groupby("hour", as_index=False).agg(
        native_load_kw=("native_load_kw", "mean"),
        price_buy=("price_buy", "mean"),
        p1_grid_import_kw=("p1_grid_import_kw", "mean"),
        bl_grid_import_kw=("bl_grid_import_kw", "mean"),
        p1_ess_charge_kw=("p1_ess_ch", "mean"),
        p1_ess_discharge_kw=("p1_ess_dis", "mean"),
        bl_ess_charge_kw=("bl_ess_ch", "mean"),
        bl_ess_discharge_kw=("bl_ess_dis", "mean"),
        p1_ev_charge_kw=("p1_ev_ch", "mean"),
        p1_ev_discharge_kw=("p1_ev_dis", "mean"),
        bl_ev_charge_kw=("bl_ev_ch", "mean"),
        p1_building_shift_kw=("p1_shift", "mean"),
        pv_available_kw=("pv_av", "mean"),
    )
    agg.insert(0, "typical_date", day)
    return agg


def write_placement_md(path: Path) -> None:
    path.write_text(
        """# 论文表格放置建议（自动生成）

## 建议放正文（精简、叙事强）

- **调度能力统计表**（`paper_dispatch_capability_stats.csv`）：一行一指标、两列对比问题一与基线，最适合在「结果分析」中用 1 段文字 + 1 张小表说明**机制差异**（储能是否可充、EV 是否放电、高价/削峰/填谷代理量等）。
- **典型日小时表**（`paper_typical_day_hourly.csv`）：单页可展示 24 行，便于与**一张叠线图**（购电/储能/电价）对应，突出「削峰填谷在一天内的形状」。

## 建议放附录（完整但仍压缩）

- **关键调度时段摘要表**（`paper_dispatch_key_segments.csv`）：连续段合并后行数远小于 672，适合附录表；若段数仍偏多，可按 `duration_h` 降序只保留前 15～20 行 + 脚注「完整见补充材料」。

## 建议仅作补充材料 / 数据发布

- **全时段 672 行调度总表**：`problem1_dispatch_timeseries.csv`、`baseline_dispatch_timeseries.csv` 与 `problem1_baseline_dispatch_timeseries_long.csv`，供审稿人核查与复现，正文从略。
- **原始模型时序输出**：`results/problem1_ultimate/p_1_5_timeseries.csv`、`baseline_timeseries_results.csv`。

## 作图配合

- 正文图：典型日 24 h 曲线（由小时表列绘制）。
- 附录图：全周购电对比或按 `paper_dispatch_key_segments` 起止时间分段着色。
""",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="论文压缩展示版调度表")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    out = repo / "results" / "tables"
    out.mkdir(parents=True, exist_ok=True)

    try:
        m = build_merged_frame(repo)
    except Exception as exc:
        print(f"失败: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    seg_df = merge_joint_segments(m)
    seg_path = out / "paper_dispatch_key_segments.csv"
    seg_df.to_csv(seg_path, index=False, encoding="utf-8-sig")

    cap_df = capability_stats(m)
    cap_path = out / "paper_dispatch_capability_stats.csv"
    cap_df.to_csv(cap_path, index=False, encoding="utf-8-sig", na_rep="null")

    day = pick_typical_day(m)
    hour_df = hourly_typical_day(m, day)
    hour_path = out / "paper_typical_day_hourly.csv"
    hour_df.to_csv(hour_path, index=False, encoding="utf-8-sig", na_rep="null")

    md_path = out / "paper_dispatch_table_placement.md"
    write_placement_md(md_path)

    meta = out / "paper_typical_day_meta.txt"
    meta.write_text(
        f"typical_date={day}\n"
        "selection_rule=argmax over days of: std(p1_grid_import)+0.01*sum(p1_ess_ch+p1_ess_dis)+50*|corr(grid,price)|\n",
        encoding="utf-8",
    )

    print(f"已写入 {seg_path} ({len(seg_df)} 段)")
    print(f"已写入 {cap_path} ({len(cap_df)} 行)")
    print(f"已写入 {hour_path} (典型日 {day}, {len(hour_df)} 行)")
    print(f"已写入 {md_path}")
    print(f"已写入 {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
