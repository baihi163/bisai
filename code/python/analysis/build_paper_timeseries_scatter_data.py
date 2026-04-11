# -*- coding: utf-8 -*-
"""
从统一时序表导出「时间轴散点图」用 CSV（全周 + 典型日），不改模型。

输入：
- results/tables/problem1_dispatch_timeseries.csv
- results/tables/baseline_dispatch_timeseries.csv

典型日选取（与 paper 压缩脚本一致）：
  argmax_d [ std(p1_grid_import) + 0.01*sum(ess_ch+ess_dis) + 50*|corr(grid, price)| ]

输出（results/tables/）：
- paper_tscatter_meta_typical_day.txt
- paper_tscatter_01_grid_fullweek.csv / paper_tscatter_01_grid_typicalday.csv
- paper_tscatter_02_ess_fullweek.csv / paper_tscatter_02_ess_typicalday.csv
- paper_tscatter_03_ev_fullweek.csv / paper_tscatter_03_ev_typicalday.csv
- paper_tscatter_04_flex_pv_fullweek.csv / paper_tscatter_04_flex_pv_typicalday.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]


def _read(repo: Path, name: str) -> pd.DataFrame:
    p = repo / "results" / "tables" / name
    if not p.is_file():
        raise FileNotFoundError(p)
    return pd.read_csv(p, encoding="utf-8-sig")


def pick_typical_day(p1: pd.DataFrame) -> str:
    p1 = p1.copy()
    p1["date"] = pd.to_datetime(p1["timestamp"]).dt.date.astype(str)
    scores: dict[str, float] = {}
    for d, g in p1.groupby("date"):
        gi = pd.to_numeric(g["grid_import_kw"], errors="coerce").fillna(0.0)
        ess = pd.to_numeric(g["ess_charge_kw"], errors="coerce").fillna(0.0) + pd.to_numeric(
            g["ess_discharge_kw"], errors="coerce"
        ).fillna(0.0)
        pr = pd.to_numeric(g["price_buy_yuan_per_kwh"], errors="coerce").fillna(0.0)
        if float(gi.std()) < 1e-6:
            corr = 0.0
        else:
            corr = abs(float(np.corrcoef(gi.to_numpy(), pr.to_numpy())[0, 1]))
        scores[str(d)] = float(gi.std() + 0.01 * float(ess.sum()) + 50.0 * corr)
    return max(scores, key=lambda k: scores[k])


def merge_aligned(repo: Path) -> tuple[pd.DataFrame, str]:
    p1 = _read(repo, "problem1_dispatch_timeseries.csv")
    bl = _read(repo, "baseline_dispatch_timeseries.csv")
    m = p1.merge(bl, on="timestamp", suffixes=("_p1", "_bl"), how="inner")
    if len(m) != len(p1) or len(m) != len(bl):
        print(f"警告: 合并后行数 {len(m)} 与单侧不一致", file=sys.stderr)
    m["slot_id"] = m["slot_id_p1"].fillna(m.get("slot_id_bl"))
    m["datetime"] = pd.to_datetime(m["timestamp"])
    m["date"] = m["datetime"].dt.date.astype(str)

    # 统一列名便于导出
    out = pd.DataFrame(
        {
            "slot_id": m["slot_id"],
            "timestamp": m["timestamp"],
            "date": m["date"],
            "price_buy_yuan_per_kwh": pd.to_numeric(m["price_buy_yuan_per_kwh_p1"], errors="coerce"),
            "p1_grid_import_kw": pd.to_numeric(m["grid_import_kw_p1"], errors="coerce"),
            "p1_grid_export_kw": pd.to_numeric(m["grid_export_kw_p1"], errors="coerce"),
            "bl_grid_import_kw": pd.to_numeric(m["grid_import_kw_bl"], errors="coerce"),
            "bl_grid_export_kw": pd.to_numeric(m["grid_export_kw_bl"], errors="coerce"),
            "p1_ess_charge_kw": pd.to_numeric(m["ess_charge_kw_p1"], errors="coerce"),
            "p1_ess_discharge_kw": pd.to_numeric(m["ess_discharge_kw_p1"], errors="coerce"),
            "bl_ess_charge_kw": pd.to_numeric(m["ess_charge_kw_bl"], errors="coerce"),
            "bl_ess_discharge_kw": pd.to_numeric(m["ess_discharge_kw_bl"], errors="coerce"),
            "p1_ev_charge_kw": pd.to_numeric(m["ev_charge_kw_p1"], errors="coerce"),
            "p1_ev_discharge_kw": pd.to_numeric(m["ev_discharge_kw_p1"], errors="coerce"),
            "bl_ev_charge_kw": pd.to_numeric(m["ev_charge_kw_bl"], errors="coerce"),
            "bl_ev_discharge_kw": pd.to_numeric(m["ev_discharge_kw_bl"], errors="coerce"),
            "p1_building_shift_kw": pd.to_numeric(m["building_shift_kw_p1"], errors="coerce"),
            "p1_building_recover_kw": pd.to_numeric(m["building_recover_kw_p1"], errors="coerce"),
            "p1_pv_curtail_kw": pd.to_numeric(m["pv_curtail_kw_p1"], errors="coerce"),
            "bl_building_shift_kw": pd.to_numeric(m["building_shift_kw_bl"], errors="coerce").fillna(0.0),
            "bl_building_recover_kw": pd.to_numeric(m["building_recover_kw_bl"], errors="coerce").fillna(0.0),
            "bl_pv_curtail_kw": pd.to_numeric(m["pv_curtail_kw_bl"], errors="coerce"),
        }
    )
    day = pick_typical_day(p1)
    return out, day


def _write_pair(df: pd.DataFrame, day: str, stem: str, cols: list[str], repo: Path) -> None:
    out = repo / "results" / "tables"
    base = ["slot_id", "timestamp", "date", "price_buy_yuan_per_kwh"] + cols
    df[base].to_csv(out / f"{stem}_fullweek.csv", index=False, encoding="utf-8-sig")
    sub = df[df["date"] == day][base]
    sub.to_csv(out / f"{stem}_typicalday.csv", index=False, encoding="utf-8-sig")


def main() -> int:
    ap = argparse.ArgumentParser(description="导出时间轴散点图用 CSV")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    out = repo / "results" / "tables"
    out.mkdir(parents=True, exist_ok=True)

    try:
        df, day = merge_aligned(repo)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    (out / "paper_tscatter_meta_typical_day.txt").write_text(
        f"typical_date={day}\n"
        "rule=argmax over calendar days: std(p1_grid_import)+0.01*sum(ess_ch+ess_dis)+50*|corr(grid_import,price)|\n",
        encoding="utf-8",
    )

    _write_pair(
        df,
        day,
        "paper_tscatter_01_grid",
        [
            "p1_grid_import_kw",
            "p1_grid_export_kw",
            "bl_grid_import_kw",
            "bl_grid_export_kw",
        ],
        repo,
    )
    _write_pair(
        df,
        day,
        "paper_tscatter_02_ess",
        ["p1_ess_charge_kw", "p1_ess_discharge_kw", "bl_ess_charge_kw", "bl_ess_discharge_kw"],
        repo,
    )
    _write_pair(
        df,
        day,
        "paper_tscatter_03_ev",
        ["p1_ev_charge_kw", "p1_ev_discharge_kw", "bl_ev_charge_kw", "bl_ev_discharge_kw"],
        repo,
    )
    _write_pair(
        df,
        day,
        "paper_tscatter_04_flex_pv",
        [
            "p1_building_shift_kw",
            "p1_building_recover_kw",
            "p1_pv_curtail_kw",
            "bl_building_shift_kw",
            "bl_building_recover_kw",
            "bl_pv_curtail_kw",
        ],
        repo,
    )

    captions = out / "paper_tscatter_figure_captions.md"
    captions.write_text(
        """# 时间轴散点图：建议标题与正文一句解释

