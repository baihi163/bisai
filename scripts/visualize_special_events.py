# -*- coding: utf-8 -*-
"""基准周三个特殊事件：可视化与汇总（timeseries_15min + scenario_notes）。"""

from pathlib import Path
from typing import Optional, Set

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "results" / "special_events"
OUT.mkdir(parents=True, exist_ok=True)

TS_PATH = RAW / "timeseries_15min.csv"
SCENARIO_PATH = RAW / "scenario_notes.csv"

DPI = 300

EVENTS = [
    {
        "event_id": 1,
        "event_name": "Low irradiance (storm clouds)",
        "label": "Event 1: Low irradiance",
        "start": pd.Timestamp("2025-07-16 11:00:00"),
        "end": pd.Timestamp("2025-07-16 14:00:00"),
        "primary_var": "solar_irradiance_wm2",
        "secondary_var": "pv_available_kw",
        "shade_color": "#4C72B0",
        "stress_type": "供给侧波动",
    },
    {
        "event_id": 2,
        "event_name": "Midday grid import cap (650 kW)",
        "label": "Event 2: Midday grid constraint",
        "start": pd.Timestamp("2025-07-17 13:00:00"),
        "end": pd.Timestamp("2025-07-17 16:00:00"),
        "primary_var": "grid_import_limit_kw",
        "secondary_var": "total_native_load_kw",
        "shade_color": "#DD8452",
        "stress_type": "外部电网约束",
    },
    {
        "event_id": 3,
        "event_name": "Evening peak grid import cap (700 kW)",
        "label": "Event 3: Evening peak grid constraint",
        "start": pd.Timestamp("2025-07-18 17:00:00"),
        "end": pd.Timestamp("2025-07-18 19:00:00"),
        "primary_var": "grid_import_limit_kw",
        "secondary_var": "total_native_load_kw",
        "shade_color": "#55A868",
        "stress_type": "晚高峰复合压力",
    },
]


