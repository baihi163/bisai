# -*- coding: utf-8 -*-
"""
论文「合图重构」：在**不改模型、不重算优化**的前提下，基于统一时序表生成
更少、信息密度更高的时间序列图。

产出（results/figures/）：
1. paper_composite_01_grid_import_fullweek.png / _typicalday.png
   — 外网购电为主：上下分面（问题一 / 基线），阶梯折线；售电全周近零时不绘制售电曲线。
2. paper_composite_02_flex_resources_net_fullweek.png / _typicalday.png
   — 灵活资源净功率总览：4 行子图、共用时间轴，每行双线（问题一 vs 基线）。
   量：ess_net, ev_net, building_shift−recover, pv_curtail。

可选数据导出（results/tables/）：
- paper_composite_merged_net_fullweek.csv / _typicalday.csv

说明文档：results/tables/paper_composite_figure_guide.md
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

EXPORT_EPS_KW = 0.5  # 售电全周若 max<=此值则完全不画售电曲线


def _load_merge(repo: Path) -> tuple[pd.DataFrame, str]:
    path = _HERE / "build_paper_timeseries_scatter_data.py"
    spec = importlib.util.spec_from_file_location("bts", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    df, day = mod.merge_aligned(repo)
    df["t"] = pd.to_datetime(df["timestamp"])
    df["p1_ess_net_kw"] = df["p1_ess_discharge_kw"] - df["p1_ess_charge_kw"]
    df["bl_ess_net_kw"] = df["bl_ess_discharge_kw"] - df["bl_ess_charge_kw"]
    df["p1_ev_net_kw"] = df["p1_ev_discharge_kw"] - df["p1_ev_charge_kw"]
    df["bl_ev_net_kw"] = df["bl_ev_discharge_kw"] - df["bl_ev_charge_kw"]
    df["p1_building_net_kw"] = df["p1_building_shift_kw"] - df["p1_building_recover_kw"]
    df["bl_building_net_kw"] = df["bl_building_shift_kw"] - df["bl_building_recover_kw"]
    return df, day


def _style_x(ax: plt.Axes, *, fullweek: bool) -> None:
    if fullweek:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=32, ha="right")


def plot_grid_composite(df: pd.DataFrame, *, fullweek: bool, out: Path, title: str) -> None:
    w, h = (16.0, 5.8) if fullweek else (11.0, 5.2)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.14})

    def panel(ax: plt.Axes, t, imp, exp, label: str) -> None:
        ax.plot(t, imp, drawstyle="steps-post", color="#1f77b4" if "问题" in label else "#ff7f0e", lw=1.35, label="购电功率")
        mx = float(np.nanmax(np.abs(exp.to_numpy()))) if len(exp) else 0.0
        if mx > EXPORT_EPS_KW:
            ax.plot(
                t,
                exp,
                drawstyle="steps-post",
                color="#888888",
                lw=0.9,
                ls="--",
                alpha=0.55,
                label="售电功率（弱显）",
            )
        ax.axhline(0.0, color="#cccccc", lw=0.7)
        ax.set_ylabel("功率（kW）", fontsize=10)
        ax.set_title(label, fontsize=10, loc="left")
        ax.legend(loc="upper right", fontsize=7.5, ncol=2)
        ax.grid(True, axis="y", alpha=0.22, linestyle=":")

    panel(axes[0], df["t"], df["p1_grid_import_kw"], df["p1_grid_export_kw"], "问题一（协调优化）— 外网购电")
    panel(axes[1], df["t"], df["bl_grid_import_kw"], df["bl_grid_export_kw"], "非协同基线 — 外网购电")
    axes[1].set_xlabel("时间", fontsize=10)
    fig.suptitle(title, fontsize=11.5, y=0.995)
    fig.text(
        0.5,
        0.02,
        "注：本算例售电功率全周为 0（grid_export_energy_kwh=0），图中不绘售电；"
        "光伏完全本地消纳（pv_curtail_energy_kwh=0），系统持续净购电。",
        ha="center",
        fontsize=7,
        color="#333333",
    )
    _style_x(axes[1], fullweek=fullweek)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.86, bottom=0.18, hspace=0.22)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_flex_net_composite(df: pd.DataFrame, *, fullweek: bool, out: Path, title: str) -> None:
    w, h = (16.0, 10.0) if fullweek else (11.0, 8.5)
    rows = [
        ("p1_ess_net_kw", "bl_ess_net_kw", "储能净功率（放电−充电）", "正值偏放电、负值偏充电"),
        ("p1_ev_net_kw", "bl_ev_net_kw", "EV 净功率（放电−充电）", "基线无 V2G 时期望贴近 EV 充电为负"),
        ("p1_building_net_kw", "bl_building_net_kw", "建筑净移位（移位−恢复）", "基线无柔性时贴近 0"),
        ("p1_pv_curtail_kw", "bl_pv_curtail_kw", "弃光功率", "非负；本算例可能全为 0"),
    ]
    fig, axes = plt.subplots(len(rows), 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.28})

    for ax, (c1, c2, rtitle, note) in zip(axes, rows):
        ax.plot(
            df["t"],
            df[c1],
            drawstyle="steps-post",
            color="#1f77b4",
            lw=1.15,
            label="问题一",
        )
        ax.plot(
            df["t"],
            df[c2],
            drawstyle="steps-post",
            color="#ff7f0e",
            lw=1.05,
            ls="-",
            alpha=0.9,
            label="基线",
        )
        ax.axhline(0.0, color="#bbbbbb", lw=0.75)
        ax.set_ylabel("kW", fontsize=9)
        ax.set_title(rtitle, fontsize=9.5, loc="left")
        ax.text(
            0.01,
            0.04,
            note,
            transform=ax.transAxes,
            fontsize=7,
            color="#444444",
            verticalalignment="bottom",
        )
        ax.legend(loc="upper right", fontsize=7.5, ncol=2)
        ax.grid(True, axis="y", alpha=0.2, linestyle=":")

    axes[-1].set_xlabel("时间", fontsize=10)
    fig.suptitle(title, fontsize=11.5, y=0.995)
    fig.text(
        0.5,
        0.01,
        "净功率符号：储能/EV 为正表示净放电占优；为负表示净充电占优。建筑净移位为正表示移位强于恢复。",
        ha="center",
        fontsize=7.5,
        color="#333333",
    )
    _style_x(axes[-1], fullweek=fullweek)
    fig.subplots_adjust(left=0.08, right=0.99, top=0.94, bottom=0.10, hspace=0.25)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def write_guide(repo: Path) -> None:
    p = repo / "results" / "tables" / "paper_composite_figure_guide.md"
    p.write_text(
        """# 论文合图重构说明

