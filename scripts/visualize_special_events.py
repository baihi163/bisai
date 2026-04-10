# -*- coding: utf-8 -*-
"""基准周三个特殊事件：可视化与汇总（timeseries_15min + scenario_notes）。"""

from pathlib import Path
from typing import Optional, Set

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.transforms import blended_transform_factory

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "results" / "special_events"
OUT.mkdir(parents=True, exist_ok=True)

TS_PATH = RAW / "timeseries_15min.csv"
SCENARIO_PATH = RAW / "scenario_notes.csv"

DPI = 300

# 图例用中文（与曲线物理量对应）
LEGEND_LOAD = "园区原生总负荷 (kW)"
LEGEND_PV = "光伏可用功率 (kW)"
LEGEND_GRID = "电网购电功率上限 (kW)"

EVENTS = [
    {
        "event_id": 1,
        "event_name": "低辐照（暴雨云）",
        "label": "事件1：低辐照（暴雨云）",
        "start": pd.Timestamp("2025-07-16 11:00:00"),
        "end": pd.Timestamp("2025-07-16 14:00:00"),
        "primary_var": "solar_irradiance_wm2",
        "secondary_var": "pv_available_kw",
        "shade_color": "#4C72B0",
        "stress_type": "供给侧波动",
    },
    {
        "event_id": 2,
        "event_name": "午间购电上限收紧（650 kW）",
        "label": "事件2：午间电网约束",
        "start": pd.Timestamp("2025-07-17 13:00:00"),
        "end": pd.Timestamp("2025-07-17 16:00:00"),
        "primary_var": "grid_import_limit_kw",
        "secondary_var": "total_native_load_kw",
        "shade_color": "#DD8452",
        "stress_type": "外部电网约束",
    },
    {
        "event_id": 3,
        "event_name": "晚高峰购电上限收紧（700 kW）",
        "label": "事件3：晚高峰电网约束",
        "start": pd.Timestamp("2025-07-18 17:00:00"),
        "end": pd.Timestamp("2025-07-18 19:00:00"),
        "primary_var": "grid_import_limit_kw",
        "secondary_var": "total_native_load_kw",
        "shade_color": "#55A868",
        "stress_type": "晚高峰复合压力",
    },
]


def setup_chinese_matplotlib() -> None:
    """数模/中文环境：优先使用系统常见中文字体，避免缺字方块。"""
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "KaiTi",
        "FangSong",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


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


VARIABLE_LABEL_ZH = {
    "solar_irradiance_wm2": "太阳辐照度(W/m²)",
    "pv_available_kw": "光伏可用功率(kW)",
    "grid_import_limit_kw": "电网购电功率上限(kW)",
    "total_native_load_kw": "园区原生总负荷(kW)",
}


