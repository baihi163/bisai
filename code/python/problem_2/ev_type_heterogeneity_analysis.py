"""
问题 2：按车型（compact / sedan / SUV）对 EV 会话做异质性统计与作图。

输入：ev_sessions_model_ready.csv（默认）或 ev_sessions.csv（需含相同核心列）。
输出：汇总表 CSV/Markdown + 两张论文用图。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED_COLS = [
    "ev_type",
    "battery_capacity_kwh",
    "initial_energy_kwh",
    "required_energy_at_departure_kwh",
    "max_charge_power_kw",
    "max_discharge_power_kw",
    "v2b_allowed",
    "degradation_cost_cny_per_kwh_throughput",
]

TYPE_ORDER = ["compact", "sedan", "SUV"]
TYPE_LABEL_ZH = {
    "compact": "紧凑型",
    "sedan": "轿车",
    "SUV": "SUV",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize_ev_type(s: object) -> str:
    t = str(s).strip().lower()
    if t == "suv":
        return "SUV"
    return t  # compact, sedan


def _dwell_hours(df: pd.DataFrame, dt_h: float) -> pd.Series:
    if "dwell_slots" in df.columns and df["dwell_slots"].notna().all():
        return df["dwell_slots"].astype(float) * dt_h
    a = pd.to_datetime(df["arrival_time"])
    d = pd.to_datetime(df["departure_time"])
    return (d - a).dt.total_seconds() / 3600.0


def setup_matplotlib_zh() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.grid": True,
            "grid.alpha": 0.35,
        }
    )


def load_sessions(path: Path, *, feasible_only: bool, dt_h: float) -> pd.DataFrame:
    df = pd.read_csv(path)
    miss = [c for c in REQUIRED_COLS if c not in df.columns]
    if miss:
        raise KeyError(f"缺少列: {miss}（文件: {path}）")
    if feasible_only and "feasibility_flag" in df.columns:
        df = df.loc[df["feasibility_flag"].astype(int) == 1].copy()
    df["ev_type"] = df["ev_type"].map(_normalize_ev_type)
    df["parking_duration_h"] = _dwell_hours(df, dt_h)
    df["v2b_allowed"] = df["v2b_allowed"].astype(int).clip(0, 1)
    for c in (
        "battery_capacity_kwh",
        "initial_energy_kwh",
        "required_energy_at_departure_kwh",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "degradation_cost_cny_per_kwh_throughput",
    ):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    cap = df["battery_capacity_kwh"].replace(0, np.nan)
    df["initial_soc"] = (df["initial_energy_kwh"] / cap).clip(lower=0.0, upper=1.5)
    df["target_departure_soc"] = (df["required_energy_at_departure_kwh"] / cap).clip(lower=0.0, upper=1.5)
    df["energy_replenishment_need_kwh"] = df["required_energy_at_departure_kwh"] - df["initial_energy_kwh"]
    df["relative_replenishment_need"] = df["energy_replenishment_need_kwh"] / cap
    return df


def _aggregate_one_type(sub: pd.DataFrame, et: str) -> dict[str, float | int | str]:
    deg = sub["degradation_cost_cny_per_kwh_throughput"]
    return {
        "ev_type": et,
        "vehicle_count": int(len(sub)),
        "mean_battery_capacity_kwh": float(sub["battery_capacity_kwh"].mean()),
        "mean_initial_energy_kwh": float(sub["initial_energy_kwh"].mean()),
        "mean_required_departure_energy_kwh": float(sub["required_energy_at_departure_kwh"].mean()),
        "mean_initial_soc": float(sub["initial_soc"].mean()),
        "mean_target_departure_soc": float(sub["target_departure_soc"].mean()),
        "mean_energy_replenishment_need_kwh": float(sub["energy_replenishment_need_kwh"].mean()),
        "mean_relative_replenishment_need": float(sub["relative_replenishment_need"].mean()),
        "mean_parking_duration_h": float(sub["parking_duration_h"].mean()),
        "mean_max_charge_power_kw": float(sub["max_charge_power_kw"].mean()),
        "mean_max_discharge_power_kw": float(sub["max_discharge_power_kw"].mean()),
        "v2b_allowed_share": float(sub["v2b_allowed"].mean()),
        "mean_degradation_cost_cny_per_kwh_throughput": float(deg.mean()),
        "min_degradation_cost_cny_per_kwh_throughput": float(deg.min()),
        "max_degradation_cost_cny_per_kwh_throughput": float(deg.max()),
        "std_degradation_cost_cny_per_kwh_throughput": float(deg.std(ddof=1)) if len(sub) > 1 else 0.0,
    }


def summarize_by_type(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for et in TYPE_ORDER:
        sub = df.loc[df["ev_type"] == et]
        if sub.empty:
            continue
        rows.append(_aggregate_one_type(sub, et))
    other = df.loc[~df["ev_type"].isin(TYPE_ORDER)]
    if not other.empty:
        for et in sorted(other["ev_type"].unique()):
            sub = df.loc[df["ev_type"] == et]
            rows.append(_aggregate_one_type(sub, str(et)))
    return pd.DataFrame(rows)


def round_summary_for_export(summ: pd.DataFrame) -> pd.DataFrame:
    """CSV / 展示用舍入：电量与 SOC 等 3 位小数；退化成本与 V2B 占比 4 位小数。"""
    out = summ.copy()
    three = [
        "mean_battery_capacity_kwh",
        "mean_initial_energy_kwh",
        "mean_required_departure_energy_kwh",
        "mean_initial_soc",
        "mean_target_departure_soc",
        "mean_energy_replenishment_need_kwh",
        "mean_relative_replenishment_need",
        "mean_parking_duration_h",
        "mean_max_charge_power_kw",
        "mean_max_discharge_power_kw",
    ]
    four = [
        "v2b_allowed_share",
        "mean_degradation_cost_cny_per_kwh_throughput",
        "min_degradation_cost_cny_per_kwh_throughput",
        "max_degradation_cost_cny_per_kwh_throughput",
        "std_degradation_cost_cny_per_kwh_throughput",
    ]
    for c in three:
        if c in out.columns:
            out[c] = out[c].astype(float).round(3)
    for c in four:
        if c in out.columns:
            out[c] = out[c].astype(float).round(4)
    return out


def _display_input_path(input_path: Path, repo_root: Path) -> str:
    try:
        return "`" + input_path.resolve().relative_to(repo_root.resolve()).as_posix() + "`"
    except ValueError:
        return "`" + input_path.resolve().as_posix() + "`"


def _nominal_capacity_clause(df: pd.DataFrame) -> str:
    """按车型列出额定容量（kWh），由数据自动识别唯一值或区间。"""
    parts: list[str] = []
    for et in TYPE_ORDER:
        sub = df.loc[df["ev_type"] == et, "battery_capacity_kwh"].dropna()
        if sub.empty:
            continue
        u = np.sort(sub.unique())
        zh = TYPE_LABEL_ZH.get(et, et)
        if len(u) == 1:
            parts.append(f"{zh}（{et}）**{float(u[0]):.0f} kWh**")
        else:
            parts.append(f"{zh}（{et}）**{float(u[0]):.1f}–{float(u[-1]):.1f} kWh**")
    return "样本中各车型额定容量依次为：" + "、".join(parts) + "。"


def _sample_count_clause(summary: pd.DataFrame, n_total: int) -> str:
    segs: list[str] = []
    for et in TYPE_ORDER:
        hit = summary.loc[summary["ev_type"] == et, "vehicle_count"]
        if hit.empty:
            continue
        zh = TYPE_LABEL_ZH.get(et, et)
        segs.append(f"{zh}（{et}）**{int(hit.iloc[0])}** 条")
    return f"全样本共 **{int(n_total)}** 条会话记录，其中 " + "、".join(segs) + "。"


def _row_by_type(summary: pd.DataFrame, et: str) -> pd.Series | None:
    hit = summary.loc[summary["ev_type"] == et]
    if hit.empty:
        return None
    return hit.iloc[0]


def _paper_body_paragraph_zh(df: pd.DataFrame, summary: pd.DataFrame, n_total: int) -> list[str]:
    """一段可粘贴进论文正文的中文表述，数值全部由本脚本统计。"""
    intro = _sample_count_clause(summary, n_total) + _nominal_capacity_clause(df)
    parts_soc: list[str] = []
    parts_tds: list[str] = []
    parts_rr: list[str] = []
    parts_deg: list[str] = []
    parts_v2b: list[str] = []
    for et in TYPE_ORDER:
        r = _row_by_type(summary, et)
        if r is None:
            continue
        zh = TYPE_LABEL_ZH.get(et, et)
        parts_soc.append(f"{zh} **{float(r['mean_initial_soc']):.3f}**")
        parts_tds.append(f"{zh} **{float(r['mean_target_departure_soc']):.3f}**")
        parts_rr.append(f"{zh} **{float(r['mean_relative_replenishment_need']):.3f}**")
        parts_deg.append(f"{zh} **{float(r['mean_degradation_cost_cny_per_kwh_throughput']):.4f}** 元/kWh")
        parts_v2b.append(f"{zh} **{float(r['v2b_allowed_share']):.1%}**")
    para = (
        intro
        + "分车型平均初始荷电状态（SOC）依次为：" + "、".join(parts_soc) + "；"
        + "平均目标离站 SOC 依次为：" + "、".join(parts_tds) + "；"
        + "平均相对补能需求（离站目标电量与初始电量之差除以额定容量）依次为：" + "、".join(parts_rr) + "。"
        + "在寿命损耗参数方面，平均吞吐退化成本依次为：" + "、".join(parts_deg) + "；"
        + "V2B 允许会话占比依次为：" + "、".join(parts_v2b) + "。"
        + "上述差异表明电动汽车群体在能量边界、补能需求与退化经济参数上具有**可辨识的结构性异质性**；"
        + "问题 2 的协同调度与寿命损耗建模宜在解释最优解时结合分车型统计，必要时对退化系数或 V2B 约束做分车型或敏感性设定。"
    )
    return [
        "## 可供论文正文引用的表述（数据驱动）",
        "",
        para,
        "",
    ]


def _auto_conclusion_lines(summary: pd.DataFrame) -> list[str]:
    """基于本表三车型（若齐全）生成简短中文结论（样本量与额定容量见文首，此处不重复）。"""
    sub = summary[summary["ev_type"].isin(TYPE_ORDER)].copy()
    if len(sub) < 2:
        return ["## 数据驱动的简要结论", "", "_车型类别不足两种，未自动生成对比结论。_", ""]
    by = sub.set_index("ev_type")
    deg_spread = float(by["mean_degradation_cost_cny_per_kwh_throughput"].max() - by["mean_degradation_cost_cny_per_kwh_throughput"].min())
    cap_spread = float(by["mean_battery_capacity_kwh"].max() - by["mean_battery_capacity_kwh"].min())
    rr_spread = float(by["mean_relative_replenishment_need"].max() - by["mean_relative_replenishment_need"].min())
    hi_deg = by["mean_degradation_cost_cny_per_kwh_throughput"].idxmax()
    lo_deg = by["mean_degradation_cost_cny_per_kwh_throughput"].idxmin()
    hi_v2b = by["v2b_allowed_share"].idxmax()
    lo_v2b = by["v2b_allowed_share"].idxmin()
    hi_cap = by["mean_battery_capacity_kwh"].idxmax()
    lines = [
        "## 数据驱动的简要结论",
        "",
        "> 说明：上文「样本规模」「额定容量分档」与「可供论文正文引用的表述」已给出会话条数与 **50 / 60 / 75 kWh** 分档，本节不再重复。",
        "",
        f"1. **是否存在明显异质性**：三款车型在平均额定能量上相差 **{cap_spread:.1f} kWh**（由分车型样本均值之差刻画）；"
        f"平均相对补能需求的极差为 **{rr_spread:.3f}**（无量纲，占额定容量比例）；"
        f"平均吞吐退化成本极差约 **{deg_spread:.4f} 元/kWh**（最高为 **{hi_deg}**，最低为 **{lo_deg}**）；"
        f"V2B 允许占比在 **{float(by.loc[lo_v2b, 'v2b_allowed_share']):.1%}**（{lo_v2b}）至 **{float(by.loc[hi_v2b, 'v2b_allowed_share']):.1%}**（{hi_v2b}）之间。"
        "综合可见**存在可用于论文描述的结构性差异**（非完全同质群体）。",
        "",
        "2. **是否支持按车型讨论寿命损耗与调度分工**：样本已为各会话给出 `degradation_cost_cny_per_kwh_throughput`，"
        "且分车型统计量差异明显，**支持**在问题 2 中将「分车型描述统计—目标函数退化项—充放电/V2B 约束」串接论述；若建模采用单一 EV 退化系数，可用本表说明**同质假设的偏差方向**并配合敏感性分析。",
        "",
        "3. **供能/削峰与优先保护**：",
        f"   - **能量型削峰/供能候选**：平均电池容量最大的车型为 **{hi_cap}**，平均吞吐退化成本最低为 **{lo_deg}**；二者一致时，该车型在「单位退化成本—可用能量体量」上最具优势；不一致时需联合曲线与约束讨论。",
        f"   - **优先少调用/强约束对象**：平均吞吐退化成本最高的 **{hi_deg}**，在相同线性退化权重下，放电与吞吐的边际经济代价最大，更宜作为**保护型**车辆（限制 V2B 深度或优先满足离站需求而非反向送电）。",
        f"   - **规则灵活性**：V2B 允许占比最高为 **{hi_v2b}**、最低为 **{lo_v2b}**，反映数据集中**硬件/规则可参与反向送电**的比例差异，调度分工需与上述经济参数一并考虑。",
        "",
    ]
    return lines


def write_markdown_zh(
    path: Path,
    summary: pd.DataFrame,
    df: pd.DataFrame,
    *,
    input_path: Path,
    repo_root: Path,
    n_total: int,
    feasible_only: bool,
    dt_h: float,
) -> None:
    scope = "仅 feasibility_flag=1" if feasible_only else "含全部会话"
    lines = [
        "# 电动汽车会话按车型异质性汇总",
        "",
        f"- **数据来源**：{_display_input_path(input_path, repo_root)}",
        f"- **样本范围**：{scope}（以下会话条数与分车型计数均由脚本对输入表自动统计）。",
        f"- **样本规模**：{_sample_count_clause(summary, n_total)}",
        f"- **额定容量分档**：{_nominal_capacity_clause(df)}",
        f"- **停车时长口径**：优先 `dwell_slots×{dt_h}` h；若无有效停留时段列则用到站—离站时间差。",
        "",
        "## 分车型统计表",
        "",
        "| 车型 | 中文 | 会话数 | 平均额定容量（kWh） | 平均初始电量（kWh） | 平均目标离站电量（kWh） | 平均初始 SOC | 平均目标离站 SOC | 平均补能需求（kWh） | 平均相对补能需求 | 平均停车时长（h） | 平均最大充电功率（kW） | 平均最大放电功率（kW） | V2B 允许占比 | 平均吞吐退化成本（元/kWh） | 退化成本最小值 | 退化成本最大值 | 退化成本标准差 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in summary.iterrows():
        et = str(r["ev_type"])
        zh = TYPE_LABEL_ZH.get(et, et)
        lines.append(
            f"| {et} | {zh} | {int(r['vehicle_count'])} | "
            f"{r['mean_battery_capacity_kwh']:.3f} | {r['mean_initial_energy_kwh']:.3f} | {r['mean_required_departure_energy_kwh']:.3f} | "
            f"{r['mean_initial_soc']:.3f} | {r['mean_target_departure_soc']:.3f} | {r['mean_energy_replenishment_need_kwh']:.3f} | {r['mean_relative_replenishment_need']:.3f} | "
            f"{r['mean_parking_duration_h']:.3f} | {r['mean_max_charge_power_kw']:.3f} | {r['mean_max_discharge_power_kw']:.3f} | "
            f"{r['v2b_allowed_share']:.4f} | {r['mean_degradation_cost_cny_per_kwh_throughput']:.4f} | "
            f"{r['min_degradation_cost_cny_per_kwh_throughput']:.4f} | {r['max_degradation_cost_cny_per_kwh_throughput']:.4f} | "
            f"{r['std_degradation_cost_cny_per_kwh_throughput']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 指标说明",
            "",
            "- **平均初始 SOC**：`initial_energy_kwh / battery_capacity_kwh`，表示到网时平均荷电状态（0–1，若数据越界则来自原始记录，本表为描述统计）。",
            "- **平均目标离站 SOC**：`required_energy_at_departure_kwh / battery_capacity_kwh`。",
            "- **平均补能需求（kWh）**：`required_energy_at_departure_kwh - initial_energy_kwh`，表示离站前需净增加的电量（可为负，表示允许离站时低于到站电量之设定，本数据以正为主）。",
            "- **平均相对补能需求**：补能需求除以额定容量，无量纲，便于在 **50 / 60 / 75 kWh** 等不同额定能量下比较「离站目标相对到站亏空」强度。",
            "- **V2B 允许占比**：会话条目中 `v2b_allowed=1` 的比例。",
            "- **吞吐退化成本（元/kWh）**：与问题 2 目标函数中线性寿命损耗项一致的会话级参数。",
            "",
            "## 与论文写作的衔接",
            "",
            "- 若各车型在**容量、SOC 轨迹、补能需求、V2B 占比、退化成本**上差异明显，可在问题 2 正文中设置「分车型描述性统计」小节，并在寿命损耗建模中讨论**是否按车型设定 EV 吞吐退化系数或约束分工**。",
            "- 图形文件见 `results/figures/problem2/` 下 `ev_type_capacity_degradation.png` 与 `ev_type_v2b_ratio.png`。",
            "",
        ]
    )
    lines.extend(_paper_body_paragraph_zh(df, summary, n_total))
    lines.extend(_auto_conclusion_lines(summary))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def plot_capacity_degradation(summary: pd.DataFrame, out_path: Path) -> None:
    sub = summary[summary["ev_type"].isin(TYPE_ORDER)].copy()
    if sub.empty:
        return
    x = np.arange(len(sub))
    labels = [f"{et}\n({TYPE_LABEL_ZH.get(et, '')})" for et in sub["ev_type"].astype(str)]
    fig, ax1 = plt.subplots(figsize=(7.5, 4.6), layout="constrained")
    w = 0.35
    ax1.bar(x - w / 2, sub["mean_battery_capacity_kwh"], width=w, label="平均电池容量（kWh）", color="#457b9d", edgecolor="#222", linewidth=0.5)
    ax1.set_ylabel("平均电池容量（kWh）")
    ax1.set_xticks(x, labels, fontsize=10)
    ax2 = ax1.twinx()
    ax2.plot(x, sub["mean_degradation_cost_cny_per_kwh_throughput"], "o-", color="#e63946", lw=2, ms=8, label="平均吞吐退化成本（元/kWh）")
    ax2.set_ylabel("平均吞吐退化成本（元/kWh）")
    ax1.set_title("分车型：平均电池容量与平均退化成本")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_v2b_ratio(summary: pd.DataFrame, out_path: Path) -> None:
    sub = summary[summary["ev_type"].isin(TYPE_ORDER)].copy()
    if sub.empty:
        return
    x = np.arange(len(sub))
    labels = [f"{et}\n({TYPE_LABEL_ZH.get(et, '')})" for et in sub["ev_type"].astype(str)]
    pct = sub["v2b_allowed_share"].to_numpy(dtype=float) * 100.0
    fig, ax = plt.subplots(figsize=(6.5, 4.5), layout="constrained")
    ax.bar(x, pct, color="#2a9d8f", edgecolor="#222", linewidth=0.5, width=0.5)
    ax.set_xticks(x, labels, fontsize=10)
    ax.set_ylabel("V2B 允许会话占比（%）")
    ax.set_title("分车型：V2B 允许比例")
    ax.set_ylim(0, max(105.0, float(np.max(pct)) * 1.15))
    for i, v in enumerate(pct):
        ax.text(i, v + 2.0, f"{v:.1f}%", ha="center", fontsize=10, fontweight="bold")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    p = argparse.ArgumentParser(description="EV 车型异质性分析")
    p.add_argument(
        "--input",
        type=Path,
        default=root / "data" / "processed" / "final_model_inputs" / "ev_sessions_model_ready.csv",
        help="EV 会话 CSV",
    )
    p.add_argument("--dt-hours", type=float, default=0.25, help="每个 dwell_slot 对应小时数（默认 15 min）")
    p.add_argument("--feasible-only", action="store_true", help="仅保留 feasibility_flag=1")
    p.add_argument("--out-csv", type=Path, default=root / "results" / "tables" / "problem2_ev_type_summary.csv")
    p.add_argument("--out-md", type=Path, default=root / "results" / "tables" / "problem2_ev_type_summary.md")
    p.add_argument(
        "--fig-cap-deg",
        type=Path,
        default=root / "results" / "figures" / "problem2" / "ev_type_capacity_degradation.png",
    )
    p.add_argument(
        "--fig-v2b",
        type=Path,
        default=root / "results" / "figures" / "problem2" / "ev_type_v2b_ratio.png",
    )
    args = p.parse_args(argv)

    setup_matplotlib_zh()
    df = load_sessions(args.input.resolve(), feasible_only=args.feasible_only, dt_h=args.dt_hours)
    n_total = len(df)
    summ = summarize_by_type(df)
    summ_out = round_summary_for_export(summ)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    summ_out.to_csv(args.out_csv, index=False, encoding="utf-8-sig")
    write_markdown_zh(
        args.out_md,
        summ_out,
        df,
        input_path=args.input,
        repo_root=root,
        n_total=n_total,
        feasible_only=args.feasible_only,
        dt_h=args.dt_hours,
    )
    plot_capacity_degradation(summ, args.fig_cap_deg)
    plot_v2b_ratio(summ, args.fig_v2b)
    print("Wrote:", args.out_csv.resolve())
    print("Wrote:", args.out_md.resolve())
    print("Wrote:", args.fig_cap_deg.resolve())
    print("Wrote:", args.fig_v2b.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
