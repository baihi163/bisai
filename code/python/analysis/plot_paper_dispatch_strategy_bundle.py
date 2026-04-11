# -*- coding: utf-8 -*-
"""
论文「调度方案」三张核心阶梯图（典型日 + 全周附录版），基于统一时序表。

图 1：外网购电阶梯 — 上下分面（问题一 / 基线）
图 2：灵活资源净功率 — 4 行共用时间轴，每行双线阶梯
图 3：储能时段末能量 SOC — 双线阶梯

输出：results/figures/paper_strategy_*_{typicalday,fullweek}.png
说明：results/tables/paper_strategy_bundle_readme.txt

依赖：pandas、matplotlib；不改模型。
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

EXPORT_SHOW_EPS = 0.5  # 售电全周 max<=此值则不绘制售电


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


def merge_dispatch(repo: Path) -> tuple[pd.DataFrame, str]:
    p1 = _read(repo, "problem1_dispatch_timeseries.csv")
    bl = _read(repo, "baseline_dispatch_timeseries.csv")
    m = p1.merge(bl, on="timestamp", suffixes=("_p1", "_bl"), how="inner")
    m["t"] = pd.to_datetime(m["timestamp"])
    m["date"] = m["t"].dt.date.astype(str)
    day = pick_typical_day(p1)
    m["p1_ess_net"] = pd.to_numeric(m["ess_discharge_kw_p1"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["ess_charge_kw_p1"], errors="coerce"
    ).fillna(0.0)
    m["bl_ess_net"] = pd.to_numeric(m["ess_discharge_kw_bl"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["ess_charge_kw_bl"], errors="coerce"
    ).fillna(0.0)
    m["p1_ev_net"] = pd.to_numeric(m["ev_discharge_kw_p1"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["ev_charge_kw_p1"], errors="coerce"
    ).fillna(0.0)
    m["bl_ev_net"] = pd.to_numeric(m["ev_discharge_kw_bl"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["ev_charge_kw_bl"], errors="coerce"
    ).fillna(0.0)
    m["p1_bld_net"] = pd.to_numeric(m["building_shift_kw_p1"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["building_recover_kw_p1"], errors="coerce"
    ).fillna(0.0)
    m["bl_bld_net"] = pd.to_numeric(m["building_shift_kw_bl"], errors="coerce").fillna(0.0) - pd.to_numeric(
        m["building_recover_kw_bl"], errors="coerce"
    ).fillna(0.0)
    return m, day


def _style_x(ax: plt.Axes, *, fullweek: bool) -> None:
    if fullweek:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    else:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")


def fig01_grid(df: pd.DataFrame, *, fullweek: bool, out: Path) -> None:
    w, h = (15.5, 5.6) if fullweek else (10.5, 5.0)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.16})

    def one(ax, imp, exp, title: str) -> None:
        ax.plot(df["t"], imp, drawstyle="steps-post", color="#1f77b4" if "问题" in title else "#ff7f0e", lw=1.4, label="外网购电")
        mx = float(np.nanmax(np.abs(exp.to_numpy())))
        if mx > EXPORT_SHOW_EPS:
            ax.plot(df["t"], exp, drawstyle="steps-post", color="#7f7f7f", lw=0.85, ls="--", alpha=0.55, label="售电")
        ax.axhline(0.0, color="#dddddd", lw=0.6)
        ax.set_ylabel("kW", fontsize=9)
        ax.set_title(title, fontsize=10, loc="left")
        ax.legend(loc="upper right", fontsize=7.5)
        ax.grid(True, axis="y", alpha=0.2, linestyle=":")

    pr = pd.to_numeric(df["price_buy_yuan_per_kwh_p1"], errors="coerce")
    one(
        axes[0],
        pd.to_numeric(df["grid_import_kw_p1"], errors="coerce"),
        pd.to_numeric(df["grid_export_kw_p1"], errors="coerce"),
        "问题一（协调优化）",
    )
    axp = axes[0].twinx()
    axp.plot(df["t"], pr, drawstyle="steps-post", color="#bcbd22", lw=0.9, alpha=0.65, label="购电价")
    axp.set_ylabel("元/kWh", fontsize=8, color="#737373")
    axp.tick_params(axis="y", labelsize=7, colors="#737373")
    one(
        axes[1],
        pd.to_numeric(df["grid_import_kw_bl"], errors="coerce"),
        pd.to_numeric(df["grid_export_kw_bl"], errors="coerce"),
        "非协同基线",
    )
    axes[1].set_xlabel("时间", fontsize=10)
    suf = "全周" if fullweek else "典型日"
    fig.suptitle(f"图1  外网购电功率时间分布（阶梯对比，{suf}）", fontsize=11.5, y=0.98)
    fig.text(
        0.5,
        0.02,
        "注：售电功率全周为 0（grid_export_energy_kwh=0），图中不绘售电；"
        "pv_curtail_energy_kwh=0，光伏完全本地消纳、系统持续净购电。",
        ha="center",
        fontsize=7,
        color="#333333",
    )
    _style_x(axes[1], fullweek=fullweek)
    fig.subplots_adjust(left=0.07, right=0.93, top=0.86, bottom=0.18, hspace=0.2)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig02_flex_net(df: pd.DataFrame, *, fullweek: bool, out: Path) -> None:
    w, h = (15.5, 9.5) if fullweek else (10.5, 8.0)
    rows = [
        ("p1_ess_net", "bl_ess_net", "储能净功率（放−充）"),
        ("p1_ev_net", "bl_ev_net", "EV 净功率（放−充）"),
        ("p1_bld_net", "bl_bld_net", "建筑净移位（移位−恢复）"),
        ("pv_curtail_kw_p1", "pv_curtail_kw_bl", "弃光功率"),
    ]
    fig, axes = plt.subplots(len(rows), 1, sharex=True, figsize=(w, h), dpi=150, gridspec_kw={"hspace": 0.26})
    for ax, (c1, c2, ttl) in zip(axes, rows):
        ax.plot(df["t"], df[c1], drawstyle="steps-post", color="#1f77b4", lw=1.1, label="问题一")
        ax.plot(df["t"], df[c2], drawstyle="steps-post", color="#ff7f0e", lw=1.05, label="基线")
        ax.axhline(0.0, color="#cccccc", lw=0.65)
        ax.set_ylabel("kW", fontsize=8)
        ax.set_title(ttl, fontsize=9.5, loc="left")
        ax.legend(loc="upper right", fontsize=7, ncol=2)
        ax.grid(True, axis="y", alpha=0.18, linestyle=":")
    axes[-1].set_xlabel("时间", fontsize=10)
    suf = "全周" if fullweek else "典型日"
    fig.suptitle(f"图2  灵活资源净功率与弃光（{suf}）", fontsize=11.5, y=0.995)
    fig.text(
        0.5,
        0.01,
        "净功率：储能/EV 为正表示该 15 min 内净放电占优；为负表示净充电占优。",
        ha="center",
        fontsize=7.5,
        color="#444444",
    )
    _style_x(axes[-1], fullweek=fullweek)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.09, hspace=0.28)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig03_soc(df: pd.DataFrame, *, fullweek: bool, out: Path) -> None:
    w, h = (15.5, 4.2) if fullweek else (10.5, 3.8)
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    s1 = pd.to_numeric(df["ess_energy_end_kwh_p1"], errors="coerce")
    s2 = pd.to_numeric(df["ess_energy_end_kwh_bl"], errors="coerce")
    ax.plot(df["t"], s1, drawstyle="steps-post", color="#1f77b4", lw=1.35, label="问题一（时段末能量）")
    ax.plot(df["t"], s2, drawstyle="steps-post", color="#ff7f0e", lw=1.25, label="基线（时段末能量）")
    ax.set_ylabel("kWh", fontsize=10)
    ax.set_xlabel("时间", fontsize=10)
    suf = "全周" if fullweek else "典型日"
    ax.set_title(f"图3  储能能量状态对比（{suf}）", fontsize=11)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.2, linestyle=":")
    _style_x(ax, fullweek=fullweek)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="三张核心调度阶梯图 bundle")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    ap.add_argument("--horizon", choices=("both", "fullweek", "typicalday"), default="both")
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    figd = repo / "results" / "figures"
    tbd = repo / "results" / "tables"
    figd.mkdir(parents=True, exist_ok=True)

    try:
        m, day = merge_dispatch(repo)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    readme = tbd / "paper_strategy_bundle_readme.txt"
    readme.write_text(
        f"typical_date={day}\n"
        "figures:\n"
        "  paper_strategy_01_grid_typicalday.png / _fullweek.png  (外网购电时间分布；售电本算例为 0 不绘)\n"
        "  paper_strategy_02_flex_net_typicalday.png / _fullweek.png\n"
        "  paper_strategy_03_ess_soc_typicalday.png / _fullweek.png\n"
        "strategy_doc: results/tables/paper_figure_strategy_dispatch.md\n"
        "grid_pv_digest: results/tables/paper_p1_grid_pv_digest_zh.md\n",
        encoding="utf-8",
    )

    for fullweek, suf in ((False, "typicalday"), (True, "fullweek")):
        if args.horizon == "fullweek" and not fullweek:
            continue
        if args.horizon == "typicalday" and fullweek:
            continue
        d = m if fullweek else m[m["date"] == day].copy()
        if len(d) < 4:
            continue
        fig01_grid(d, fullweek=fullweek, out=figd / f"paper_strategy_01_grid_{suf}.png")
        fig02_flex_net(d, fullweek=fullweek, out=figd / f"paper_strategy_02_flex_net_{suf}.png")
        fig03_soc(d, fullweek=fullweek, out=figd / f"paper_strategy_03_ess_soc_{suf}.png")
        print(figd / f"paper_strategy_01_grid_{suf}.png")
        print(figd / f"paper_strategy_02_flex_net_{suf}.png")
        print(figd / f"paper_strategy_03_ess_soc_{suf}.png")

    print(readme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
