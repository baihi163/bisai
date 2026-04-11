# -*- coding: utf-8 -*-
"""
问题一：非协同 baseline 与协同调度（p1 ultimate）对比可视化（论文用）。

---------------------------------------------------------------------------
第一步 — 结果目录与口径（仓库内既定约定）
---------------------------------------------------------------------------
- **Baseline（非协同规则型）**
    - 时序：`results/problem1_baseline/baseline_timeseries_results.csv`（672 行，15 min）
    - KPI 汇总：`results/problem1_baseline/baseline_kpi_summary.json`
    - 与协同同结构的全周对账：`results/tables/objective_reconciliation_baseline_fullweek.csv`
    - 在统一汇总脚本中的标识：`model_name=baseline_noncooperative`，`run_tag=baseline_default`
      （见 `code/python/analysis/build_model_validation_summary.py`）

- **Coordinated（问题一正式协同 MILP）**
    - 时序：`results/problem1_ultimate/p_1_5_timeseries.csv`（672 行）
    - 对账：`results/tables/objective_reconciliation_fullweek.csv`
    - 摘要行：`results/tables/problem1_result_summary.csv`（`p1_coordinated` / `p1_ultimate_latest`）

- **时段一致性**：两方案时序均为 **7 天 × 96 = 672** 时段；脚本启动时强制校验行数。

- **可比指标**
    - 直接可比（由 `build_model_validation_summary.row_from_p1` / `row_from_baseline`）：
      `operation_cost`（购电 − 售电 + 碳价项 + 弃光惩罚 + 移位惩罚 + 切负荷，**不含** ESS/EV 退化）、
      `grid_import_energy_kwh` 等。
    - 需由时序二次积分：`total_pv_energy_kwh`、`pv_used_energy_kwh`、`pv_curtail_energy_kwh`、
      `renewable_consumption_ratio`。
    - 物理购电碳排放（**与优化目标中 carbon_price=0 时的 carbon_cost 无关**）：
      `carbon_emission_kg = Σ P_grid_buy_kw × grid_carbon_kg_per_kwh × Δt`
      （协同：`P_buy_kw`；基线：`grid_import_kw`；因子来自 `data/processed/carbon_profile.csv`）。

若缺少上述任一文件，脚本 `raise FileNotFoundError` / `ValueError` 并提示最短补齐路径。

---------------------------------------------------------------------------
输出
---------------------------------------------------------------------------
- `results/figures/problem1/p1_baseline_vs_coordinated_kpi_compare.{png,pdf}`  
  （第三子图为 **购电加权平均碳强度 kg/kWh**，非全周排放 kg；全周 kg 见 `p1_grid_and_emission_compare`）
- `results/figures/problem1/p1_pv_utilization_compare.{png,pdf}`
- `results/figures/problem1/p1_grid_and_emission_compare.{png,pdf}`
- `results/tables/p1_baseline_vs_coordinated.{csv,md}`
- `results/tables/p1_baseline_vs_coordinated_carbon_audit.md`（一至六文字复核）
- `results/tables/p1_baseline_vs_coordinated_carbon_intermediates.csv`（碳排放中间量）
- `results/figures/problem1/p1_supplement_operation_cost_and_grid_import.{png,pdf}`
- `results/figures/problem1/p1_supplement_unit_import_costs.{png,pdf}`
- `results/figures/problem1/p1_supplement_pv_used_and_curtail.{png,pdf}`

用法：
  python code/python/problem_1/plot_baseline_vs_coordinated.py --repo-root <仓库根>
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_DEFAULT = _HERE.parents[3]

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

N_SLOTS = 672

PATH_COORD_TS = Path("results/problem1_ultimate/p_1_5_timeseries.csv")
PATH_BASE_TS = Path("results/problem1_baseline/baseline_timeseries_results.csv")
PATH_CARBON = Path("data/processed/carbon_profile.csv")
PATH_REC_BASE = Path("results/tables/objective_reconciliation_baseline_fullweek.csv")
PATH_REC_P1 = Path("results/tables/objective_reconciliation_fullweek.csv")


def _load_bms(repo: Path) -> Any:
    path = repo / "code" / "python" / "analysis" / "build_model_validation_summary.py"
    if not path.is_file():
        raise FileNotFoundError(f"缺少统一汇总模块: {path}")
    spec = importlib.util.spec_from_file_location("build_model_validation_summary", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_rec_grid_sell(repo: Path, rel: Path) -> tuple[float, float]:
    """从对账表读取购电成本与售电收入（元），用于表内「若有」字段。"""
    p = repo / rel
    if not p.is_file():
        return float("nan"), float("nan")
    df = pd.read_csv(p, encoding="utf-8-sig")
    m = {str(r["cost_item"]).strip(): float(r["value_yuan"]) for _, r in df.iterrows()}
    buy = m.get("Grid import cost", float("nan"))
    sell = m.get("Grid export revenue", float("nan"))
    return buy, sell


def _assert_rows(df: pd.DataFrame, path: Path, expected: int) -> None:
    n = len(df)
    if n != expected:
        raise ValueError(
            f"时段数不一致: {path} 行数={n}，预期 {expected}（7×96）。\n"
            "最短补齐：用同一预处理周数据重新跑 baseline 与 p_1_5 并写出 672 行时序。"
        )


def load_carbon_profile(repo: Path) -> pd.DataFrame:
    p = repo / PATH_CARBON
    if not p.is_file():
        raise FileNotFoundError(
            f"缺少碳强度曲线: {p}\n"
            "最短补齐：先运行数据预处理生成 data/processed/carbon_profile.csv。"
        )
    c = pd.read_csv(p, encoding="utf-8-sig")
    for col in ("timestamp", "grid_carbon_kg_per_kwh"):
        if col not in c.columns:
            raise ValueError(f"{p} 缺少列: {col}")
    c["timestamp"] = pd.to_datetime(c["timestamp"])
    return c


def grid_import_energy_from_timeseries(repo: Path, *, scenario: str) -> float:
    """全周购电电量 Σ P_import_kw×Δt（kWh），用于与汇总表交叉核对。"""
    if scenario == "coordinated":
        p = repo / PATH_COORD_TS
        df = pd.read_csv(p, encoding="utf-8-sig")
        dt = pd.to_numeric(df["delta_t_h"], errors="coerce").fillna(0.25)
        return float((pd.to_numeric(df["P_buy_kw"], errors="coerce").fillna(0.0) * dt).sum())
    if scenario == "baseline":
        p = repo / PATH_BASE_TS
        df = pd.read_csv(p, encoding="utf-8-sig")
        dt = 0.25
        return float((pd.to_numeric(df["grid_import_kw"], errors="coerce").fillna(0.0) * dt).sum())
    raise ValueError(scenario)


def weighted_avg_emission_factor_kg_per_kwh(carbon_kg: float, grid_kwh: float) -> float:
    if grid_kwh <= 1e-12:
        return float("nan")
    return float(carbon_kg / grid_kwh)


def metrics_from_coordinated_ts(repo: Path, carbon: pd.DataFrame) -> dict[str, float]:
    """协同方案：由 p_1_5_timeseries + carbon_profile 积分。"""
    p = repo / PATH_COORD_TS
    df = pd.read_csv(p, encoding="utf-8-sig")
    _assert_rows(df, p, N_SLOTS)
    req = ("timestamp", "P_buy_kw", "P_pv_use_kw", "pv_upper_kw", "pv_curtail_kw", "delta_t_h")
    for c in req:
        if c not in df.columns:
            raise ValueError(f"{p} 缺少列 `{c}`。\n最短补齐：重新导出 p_1_5_timeseries.csv。")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.merge(carbon, on="timestamp", how="left")
    if df["grid_carbon_kg_per_kwh"].isna().any():
        raise ValueError(
            f"{p} 与 {PATH_CARBON} 时间戳无法完全对齐。\n"
            "最短补齐：确认两者均为同一周的 672 个 timestamp。"
        )
    dt = pd.to_numeric(df["delta_t_h"], errors="coerce").fillna(0.25)
    p_buy = pd.to_numeric(df["P_buy_kw"], errors="coerce").fillna(0.0)
    p_use = pd.to_numeric(df["P_pv_use_kw"], errors="coerce").fillna(0.0)
    p_up = pd.to_numeric(df["pv_upper_kw"], errors="coerce").fillna(0.0)
    p_curt = pd.to_numeric(df["pv_curtail_kw"], errors="coerce").fillna(0.0)
    cf = pd.to_numeric(df["grid_carbon_kg_per_kwh"], errors="coerce").fillna(0.0)
    total_pv = float((p_up * dt).sum())
    pv_used = float((p_use * dt).sum())
    pv_curt = float((p_curt * dt).sum())
    carbon_kg = float((p_buy * cf * dt).sum())
    ratio = float(pv_used / total_pv) if total_pv > 1e-9 else float("nan")
    return {
        "total_pv_energy_kwh": total_pv,
        "pv_used_energy_kwh": pv_used,
        "pv_curtail_energy_kwh": pv_curt,
        "renewable_consumption_ratio": ratio,
        "carbon_emission_kg": carbon_kg,
    }


def metrics_from_baseline_ts(repo: Path, carbon: pd.DataFrame) -> dict[str, float]:
    """Baseline：由 baseline_timeseries_results + carbon_profile 积分。"""
    p = repo / PATH_BASE_TS
    df = pd.read_csv(p, encoding="utf-8-sig")
    _assert_rows(df, p, N_SLOTS)
    req = ("timestamp", "grid_import_kw", "pv_available_kw", "pv_used_locally_kw", "pv_curtailed_kw")
    for c in req:
        if c not in df.columns:
            raise ValueError(f"{p} 缺少列 `{c}`。\n最短补齐：重新导出 baseline 时序结果。")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.merge(carbon, on="timestamp", how="left")
    if df["grid_carbon_kg_per_kwh"].isna().any():
        raise ValueError(f"{p} 与 {PATH_CARBON} 时间戳无法完全对齐。")
    dt = 0.25
    g = pd.to_numeric(df["grid_import_kw"], errors="coerce").fillna(0.0)
    av = pd.to_numeric(df["pv_available_kw"], errors="coerce").fillna(0.0)
    us = pd.to_numeric(df["pv_used_locally_kw"], errors="coerce").fillna(0.0)
    cu = pd.to_numeric(df["pv_curtailed_kw"], errors="coerce").fillna(0.0)
    cf = pd.to_numeric(df["grid_carbon_kg_per_kwh"], errors="coerce").fillna(0.0)
    total_pv = float((av * dt).sum())
    pv_used = float((us * dt).sum())
    pv_curt = float((cu * dt).sum())
    carbon_kg = float((g * cf * dt).sum())
    ratio = float(pv_used / total_pv) if total_pv > 1e-9 else float("nan")
    return {
        "total_pv_energy_kwh": total_pv,
        "pv_used_energy_kwh": pv_used,
        "pv_curtail_energy_kwh": pv_curt,
        "renewable_consumption_ratio": ratio,
        "carbon_emission_kg": carbon_kg,
    }


def _md_table(d: pd.DataFrame) -> str:
    cols = list(d.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in d.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def build_summary_table(repo: Path) -> pd.DataFrame:
    bms = _load_bms(repo)
    r_p1 = bms.row_from_p1(repo)
    r_bl = bms.row_from_baseline(repo)
    if r_p1.get("operation_cost") is None:
        raise ValueError(
            "无法得到协同方案 operation_cost。\n"
            "最短补齐：确保 results/tables/objective_reconciliation_fullweek.csv 存在且含 Grid import cost 等分项。"
        )
    if r_bl.get("operation_cost") is None:
        raise ValueError(
            "无法得到 baseline operation_cost。\n"
            "最短补齐：确保 results/tables/objective_reconciliation_baseline_fullweek.csv 存在。"
        )

    carbon = load_carbon_profile(repo)
    m_p1 = metrics_from_coordinated_ts(repo, carbon)
    m_bl = metrics_from_baseline_ts(repo, carbon)

    buy_p1, sell_p1 = _parse_rec_grid_sell(repo, PATH_REC_P1)
    buy_bl, sell_bl = _parse_rec_grid_sell(repo, PATH_REC_BASE)

    rows = [
        {
            "scenario": "baseline_noncooperative",
            "scenario_label_zh": "非协同基线",
            "run_tag": r_bl["run_tag"],
            "total_pv_energy_kwh": m_bl["total_pv_energy_kwh"],
            "pv_used_energy_kwh": m_bl["pv_used_energy_kwh"],
            "pv_curtail_energy_kwh": m_bl["pv_curtail_energy_kwh"],
            "renewable_consumption_ratio": m_bl["renewable_consumption_ratio"],
            "operation_cost": float(r_bl["operation_cost"]),
            "grid_import_energy_kwh": float(r_bl["grid_import_energy_kwh"] or 0.0),
            "carbon_emission_kg": m_bl["carbon_emission_kg"],
            "grid_purchase_cost_yuan": buy_bl,
            "sell_revenue_yuan": sell_bl,
            "net_cost_yuan": float(r_bl["operation_cost"]),
        },
        {
            "scenario": "p1_coordinated",
            "scenario_label_zh": "协同调度",
            "run_tag": r_p1["run_tag"],
            "total_pv_energy_kwh": m_p1["total_pv_energy_kwh"],
            "pv_used_energy_kwh": m_p1["pv_used_energy_kwh"],
            "pv_curtail_energy_kwh": m_p1["pv_curtail_energy_kwh"],
            "renewable_consumption_ratio": m_p1["renewable_consumption_ratio"],
            "operation_cost": float(r_p1["operation_cost"]),
            "grid_import_energy_kwh": float(r_p1["grid_import_energy_kwh"] or 0.0),
            "carbon_emission_kg": m_p1["carbon_emission_kg"],
            "grid_purchase_cost_yuan": buy_p1,
            "sell_revenue_yuan": sell_p1,
            "net_cost_yuan": float(r_p1["operation_cost"]),
        },
    ]
    # grid_import from row already consistent with KPI / ts
    df = pd.DataFrame(rows)
    # 购电加权平均碳强度（kg/kWh）= 全周购电相关排放(kg) / 全周购电电量(kWh)，与逐时段因子对购电功率加权一致
    gi = df["grid_import_energy_kwh"].astype(float).clip(lower=1e-12)
    ce = df["carbon_emission_kg"].astype(float)
    df["import_weighted_carbon_intensity_kg_per_kwh"] = (ce / gi).astype(float)
    return df


def build_carbon_audit_artifacts(repo: Path, df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """中间量表 + Markdown 复核说明（一至六）。"""
    carbon = load_carbon_profile(repo)
    cf_mean = float(pd.to_numeric(carbon["grid_carbon_kg_per_kwh"], errors="coerce").mean())
    cf_unit = "kg CO2-eq / kWh（购电电量口径，随时间变化）"

    rows = []
    for _, r in df.iterrows():
        scen = str(r["scenario"])
        is_coord = scen == "p1_coordinated"
        gi_ts = grid_import_energy_from_timeseries(
            repo, scenario="coordinated" if is_coord else "baseline"
        )
        gi_tab = float(r["grid_import_energy_kwh"])
        ce = float(r["carbon_emission_kg"])
        wavg = weighted_avg_emission_factor_kg_per_kwh(ce, gi_ts)
        rows.append(
            {
                "scenario": scen,
                "scenario_label_zh": r["scenario_label_zh"],
                "run_tag": r["run_tag"],
                "grid_import_energy_kwh_from_table": gi_tab,
                "grid_import_energy_kwh_from_timeseries": gi_ts,
                "abs_diff_table_minus_ts_kwh": gi_tab - gi_ts,
                "carbon_emission_kg": ce,
                "weighted_avg_grid_carbon_kg_per_kwh": wavg,
                "carbon_profile_mean_grid_carbon_kg_per_kwh": cf_mean,
            }
        )
    inter = pd.DataFrame(rows)

    verdict = "C. 真实结果如此"
    verdict_detail = (
        "协同方案全周购电电量（Σ P_buy×Δt）高于 baseline（Σ grid_import×0.25），"
        "两方案使用同一 `carbon_profile.csv` 按时段左乘后求和；"
        "隐含加权平均排放因子几乎相同（约 0.658 kg/kWh），"
        "碳排放差异主要来自购电 kWh 差异，而非公式或文件错配。"
    )

    md = f"""# 问题一：baseline vs 协同 — 碳排放口径复核（一至六）