## 原 8 张时间散点图 → 新 4 张合图（压缩关系）

| 原图（8 张） | 并入新图 |
|--------------|-----------|
| `paper_tscatter_01_grid_*`（购电散点；售电本算例为 0 不绘） | **合图 1**：`paper_composite_01_grid_import_*` — 外网购电阶梯线为主，售电曲线省略 |
| `paper_tscatter_02_ess_*` | **合图 2** 第 1 行：储能净功率 |
| `paper_tscatter_03_ev_*` | **合图 2** 第 2 行：EV 净功率 |
| `paper_tscatter_04_flex_pv_*` 中建筑与弃光 | **合图 2** 第 3–4 行：建筑净移位、弃光 |

叙事上：**合图 1** 回答「外网结果是否削峰」；**合图 2** 回答「协同机制由哪些灵活资源在时间轴上承担」。

## 新图文件与建议标题

| 文件 | 建议图题 | 正文 / 附录 |
|------|-----------|-------------|
| `paper_composite_01_grid_import_typicalday.png` | 典型日外网购电功率时间分布（问题一 vs 基线） | **正文**（与削峰填谷叙述直接挂钩） |
| `paper_composite_01_grid_import_fullweek.png` | 全周外网购电功率时间分布（问题一 vs 基线） | **附录** |
| `paper_composite_02_flex_resources_net_typicalday.png` | 典型日灵活资源净功率协同总览 | **正文**（机制一张说清） |
| `paper_composite_02_flex_resources_net_fullweek.png` | 全周灵活资源净功率协同总览 | **附录** |

