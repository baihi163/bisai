# -*- coding: utf-8 -*-
"""
时间轴散点图：上下分面（问题一 / 基线），共用横轴时间。

依赖：matplotlib、pandas；先运行 build_paper_timeseries_scatter_data.py 生成 CSV。

输出：results/figures/
- paper_tscatter_01_grid_fullweek.png / _typicalday.png
- paper_tscatter_02_ess_*.png
- paper_tscatter_03_ev_*.png
- paper_tscatter_04_flex_pv_*.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:
    print("请安装 matplotlib", file=sys.stderr)
    raise

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

SeriesSpec = tuple[str, str, str, str]  # col, label, color, marker


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["t"] = pd.to_datetime(df["timestamp"])
    return df


def _style_time_axis(ax: plt.Axes, *, fullweek: bool) -> None:
    if fullweek:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")


def plot_faceted(
    df: pd.DataFrame,
    *,
    p1_series: list[SeriesSpec],
    bl_series: list[SeriesSpec],
    ylabel: str,
    title: str,
    out_path: Path,
    fullweek: bool,
    footnote: str | None = None,
) -> None:
    h = 7.5 if fullweek else 6.2
    w = 16.0 if fullweek else 11.0
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.12})

    for ax, series, row_title in (
        (axes[0], p1_series, "问题一（协调优化）"),
        (axes[1], bl_series, "非协同基线"),
    ):
        for col, lab, c, mk in series:
            y = pd.to_numeric(df[col], errors="coerce").fillna(0.0).to_numpy()
            ax.scatter(
                df["t"],
                y,
                s=14 if fullweek else 22,
                alpha=0.55,
                c=c,
                marker=mk,
                label=lab,
                edgecolors="none",
                rasterized=True,
            )
        ax.axhline(0.0, color="#bbbbbb", linewidth=0.8, linestyle="-", zorder=0)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(row_title, fontsize=10, loc="left")
        ax.legend(loc="upper right", fontsize=8, ncol=min(3, len(series)), framealpha=0.9)
        ax.grid(True, axis="y", alpha=0.25, linestyle=":")

    axes[1].set_xlabel("时间", fontsize=10)
    fig.suptitle(title, fontsize=12, y=0.995)
    _style_time_axis(axes[1], fullweek=fullweek)
    btm = 0.20 if footnote else 0.14
    if footnote:
        fig.text(
            0.5,
            0.02,
            footnote,
            ha="center",
            fontsize=6.8,
            color="#333333",
        )
    fig.subplots_adjust(left=0.07, right=0.99, top=0.91, bottom=btm, hspace=0.2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


GRID_FOOTNOTE = (
    "注：本算例向电网售电功率全周为 0（grid_export_energy_kwh=0），故仅绘购电散点；"
    "非模型禁止反送，系光伏可用功率低于协同后等效负荷且弃光电量为 0（pv_curtail_energy_kwh=0），"
    "光伏完全本地消纳、系统持续净购电。"
)

FIGS: list[
    tuple[str, list[SeriesSpec], list[SeriesSpec], str, str, str, str | None]
] = [
    (
        "01_grid",
        [
            ("p1_grid_import_kw", "外网购电", "#1f77b4", "o"),
        ],
        [
            ("bl_grid_import_kw", "外网购电", "#ff7f0e", "o"),
        ],
        "功率（kW）",
        "图1  外网购电功率时间分布（全周）",
        "图1  外网购电功率时间分布（典型日）",
        GRID_FOOTNOTE,
    ),
    (
        "02_ess",
        [
            ("p1_ess_charge_kw", "储能充电", "#2ca02c", "o"),
            ("p1_ess_discharge_kw", "储能放电", "#d62728", "s"),
        ],
        [
            ("bl_ess_charge_kw", "储能充电", "#98df8a", "o"),
            ("bl_ess_discharge_kw", "储能放电", "#ff9896", "s"),
        ],
        "功率（kW）",
        "图2  储能充放电功率时间分布（全周）",
        "图2  储能充放电功率时间分布（典型日）",
        None,
    ),
    (
        "03_ev",
        [
            ("p1_ev_charge_kw", "EV充电", "#9467bd", "o"),
            ("p1_ev_discharge_kw", "EV放电", "#8c564b", "D"),
        ],
        [
            ("bl_ev_charge_kw", "EV充电", "#c5b0d5", "o"),
            ("bl_ev_discharge_kw", "EV放电", "#c49c94", "D"),
        ],
        "功率（kW）",
        "图3  电动汽车充放电功率时间分布（全周）",
        "图3  电动汽车充放电功率时间分布（典型日）",
        None,
    ),
    (
        "04_flex_pv",
        [
            ("p1_building_shift_kw", "建筑移位", "#e377c2", "o"),
            ("p1_building_recover_kw", "建筑恢复", "#7f7f7f", "s"),
            ("p1_pv_curtail_kw", "弃光", "#bcbd22", "^"),
        ],
        [
            ("bl_building_shift_kw", "建筑移位", "#f7b6d2", "o"),
            ("bl_building_recover_kw", "建筑恢复", "#c7c7c7", "s"),
            ("bl_pv_curtail_kw", "弃光", "#dbdb8d", "^"),
        ],
        "功率（kW）",
        "图4  建筑柔性及弃光功率时间分布（全周）",
        "图4  建筑柔性及弃光功率时间分布（典型日）",
        None,
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="绘制时间轴分面散点图")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    ap.add_argument(
        "--horizon",
        choices=("both", "fullweek", "typicalday"),
        default="both",
        help="生成全周、典型日或二者",
    )
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    tbl = repo / "results" / "tables"
    figd = repo / "results" / "figures"

    for stem, p1s, bls, ylab, title_fw, title_td, fnote in FIGS:
        for suf, fullweek, title in (("fullweek", True, title_fw), ("typicalday", False, title_td)):
            if args.horizon == "fullweek" and not fullweek:
                continue
            if args.horizon == "typicalday" and fullweek:
                continue
            csv = tbl / f"paper_tscatter_{stem}_{suf}.csv"
            if not csv.is_file():
                print(f"跳过（缺文件）: {csv}", file=sys.stderr)
                continue
            df = _load(csv)
            outp = figd / f"paper_tscatter_{stem}_{suf}.png"
            plot_faceted(
                df,
                p1_series=p1s,
                bl_series=bls,
                ylabel=ylab,
                title=title,
                out_path=outp,
                fullweek=fullweek,
                footnote=fnote,
            )
            print(outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
