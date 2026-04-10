"""数据分析脚本：生成描述性统计表、基础可视化图和简要分析报告。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR = ROOT / "data" / "raw"
TABLE_DIR = ROOT / "results" / "tables"
FIG_DIR = ROOT / "results" / "figures"
NOTE_DIR = ROOT / "notes"
LANG = "zh"

I18N = {
    "Date": "日期",
    "Power (kW)": "功率（kW）",
    "CNY/kWh": "元/kWh",
    "kgCO2/kWh": "kgCO2/kWh",
    "Count": "数量",
    "Energy (kWh)": "能量（kWh）",
    "Total Native Load (7 Days)": "总原生负荷时序（7天）",
    "Total Load": "总负荷",
    "4-Point Moving Average": "4点滑动平均",
    "Campus Native Load Profile (7 Days)": "园区原生负荷画像（7天）",
    "Building Loads Comparison (7 Days)": "三类建筑负荷对比（7天）",
    "Office": "办公楼",
    "Wet Lab": "湿实验楼",
    "Teaching Center": "教学中心",
    "PV Available Power (7 Days)": "光伏可用出力时序（7天）",
    "PV Available": "光伏可用出力",
    "PV vs Total Load (7 Days)": "光伏与总负荷对比（7天）",
    "PV and Load Coupling (7-Day Overview)": "光伏与负荷耦合关系（7天总览）",
    "Typical Day Detail": "典型日细节",
    "Buy Price": "购电价",
    "Sell Price": "售电价",
    "Buy/Sell Price (7 Days)": "购售电价时序（7天）",
    "Grid Carbon Factor (7 Days)": "电网碳排因子时序（7天）",
    "EV Online Count (7 Days)": "EV在线数量时序（7天）",
    "Vehicle Count": "车辆数量",
    "EV Online Count Profile (7 Days)": "EV在线数量画像（7天）",
    "Charge Power Upper Bound": "最大充电功率边界",
    "Discharge Power Upper Bound": "最大放电功率边界",
    "EV Charge/Discharge Power Bounds (7 Days)": "EV充放电功率边界（7天）",
    "EV Charging/Discharging Capability (7 Days)": "EV充放电能力（7天）",
    "Charge Bound (kW)": "充电边界（kW）",
    "Discharge Bound (kW)": "放电边界（kW）",
    "Initial Energy Inflow": "EV 初始流入能量 (kWh)",
    "Required Departure Outflow": "EV 需求流出能量 (kWh)",
    "EV Energy Inflow/Outflow (7 Days)": "EV 能量流入/流出 (7天)",
}


def tr(text: str) -> str:
    return I18N.get(text, text) if LANG == "zh" else text


def zh_fig_name(filename: str) -> str:
    if LANG != "zh":
        return filename
    p = Path(filename)
    return f"{p.stem}_zh{p.suffix}"

PALETTE = {
    "navy": "#1f3b5c",
    "teal": "#2a9d8f",
    "orange": "#e76f51",
    "gold": "#e9c46a",
    "green": "#4c956c",
    "purple": "#6d597a",
    "gray": "#6c757d",
}

FIGSIZE = (12, 5.6)
FIGSIZE_PAPER = (13.5, 6.6)
TITLE_SIZE = 14
LABEL_SIZE = 12
TICK_SIZE = 10
LEGEND_SIZE = 10


def setup_theme() -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#d8dadd",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": "#d0d0d0",
            "grid.linestyle": "--",
            "grid.linewidth": 0.7,
            "grid.alpha": 0.7,
            "axes.titleweight": "semibold",
            "axes.titlesize": TITLE_SIZE,
            "axes.labelsize": LABEL_SIZE,
            "xtick.labelsize": TICK_SIZE,
            "ytick.labelsize": TICK_SIZE,
            "legend.fontsize": LEGEND_SIZE,
            "legend.frameon": False,
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )


def _style_time_axis(ax) -> None:
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 12]))
    ax.tick_params(axis="x", rotation=25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlabel(tr("Date"))


def _style_time_axis_paper(ax) -> None:
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.tick_params(axis="x", rotation=18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlabel(tr("Date"))


def output_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / filename
    if p.exists() and p.stat().st_size > 0:
        stem, suffix = p.stem, p.suffix
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return directory / f"{stem}_{ts}{suffix}"
    return p


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    p = output_path(TABLE_DIR, filename)
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def save_fig(filename: str, title: str, ylabel: str = "") -> Path:
    p = output_path(FIG_DIR, filename)
    ax = plt.gca()
    ax.set_title(title, pad=10)
    if ylabel:
        ax.set_ylabel(ylabel)
    _style_time_axis(ax)
    plt.tight_layout()
    plt.savefig(p, dpi=300)
    plt.close()
    return p


def main() -> None:
    setup_theme()
    # Load data
    load_df = pd.read_csv(PROCESSED_DIR / "load_profile.csv")
    pv_df = pd.read_csv(PROCESSED_DIR / "pv_profile.csv")
    price_df = pd.read_csv(PROCESSED_DIR / "price_profile.csv")
    carbon_df = pd.read_csv(PROCESSED_DIR / "carbon_profile.csv")
    ev_agg_df = pd.read_csv(PROCESSED_DIR / "ev_aggregate_profile.csv")
    ev_sessions_df = pd.read_csv(PROCESSED_DIR / "ev_sessions_clean.csv")

    for df in [load_df, pv_df, price_df, carbon_df, ev_agg_df]:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

    # ---------- 1) 负荷分析 ----------
    plt.figure(figsize=FIGSIZE)
    plt.plot(
        load_df["timestamp"],
        load_df["total_native_load_kw"],
        lw=2.4,
        color=PALETTE["navy"],
    )
    load_ts_fig = save_fig(
        zh_fig_name("load_total_7d_timeseries.png"),
        tr("Total Native Load (7 Days)"),
        ylabel=tr("Power (kW)"),
    )
    # Paper-grade redraw: stronger envelope sensation for load curve.
    fig, ax = plt.subplots(figsize=FIGSIZE_PAPER, constrained_layout=True)
    x = load_df["timestamp"]
    y = load_df["total_native_load_kw"]
    y_smooth = y.rolling(window=4, min_periods=1, center=True).mean()
    ax.fill_between(x, y, color=PALETTE["navy"], alpha=0.10)
    ax.plot(x, y, lw=1.7, color=PALETTE["navy"], alpha=0.85, label=tr("Total Load"))
    ax.plot(x, y_smooth, lw=2.8, color="#14283f", alpha=0.95, label=tr("4-Point Moving Average"))
    ax.set_title(tr("Campus Native Load Profile (7 Days)"), pad=10)
    ax.set_ylabel(tr("Power (kW)"))
    _style_time_axis_paper(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.14), ncol=2)
    load_ts_paper = output_path(FIG_DIR, zh_fig_name("load_total_7d_timeseries_paper.png"))
    fig.savefig(load_ts_paper, dpi=300)
    plt.close(fig)

    load_daily = (
        load_df.groupby("date")["total_native_load_kw"]
        .agg(load_peak_kw="max", load_valley_kw="min", load_mean_kw="mean")
        .reset_index()
    )
    load_daily["load_energy_kwh"] = load_daily["load_mean_kw"] * 24.0
    load_daily_tbl = save_csv(load_daily, "load_daily_stats.csv")

    plt.figure(figsize=FIGSIZE)
    plt.plot(
        load_df["timestamp"],
        load_df["office_building_kw"],
        label=tr("Office"),
        lw=2.0,
        color="#6FAFA6",
        alpha=0.88,
    )
    plt.plot(
        load_df["timestamp"],
        load_df["wet_lab_kw"],
        label=tr("Wet Lab"),
        lw=2.0,
        color="#E59A7A",
        alpha=0.88,
    )
    plt.plot(
        load_df["timestamp"],
        load_df["teaching_center_kw"],
        label=tr("Teaching Center"),
        lw=2.0,
        color="#8B7C9E",
        alpha=0.88,
    )
    plt.legend(loc="upper right", ncol=3)
    load_building_fig = save_fig(
        zh_fig_name("load_buildings_compare_7d.png"),
        tr("Building Loads Comparison (7 Days)"),
        ylabel=tr("Power (kW)"),
    )

    # ---------- 2) 光伏分析 ----------
    plt.figure(figsize=FIGSIZE)
    plt.plot(
        pv_df["timestamp"],
        pv_df["pv_available_kw"],
        color=PALETTE["gold"],
        lw=2.2,
    )
    pv_ts_fig = save_fig(zh_fig_name("pv_7d_timeseries.png"), tr("PV Available Power (7 Days)"), ylabel=tr("Power (kW)"))

    pv_daily = (
        pv_df.groupby("date")["pv_available_kw"]
        .agg(pv_peak_kw="max", pv_mean_kw="mean")
        .reset_index()
    )
    pv_daily["pv_energy_kwh"] = pv_daily["pv_mean_kw"] * 24.0
    pv_daily_tbl = save_csv(pv_daily, "pv_daily_stats.csv")

    lp = load_df[["timestamp", "total_native_load_kw"]].merge(
        pv_df[["timestamp", "pv_available_kw"]], on="timestamp", how="inner"
    )
    plt.figure(figsize=FIGSIZE)
    c_load = "#BEBAB9"
    c_pv = "#C47070"
    plt.plot(
        lp["timestamp"],
        lp["total_native_load_kw"],
        label=tr("Total Load"),
        lw=2.6,
        color=c_load,
    )
    plt.plot(
        lp["timestamp"],
        lp["pv_available_kw"],
        label=tr("PV Available"),
        lw=2.2,
        color=c_pv,
    )
    plt.fill_between(
        lp["timestamp"],
        lp["pv_available_kw"],
        color=c_pv,
        alpha=0.18,
    )
    plt.legend(loc="upper right")
    pv_load_fig = save_fig(zh_fig_name("pv_vs_load_7d.png"), tr("PV vs Total Load (7 Days)"), ylabel=tr("Power (kW)"))
    # Paper-grade redraw: overview + typical-day detail.
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 7.2),
        sharex=False,
        gridspec_kw={"height_ratios": [2.0, 1.2]},
        constrained_layout=True,
    )
    ax1, ax2 = axes
    x = lp["timestamp"]
    load_y = lp["total_native_load_kw"]
    pv_y = lp["pv_available_kw"]
    c_load = "#BEBAB9"
    c_pv = "#C47070"
    ax1.fill_between(x, load_y, color=c_load, alpha=0.14, zorder=1)
    ax1.plot(x, load_y, lw=2.5, color=c_load, label=tr("Total Load"), zorder=3)
    ax1.fill_between(x, pv_y, color=c_pv, alpha=0.30, zorder=2)
    ax1.plot(x, pv_y, lw=1.9, color=c_pv, label=tr("PV Available"), zorder=4)
    ax1.set_title(tr("PV and Load Coupling (7-Day Overview)"), pad=10)
    ax1.set_ylabel(tr("Power (kW)"))
    _style_time_axis_paper(ax1)
    ax1.legend(loc="upper right", framealpha=0.92)

    # Typical day: day with max PV peak
    lp_tmp = lp.copy()
    lp_tmp["date"] = lp_tmp["timestamp"].dt.date
    peak_day = lp_tmp.groupby("date")["pv_available_kw"].max().idxmax()
    day_df = lp_tmp[lp_tmp["date"] == peak_day]
    ax2.fill_between(day_df["timestamp"], day_df["pv_available_kw"], color=c_pv, alpha=0.35)
    ax2.plot(
        day_df["timestamp"],
        day_df["total_native_load_kw"],
        lw=2.1,
        color=c_load,
        label=tr("Total Load"),
    )
    ax2.plot(
        day_df["timestamp"],
        day_df["pv_available_kw"],
        lw=1.8,
        color=c_pv,
        label=tr("PV Available"),
    )
    ax2.set_title(f"{tr('Typical Day Detail')}（{peak_day}）", pad=8)
    ax2.set_ylabel(tr("Power (kW)"))
    _style_time_axis_paper(ax2)
    ax2.legend(loc="upper right", framealpha=0.92)
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    pv_load_paper = output_path(FIG_DIR, zh_fig_name("pv_vs_load_7d_paper.png"))
    fig.savefig(pv_load_paper, dpi=300)
    plt.close(fig)

    # ---------- 3) 电价与碳排 ----------
    plt.figure(figsize=FIGSIZE)
    plt.plot(
        price_df["timestamp"],
        price_df["grid_buy_price_cny_per_kwh"],
        label=tr("Buy Price"),
        lw=2.0,
        color=PALETTE["teal"],
    )
    plt.plot(
        price_df["timestamp"],
        price_df["grid_sell_price_cny_per_kwh"],
        label=tr("Sell Price"),
        lw=1.8,
        color=PALETTE["gray"],
    )
    plt.legend(loc="upper right")
    price_fig = save_fig(zh_fig_name("price_buy_sell_7d.png"), tr("Buy/Sell Price (7 Days)"), ylabel=tr("CNY/kWh"))

    plt.figure(figsize=FIGSIZE)
    plt.plot(
        carbon_df["timestamp"],
        carbon_df["grid_carbon_kg_per_kwh"],
        color=PALETTE["green"],
        lw=2.0,
    )
    carbon_fig = save_fig(zh_fig_name("carbon_factor_7d.png"), tr("Grid Carbon Factor (7 Days)"), ylabel=tr("kgCO2/kWh"))

    bins = [-1e9, 0.5, 0.8, 1e9]
    labels = ["low(<=0.5)", "mid(0.5,0.8]", "high(>0.8)"]
    seg = pd.cut(price_df["grid_buy_price_cny_per_kwh"], bins=bins, labels=labels)
    price_seg_tbl = (
        seg.value_counts()
        .rename_axis("buy_price_segment")
        .reset_index(name="period_count")
        .sort_values("buy_price_segment")
    )
    price_seg_tbl["share"] = price_seg_tbl["period_count"] / max(len(price_df), 1)
    price_seg_tbl_path = save_csv(price_seg_tbl, "price_segment_stats.csv")

    # ---------- 4) EV 聚合 ----------
    plt.figure(figsize=FIGSIZE)
    plt.plot(
        ev_agg_df["timestamp"],
        ev_agg_df["online_count"],
        color=PALETTE["purple"],
        lw=2.2,
    )
    ev_online_fig = save_fig(zh_fig_name("ev_online_count_7d.png"), tr("EV Online Count (7 Days)"), ylabel=tr("Count"))
    # Paper-grade redraw: line + area emphasis.
    fig, ax = plt.subplots(figsize=FIGSIZE_PAPER, constrained_layout=True)
    x = ev_agg_df["timestamp"]
    y = ev_agg_df["online_count"]
    ax.fill_between(x, y, color=PALETTE["purple"], alpha=0.15)
    ax.plot(x, y, color="#4f3b63", lw=2.4)
    ax.set_title(tr("EV Online Count Profile (7 Days)"), pad=10)
    ax.set_ylabel(tr("Vehicle Count"))
    _style_time_axis_paper(ax)
    ev_online_paper = output_path(FIG_DIR, zh_fig_name("ev_online_count_7d_paper.png"))
    fig.savefig(ev_online_paper, dpi=300)
    plt.close(fig)

    plt.figure(figsize=FIGSIZE)
    plt.plot(
        ev_agg_df["timestamp"],
        ev_agg_df["p_ev_ch_max_kw"],
        label=tr("Charge Power Upper Bound"),
        lw=2.4,
        color=PALETTE["teal"],
    )
    plt.plot(
        ev_agg_df["timestamp"],
        ev_agg_df["p_ev_dis_max_kw"],
        label=tr("Discharge Power Upper Bound"),
        lw=2.0,
        color=PALETTE["orange"],
    )
    plt.legend(loc="upper right")
    ev_power_fig = save_fig(
        zh_fig_name("ev_power_bounds_7d.png"),
        tr("EV Charge/Discharge Power Bounds (7 Days)"),
        ylabel=tr("Power (kW)"),
    )
    # Paper-grade redraw: layered subplots for clearer structure.
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 7.0),
        sharex=True,
        gridspec_kw={"hspace": 0.08},
        constrained_layout=True,
    )
    ax_up, ax_dn = axes
    x = ev_agg_df["timestamp"]
    y_ch = ev_agg_df["p_ev_ch_max_kw"]
    y_dis = ev_agg_df["p_ev_dis_max_kw"]
    ax_up.fill_between(x, y_ch, color=PALETTE["teal"], alpha=0.16)
    ax_up.plot(x, y_ch, lw=2.5, color="#1b7f75")
    ax_up.set_title(tr("EV Charging/Discharging Capability (7 Days)"), pad=10)
    ax_up.set_ylabel(tr("Charge Bound (kW)"))
    _style_time_axis_paper(ax_up)
    ax_up.tick_params(labelbottom=False)

    ax_dn.fill_between(x, y_dis, color=PALETTE["orange"], alpha=0.16)
    ax_dn.plot(x, y_dis, lw=2.3, color="#bb5b45")
    ax_dn.set_ylabel(tr("Discharge Bound (kW)"))
    _style_time_axis_paper(ax_dn)
    ax_dn.set_xlabel("Date")
    ev_power_paper = output_path(FIG_DIR, zh_fig_name("ev_power_bounds_7d_paper.png"))
    fig.savefig(ev_power_paper, dpi=300)
    plt.close(fig)

    plt.figure(figsize=FIGSIZE)
    plt.plot(
        ev_agg_df["timestamp"],
        ev_agg_df["e_ev_init_inflow_kwh"],
        label=tr("Initial Energy Inflow"),
        lw=2.0,
        color="#91CAE8",
        alpha=0.95,
    )
    plt.plot(
        ev_agg_df["timestamp"],
        ev_agg_df["e_ev_req_outflow_kwh"],
        label=tr("Required Departure Outflow"),
        lw=1.8,
        color="#F48892",
        alpha=0.95,
    )
    plt.legend(loc="upper right")
    ev_energy_fig = save_fig(
        zh_fig_name("ev_energy_inflow_outflow_7d.png"),
        tr("EV Energy Inflow/Outflow (7 Days)"),
        ylabel=tr("Energy (kWh)"),
    )

    ev_sessions_df["arrival_slot"] = pd.to_datetime(ev_sessions_df["arrival_slot"])
    ev_sessions_df["departure_slot"] = pd.to_datetime(ev_sessions_df["departure_slot"])
    ev_sessions_df["stay_hours"] = (
        (ev_sessions_df["departure_slot"] - ev_sessions_df["arrival_slot"]).dt.total_seconds() / 3600
    )
    ev_stats = pd.DataFrame(
        {
            "metric": [
                "session_count",
                "avg_stay_hours",
                "avg_initial_energy_kwh",
                "avg_required_departure_energy_kwh",
            ],
            "value": [
                float(len(ev_sessions_df)),
                float(ev_sessions_df["stay_hours"].mean()),
                float(ev_sessions_df["initial_energy_kwh"].mean()),
                float(ev_sessions_df["required_energy_at_departure_kwh"].mean()),
            ],
        }
    )
    ev_stats_tbl = save_csv(ev_stats, "ev_session_stats.csv")

    # report
    report = output_path(NOTE_DIR, "数据分析.md")
    load_peak = load_daily["load_peak_kw"].max()
    load_valley = load_daily["load_valley_kw"].min()
    pv_peak = pv_daily["pv_peak_kw"].max()
    avg_buy = price_df["grid_buy_price_cny_per_kwh"].mean()
    avg_carbon = carbon_df["grid_carbon_kg_per_kwh"].mean()
    avg_online = ev_agg_df["online_count"].mean()

    text = f"""# 数据分析

