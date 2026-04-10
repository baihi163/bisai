# -*- coding: utf-8 -*-
"""
从已有 baseline 仿真结果导出 KPI 表、策略说明、MATLAB 作图数据与预览图。
不修改仿真逻辑，仅读取 results/problem1_baseline/ 下文件。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "results" / "problem1_baseline"
FIG = BASE / "figures"

KPI_DEFS: list[tuple[str, str, str, str]] = [
    ("total_grid_import_kwh", "电网总购电量", "kWh", "全周从电网购入的有功电量累计。"),
    ("total_grid_export_kwh", "电网总售电量", "kWh", "全周向电网送出的有功电量累计。"),
    ("total_pv_curtailed_kwh", "光伏总弃电量", "kWh", "全周弃光能量累计。"),
    ("total_cost_cny", "总运行费用", "元", "购电支出减售电收入（按时段电价折算）。"),
    ("pv_utilization_rate", "光伏利用率", "—", "1 − 弃光电量/可发电量；无量纲，范围约 [0,1]。"),
    ("ev_demand_met_rate", "EV 离站需求满足率", "—", "离站时能量达标的车辆占比；无量纲。"),
    ("peak_grid_import_kw", "峰值购电功率", "kW", "单时段最大购电功率。"),
    ("total_unmet_load_kwh", "未供能缺电量", "kWh", "购电达上限后仍不足的功率缺口折算电量。"),
    ("ess_total_charge_throughput_kwh", "储能总充电量", "kWh", "储能交流侧充电能量累计。"),
    ("ess_total_discharge_throughput_kwh", "储能总放电量", "kWh", "储能交流侧放电能量累计。"),
    ("total_ev_charge_kwh", "EV 总充电量（交流侧）", "kWh", "∑ ev_total_charge_kw×Δt。"),
    ("total_pv_used_locally_kwh", "光伏本地消纳电量", "kWh", "∑ pv_used_locally_kw×Δt。"),
    ("total_pv_to_ess_kwh", "光伏入储电量", "kWh", "∑ pv_to_ess_kw×Δt。"),
    ("total_sell_revenue_cny", "总售电收入", "元", "∑ grid_export_kw×sell_price×Δt。"),
    ("average_grid_import_kw", "平均购电功率", "kW", "全时段 grid_import_kw 算术平均。"),
    ("ess_min_energy_kwh", "储能能量最小值", "kWh", "ess_energy_kwh 全周最小。"),
    ("ess_max_energy_kwh", "储能能量最大值", "kWh", "ess_energy_kwh 全周最大。"),
    ("ev_average_completion_ratio", "EV 平均能量完成比", "—", "各车离站 energy_completion_ratio 均值（有效值）。"),
    ("unmet_load_slots_count", "未供能时段数", "—", "unmet_load_kw>0 的时段个数。"),
]


def setup_plot_font() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def load_sources() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    ts = pd.read_csv(BASE / "baseline_timeseries_results.csv")
    ev = pd.read_csv(BASE / "baseline_ev_session_summary.csv")
    kpi = json.loads((BASE / "baseline_kpi_summary.json").read_text(encoding="utf-8"))
    return ts, ev, kpi


def write_kpi_tables(kpi: dict) -> None:
    rows = []
    for key, name, unit, desc in KPI_DEFS:
        val = kpi.get(key, "")
        if val is None:
            val = ""
        rows.append(
            {
                "metric_key": key,
                "metric_name": name,
                "value": val,
                "unit": unit,
                "description": desc,
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(BASE / "baseline_kpi_table.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# Baseline KPI 汇总表",
        "",
        "| 指标键名 | 指标名称 | 数值 | 单位 | 含义说明 |",
        "|----------|----------|------|------|----------|",
    ]
    for _, r in df.iterrows():
        v = r["value"]
        if isinstance(v, float):
            v = f"{v:.6g}"
        lines.append(
            f"| `{r['metric_key']}` | {r['metric_name']} | {v} | {r['unit']} | {r['description']} |"
        )
    lines.append("")
    (BASE / "baseline_kpi_table.md").write_text("\n".join(lines), encoding="utf-8")


def write_strategy_table() -> None:
    text = """# Baseline 非协同策略说明表

本文档与 `run_baseline_noncooperative.py` 实现一致，供与协同优化模型对照。