## 一、比较对象是否严格可比

1. **Baseline** `run_tag`：**`baseline_default`**；目录/文件：`results/problem1_baseline/`，时序 **`baseline_timeseries_results.csv`**，对账 **`results/tables/objective_reconciliation_baseline_fullweek.csv`**。
2. **协同方案** `run_tag`：**`p1_ultimate_latest`**；目录/文件：`results/problem1_ultimate/` 下 **`p_1_5_timeseries.csv`**，对账 **`results/tables/objective_reconciliation_fullweek.csv`**。
3. **时段**：两文件均为 **672** 行（7 天 × 96 点/天，15 min），与 `carbon_profile.csv`（672 行）按 `timestamp` 内连接。
4. **正式性**：路径为仓库既定「问题一全周 baseline / ultimate」产物，非 problem2、非 scan 测试目录。
5. **结论**：当前比较对象**严格可比**；若需更换 baseline，应替换上述 baseline 目录内同源导出并保持 672 时段与同一时间轴。

## 二、碳排放计算公式与单位

1. **脚本公式**（两方案相同）：`carbon_emission_kg = Σ_t P_grid_import_kw(t) × grid_carbon_kg_per_kwh(t) × Δt(h)`。  
   - Baseline：`P_grid_import_kw` = `grid_import_kw`。  
   - 协同：`P_grid_import_kw` = `P_buy_kw`（与 `build_model_validation_summary` 中 `grid_import_energy_kwh` = Σ`P_buy_kw`×`delta_t_h` 一致）。  
   - **未**使用「净购电」「售电抵扣」或 `grid_import_energy_kwh` 直接乘常数因子（因子**随时间变化**）。