## 与旧脚本关系

- 旧脚本 `plot_paper_timeseries_scatters.py` 生成的 8 张 `paper_tscatter_*` 可保留作补充材料；**投稿排版以本目录 `paper_composite_*` 为主图**。
- 数据仍来自 `problem1_dispatch_timeseries.csv` / `baseline_dispatch_timeseries.csv`（经 `build_paper_timeseries_scatter_data.merge_aligned` 对齐）。

## 作图脚本

`code/python/analysis/plot_paper_dispatch_composite_figures.py`

可选合并净功率表：`paper_composite_merged_net_*.csv`。

## 图注建议（本算例）

合图 1 图下已自动生成脚注：售电全周为 0（`grid_export_energy_kwh=0`）故不绘售电；`pv_curtail_energy_kwh=0`，光伏完全本地消纳、系统持续净购电。详见 `paper_p1_grid_pv_digest_zh.md`。
""",
        encoding="utf-8",
    )
    print(p)


def export_net_csv(df: pd.DataFrame, day: str, repo: Path) -> None:
    out = repo / "results" / "tables"
    cols = [
        "slot_id",
        "timestamp",
        "date",
        "price_buy_yuan_per_kwh",
        "p1_grid_import_kw",
        "bl_grid_import_kw",
        "p1_ess_net_kw",
        "bl_ess_net_kw",
        "p1_ev_net_kw",
        "bl_ev_net_kw",
        "p1_building_net_kw",
        "bl_building_net_kw",
        "p1_pv_curtail_kw",
        "bl_pv_curtail_kw",
    ]
    df[cols].to_csv(out / "paper_composite_merged_net_fullweek.csv", index=False, encoding="utf-8-sig")
    df[df["date"] == day][cols].to_csv(out / "paper_composite_merged_net_typicalday.csv", index=False, encoding="utf-8-sig")


def main() -> int:
    ap = argparse.ArgumentParser(description="论文合图：电网 + 灵活资源净功率总览")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    ap.add_argument("--horizon", choices=("both", "fullweek", "typicalday"), default="both")
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    figd = repo / "results" / "figures"

    try:
        df, day = _load_merge(repo)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    export_net_csv(df, day, repo)
    write_guide(repo)

    for fullweek, suf in ((True, "fullweek"), (False, "typicalday")):
        if args.horizon == "fullweek" and not fullweek:
            continue
        if args.horizon == "typicalday" and fullweek:
            continue
        sub = df if fullweek else df[df["date"] == day].copy()
        if len(sub) < 4:
            print(f"数据过少: {suf}", file=sys.stderr)
            continue

        t1 = (
            "全周外网购电功率时间分布（阶梯对比）"
            if fullweek
            else "典型日外网购电功率时间分布（阶梯对比）"
        )
        plot_grid_composite(
            sub,
            fullweek=fullweek,
            out=figd / f"paper_composite_01_grid_import_{suf}.png",
            title=t1,
        )
        t2 = "全周灵活资源净功率协同总览" if fullweek else "典型日灵活资源净功率协同总览"
        plot_flex_net_composite(
            sub,
            fullweek=fullweek,
            out=figd / f"paper_composite_02_flex_resources_net_{suf}.png",
            title=t2,
        )
        print(figd / f"paper_composite_01_grid_import_{suf}.png")
        print(figd / f"paper_composite_02_flex_resources_net_{suf}.png")

    print(repo / "results" / "tables" / "paper_composite_merged_net_fullweek.csv")
    print(repo / "results" / "tables" / "paper_composite_merged_net_typicalday.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