| 模块 | 策略摘要 |
|------|----------|
| **建筑负荷** | 仅使用输入 `total_native_load_kw`；柔性负荷不参与调节，调节量为 0。 |
| **EV** | 到站即充：连接时段内若电量未达离站目标，按交流侧最大允许充电功率（受目标与容量及固定充电效率 η_ev 约束）充电；不向园区放电（V2B）。 |
| **储能** | 剩余光伏优先充储能；购电价处于全周**高价区间**（不低于 **0.8 分位数**，约最贵 20% 时段）且存在功率缺口时放电以降低购电；其余静置；不从电网充电。 |
| **光伏** | 优先供本地（负荷+EV）；剩余用于储能充电；再剩余按上网功率上限售电；超出部分弃光。 |
| **电网** | 缺口由购电补足，受进口功率上限约束；不足部分记 `unmet_load_kw`，仿真不中断。 |

## 备注

- 「高价区间」判定：购电价不低于全周购电价样本的 **0.8 分位数**；规则型、非优化。
- 时间步长：15 min（0.25 h）。

---
*由 `code/python/baseline/export_baseline_reports.py` 生成*
"""
    (BASE / "baseline_strategy_table.md").write_text(text, encoding="utf-8")


def write_plot_data(ts: pd.DataFrame) -> None:
    cols = [
        "timestamp",
        "native_load_kw",
        "ev_total_charge_kw",
        "total_load_with_ev_kw",
        "pv_available_kw",
        "pv_used_locally_kw",
        "ess_charge_kw",
        "ess_discharge_kw",
        "ess_energy_kwh",
        "grid_import_kw",
        "grid_export_kw",
        "buy_price",
        "sell_price",
        "unmet_load_kw",
        "net_load_before_ess_kw",
        "net_load_after_ess_kw",
        "residual_demand_after_pv_kw",
        "residual_demand_after_ess_kw",
    ]
    missing = [c for c in cols if c not in ts.columns]
    if missing:
        raise ValueError(f"时序结果缺列: {missing}")
    ts[cols].to_csv(BASE / "baseline_plot_data.csv", index=False, encoding="utf-8-sig")


def plot_previews(ts: pd.DataFrame, ev: pd.DataFrame) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    ts = ts.copy()
    ts["t"] = pd.to_datetime(ts["timestamp"])

    # (1) overview
    fig, ax1 = plt.subplots(figsize=(12, 4), dpi=120)
    ax2 = ax1.twinx()
    ax1.plot(ts["t"], ts["native_load_kw"], label="原生负荷 (kW)", color="#1f77b4", lw=1.0)
    ax1.plot(ts["t"], ts["ev_total_charge_kw"], label="EV 总充电 (kW)", color="#ff7f0e", lw=1.0)
    ax1.plot(ts["t"], ts["pv_available_kw"], label="光伏可用 (kW)", color="#2ca02c", lw=1.0)
    ax2.plot(ts["t"], ts["grid_import_kw"], label="购电功率 (kW)", color="#d62728", lw=1.0, ls="-")
    ax1.set_ylabel("kW")
    ax2.set_ylabel("购电 (kW)", color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    ax1.set_title("Baseline 预览：负荷 / EV 充电 / 光伏 / 购电")
    ax1.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "baseline_overview_preview.png", bbox_inches="tight")
    plt.close(fig)

    # (2) ESS
    fig, ax1 = plt.subplots(figsize=(12, 4), dpi=120)
    ax2 = ax1.twinx()
    ax1.plot(ts["t"], ts["ess_energy_kwh"], color="#9467bd", lw=1.2, label="储能能量 (kWh)")
    ax1.set_ylabel("能量 (kWh)")
    ax2.plot(ts["t"], ts["ess_charge_kw"], color="#2ca02c", lw=0.9, alpha=0.8, label="充电功率 (kW)")
    ax2.plot(ts["t"], ts["ess_discharge_kw"], color="#bcbd22", lw=0.9, alpha=0.8, label="放电功率 (kW)")
    ax2.set_ylabel("功率 (kW)")
    ax1.set_title("Baseline 预览：储能状态与充放电功率")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "baseline_ess_preview.png", bbox_inches="tight")
    plt.close(fig)

    # (3) price vs grid import
    fig, ax1 = plt.subplots(figsize=(12, 4), dpi=120)
    ax2 = ax1.twinx()
    ax1.plot(ts["t"], ts["grid_import_kw"], color="#1f77b4", lw=1.0, label="购电功率 (kW)")
    ax1.set_ylabel("购电功率 (kW)")
    ax2.plot(ts["t"], ts["buy_price"], color="#ff7f0e", lw=1.0, label="购电电价 (元/kWh)")
    ax2.set_ylabel("电价 (元/kWh)")
    ax1.set_title("Baseline 预览：购电功率与购电电价")
    ax1.legend(loc="upper left", fontsize=8)
    ax2.legend(loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIG / "baseline_price_grid_preview.png", bbox_inches="tight")
    plt.close(fig)

    # (4) EV summary
    met = int(ev["demand_met_flag"].sum())
    nmet = int((~ev["demand_met_flag"]).sum())
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=120)
    axes[0].bar(["满足", "未满足"], [met, nmet], color=["#2ca02c", "#d62728"])
    axes[0].set_title("EV 离站需求满足情况（辆数）")
    axes[0].set_ylabel("车辆数")
    for i, v in enumerate([met, nmet]):
        axes[0].text(i, v + 0.5, str(v), ha="center", fontsize=10)

    req = ev["required_energy_at_departure_kwh"].to_numpy()
    fin = ev["final_energy_at_departure_kwh"].to_numpy()
    short = np.maximum(0, req - fin)
    axes[1].hist(short, bins=20, color="#7f7f7f", edgecolor="white")
    axes[1].set_title("离站能量缺口分布 (kWh)\nmax(0, 需求−实际)")
    axes[1].set_xlabel("kWh")
    axes[1].set_ylabel("车辆数")
    fig.suptitle("Baseline 预览：EV 会话汇总", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / "baseline_ev_summary_preview.png", bbox_inches="tight")
    plt.close(fig)


def write_figures_notes() -> None:
    text = """# Baseline 图表与数据说明（供 MATLAB 与论文对照）