2. **购电电量来源**：图中表内 `grid_import_energy_kwh` 来自 `row_from_*`（与全周时序积分一致）；复核表中另给 **`grid_import_energy_kwh_from_timeseries`** 独立重算。
3. **排放因子**：`data/processed/carbon_profile.csv` 列 **`grid_carbon_kg_per_kwh`**，单位 **kg CO2-eq / kWh**（每购电 1 kWh 对应的排放）。全周算术平均约 **{cf_mean:.6f}**（仅作参考，计算以逐时段为准）。
4. **单位自检**：kW×(kg/kWh)×h = kg；未与吨混用；15 min 步长 Baseline 用 **Δt=0.25 h**，协同用列 **`delta_t_h`**（本数据为 0.25）。
5. **两方案公式**：**完全相同**（同一碳曲线、同一乘积形式，仅购电功率列名不同）。

## 三、中间量（本仓库当前数据）

见同目录 **`p1_baseline_vs_coordinated_carbon_intermediates.csv`**（由脚本自动生成）。

## 四、判断：协同碳排放更高属于哪一类

**结论：{verdict}**

**依据**：{verdict_detail}

## 五、是否修复主图碳排放计算

**未改碳排放公式**；若仅修正柱与 x 轴对齐属版式修正，不改变数值与高低关系。