SUMMARY_COLUMNS_ZH = {
    "event_id": "事件编号",
    "event_name": "事件名称",
    "start_time": "开始时刻",
    "end_time": "结束时刻",
    "duration_hours": "持续时长_h",
    "affected_variable_primary": "主要影响变量",
    "affected_variable_secondary": "次要影响变量",
    "event_period_mean_load_kw": "事件期平均负荷_kW",
    "event_period_peak_load_kw": "事件期峰值负荷_kW",
    "event_period_mean_pv_kw": "事件期平均光伏_kW",
    "event_period_min_pv_kw": "事件期最小光伏_kW",
    "event_period_mean_grid_limit_kw": "事件期平均购电上限_kW",
    "weekly_mean_load_kw": "全周平均负荷_kW",
    "weekly_mean_pv_kw": "全周平均光伏_kW",
    "weekly_mean_grid_limit_kw": "全周平均购电上限_kW",
    "event_period_mean_net_load_kw": "事件期平均净负荷_kW",
    "weekly_mean_net_load_kw": "全周平均净负荷_kW",
    "relative_change_vs_weekly_mean": "相对全周或对照窗口的变化",
    "interpretation": "简要解释",
}


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
                f"{VARIABLE_LABEL_ZH.get(prim, prim)}：{pct_change(e_prim, ref_irr):.1f}%（相对同周其他日 11:00–14:00 均值）",
                f"{VARIABLE_LABEL_ZH.get(sec, sec)}：{pct_change(e_pv_mean, ref_pv):.1f}%（同时段对照）",
            ]
            interp = (
                "暴雨云导致该午间窗口内辐照度与光伏可用出力相对同周其他日同一时段明显偏低，"
                "净负荷抬升，放大对购电/储能的依赖。"
            )
        elif ev["event_id"] == 2:
            e_prim = sub[prim].mean()
            rel_parts = [
                f"{VARIABLE_LABEL_ZH.get(prim, prim)}：{pct_change(e_prim, wm['weekly_mean_grid_limit_kw']):.1f}%（相对全周均值）",
            ]
            interp = (
                "午间时段电网购电上限降至650 kW，在负荷与光伏叠加下更易出现购电越限或需依赖储能/削减。"
            )
        else:
            e_prim = sub[prim].mean()
            rel_parts = [
                f"{VARIABLE_LABEL_ZH.get(prim, prim)}：{pct_change(e_prim, wm['weekly_mean_grid_limit_kw']):.1f}%（相对全周均值）",
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
                "affected_variable_primary": VARIABLE_LABEL_ZH.get(prim, prim),
                "affected_variable_secondary": VARIABLE_LABEL_ZH.get(sec, sec),
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


def _event_time_range_str(ev: dict) -> str:
    s = ev["start"].strftime("%m月%d日 %H:%M")
    e = ev["end"].strftime("%H:%M")
    return f"{s}—{e}"


def plot_overview(df: pd.DataFrame) -> None:
    fig, ax_left = plt.subplots(figsize=(14, 6.0), dpi=DPI)
    ax_right = ax_left.twinx()

    ts = df["timestamp"]
    (l1,) = ax_left.plot(ts, df["total_native_load_kw"], color="#1f77b4", lw=1.2, label=LEGEND_LOAD)
    (l2,) = ax_left.plot(ts, df["pv_available_kw"], color="#ff7f0e", lw=1.2, label=LEGEND_PV)
    (l3,) = ax_right.plot(ts, df["grid_import_limit_kw"], color="#2ca02c", lw=1.2, ls="-", label=LEGEND_GRID)

    for ev in EVENTS:
        ax_left.axvspan(
            ev["start"],
            ev["end"],
            color=ev["shade_color"],
            alpha=0.22,
            zorder=0,
        )

    ax_left.set_xlabel("时间", fontsize=11, labelpad=36)
    ax_left.set_ylabel("功率 (kW)", fontsize=11, color="#333333")
    ax_right.set_ylabel("购电功率上限 (kW)", fontsize=11, color="#2ca02c")
    ax_left.tick_params(axis="y", labelcolor="#333333")
    ax_right.tick_params(axis="y", labelcolor="#2ca02c")
    ax_left.set_title(
        "基准周总览：园区原生负荷、光伏可用出力与电网购电上限\n（阴影为三个典型压力时段）",
        fontsize=12,
    )
    ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    ax_left.xaxis.set_major_locator(mdates.DayLocator())
    ax_left.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    plt.setp(ax_left.get_xticklabels(), rotation=12, ha="right")

    # 事件说明贴在时间轴下方（数据坐标 x + 轴坐标 y），不进入主绘图区
    trans = blended_transform_factory(ax_left.transData, ax_left.transAxes)
    for ev in EVENTS:
        mid = ev["start"] + (ev["end"] - ev["start"]) / 2
        caption = f"{ev['label']}\n{_event_time_range_str(ev)}"
        ax_left.text(
            mid,
            -0.20,
            caption,
            transform=trans,
            ha="center",
            va="top",
            fontsize=8,
            color=ev["shade_color"],
            fontweight="bold",
            clip_on=False,
        )

    lines = [l1, l2, l3]
    labels = [l.get_label() for l in lines]
    fig.legend(
        lines,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=3,
        frameon=True,
        fontsize=9,
        framealpha=0.95,
    )

    fig.subplots_adjust(bottom=0.30, top=0.88, left=0.08, right=0.92)
    fig.savefig(
        OUT / "special_events_overview.png",
        dpi=DPI,
        bbox_inches="tight",
        pad_inches=0.45,
    )
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
        ax.plot(sub["timestamp"], sub["total_native_load_kw"], color="#1f77b4", lw=1.3, label=LEGEND_LOAD)
        ax.plot(sub["timestamp"], sub["pv_available_kw"], color="#ff7f0e", lw=1.3, label=LEGEND_PV)
        ax_t.plot(sub["timestamp"], sub["grid_import_limit_kw"], color="#2ca02c", lw=1.3, ls="-", label=LEGEND_GRID)
        ax.axvspan(ev["start"], ev["end"], color=ev["shade_color"], alpha=0.25, zorder=0)
        ax.set_ylabel("负荷 / 光伏 (kW)", fontsize=10)
        ax_t.set_ylabel("购电上限 (kW)", fontsize=10, color="#2ca02c")
        ax_t.tick_params(axis="y", labelcolor="#2ca02c")
        ax.set_title(ev["label"], fontsize=11, fontweight="bold")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%m-%d"))
        ax.legend(loc="upper left", fontsize=8)
        h_t, l_t = ax_t.get_legend_handles_labels()
        if h_t:
            ax_t.legend(h_t, l_t, loc="upper right", fontsize=8)

    axes[-1].set_xlabel("时间", fontsize=11)
    fig.suptitle("分事件局部放大（各窗口为事件前后各扩展 2 小时）", fontsize=12, y=1.01)
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
    sdf_zh = sdf.rename(columns=SUMMARY_COLUMNS_ZH)
    lines = [
        "# 特殊事件汇总（special_events_summary）",
        "",
        "数据来源：`data/raw/timeseries_15min.csv`，事件定义见 `data/raw/scenario_notes.csv`。",
        "",
        dataframe_to_markdown_table(sdf_zh),
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
| 事件1 | 2025-07-16 11:00–14:00 强对流天气云系导致**太阳辐照度下降**，进而压低**光伏可用出力**。 |
| 事件2 | 2025-07-17 13:00–16:00 **午间购电功率上限**在数据中降至 **650 kW**（外网或合约约束的体现）。 |
| 事件3 | 2025-07-18 17:00–19:00 **晚高峰**时段购电上限降至 **700 kW**，与典型负荷抬升时段重叠。 |

## 3. 系统压力类型归类

| 事件 | 压力类型 |
|------|----------|
| 事件1 | **供给侧波动**（可再生出力不确定性/天气冲击） |
| 事件2 | **外部电网约束**（并网购电能力受限） |
| 事件3 | **晚高峰复合压力**（负荷侧偏高 + 外网约束叠加） |

## 4. 与问题1建模的关系

三个事件分别覆盖了**光伏波动**、**午间净负荷与购电上限冲突**、**晚高峰净负荷与购电上限冲突**等典型可行域收紧情形，可直接用于：

- 校验调度模型在**约束绑定**时是否可行、是否需要削减/储能/V2B 等柔性资源；
- 作为**代表性场景**讨论成本、碳排与可靠性权衡；
- 与全周平均工况对比，突出**极端但合理**的运行压力，适合写入论文案例与图表解读。

## 5. 汇总表中相对变化口径

- **事件1**：`solar_irradiance_wm2` 与 `pv_available_kw` 的相对变化以**同周其他日、相同 11:00–14:00 钟点窗口**的均值为参照（避免全周 24h 均值被夜间零辐照稀释，导致符号误导）。
- **事件2、3**：`grid_import_limit_kw` 相对变化仍以**全周 15 min 序列均值**为参照。

---
*由 `scripts/visualize_special_events.py` 自动生成说明骨架；数值结果见同目录 `special_events_summary.csv`。*
"""
    (OUT / "special_events_notes.md").write_text(text, encoding="utf-8")


def main() -> None:
    df = load_timeseries()
    sdf = build_summary_rows(df)
    sdf.rename(columns=SUMMARY_COLUMNS_ZH).to_csv(
        OUT / "special_events_summary.csv", index=False, encoding="utf-8-sig"
    )

    (OUT / "special_events_summary.md").write_text(summary_to_markdown(sdf), encoding="utf-8")

    setup_chinese_matplotlib()
    plot_overview(df)
    plot_zoom_panels(df)
    write_notes_md()


if __name__ == "__main__":
    main()