## 输出文件一览

| 文件 | 类型 | 用途 |
|------|------|------|
| `baseline_kpi_table.csv` / `.md` | 表 | KPI 指标键名、中文名、数值、单位与含义，便于报告与 MATLAB 读表。 |
| `baseline_strategy_table.md` | 表 | 非协同策略文字说明，与协同模型策略对比时用。 |
| `baseline_plot_data.csv` | 时序 | **MATLAB 主作图源**：UTF-8 CSV，列名英文化，可直接 `readtable` / `readmatrix`。 |
| `figures/baseline_*_preview.png` | 图 | Python 预览，检查趋势与数量级；**论文终稿建议用 MATLAB 重绘**。 |

## 各预览图含义

1. **baseline_overview_preview.png**  
   - 原生负荷、EV 总充电、光伏可用、购电功率同屏（购电为右轴）。  
   - 用于快速查看供需与购电是否随负荷/光伏联动。

2. **baseline_ess_preview.png**  
   - 储能能量（kWh）与充、放电功率（kW）。  
   - 用于检查 SOC 轨迹及高价放电、光伏充电等行为是否与策略一致。

3. **baseline_price_grid_preview.png**  
   - 购电功率与购电电价。  
   - 用于对照电价时段与购电/储能逻辑。

4. **baseline_ev_summary_preview.png**  
   - 左：离站需求满足/未满足车辆数；右：离站能量缺口 `max(0, 需求−实际)` 直方图。  
   - 用于评估到站即充规则下的 EV 达标情况。

## MATLAB 读取建议

- 使用 `baseline_plot_data.csv`，注意编码为 **UTF-8**（必要时指定 `Encoding`）。  
- `timestamp` 列为字符串或解析为 `datetime`。  
- 功率类列为 kW，能量列为 kWh，电价为 元/kWh。

## 与协同模型比较时的用法

1. **KPI 表**：协同模型运行后生成同结构 `*_kpi_table.csv`，按 `metric_key` 对齐逐行对比。  
2. **时序作图数据**：协同模型导出相同列名的 `*_plot_data.csv`，在 MATLAB 中叠加曲线或计算差分序列（购电、弃光、成本等）。  
3. **策略表**：论文中可用两列表格并列描述 baseline 规则与协同优化差异。  
4. **预览图**：仅作开发检查；对比图建议在 MATLAB 中统一线型、色板与分辨率后出图。

---
*由 `code/python/baseline/export_baseline_reports.py` 生成*
"""
    (BASE / "baseline_figures_notes.md").write_text(text, encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not BASE.is_dir():
        raise FileNotFoundError(f"缺少目录: {BASE}")

    ts, ev, kpi = load_sources()
    write_kpi_tables(kpi)
    write_strategy_table()
    write_plot_data(ts)
    setup_plot_font()
    plot_previews(ts, ev)
    write_figures_notes()

    print("=== baseline 报表与预览导出完成 ===")
    print(f"目录: {BASE}")
    print(f"  - baseline_kpi_table.csv / .md")
    print(f"  - baseline_strategy_table.md")
    print(f"  - baseline_plot_data.csv")
    print(f"  - figures/*.png")
    print(f"  - baseline_figures_notes.md")


if __name__ == "__main__":
    main()