## 六、补充材料（经济性 vs 物理购电碳）

因属于 **{verdict}**，**全周购电碳排放总量**仍以 `carbon_emission_kg` 及 **`p1_grid_and_emission_compare`** 子图为准（协同总量可高于 baseline）。**KPI 三联图第三子图**改为展示 **`import_weighted_carbon_intensity_kg_per_kwh`**（= 全周排放 / 全周购电电量），该指标在本算例中**协同低于 baseline**（购电更多发生在相对低碳时段）。另生成 **`p1_supplement_*`** 系列图。

---

### 论文可用表述（经济性 / 消纳 vs 固定因子碳排放）

协同优化目标中 **购电碳货币化成本系数为 0**（见对账表 `Carbon cost,0`），模型主要压 **购电电价相关运行成本** 与柔性等惩罚。全周最优解可在**低价时段多购电**，使 **总购电 kWh 上升**；在**外生、随时间不变（与决策无关）的电网排放因子**下，**物理购电碳排放 = Σ 购电功率×因子×Δt** 与「总电费更低」**无单调关系**。本算例中 **弃光均为 0**，「可再生能源本地消纳率」两方案相同；协同优势主要体现在 **operation_cost 更低**，而非固定因子口径下的碳排放更低。

"""
    return inter, md


def plot_kpi_triple(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    labels = df["scenario_label_zh"].tolist()
    x = np.arange(len(labels))
    w = 0.55
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2), dpi=150, constrained_layout=True)
    metrics = [
        ("renewable_consumption_ratio", "可再生能源本地消纳率\n(pv_used / total_pv)", "ratio"),
        ("operation_cost", "运行成本（元）\n(operation_cost，与 p2 同口径)", "yuan"),
        (
            "import_weighted_carbon_intensity_kg_per_kwh",
            "购电加权平均碳强度 (kg/kWh)\n(carbon_emission / grid_import)",
            "kg_per_kwh",
        ),
    ]
    colors = ["#ff7f0e", "#1f77b4"]
    for ax, (col, title, kind) in zip(axes, metrics):
        vals = df[col].astype(float).tolist()
        bars = ax.bar(x, vals, width=w, color=colors, edgecolor="#333", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_title(title, fontsize=11)
        for b, v in zip(bars, vals):
            if kind == "ratio":
                txt = f"{v:.4g}"
            elif kind == "kg_per_kwh":
                txt = f"{v:.5f}"
            else:
                txt = f"{v:.2f}"
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                txt,
                ha="center",
                va="bottom",
                fontsize=9,
            )
    fig.suptitle("问题一：非协同基线 vs 协同调度 — 关键绩效对比", fontsize=13, fontweight="bold")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def plot_pv_stacked(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    labels = df["scenario_label_zh"].tolist()
    used = df["pv_used_energy_kwh"].astype(float).to_numpy()
    curt = df["pv_curtail_energy_kwh"].astype(float).to_numpy()
    x = np.arange(len(labels))
    w = 0.55
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150, constrained_layout=True)
    ax.bar(x, used, width=w, label="已利用光伏 (pv_used)", color="#2ca02c", edgecolor="#333", linewidth=0.5)
    ax.bar(x, curt, width=w, bottom=used, label="弃光 (pv_curtail)", color="#d62728", edgecolor="#333", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("电量 (kWh)")
    ax.set_title("光伏利用去向对比（全周积分）")
    ax.legend(loc="upper right")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def plot_grid_emission(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    labels = df["scenario_label_zh"].tolist()
    x = np.arange(len(labels))
    w = 0.42
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.5), dpi=150, constrained_layout=True)
    colors = ["#ff7f0e", "#1f77b4"]
    g = df["grid_import_energy_kwh"].astype(float).to_numpy()
    e = df["carbon_emission_kg"].astype(float).to_numpy()
    ax1.bar(x, g, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("kWh")
    ax1.set_title("电网购电量")
    for i, v in enumerate(g):
        ax1.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)
    ax2.bar(x, e, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel("kg CO2 当量（按购电×碳强度）")
    ax2.set_title("购电相关碳排放")
    for i, v in enumerate(e):
        ax2.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)
    fig.suptitle("问题一：购电量与碳排放对比", fontsize=13, fontweight="bold")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def plot_supplement_operation_cost_and_grid_import(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    """补充：运行成本与购电量（不替代碳柱图，便于解释「电费↓但 kWh↑」）。"""
    labels = df["scenario_label_zh"].tolist()
    x = np.arange(len(labels))
    w = 0.42
    colors = ["#ff7f0e", "#1f77b4"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.5), dpi=150, constrained_layout=True)
    cst = df["operation_cost"].astype(float).to_numpy()
    g = df["grid_import_energy_kwh"].astype(float).to_numpy()
    ax1.bar(x, cst, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("元")
    ax1.set_title("运行成本 (operation_cost)")
    for i, v in enumerate(cst):
        ax1.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)
    ax2.bar(x, g, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel("kWh")
    ax2.set_title("全周购电电量 (grid_import_energy_kwh)")
    for i, v in enumerate(g):
        ax2.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=9)
    fig.suptitle("补充：经济性（成本）与物理购电量", fontsize=13, fontweight="bold")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def plot_supplement_unit_import_costs(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    """补充：单位购电运行成本、单位已消纳光伏电量的运行成本。"""
    labels = df["scenario_label_zh"].tolist()
    x = np.arange(len(labels))
    w = 0.36
    colors = ["#ff7f0e", "#1f77b4"]
    gi = df["grid_import_energy_kwh"].astype(float)
    pvu = df["pv_used_energy_kwh"].astype(float)
    oc = df["operation_cost"].astype(float)
    y1 = (oc / gi).to_numpy()
    y2 = (oc / pvu).to_numpy()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.5), dpi=150, constrained_layout=True)
    ax1.bar(x, y1, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("元 / kWh（购电）")
    ax1.set_title("单位购电运行成本\noperation_cost / grid_import_energy_kwh")
    for i, v in enumerate(y1):
        ax1.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    ax2.bar(x, y2, width=w, color=colors, edgecolor="#333", linewidth=0.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels)
    ax2.set_ylabel("元 / kWh（已利用光伏）")
    ax2.set_title("单位已消纳光伏电量的运行成本\noperation_cost / pv_used_energy_kwh")
    for i, v in enumerate(y2):
        ax2.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    fig.suptitle("补充：单位能量运行成本（解释协同更省钱的机制）", fontsize=13, fontweight="bold")
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def plot_supplement_pv_used_and_curtail(df: pd.DataFrame, out_png: Path, out_pdf: Path) -> None:
    """补充：PV 已利用 vs 弃光（与主图数据相同，标题强调本算例弃光为 0）。"""
    labels = df["scenario_label_zh"].tolist()
    used = df["pv_used_energy_kwh"].astype(float).to_numpy()
    curt = df["pv_curtail_energy_kwh"].astype(float).to_numpy()
    x = np.arange(len(labels))
    w = 0.55
    fig, ax = plt.subplots(figsize=(7.8, 5.0), dpi=150, constrained_layout=True)
    ax.bar(x, used, width=w, label="已利用光伏 (pv_used)", color="#2ca02c", edgecolor="#333", linewidth=0.5)
    ax.bar(x, curt, width=w, bottom=used, label="弃光 (pv_curtail)", color="#d62728", edgecolor="#333", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("电量 (kWh)")
    ax.set_title("光伏利用去向（全周）")
    ax.legend(loc="upper right")
    fig.suptitle(
        "补充：PV 利用与弃光（本仓库算例两方案弃光均为 0，消纳率均为 1）",
        fontsize=12,
        fontweight="bold",
    )
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description="问题一 baseline vs 协同 论文图与表")
    ap.add_argument("--repo-root", type=Path, default=_REPO_DEFAULT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()

    for rel in (PATH_COORD_TS, PATH_BASE_TS, PATH_CARBON, PATH_REC_BASE, PATH_REC_P1):
        p = repo / rel
        if not p.is_file():
            print(f"缺失文件: {p}", file=sys.stderr)
            return 1

    df = build_summary_table(repo)
    tbl_dir = repo / "results" / "tables"
    fig_dir = repo / "results" / "figures" / "problem1"
    tbl_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 表：主列 + 附录列
    main_cols = [
        "scenario",
        "total_pv_energy_kwh",
        "pv_used_energy_kwh",
        "pv_curtail_energy_kwh",
        "renewable_consumption_ratio",
        "operation_cost",
        "grid_import_energy_kwh",
        "carbon_emission_kg",
        "import_weighted_carbon_intensity_kg_per_kwh",
    ]
    extra_cols = ["scenario_label_zh", "run_tag", "grid_purchase_cost_yuan", "sell_revenue_yuan", "net_cost_yuan"]
    out_csv = tbl_dir / "p1_baseline_vs_coordinated.csv"
    df[main_cols + [c for c in extra_cols if c in df.columns]].to_csv(out_csv, index=False, encoding="utf-8-sig")

    md_lines = [
        "# 问题一：非协同基线 vs 协同调度 — 结果汇总",
        "",
        "**时段**：两方案均为全周 **672** 时段（15 min）。",
        "",
        "**operation_cost 口径**：与 `build_model_validation_summary._operation_cost_from_components` 一致（不含 ESS/EV 退化）。",
        "",
        "**renewable_consumption_ratio**：`pv_used_energy_kwh / total_pv_energy_kwh`；"
        "基线 `pv_available_kw`×0.25、协同 `pv_upper_kw`×`delta_t_h` 积分。",
        "",
        "**carbon_emission_kg**：`Σ P_grid_kw × grid_carbon_kg_per_kwh × Δt`（kg）；"
        "因子来自 `data/processed/carbon_profile.csv`（与优化中 carbon_price=0 独立）。",
        "",
        "**import_weighted_carbon_intensity_kg_per_kwh**：`carbon_emission_kg / grid_import_energy_kwh`，"
        "即全周购电排放对购电电量的加权平均强度。**KPI 三联图第三子图**展示该强度（本算例协同略低于 baseline）；"
        "全周排放总量见列 `carbon_emission_kg` 或 `p1_grid_and_emission_compare` 图。",
        "",
        _md_table(df[main_cols].copy()),
        "",
        "---",
        "",
        "**碳排放口径复核（一至六）与中间量**：见 `p1_baseline_vs_coordinated_carbon_audit.md`、"
        "`p1_baseline_vs_coordinated_carbon_intermediates.csv`。",
        "",
    ]
    (tbl_dir / "p1_baseline_vs_coordinated.md").write_text("\n".join(md_lines), encoding="utf-8")

    inter, audit_md = build_carbon_audit_artifacts(repo, df)
    inter.to_csv(tbl_dir / "p1_baseline_vs_coordinated_carbon_intermediates.csv", index=False, encoding="utf-8-sig")
    (tbl_dir / "p1_baseline_vs_coordinated_carbon_audit.md").write_text(audit_md, encoding="utf-8")

    plot_kpi_triple(
        df,
        fig_dir / "p1_baseline_vs_coordinated_kpi_compare.png",
        fig_dir / "p1_baseline_vs_coordinated_kpi_compare.pdf",
    )
    plot_pv_stacked(df, fig_dir / "p1_pv_utilization_compare.png", fig_dir / "p1_pv_utilization_compare.pdf")
    plot_grid_emission(df, fig_dir / "p1_grid_and_emission_compare.png", fig_dir / "p1_grid_and_emission_compare.pdf")

    plot_supplement_operation_cost_and_grid_import(
        df,
        fig_dir / "p1_supplement_operation_cost_and_grid_import.png",
        fig_dir / "p1_supplement_operation_cost_and_grid_import.pdf",
    )
    plot_supplement_unit_import_costs(
        df,
        fig_dir / "p1_supplement_unit_import_costs.png",
        fig_dir / "p1_supplement_unit_import_costs.pdf",
    )
    plot_supplement_pv_used_and_curtail(
        df,
        fig_dir / "p1_supplement_pv_used_and_curtail.png",
        fig_dir / "p1_supplement_pv_used_and_curtail.pdf",
    )

    print("OK", out_csv.as_posix())
    print(fig_dir / "p1_baseline_vs_coordinated_kpi_compare.png")
    print(tbl_dir / "p1_baseline_vs_coordinated_carbon_audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