def load_timeseries() -> pd.DataFrame:
    df = pd.read_csv(TS_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["net_load_kw"] = df["total_native_load_kw"] - df["pv_available_kw"]
    return df


def weekly_means(df: pd.DataFrame) -> dict:
    return {
        "weekly_mean_load_kw": df["total_native_load_kw"].mean(),
        "weekly_mean_pv_kw": df["pv_available_kw"].mean(),
        "weekly_mean_grid_limit_kw": df["grid_import_limit_kw"].mean(),
        "weekly_mean_irradiance_wm2": df["solar_irradiance_wm2"].mean(),
        "weekly_mean_net_load_kw": df["net_load_kw"].mean(),
    }


def event_mask(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return (df["timestamp"] >= start) & (df["timestamp"] < end)


def mask_same_clock_window(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    exclude_dates: Optional[Set[pd.Timestamp]] = None,
) -> pd.Series:
    """与事件同「日内钟点区间」的所有时段（可排除指定日历日）。"""
    sh, sm = start.hour, start.minute
    eh, em = end.hour, end.minute
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    mins = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    m = (mins >= start_min) & (mins < end_min)
    if exclude_dates:
        dnorm = df["timestamp"].dt.normalize()
        for d in exclude_dates:
            m = m & (dnorm != pd.Timestamp(d).normalize())
    return m


def pct_change(event_val: float, weekly_val: float) -> float:
    if weekly_val == 0 or (weekly_val != weekly_val):
        return float("nan")
    return (event_val - weekly_val) / weekly_val * 100.0


def build_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    wm = weekly_means(df)
    rows = []
    for ev in EVENTS:
        m = event_mask(df, ev["start"], ev["end"])
        sub = df.loc[m]
        dur_h = (ev["end"] - ev["start"]).total_seconds() / 3600.0

        prim = ev["primary_var"]
        sec = ev["secondary_var"]
        e_load = sub["total_native_load_kw"].mean()
        e_peak = sub["total_native_load_kw"].max()
        e_pv_mean = sub["pv_available_kw"].mean()
        e_pv_min = sub["pv_available_kw"].min()
        e_grid = sub["grid_import_limit_kw"].mean()
        e_net = sub["net_load_kw"].mean()

        if ev["event_id"] == 1:
            e_prim = sub[prim].mean()
            ref_m = mask_same_clock_window(df, ev["start"], ev["end"], exclude_dates={ev["start"].normalize()})
            ref_irr = df.loc[ref_m, "solar_irradiance_wm2"].mean()
            ref_pv = df.loc[ref_m, "pv_available_kw"].mean()
            rel_parts = [
                f"{prim}: {pct_change(e_prim, ref_irr):.1f}% (vs 11:00–14:00 on other days)",
                f"{sec}: {pct_change(e_pv_mean, ref_pv):.1f}% (vs same window)",
            ]
            interp = (
                "暴雨云导致该午间窗口内辐照度与光伏可用出力相对同周其他日同一时段明显偏低，"
                "净负荷抬升，放大对购电/储能的依赖。"
            )
        elif ev["event_id"] == 2:
            e_prim = sub[prim].mean()
            rel_parts = [
                f"{prim}: {pct_change(e_prim, wm['weekly_mean_grid_limit_kw']):.1f}%",
            ]
            interp = (
                "午间时段电网购电上限降至650 kW，在负荷与光伏叠加下更易出现购电越限或需依赖储能/削减。"
            )
        else:
            e_prim = sub[prim].mean()
            rel_parts = [
                f"{prim}: {pct_change(e_prim, wm['weekly_mean_grid_limit_kw']):.1f}%",
            ]
            interp = (
                "晚高峰时段购电上限收紧至700 kW，与负荷上升叠加，形成“负荷高+外网紧”的复合压力。"
            )

        rows.append(
            {
                "event_id": ev["event_id"],
                "event_name": ev["event_name"],
                "start_time": ev["start"].isoformat(sep=" "),
                "end_time": ev["end"].isoformat(sep=" "),
                "duration_hours": round(dur_h, 4),
                "affected_variable_primary": prim,
                "affected_variable_secondary": sec,
                "event_period_mean_load_kw": round(e_load, 4),
                "event_period_peak_load_kw": round(float(e_peak), 4),
                "event_period_mean_pv_kw": round(e_pv_mean, 4),
                "event_period_min_pv_kw": round(float(e_pv_min), 4),
                "event_period_mean_grid_limit_kw": round(e_grid, 4),
                "weekly_mean_load_kw": round(wm["weekly_mean_load_kw"], 4),
                "weekly_mean_pv_kw": round(wm["weekly_mean_pv_kw"], 4),
                "weekly_mean_grid_limit_kw": round(wm["weekly_mean_grid_limit_kw"], 4),
                "event_period_mean_net_load_kw": round(e_net, 4),
                "weekly_mean_net_load_kw": round(wm["weekly_mean_net_load_kw"], 4),
                "relative_change_vs_weekly_mean": "; ".join(rel_parts),
                "interpretation": interp,
            }
        )
    return pd.DataFrame(rows)


def plot_overview(df: pd.DataFrame) -> None:
    fig, ax_left = plt.subplots(figsize=(14, 5.5), dpi=DPI)
    ax_right = ax_left.twinx()

    ts = df["timestamp"]
    (l1,) = ax_left.plot(ts, df["total_native_load_kw"], color="#1f77b4", lw=1.2, label="total_native_load_kw")
    (l2,) = ax_left.plot(ts, df["pv_available_kw"], color="#ff7f0e", lw=1.2, label="pv_available_kw")
    (l3,) = ax_right.plot(ts, df["grid_import_limit_kw"], color="#2ca02c", lw=1.2, ls="-", label="grid_import_limit_kw")

    for ev in EVENTS:
        ax_left.axvspan(
            ev["start"],
            ev["end"],
            color=ev["shade_color"],
            alpha=0.22,
            zorder=0,
        )
        y_text = ax_left.get_ylim()[1] * (0.92 - 0.08 * (ev["event_id"] - 1))
        ax_left.text(
            ev["start"] + (ev["end"] - ev["start"]) / 2,
            y_text,
            ev["label"],
            ha="center",
            va="top",
            fontsize=9,
            fontweight="bold",
            color="#333333",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="0.7", alpha=0.9),
        )

    ax_left.set_xlabel("Time", fontsize=11)
    ax_left.set_ylabel("Power (kW)", fontsize=11, color="#333333")
    ax_right.set_ylabel("Grid import limit (kW)", fontsize=11, color="#2ca02c")
    ax_left.tick_params(axis="y", labelcolor="#333333")
    ax_right.tick_params(axis="y", labelcolor="#2ca02c")
    ax_left.set_title(
        "Base week overview: native load, PV availability, and grid import limit\n"
        "(three benchmark stress windows shaded)",
        fontsize=12,
    )
    ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax_left.xaxis.set_major_locator(mdates.DayLocator())
    ax_left.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    fig.autofmt_xdate()

    lines = [l1, l2, l3]
    labels = [l.get_label() for l in lines]
    ax_left.legend(lines, labels, loc="upper left", framealpha=0.95)

    fig.tight_layout()
    fig.savefig(OUT / "special_events_overview.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_zoom_panels(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), dpi=DPI, sharey=False)
    extend = pd.Timedelta(hours=2)

    for ax, ev in zip(axes, EVENTS):
        w_start = ev["start"] - extend
        w_end = ev["end"] + extend
        sub = df[(df["timestamp"] >= w_start) & (df["timestamp"] <= w_end)].copy()
        if sub.empty:
            continue
        ax_t = ax.twinx()
        ax.plot(sub["timestamp"], sub["total_native_load_kw"], color="#1f77b4", lw=1.3, label="total_native_load_kw")
        ax.plot(sub["timestamp"], sub["pv_available_kw"], color="#ff7f0e", lw=1.3, label="pv_available_kw")
        ax_t.plot(sub["timestamp"], sub["grid_import_limit_kw"], color="#2ca02c", lw=1.3, ls="-", label="grid_import_limit_kw")
        ax.axvspan(ev["start"], ev["end"], color=ev["shade_color"], alpha=0.25, zorder=0)
        ax.set_ylabel("Load / PV (kW)", fontsize=10)
        ax_t.set_ylabel("Grid limit (kW)", fontsize=10, color="#2ca02c")
        ax_t.tick_params(axis="y", labelcolor="#2ca02c")
        ax.set_title(ev["label"], fontsize=11, fontweight="bold")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%m-%d"))
        ax.legend(loc="upper left", fontsize=8)
        h_t, l_t = ax_t.get_legend_handles_labels()
        if h_t:
            ax_t.legend(h_t, l_t, loc="upper right", fontsize=8)

    axes[-1].set_xlabel("Time", fontsize=11)
    fig.suptitle("Zoomed views (±2 h around each event)", fontsize=12, y=1.01)
    fig.tight_layout()
    fig.savefig(OUT / "special_events_zoomed_panels.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def dataframe_to_markdown_table(df: pd.DataFrame) -> str:
    """不依赖 tabulate，与 pandas to_markdown 等价的 GitHub 风格表。"""
    cols = [str(c) for c in df.columns]
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    head = "| " + " | ".join(c.replace("|", "\\|") for c in cols) + " |"
    body_rows = []
    for _, row in df.iterrows():
        cells = []
        for c in df.columns:
            v = row[c]
            s = "" if pd.isna(v) else str(v)
            cells.append(s.replace("|", "\\|").replace("\n", " "))
        body_rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep] + body_rows)


def summary_to_markdown(sdf: pd.DataFrame) -> str:
    lines = [
        "# 特殊事件汇总（special_events_summary）",
        "",
        "数据来源：`data/raw/timeseries_15min.csv`，事件定义见 `data/raw/scenario_notes.csv`。",
        "",
        dataframe_to_markdown_table(sdf),
        "",
    ]
    return "\n".join(lines)


def write_notes_md() -> None:
    scenario = pd.read_csv(SCENARIO_PATH)
    snip = scenario[scenario["item"].str.startswith("stress_event_")].to_string(index=False)
    text = f"""# 基准周特殊事件说明（special_events_notes）

## 1. 来源

以下条目摘自 `data/raw/scenario_notes.csv`：

```
{snip}
```

## 2. 物理含义

| 事件 | 含义 |
|------|------|
| Event 1 | 2025-07-16 11:00–14:00 强对流天气云系导致**太阳辐照度下降**，进而压低**光伏可用出力**。 |
| Event 2 | 2025-07-17 13:00–16:00 **午间购电功率上限**在数据中降至 **650 kW**（外网或合约约束的体现）。 |
| Event 3 | 2025-07-18 17:00–19:00 **晚高峰**时段购电上限降至 **700 kW**，与典型负荷抬升时段重叠。 |

## 3. 系统压力类型归类

| 事件 | 压力类型 |
|------|----------|
| Event 1 | **供给侧波动**（可再生出力不确定性/天气冲击） |
| Event 2 | **外部电网约束**（并网购电能力受限） |
| Event 3 | **晚高峰复合压力**（负荷侧偏高 + 外网约束叠加） |

## 4. 与问题1建模的关系

三个事件分别覆盖了**光伏波动**、**午间净负荷与购电上限冲突**、**晚高峰净负荷与购电上限冲突**等典型可行域收紧情形，可直接用于：

- 校验调度模型在**约束绑定**时是否可行、是否需要削减/储能/V2B 等柔性资源；
- 作为**代表性场景**讨论成本、碳排与可靠性权衡；
- 与全周平均工况对比，突出**极端但合理**的运行压力，适合写入论文案例与图表解读。

## 5. 汇总表中相对变化口径

- **Event 1**：`solar_irradiance_wm2` 与 `pv_available_kw` 的相对变化以**同周其他日、相同 11:00–14:00 钟点窗口**的均值为参照（避免全周 24h 均值被夜间零辐照稀释，导致符号误导）。
- **Event 2、3**：`grid_import_limit_kw` 相对变化仍以**全周 15 min 序列均值**为参照。

---
*由 `scripts/visualize_special_events.py` 自动生成说明骨架；数值结果见同目录 `special_events_summary.csv`。*
"""
    (OUT / "special_events_notes.md").write_text(text, encoding="utf-8")


def main() -> None:
    df = load_timeseries()
    sdf = build_summary_rows(df)
    sdf.to_csv(OUT / "special_events_summary.csv", index=False, encoding="utf-8-sig")

    (OUT / "special_events_summary.md").write_text(summary_to_markdown(sdf), encoding="utf-8")

    plt.rcParams["font.family"] = ["DejaVu Sans", "Arial", "sans-serif"]
    plot_overview(df)
    plot_zoom_panels(df)
    write_notes_md()


if __name__ == "__main__":
    main()
