"""
问题 1：协同模型 vs baseline 论文用对比图（仅读结果、作图，不修改 MILP）。

默认读取全周结果与对账表，输出 PNG 至 results/figures/problem1/。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import objective_reconciliation as obr


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def setup_matplotlib() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "axes.grid": True,
            "grid.alpha": 0.35,
            "grid.linestyle": "--",
        }
    )


def baseline_raw_to_aligned(raw: pd.DataFrame, grid_limits: pd.DataFrame, dt_h: float) -> pd.DataFrame:
    """由 baseline_timeseries_results 与 grid_limits 生成与协同表对齐的列。"""
    g = grid_limits[["timestamp", "grid_import_limit_kw"]].copy()
    g["timestamp"] = pd.to_datetime(g["timestamp"])
    df = raw.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    m = df.merge(g, on="timestamp", how="left")
    n = len(m)
    pv_use = (
        m["pv_used_locally_kw"].to_numpy(dtype=np.float64)
        + m["pv_to_ess_kw"].to_numpy(dtype=np.float64)
        + m["pv_export_kw"].to_numpy(dtype=np.float64)
    )
    return pd.DataFrame(
        {
            "timestamp": m["timestamp"],
            "delta_t_h": dt_h,
            "grid_import_kw": m["grid_import_kw"],
            "grid_export_kw": m["grid_export_kw"],
            "ess_charge_kw": m["ess_charge_kw"],
            "ess_discharge_kw": m["ess_discharge_kw"],
            "ev_charge_kw": m["ev_total_charge_kw"],
            "ev_discharge_kw": m["ev_total_discharge_kw"],
            "building_flex_kw": np.zeros(n, dtype=np.float64),
            "pv_use_kw": pv_use,
            "pv_upper_kw": m["pv_available_kw"],
            "pv_curtail_kw": m["pv_curtailed_kw"],
            "load_shed_kw": m["unmet_load_kw"],
            "price_buy_yuan_per_kwh": m["buy_price"],
            "grid_import_limit_kw": m["grid_import_limit_kw"].to_numpy(dtype=np.float64),
        }
    )


def load_timeseries(
    coord_path: Path,
    baseline_aligned_path: Path,
    baseline_raw_path: Path,
    grid_limits_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = pd.read_csv(coord_path)
    c["timestamp"] = pd.to_datetime(c["timestamp"])
    dt = float(c["delta_t_h"].iloc[0]) if "delta_t_h" in c.columns else 0.25
    g = pd.read_csv(grid_limits_path)
    g["timestamp"] = pd.to_datetime(g["timestamp"])

    if baseline_aligned_path.is_file():
        b = pd.read_csv(baseline_aligned_path)
        b["timestamp"] = pd.to_datetime(b["timestamp"])
    else:
        if not baseline_raw_path.is_file():
            raise FileNotFoundError(
                f"缺少 baseline 对齐时序 {baseline_aligned_path}，且未找到原始时序 {baseline_raw_path}。"
                "请先运行 baseline 仿真或指定 --baseline-raw-timeseries。"
            )
        raw = pd.read_csv(baseline_raw_path)
        b = baseline_raw_to_aligned(raw, g, dt)
    return c, b


def load_cost_comparison(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_event_summary(path: Path | None) -> pd.DataFrame:
    if path is None or not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path)


def _event_id_display_zh(eid: str) -> str:
    m = {
        "stress_event_1": "压力事件一",
        "stress_event_2": "压力事件二",
        "stress_event_3": "压力事件三",
    }
    return m.get(eid, eid)


def plot_total_cost_comparison(df: pd.DataFrame, out_path: Path, title_zh: str) -> None:
    row = df.loc[df["cost_item"] == "Objective from solver"]
    if row.empty:
        raise ValueError("成本对比表中缺少 Objective from solver 行")
    c = float(row["coordinated_model_yuan"].iloc[0])
    b = float(row["baseline_yuan"].iloc[0])
    fig, ax = plt.subplots(figsize=(6.5, 4.2), layout="constrained")
    labels = ["协同调度", "基线（非协同）"]
    vals = [c, b]
    colors = ["#2a9d8f", "#e76f51"]
    bars = ax.bar(labels, vals, color=colors, width=0.45, edgecolor="#333", linewidth=0.6)
    ax.set_ylabel("总运行成本（元）")
    ax.set_title(title_zh)
    for bar, v in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(vals) * 0.02,
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
    ax.margins(y=0.12)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_cost_breakdown_comparison(df: pd.DataFrame, out_path: Path, title_zh: str) -> None:
    items = [
        "Grid import cost",
        "Grid export revenue",
        "PV curtailment penalty",
        "Load shed penalty",
        "Building shift penalty",
        "ESS degradation cost",
        "EV degradation cost",
        "Carbon cost",
    ]
    sub = df[df["cost_item"].isin(items)].copy()
    if len(sub) != len(items):
        missing = set(items) - set(sub["cost_item"])
        raise ValueError(f"成本分项缺失: {missing}")
    sub = sub.set_index("cost_item").loc[items].reset_index()
    y = np.arange(len(items))
    h = 0.35
    fig, ax = plt.subplots(figsize=(9.5, 5.8), layout="constrained")
    cvals = sub["coordinated_model_yuan"].to_numpy(dtype=float)
    bvals = sub["baseline_yuan"].to_numpy(dtype=float)
    ax.barh(y - h / 2, cvals, height=h, label="协同调度", color="#2a9d8f", edgecolor="#222", linewidth=0.4)
    ax.barh(y + h / 2, bvals, height=h, label="基线（非协同）", color="#e76f51", edgecolor="#222", linewidth=0.4)
    ax.set_yticks(y, [obr.cost_item_label_zh(s) for s in items], fontsize=8)
    ax.set_xlabel("金额（元）")
    ax.set_title(title_zh)
    ax.legend(loc="lower right")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _event_spans(events_df: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, str, str]]:
    spans: list[tuple[pd.Timestamp, pd.Timestamp, str, str]] = []
    if events_df is None or events_df.empty:
        return spans
    for _, r in events_df.iterrows():
        eid = str(r.get("event_id", ""))
        w0 = pd.to_datetime(r["window_start"], utc=False)
        w1 = pd.to_datetime(r["window_end"], utc=False)
        note = str(r.get("scenario_note", ""))[:40]
        spans.append((w0, w1, eid, note))
    return spans


def plot_grid_import_timeseries(
    coord: pd.DataFrame,
    base: pd.DataFrame,
    events_df: pd.DataFrame,
    out_path: Path,
    title_zh: str,
) -> None:
    fig, ax = plt.subplots(figsize=(12.5, 4.8), layout="constrained")
    ts = coord["timestamp"]
    ax.plot(ts, coord["P_buy_kw"], label="协同：购电功率", color="#1d3557", lw=1.2)
    ax.plot(ts, base["grid_import_kw"], label="基线：购电功率", color="#e76f51", lw=1.0, alpha=0.9, linestyle="--")
    if "grid_import_limit_kw" in coord.columns:
        lim_c = coord["grid_import_limit_kw"]
    else:
        lim_c = base["grid_import_limit_kw"]
    ax.plot(ts, lim_c, label="购电功率上限", color="#6c757d", lw=1.0, linestyle=":")

    spans = _event_spans(events_df)
    stress_color = "#dee2e6"
    for i, (w0, w1, _eid, _) in enumerate(spans):
        ax.axvspan(w0, w1, color=stress_color, alpha=0.35, label="典型压力时段（浅色阴影）" if i == 0 else None)

    ax.set_ylabel("功率（kW）")
    ax.set_xlabel("时间（月-日，15 min 步长）")
    ax.set_title(title_zh)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=6))
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
    ax.legend(loc="upper left", ncol=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _pick_event_row(events_df: pd.DataFrame, prefer: str) -> pd.Series | None:
    if events_df is None or events_df.empty:
        return None
    hit = events_df[events_df["event_id"].astype(str) == prefer]
    if not hit.empty:
        return hit.iloc[0]
    return events_df.iloc[-1]


def plot_event_resource_response(
    coord: pd.DataFrame,
    base: pd.DataFrame,
    events_df: pd.DataFrame,
    prefer_event: str,
    out_path: Path,
    title_zh: str,
) -> None:
    row = _pick_event_row(events_df, prefer_event)
    if row is None:
        raise ValueError("无事件汇总表或表为空，无法绘制事件窗口图")
    w0 = pd.to_datetime(row["window_start"])
    w1 = pd.to_datetime(row["window_end"])
    eid = str(row["event_id"])
    csub = coord[(coord["timestamp"] >= w0) & (coord["timestamp"] < w1)].copy()
    bsub = base[(base["timestamp"] >= w0) & (base["timestamp"] < w1)].copy()
    if csub.empty or bsub.empty:
        raise ValueError(f"事件 {eid} 窗口内无时序数据")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.2), layout="constrained", sharex=True)
    ax1.axvspan(w0, w1, color="#ffe5d9", alpha=0.4, label="压力事件窗口（浅色）")
    ax1.plot(csub["timestamp"], csub["P_buy_kw"], label="协同：购电", color="#1d3557", lw=1.5)
    ax1.plot(bsub["timestamp"], bsub["grid_import_kw"], label="基线：购电", color="#e76f51", lw=1.2, linestyle="--")
    ax1.plot(csub["timestamp"], csub["P_ess_dis_kw"], label="协同：储能放电", color="#457b9d", lw=1.2)
    ax1.plot(bsub["timestamp"], bsub["ess_discharge_kw"], label="基线：储能放电", color="#457b9d", lw=1.0, alpha=0.55, linestyle=":")
    ax1.plot(csub["timestamp"], csub["P_ev_dis_total_kw"], label="协同：电动汽车放电", color="#9b59b6", lw=1.2)
    ax1.plot(bsub["timestamp"], bsub["ev_discharge_kw"], label="基线：电动汽车放电", color="#9b59b6", lw=1.0, alpha=0.55, linestyle=":")
    ax1.set_ylabel("功率（kW）")
    ax1.set_title(f"{title_zh}\n（{_event_id_display_zh(eid)}）")
    ax1.legend(loc="upper left", ncol=2, fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2.plot(csub["timestamp"], csub["building_flex_power_kw"], label="协同：建筑柔性功率", color="#2a9d8f", lw=1.3)
    ax2.plot(csub["timestamp"], csub["pv_curtail_kw"], label="协同：弃光功率", color="#f4a261", lw=1.2)
    ax2.plot(bsub["timestamp"], bsub["building_flex_kw"], label="基线：建筑柔性功率", color="#2a9d8f", lw=1.0, linestyle=":", alpha=0.7)
    ax2.plot(bsub["timestamp"], bsub["pv_curtail_kw"], label="基线：弃光功率", color="#f4a261", lw=1.0, linestyle=":", alpha=0.7)
    ax2.set_ylabel("功率（kW）")
    ax2.set_xlabel("时间（月-日 时:分，15 min 步长）")
    ax2.legend(loc="upper left", ncol=2, fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    plt.setp(ax2.get_xticklabels(), rotation=15, ha="right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def merge_grid_limit_on_coordinated(coord: pd.DataFrame, grid_limits_path: Path) -> pd.DataFrame:
    if "grid_import_limit_kw" in coord.columns:
        return coord
    g = pd.read_csv(grid_limits_path)
    g["timestamp"] = pd.to_datetime(g["timestamp"])
    out = coord.merge(g[["timestamp", "grid_import_limit_kw"]], on="timestamp", how="left")
    return out


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="问题1 协同 vs baseline 论文对比图")
    parser.add_argument(
        "--coord-timeseries",
        type=Path,
        default=root / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv",
    )
    parser.add_argument(
        "--baseline-timeseries",
        type=Path,
        default=root / "results" / "problem1_baseline" / "baseline_timeseries_aligned.csv",
    )
    parser.add_argument(
        "--baseline-raw-timeseries",
        type=Path,
        default=root / "results" / "problem1_baseline" / "baseline_timeseries_results.csv",
    )
    parser.add_argument(
        "--grid-limits",
        type=Path,
        default=root / "data" / "processed" / "final_model_inputs" / "grid_limits.csv",
    )
    parser.add_argument(
        "--cost-comparison",
        type=Path,
        default=root / "results" / "tables" / "objective_cost_comparison_fullweek.csv",
    )
    parser.add_argument(
        "--event-summary",
        type=Path,
        default=root / "results" / "tables" / "event_response_summary.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=root / "results" / "figures" / "problem1",
    )
    parser.add_argument("--event-id", type=str, default="stress_event_3", help="事件窗口图优先使用的事件 ID")
    args = parser.parse_args(argv)

    setup_matplotlib()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        df_cost = load_cost_comparison(args.cost_comparison)
    except OSError as exc:
        print(f"无法读取成本对比表: {exc}", file=sys.stderr)
        return 2

    try:
        coord, base = load_timeseries(
            args.coord_timeseries,
            args.baseline_timeseries,
            args.baseline_raw_timeseries,
            args.grid_limits,
        )
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"时序加载失败: {exc}", file=sys.stderr)
        return 2

    coord = merge_grid_limit_on_coordinated(coord, args.grid_limits)
    events_df = load_event_summary(args.event_summary)

    plot_total_cost_comparison(df_cost, args.out_dir / "total_cost_comparison.png", "全周总运行成本对比")
    plot_cost_breakdown_comparison(df_cost, args.out_dir / "cost_breakdown_comparison.png", "成本分项对比")
    plot_grid_import_timeseries(
        coord,
        base,
        events_df,
        args.out_dir / "grid_import_timeseries_comparison.png",
        "全周电网购电功率时序对比",
    )
    try:
        plot_event_resource_response(
            coord,
            base,
            events_df,
            args.event_id,
            args.out_dir / "stress_event_3_resource_response.png",
            "特殊事件窗口内多资源协同响应",
        )
    except ValueError as exc:
        print(f"事件窗口图跳过: {exc}", file=sys.stderr)

    print("已生成:", args.out_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