## 分析范围
- 数据来源：`data/processed/`（并参考 `data/raw/` 语义说明）
- 时间范围：2025-07-14 至 2025-07-20（15分钟粒度，7天）

## 主要发现
- 负荷方面：总负荷存在清晰日内波动，周内峰值约 `{load_peak:.2f} kW`，谷值约 `{load_valley:.2f} kW`。
- 建筑对比：办公楼、湿实验楼、教学中心三类负荷曲线节律不同，叠加后形成总负荷曲线。
- 光伏方面：光伏呈明显昼夜特征，周内峰值约 `{pv_peak:.2f} kW`；与总负荷同图可见白天有一定削峰潜力。
- 电价与碳排：购售电价存在分时差异，平均购电价约 `{avg_buy:.3f} CNY/kWh`；碳因子均值约 `{avg_carbon:.3f} kgCO2/kWh`。
- EV聚合：在站车辆规模随时段变化，平均在线数约 `{avg_online:.2f}`；充放电功率边界与进出站能量流在时段上存在集中分布。

## 产物清单
- 表格：
  - `{load_daily_tbl.as_posix()}`
  - `{pv_daily_tbl.as_posix()}`
  - `{price_seg_tbl_path.as_posix()}`
  - `{ev_stats_tbl.as_posix()}`
- 图形：
  - `{load_ts_fig.as_posix()}`
  - `{load_ts_paper.as_posix()}`
  - `{load_building_fig.as_posix()}`
  - `{pv_ts_fig.as_posix()}`
  - `{pv_load_fig.as_posix()}`
  - `{pv_load_paper.as_posix()}`
  - `{price_fig.as_posix()}`
  - `{carbon_fig.as_posix()}`
  - `{ev_online_fig.as_posix()}`
  - `{ev_online_paper.as_posix()}`
  - `{ev_power_fig.as_posix()}`
  - `{ev_power_paper.as_posix()}`
  - `{ev_energy_fig.as_posix()}`
"""
    report.write_text(text, encoding="utf-8")

    print("Analysis done.")
    print(f"Tables dir: {TABLE_DIR.as_posix()}")
    print(f"Figures dir: {FIG_DIR.as_posix()}")
    print(f"Report: {report.as_posix()}")


if __name__ == "__main__":
    main()
