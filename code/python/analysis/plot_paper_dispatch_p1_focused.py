# -*- coding: utf-8 -*-
"""
以问题一协同优化为时序展示主体；基线仅在「购电对比」图中出现。

输出（results/figures/）：
1. paper_p1focus_typicalday_dispatch.png   — 典型日：问题一多通道阶梯图
2. paper_p1focus_fullweek_dispatch.png     — 全周：问题一多通道总览
3. paper_p1focus_grid_compare_typicalday.png
4. paper_p1focus_grid_compare_fullweek.png — 外网购电：问题一 vs 基线 双线阶梯（本算例售电恒为 0，图注说明）

数据：results/tables/problem1_dispatch_timeseries.csv、baseline_dispatch_timeseries.csv
典型日选取：与仓库其他 paper 脚本一致（std(购电)+… 打分最大日）。
"""
from __future__ import annotations

import argparse
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


def _read(repo: Path, name: str) -> pd.DataFrame:
    p = repo / "results" / "tables" / name
    if not p.is_file():
        raise FileNotFoundError(p)
    return pd.read_csv(p, encoding="utf-8-sig")


def pick_typical_day(p1: pd.DataFrame) -> str:
    p1 = p1.copy()
    p1["_d"] = pd.to_datetime(p1["timestamp"]).dt.date.astype(str)
    best_d, best_s = "", -1.0
    for d, g in p1.groupby("_d"):
        gi = pd.to_numeric(g["grid_import_kw"], errors="coerce").fillna(0.0)
        ess = pd.to_numeric(g["ess_charge_kw"], errors="coerce").fillna(0.0) + pd.to_numeric(
            g["ess_discharge_kw"], errors="coerce"
        ).fillna(0.0)
        pr = pd.to_numeric(g["price_buy_yuan_per_kwh"], errors="coerce").fillna(0.0)
        corr = 0.0 if float(gi.std()) < 1e-6 else abs(float(np.corrcoef(gi.to_numpy(), pr.to_numpy())[0, 1]))
        s = float(gi.std() + 0.01 * float(ess.sum()) + 50.0 * corr)
        if s > best_s:
            best_s, best_d = s, str(d)
    return best_d


def _style_x(ax: plt.Axes, *, fullweek: bool) -> None:
    if fullweek:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=28, ha="right")


