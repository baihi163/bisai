"""场景驱动细化数据分析：论文成品级专题图重绘。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
FIG_DIR = ROOT / "results" / "figures"
TABLE_DIR = ROOT / "results" / "tables"
NOTE_DIR = ROOT / "notes"
LANG = "zh"

I18N = {
    "Normal day": "正常日",
    "Low-irradiance day": "低辐照日",
    "Import-limited day": "进线受限日",
    "Hour of Day": "时刻",
    "Total Native Load (kW)": "总原生负荷（kW）",
    "PV Available (kW)": "光伏可用出力（kW）",
    "Typical-Day Load Profiles (24 h Aligned)": "典型日负荷对比（24小时对齐）",
    "Typical-Day PV Profiles: Noon Support Loss on 2025-07-16": "典型日光伏对比：2025-07-16中午支撑下滑",
    "Storm-cloud window": "暴云扰动时段",
    "Load": "总负荷",
    "Grid limit": "进线限额",
    "PV": "光伏可用出力",
    "Deficit zone": "供电缺口区",
    "Event window": "事件窗口",
    "Stress window": "压力窗口",
    "Power (kW)": "功率（kW）",
    "Time": "时间",
    "Supply Pressure: Margin Between Demand and Available Supply": "供电压力：需求与可供给余量对比",
    "EV Online Count": "EV在线数量",
    "EV Count": "EV数量",
    "EV Max Charge Power": "EV最大充电能力",
    "EV Max Discharge Power": "EV最大放电能力",
    "Power Bound (kW)": "功率边界（kW）",
    "EV Support Potential: Online vs Power Bounds": "EV支撑潜力：在线规模与功率边界",
    "Irradiance (event day)": "辐照度（事件日）",
    "Irradiance (normal day)": "辐照度（正常日）",
    "Irradiance (W/m²)": "辐照度（W/m²）",
    "PV (event day)": "光伏出力（事件日）",
    "PV (normal day)": "光伏出力（正常日）",
    "Storm-Cloud Disturbance: Noon Irradiance and PV Support Drop": "暴云扰动：中午辐照与光伏支撑下滑",
}


def tr(text: str) -> str:
    return I18N.get(text, text) if LANG == "zh" else text


def zh_fig_name(filename: str) -> str:
    if LANG != "zh":
        return filename
    p = Path(filename)
    return f"{p.stem}_zh{p.suffix}"

PALETTE = {
    "load": "#16324f",
    "pv": "#c5852f",
    "grid": "#1b7f75",
    "pressure": "#bb3e03",
    "price": "#5e548e",
    "carbon": "#4c956c",
    "ev": "#6d597a",
}


def output_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / filename
    if p.exists() and p.stat().st_size > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return directory / f"{p.stem}_{ts}{p.suffix}"
    return p


def setup_theme() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.color": "#e6e7e9",
            "grid.linestyle": "--",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.55,
            "axes.edgecolor": "#d8dadd",
            "axes.linewidth": 0.8,
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.titlesize": 14,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "legend.frameon": False,
        }
    )


def style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def main() -> None:
    setup_theme()
    # load & merge
    load = pd.read_csv(PROCESSED / "load_profile.csv")
    pv = pd.read_csv(PROCESSED / "pv_profile.csv")
    price = pd.read_csv(PROCESSED / "price_profile.csv")
    carbon = pd.read_csv(PROCESSED / "carbon_profile.csv")
    grid = pd.read_csv(PROCESSED / "grid_limits.csv")
    ev = pd.read_csv(PROCESSED / "ev_aggregate_profile.csv")
    ts_raw = pd.read_csv(RAW / "timeseries_15min.csv")[["timestamp", "solar_irradiance_wm2"]]

    df = (
        load.merge(pv, on="timestamp")
        .merge(grid, on="timestamp")
        .merge(price, on="timestamp")
        .merge(carbon, on="timestamp")
        .merge(ev[["timestamp", "online_count", "p_ev_ch_max_kw", "p_ev_dis_max_kw"]], on="timestamp")
        .merge(ts_raw, on="timestamp", how="left")
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    df["pressure_index"] = (
        df["total_native_load_kw"] - df["pv_available_kw"] - df["grid_import_limit_kw"]
    )

    events = [
        (
            "stress_event_1",
            pd.Timestamp("2025-07-16 11:00:00"),
            pd.Timestamp("2025-07-16 14:00:00"),
            "Low irradiance due to storm clouds",
            "光伏下降压力",
        ),
        (
            "stress_event_2",
            pd.Timestamp("2025-07-17 13:00:00"),
            pd.Timestamp("2025-07-17 16:00:00"),
            "Grid import limit reduced to 650 kW",
            "外部供电受限压力",
        ),
        (
            "stress_event_3",
            pd.Timestamp("2025-07-18 17:00:00"),
            pd.Timestamp("2025-07-18 19:00:00"),
            "Grid import limit reduced to 700 kW during evening peak",
            "晚高峰叠加受限压力",
        ),
    ]

    event_table_paths = []
    event_fig_paths = []

    # typical day comparison (only core-variable comparison charts)
    day_tags = {
        "normal_day": pd.Timestamp("2025-07-15").date(),
        "low_irradiance_day": pd.Timestamp("2025-07-16").date(),
        "import_limited_day": pd.Timestamp("2025-07-17").date(),
    }
    rows = []
    for tag, day in day_tags.items():
        d = df[df["date"] == day]
        rows.append(
            {
                "day_type": tag,
                "date": str(day),
                "load_peak_kw": float(d["total_native_load_kw"].max()),
                "load_energy_kwh": float(d["total_native_load_kw"].mean() * 24),
                "pv_peak_kw": float(d["pv_available_kw"].max()),
                "pv_energy_kwh": float(d["pv_available_kw"].mean() * 24),
                "grid_limit_min_kw": float(d["grid_import_limit_kw"].min()),
                "buy_price_mean": float(d["grid_buy_price_cny_per_kwh"].mean()),
                "carbon_mean": float(d["grid_carbon_kg_per_kwh"].mean()),
                "pressure_max_kw": float(d["pressure_index"].max()),
            }
        )
    typical_df = pd.DataFrame(rows)
    typical_path = output_path(TABLE_DIR, "typical_days_comparison.csv")
    typical_df.to_csv(typical_path, index=False, encoding="utf-8-sig")

    # A1) typical day load comparison
    fig, ax = plt.subplots(figsize=(13, 6), constrained_layout=True)
    load_styles = {
        "normal_day": {"label": "Normal day", "color": "#5f6b7a", "lw": 1.8, "zorder": 2},
        "low_irradiance_day": {"label": "Low-irradiance day", "color": "#1f3b5c", "lw": 2.7, "zorder": 4},
        "import_limited_day": {"label": "Import-limited day", "color": "#3d5a80", "lw": 2.2, "zorder": 3},
    }
    for tag, day in day_tags.items():
        d = df[df["date"] == day]
        ax.plot(
            d["hour"],
            d["total_native_load_kw"],
            lw=load_styles[tag]["lw"],
            label=tr(load_styles[tag]["label"]),
            color=load_styles[tag]["color"],
            zorder=load_styles[tag]["zorder"],
        )
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel(tr("Hour of Day"))
    ax.set_ylabel(tr("Total Native Load (kW)"))
    ax.set_title(tr("Typical-Day Load Profiles (24 h Aligned)"), pad=10)
    style_axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=3)
    typical_load_fig = output_path(FIG_DIR, zh_fig_name("typical_day_load_comparison.png"))
    fig.savefig(typical_load_fig, dpi=300)
    plt.close(fig)

    # A2) typical day pv comparison
    fig, ax = plt.subplots(figsize=(13, 6), constrained_layout=True)
    pv_styles = {
        "normal_day": {"label": "Normal day", "color": "#9aa0a6", "lw": 1.7, "fill": 0.0, "zorder": 2},
        "low_irradiance_day": {"label": "Low-irradiance day", "color": "#9c6a2f", "lw": 2.7, "fill": 0.20, "zorder": 4},
        "import_limited_day": {"label": "Import-limited day", "color": "#6e7681", "lw": 2.0, "fill": 0.0, "zorder": 3},
    }
    for tag, day in day_tags.items():
        d = df[df["date"] == day]
        st = pv_styles[tag]
        ax.plot(d["hour"], d["pv_available_kw"], lw=st["lw"], label=tr(st["label"]), color=st["color"], zorder=st["zorder"])
        if st["fill"] > 0:
            ax.fill_between(d["hour"], d["pv_available_kw"], color=st["color"], alpha=st["fill"], zorder=1)
    ax.axvspan(11, 14, color="#f2dfc7", alpha=0.35)
    ax.text(11.15, ax.get_ylim()[1] * 0.94, tr("Storm-cloud window"), fontsize=9, color="#7b5a2e")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel(tr("Hour of Day"))
    ax.set_ylabel(tr("PV Available (kW)"))
    ax.set_title(tr("Typical-Day PV Profiles: Noon Support Loss on 2025-07-16"), pad=10)
    style_axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=3)
    typical_pv_fig = output_path(FIG_DIR, zh_fig_name("typical_day_pv_comparison.png"))
    fig.savefig(typical_pv_fig, dpi=300)
    plt.close(fig)

    # B) stress_event_2 and stress_event_3: main supply-pressure + EV-support
    for event_id, start, end, desc, pressure_type in events:
        if event_id not in {"stress_event_2", "stress_event_3"}:
            continue
        win = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].copy()
        if win.empty:
            continue
        win["margin_kw"] = (
            win["grid_import_limit_kw"] + win["pv_available_kw"] - win["total_native_load_kw"]
        )
        win["deficit_kw"] = (-win["margin_kw"]).clip(lower=0)

        summary = pd.DataFrame(
            {
                "event_id": [event_id],
                "start_time": [start],
                "end_time": [end],
                "pressure_type": [pressure_type],
                "margin_min_kw": [float(win["margin_kw"].min())],
                "margin_mean_kw": [float(win["margin_kw"].mean())],
                "deficit_max_kw": [float(win["deficit_kw"].max())],
                "deficit_duration_h": [float((win["deficit_kw"] > 0).sum() * 0.25)],
                "ev_online_mean": [float(win["online_count"].mean())],
                "ev_ch_max_mean_kw": [float(win["p_ev_ch_max_kw"].mean())],
                "ev_dis_max_mean_kw": [float(win["p_ev_dis_max_kw"].mean())],
            }
        )
        tbl = output_path(TABLE_DIR, f"{event_id}_summary.csv")
        summary.to_csv(tbl, index=False, encoding="utf-8-sig")
        event_table_paths.append(tbl)

        # Main: supply pressure figure
        fig, ax = plt.subplots(figsize=(13, 6), constrained_layout=True)
        x = win["timestamp"]
        ax.plot(x, win["total_native_load_kw"], lw=2.8, color=PALETTE["load"], label=tr("Load"), zorder=4)
        ax.plot(x, win["grid_import_limit_kw"], lw=2.2, color=PALETTE["grid"], label=tr("Grid limit"), zorder=3)
        ax.fill_between(x, win["pv_available_kw"], color=PALETTE["pv"], alpha=0.20, label=tr("PV"), zorder=2)
        ax.fill_between(
            x,
            win["total_native_load_kw"],
            win["grid_import_limit_kw"] + win["pv_available_kw"],
            where=(win["margin_kw"] < 0),
            color="#d00000",
            alpha=0.11,
            label=tr("Deficit zone"),
            zorder=1,
        )
        ax.axvspan(start, end, color="#dfe3e8", alpha=0.55, label=tr("Event window"), zorder=0)
        ax.text(
            x.iloc[0],
            ax.get_ylim()[1] * 0.95,
            tr("Stress window"),
            fontsize=9,
            color="#5b616a",
            va="top",
        )
        ax.set_ylabel(tr("Power (kW)"))
        ax.set_xlabel(tr("Time"))
        ax.set_title(f"{event_id.upper()} {tr('Supply Pressure: Margin Between Demand and Available Supply')}", pad=10)
        style_axes(ax)
        ax.tick_params(axis="x", rotation=20)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=4)
        p = output_path(FIG_DIR, zh_fig_name(f"{event_id}_supply_pressure.png"))
        fig.savefig(p, dpi=300)
        plt.close(fig)
        event_fig_paths.append(p)

        # Secondary: EV support figure
        fig, ax1 = plt.subplots(figsize=(13, 6), constrained_layout=True)
        ax1.plot(x, win["online_count"], lw=2.4, color=PALETTE["ev"], label=tr("EV Online Count"))
        ax1.fill_between(x, win["online_count"], color=PALETTE["ev"], alpha=0.12)
        ax1.set_ylabel(tr("EV Count"))
        ax1.set_xlabel(tr("Time"))
        ax1.axvspan(start, end, color="#adb5bd", alpha=0.13, label=tr("Event window"))
        style_axes(ax1)
        ax2 = ax1.twinx()
        ax2.plot(x, win["p_ev_ch_max_kw"], lw=2.0, color=PALETTE["grid"], label=tr("EV Max Charge Power"))
        ax2.plot(x, win["p_ev_dis_max_kw"], lw=2.0, color=PALETTE["pressure"], label=tr("EV Max Discharge Power"))
        ax2.set_ylabel(tr("Power Bound (kW)"))
        ax2.spines["top"].set_visible(False)
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2)
        ax1.set_title(f"{event_id.upper()} {tr('EV Support Potential: Online vs Power Bounds')}", pad=10)
        ax1.tick_params(axis="x", rotation=20)
        p = output_path(FIG_DIR, zh_fig_name(f"{event_id}_ev_support.png"))
        fig.savefig(p, dpi=300)
        plt.close(fig)
        event_fig_paths.append(p)

    # C) stress_event_1 dedicated PV-drop figure with normal-day comparison
    s1_start = pd.Timestamp("2025-07-16 11:00:00")
    s1_end = pd.Timestamp("2025-07-16 14:00:00")
    s1 = df[(df["timestamp"] >= s1_start) & (df["timestamp"] <= s1_end)].copy()
    normal = df[
        (df["timestamp"] >= pd.Timestamp("2025-07-15 11:00:00"))
        & (df["timestamp"] <= pd.Timestamp("2025-07-15 14:00:00"))
    ].copy()
    fig, ax1 = plt.subplots(figsize=(13, 6), constrained_layout=True)
    ax1.plot(s1["hour"], s1["solar_irradiance_wm2"], lw=2.6, color="#5d536b", label=tr("Irradiance (event day)"))
    ax1.plot(normal["hour"], normal["solar_irradiance_wm2"], lw=1.6, color="#a8adb4", linestyle="--", label=tr("Irradiance (normal day)"))
    ax1.set_xlabel(tr("Hour of Day"))
    ax1.set_ylabel(tr("Irradiance (W/m²)"))
    style_axes(ax1)
    ax2 = ax1.twinx()
    ax2.fill_between(s1["hour"], s1["pv_available_kw"], color=PALETTE["pv"], alpha=0.20, label=tr("PV (event day)"))
    ax2.plot(s1["hour"], s1["pv_available_kw"], lw=2.4, color=PALETTE["pv"])
    ax2.plot(normal["hour"], normal["pv_available_kw"], lw=1.6, color="#8c8c8c", linestyle="--", label=tr("PV (normal day)"))
    ax2.set_ylabel(tr("PV Available (kW)"))
    ax2.spines["top"].set_visible(False)
    ax1.axvspan(11, 14, color="#f2dfc7", alpha=0.30)
    ax1.text(11.15, ax1.get_ylim()[1] * 0.94, tr("Storm-cloud window"), fontsize=9, color="#7b5a2e")
    ax1.set_title(tr("Storm-Cloud Disturbance: Noon Irradiance and PV Support Drop"), pad=10)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=2)
    s1_fig = output_path(FIG_DIR, zh_fig_name("stress_event_1_pv_drop.png"))
    fig.savefig(s1_fig, dpi=300)
    plt.close(fig)
    event_fig_paths.append(s1_fig)

    s1_tbl = pd.DataFrame(
        {
            "event_id": ["stress_event_1"],
            "window": ["2025-07-16 11:00-14:00"],
            "pv_mean_event_kw": [float(s1["pv_available_kw"].mean())],
            "pv_mean_normal_kw": [float(normal["pv_available_kw"].mean())],
            "irr_mean_event_wm2": [float(s1["solar_irradiance_wm2"].mean())],
            "irr_mean_normal_wm2": [float(normal["solar_irradiance_wm2"].mean())],
            "pv_drop_ratio": [float(1 - s1["pv_available_kw"].mean() / normal["pv_available_kw"].mean())],
        }
    )
    s1_tbl_path = output_path(TABLE_DIR, "stress_event_1_summary.csv")
    s1_tbl.to_csv(s1_tbl_path, index=False, encoding="utf-8-sig")
    event_table_paths.append(s1_tbl_path)

    # report
    note_path = output_path(NOTE_DIR, "专题数据分析.md")
    lines = [
        "# 专题数据分析",
        "",
        "## 场景事件背景",
        "- 基于 `scenario_notes.csv` 的 3 个 stress events 进行事件窗口分析。",
        "- 压力指标定义：`pressure_index = total_native_load_kw - pv_available_kw - grid_import_limit_kw`。",
        "",
        "## 图解说明（重构为单图单问题）",
        "- `typical_day_load_comparison.png`：仅比较三类典型日的 24h 负荷曲线，服务于“负荷形态差异”段落，避免混入其他变量导致主结论分散。",
        "- `typical_day_pv_comparison.png`：仅比较三类典型日的 24h 光伏曲线，并高亮 07-16 11:00~14:00，服务于“低辐照导致中午支撑下滑”段落。",
        "- `stress_event_2_supply_pressure.png`：只呈现 Load、Grid Limit、PV，并用 margin<0 阴影标记供电缺口，服务于“进线受限下供需边界贴近”段落。",
        "- `stress_event_2_ev_support.png`：单独呈现 EV 在线规模与充放电边界，服务于“EV 是否具备事件响应潜力”段落。",
        "- `stress_event_3_supply_pressure.png`：对应晚高峰受限窗口，突出峰时供电余量收窄，服务于“峰时风险”段落。",
        "- `stress_event_3_ev_support.png`：对应晚高峰受限窗口下 EV 调节能力刻画，服务于“车网协同潜力”段落。",
        "- `stress_event_1_pv_drop.png`：比较事件日与正常日同窗辐照/PV，服务于“天气扰动削弱中午光伏支撑”段落。",
        "",
        "## 典型日对比分析",
        "- 选取正常日（2025-07-15）、低辐照日（2025-07-16）、进线受限日（2025-07-17）进行对比。",
        "- 对比维度包括负荷峰值/日电量、光伏峰值/日电量、进线限额最低值、电价均值、碳因子均值、日内压力峰值。",
        "",
        "## 建模启示",
        "- 低辐照事件下，PV 支撑下降，需提高储能与需求响应在午间的补偿能力。",
        "- 进线受限事件下，负荷与限额边界更易贴近，需提前做跨时段能量调配。",
        "- 晚高峰叠加受限时段中，EV 可用能力与负荷时段耦合更强，时段边界约束更关键。",
        "",
        "## 产物路径",
    ]
    lines.extend([f"- 事件图：`{p.as_posix()}`" for p in event_fig_paths])
    lines.extend([f"- 事件表：`{p.as_posix()}`" for p in event_table_paths])
    lines.append(f"- 典型日负荷图：`{typical_load_fig.as_posix()}`")
    lines.append(f"- 典型日光伏图：`{typical_pv_fig.as_posix()}`")
    lines.append(f"- 典型日对比表：`{typical_path.as_posix()}`")
    lines.append("")
    note_path.write_text("\n".join(lines), encoding="utf-8")

    print("Scenario analysis done.")
    for p in event_fig_paths:
        print(f"FIG: {p.as_posix()}")
    for p in event_table_paths:
        print(f"TBL: {p.as_posix()}")
    print(f"FIG: {typical_load_fig.as_posix()}")
    print(f"FIG: {typical_pv_fig.as_posix()}")
    print(f"TBL: {typical_path.as_posix()}")
    print(f"NOTE: {note_path.as_posix()}")


if __name__ == "__main__":
    main()