## 图1 外网购电（售电全周为 0，图中略）

- **建议标题**：分时外网购电功率对比（问题一 vs 非协同基线）
- **一句解释**：本算例向电网售电功率全周为 0（`grid_export_energy_kwh=0`），散点图仅绘购电；非模型禁止反送，系光伏可用功率低于协同后等效负荷且弃光电量为 0（`pv_curtail_energy_kwh=0`），光伏完全本地消纳、系统持续净购电。协调优化相对基线主要体现为购电峰值与形状的差别。

## 图2 储能调度（充 / 放电功率随时间）

- **建议标题**：固定储能充放电功率时间分布对比
- **一句解释**：问题一在凌晨与光伏富余窗形成明显充电簇、傍晚形成放电簇，呈现可复述的削峰填谷时间结构；基线放电仅零星出现在高价规则窗，充电几乎缺位，体现规则型储能利用边界。

## 图3 EV 调度（充 / 放电功率随时间）

- **建议标题**：电动汽车聚合充放电功率时间分布对比
- **一句解释**：协调模型在日间与晚峰附近出现放电点云，与购电削减时段可对齐阅读；基线仅有充电轨迹、放电恒为零，从时间轴上直接展示 V2G 参与与否的差异。

## 图4 建筑柔性与弃光（移位 / 恢复 / 弃光随时间）

- **建议标题**：建筑柔性功率与弃光功率时间分布对比
- **一句解释**：问题一在若干连续时段呈现移位与恢复的交替结构，与弃光（本算例多为零）同轴展示，便于说明「建筑时间转移」对园区功率曲线的整形作用；基线对应列为零，可作为非协同参照的空白对照。

---
作图数据：`paper_tscatter_*_fullweek.csv` / `*_typicalday.csv`；脚本：`plot_paper_timeseries_scatters.py`；图：`results/figures/paper_tscatter_*`。
""",
        encoding="utf-8",
    )
    print(captions)

    print(f"典型日: {day}")
    for stem in ("paper_tscatter_01_grid", "paper_tscatter_02_ess", "paper_tscatter_03_ev", "paper_tscatter_04_flex_pv"):
        print(out / f"{stem}_fullweek.csv")
        print(out / f"{stem}_typicalday.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