def plot_p1_multichannel(p1: pd.DataFrame, *, fullweek: bool, out: Path) -> None:
    p1 = p1.copy()
    p1["t"] = pd.to_datetime(p1["timestamp"])
    w = 15.5 if fullweek else 10.0
    h = 11.0 if fullweek else 9.5
    fig, axes = plt.subplots(5, 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.22})

    gi = pd.to_numeric(p1["grid_import_kw"], errors="coerce")
    pr = pd.to_numeric(p1["price_buy_yuan_per_kwh"], errors="coerce")
    axes[0].plot(p1["t"], gi, drawstyle="steps-post", color="#1f77b4", lw=1.35, label="购电")
    axes[0].set_ylabel("kW", fontsize=9)
    axes[0].set_title("外网购电", fontsize=9.5, loc="left")
    axes[0].legend(loc="upper left", fontsize=7)
    axes[0].grid(True, axis="y", alpha=0.2, linestyle=":")
    axp = axes[0].twinx()
    axp.plot(p1["t"], pr, drawstyle="steps-post", color="#bcbd22", lw=0.95, alpha=0.75, label="购电价")
    axp.set_ylabel("元/kWh", fontsize=8, color="#666666")
    axp.tick_params(axis="y", labelsize=7, colors="#666666")

    ech = pd.to_numeric(p1["ess_charge_kw"], errors="coerce")
    edc = pd.to_numeric(p1["ess_discharge_kw"], errors="coerce")
    axes[1].plot(p1["t"], ech, drawstyle="steps-post", color="#2ca02c", lw=1.1, label="储能充电")
    axes[1].plot(p1["t"], edc, drawstyle="steps-post", color="#d62728", lw=1.1, label="储能放电")
    axes[1].set_ylabel("kW", fontsize=9)
    axes[1].set_title("储能充放电", fontsize=9.5, loc="left")
    axes[1].legend(loc="upper left", fontsize=7, ncol=2)
    axes[1].grid(True, axis="y", alpha=0.2, linestyle=":")

    vch = pd.to_numeric(p1["ev_charge_kw"], errors="coerce")
    vdc = pd.to_numeric(p1["ev_discharge_kw"], errors="coerce")
    axes[2].plot(p1["t"], vch, drawstyle="steps-post", color="#9467bd", lw=1.05, label="EV 充电")
    axes[2].plot(p1["t"], vdc, drawstyle="steps-post", color="#8c564b", lw=1.05, label="EV 放电")
    axes[2].set_ylabel("kW", fontsize=9)
    axes[2].set_title("电动汽车充放电", fontsize=9.5, loc="left")
    axes[2].legend(loc="upper left", fontsize=7, ncol=2)
    axes[2].grid(True, axis="y", alpha=0.2, linestyle=":")

    sh = pd.to_numeric(p1["building_shift_kw"], errors="coerce")
    rc = pd.to_numeric(p1["building_recover_kw"], errors="coerce")
    axes[3].plot(p1["t"], sh, drawstyle="steps-post", color="#e377c2", lw=1.05, label="建筑移位")
    axes[3].plot(p1["t"], rc, drawstyle="steps-post", color="#7f7f7f", lw=1.05, label="建筑恢复")
    axes[3].set_ylabel("kW", fontsize=9)
    axes[3].set_title("建筑柔性", fontsize=9.5, loc="left")
    axes[3].legend(loc="upper left", fontsize=7, ncol=2)
    axes[3].grid(True, axis="y", alpha=0.2, linestyle=":")

    cur = pd.to_numeric(p1["pv_curtail_kw"], errors="coerce")
    axes[4].plot(p1["t"], cur, drawstyle="steps-post", color="#bcbd22", lw=1.1, label="弃光")
    axes[4].set_ylabel("kW", fontsize=9)
    axes[4].set_title("弃光功率", fontsize=9.5, loc="left")
    axes[4].legend(loc="upper left", fontsize=7)
    axes[4].grid(True, axis="y", alpha=0.2, linestyle=":")
    axes[4].set_xlabel("时间", fontsize=10)

    suf = "全周" if fullweek else "典型日"
    fig.suptitle(
        f"问题一协调优化 — 多通道调度（{suf}，光伏本地全消纳、持续净购电）",
        fontsize=12,
        y=0.995,
    )
    fig.text(
        0.5,
        0.03,
        "阶梯线：每 15 min 内功率取常值；首子图为外网购电功率，右轴为分时购电价。\n"
        "本算例售电功率全周为 0（grid_export_energy_kwh=0），故不绘售电曲线；非模型禁止反送，"
        "系全周光伏可用功率均低于协同后等效负荷且弃光电量为 0（pv_curtail_energy_kwh=0），母线无富余外送。",
        ha="center",
        fontsize=7,
        color="#333333",
    )
    _style_x(axes[4], fullweek=fullweek)
    fig.subplots_adjust(left=0.09, right=0.94, top=0.91, bottom=0.14, hspace=0.28)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_grid_compare(m: pd.DataFrame, *, fullweek: bool, out: Path) -> None:
    m = m.copy()
    m["t"] = pd.to_datetime(m["timestamp"])
    w = 15.0 if fullweek else 9.5
    h = 3.6 if fullweek else 3.2
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    g1 = pd.to_numeric(m["grid_import_kw_p1"], errors="coerce")
    g2 = pd.to_numeric(m["grid_import_kw_bl"], errors="coerce")
    ax.plot(m["t"], g1, drawstyle="steps-post", color="#1f77b4", lw=1.45, label="问题一 购电")
    ax.plot(m["t"], g2, drawstyle="steps-post", color="#ff7f0e", lw=1.25, alpha=0.9, label="基线 购电")
    ax.set_ylabel("kW", fontsize=10)
    ax.set_xlabel("时间", fontsize=10)
    suf = "全周" if fullweek else "典型日"
    ax.set_title(f"外网购电功率对比（{suf}）", fontsize=11)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.2, linestyle=":")
    _style_x(ax, fullweek=fullweek)
    fig.text(
        0.5,
        0.02,
        "注：问题一与基线在本算例 grid_export_energy_kwh 均为 0，仅对比购电；"
        "光伏完全本地消纳（pv_curtail_energy_kwh=0），系统持续净购电。",
        ha="center",
        fontsize=7,
        color="#333333",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="问题一为主时序 + 购电双模型对比")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    ap.add_argument("--horizon", choices=("both", "fullweek", "typicalday"), default="both")
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    figd = repo / "results" / "figures"
    tbd = repo / "results" / "tables"

    try:
        p1 = _read(repo, "problem1_dispatch_timeseries.csv")
        bl = _read(repo, "baseline_dispatch_timeseries.csv")
        m = p1.merge(bl, on="timestamp", suffixes=("_p1", "_bl"), how="inner")
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    day = pick_typical_day(p1)
    m["date"] = pd.to_datetime(m["timestamp"]).dt.date.astype(str)

    tbd.mkdir(parents=True, exist_ok=True)
    (tbd / "paper_p1focus_meta.txt").write_text(
        f"typical_date={day}\n"
        "p1_multichannel_figures: problem1 only\n"
        "grid_compare: problem1 vs baseline grid_import_kw only\n"
        "grid_export_energy_kwh_p1=0; pv_curtail_energy_kwh_p1=0 (see paper_p1_grid_pv_digest_zh.md)\n",
        encoding="utf-8",
    )

    for fullweek, suf in ((False, "typicalday"), (True, "fullweek")):
        if args.horizon == "fullweek" and not fullweek:
            continue
        if args.horizon == "typicalday" and fullweek:
            continue
        p1s = p1 if fullweek else p1[pd.to_datetime(p1["timestamp"]).dt.date.astype(str) == day].copy()
        ms = m if fullweek else m[m["date"] == day].copy()
        if len(p1s) < 4 or len(ms) < 4:
            print(f"数据过少: {suf}", file=sys.stderr)
            continue
        plot_p1_multichannel(
            p1s,
            fullweek=fullweek,
            out=figd / f"paper_p1focus_{'fullweek' if fullweek else 'typicalday'}_dispatch.png",
        )
        plot_grid_compare(ms, fullweek=fullweek, out=figd / f"paper_p1focus_grid_compare_{suf}.png")
        print(figd / f"paper_p1focus_{'fullweek' if fullweek else 'typicalday'}_dispatch.png")
        print(figd / f"paper_p1focus_grid_compare_{suf}.png")

    print(tbd / "paper_p1focus_meta.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
