"""
问题 1 主模型结果的后处理：特殊事件窗口内的响应指标统计。

不修改 MILP 本体，仅读取 scenario_notes.csv 中的 stress_event_* 行、
对齐主模型导出的时序功率表，汇总能量/峰值并输出 CSV + 方法说明 Markdown。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd

_WINDOW_RE = re.compile(
    r"(?P<ymd>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<h1>\d{1,2}):(?P<m1>\d{2})\s*[-–]\s*"
    r"(?P<h2>\d{1,2}):(?P<m2>\d{2})"
)
_STRESS_ITEM_RE = re.compile(r"^stress_event_\d+$", re.IGNORECASE)


def _pick_scenario_notes(repo_root: Path) -> Path:
    raw = repo_root / "data" / "raw" / "scenario_notes.csv"
    if raw.is_file():
        return raw
    alt = repo_root / "B_data" / "scenario_notes.csv"
    if alt.is_file():
        return alt
    raise FileNotFoundError(
        f"未找到 scenario_notes.csv，已尝试: {raw} 与 {alt}"
    )


def parse_stress_events_from_scenario(scenario_csv: Path) -> pd.DataFrame:
    """
    读取 scenario_notes.csv（item,value），解析 stress_event_* 的时间窗。
    时间窗格式：值字符串开头为 `YYYY-MM-DD HH:MM-HH:MM`（同日结束时刻）。
    """
    df = pd.read_csv(scenario_csv)
    if not {"item", "value"}.issubset(df.columns):
        raise KeyError("scenario_notes.csv 需包含 item, value 列")

    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        item = str(r["item"]).strip()
        if not _STRESS_ITEM_RE.match(item):
            continue
        raw_val = str(r["value"]).strip()
        m = _WINDOW_RE.match(raw_val)
        if not m:
            raise ValueError(f"无法解析事件 {item} 的时间窗，值: {raw_val[:80]!r}...")
        ymd = m.group("ymd")
        h1, m1, h2, m2 = (
            int(m.group("h1")),
            int(m.group("m1")),
            int(m.group("h2")),
            int(m.group("m2")),
        )
        start = pd.Timestamp(f"{ymd} {h1:02d}:{m1:02d}:00")
        end = pd.Timestamp(f"{ymd} {h2:02d}:{m2:02d}:00")
        if end <= start:
            raise ValueError(f"事件 {item} 结束时刻应晚于开始: {raw_val}")
        note = raw_val[m.end() :].strip()
        rows.append(
            {
                "event_id": item,
                "window_start": start,
                "window_end": end,
                "scenario_note": note,
            }
        )
    if not rows:
        raise ValueError(f"{scenario_csv} 中未找到 stress_event_* 行")
    out = pd.DataFrame(rows).sort_values("event_id").reset_index(drop=True)
    return out


def _resolve_delta_t_hours(ts_df: pd.DataFrame, delta_t_hours: float | None) -> float:
    if delta_t_hours is not None and delta_t_hours > 0:
        return float(delta_t_hours)
    if "delta_t_h" in ts_df.columns:
        v = float(ts_df["delta_t_h"].iloc[0])
        if v > 0:
            return v
    tsc = pd.to_datetime(ts_df["timestamp"], errors="coerce")
    if len(tsc) >= 2 and tsc.notna().all():
        dt = (tsc.iloc[1] - tsc.iloc[0]).total_seconds() / 3600.0
        if dt > 0:
            return dt
    raise ValueError("无法确定 delta_t：请传入 delta_t_hours 或在时序表中提供 delta_t_h")


def summarize_events_for_timeseries(
    ts_df: pd.DataFrame,
    events_df: pd.DataFrame,
    *,
    delta_t_hours: float | None = None,
) -> pd.DataFrame:
    """对每个事件窗口汇总购售电、储能/EV 放电、柔性、削减、弃光等指标。"""
    required = {
        "timestamp",
        "P_buy_kw",
        "P_sell_kw",
        "P_ess_dis_kw",
        "P_ev_dis_total_kw",
        "building_flex_power_kw",
        "P_shed_total_kw",
        "pv_curtail_kw",
    }
    miss = required - set(ts_df.columns)
    if miss:
        raise KeyError(f"时序表缺少列: {sorted(miss)}")

    dt = _resolve_delta_t_hours(ts_df, delta_t_hours)
    ts = pd.to_datetime(ts_df["timestamp"])
    dfc = ts_df.copy()
    dfc["_ts"] = ts

    summaries: list[dict[str, Any]] = []
    for _, ev in events_df.iterrows():
        w0, w1 = ev["window_start"], ev["window_end"]
        mask = (dfc["_ts"] >= w0) & (dfc["_ts"] < w1)
        sub = dfc.loc[mask]
        n_p = int(len(sub))
        if n_p == 0:
            summaries.append(
                {
                    "event_id": ev["event_id"],
                    "window_start": w0.isoformat(),
                    "window_end": w1.isoformat(),
                    "scenario_note": ev["scenario_note"],
                    "n_periods_in_window": 0,
                    "total_grid_import_kwh": float("nan"),
                    "peak_grid_import_kw": float("nan"),
                    "total_grid_export_kwh": float("nan"),
                    "total_ess_discharge_kwh": float("nan"),
                    "total_ev_discharge_kwh": float("nan"),
                    "total_building_flex_energy_kwh": float("nan"),
                    "total_load_shed_kwh": float("nan"),
                    "total_pv_curtail_kwh": float("nan"),
                    "warning": "窗口内无时序点（检查 horizon 是否覆盖该事件日）",
                }
            )
            continue
        p_buy = sub["P_buy_kw"].astype(float)
        p_sell = sub["P_sell_kw"].astype(float)
        summaries.append(
            {
                "event_id": ev["event_id"],
                "window_start": w0.isoformat(),
                "window_end": w1.isoformat(),
                "scenario_note": ev["scenario_note"],
                "n_periods_in_window": n_p,
                "total_grid_import_kwh": float(p_buy.sum() * dt),
                "peak_grid_import_kw": float(p_buy.max()),
                "total_grid_export_kwh": float(p_sell.sum() * dt),
                "total_ess_discharge_kwh": float(sub["P_ess_dis_kw"].astype(float).sum() * dt),
                "total_ev_discharge_kwh": float(sub["P_ev_dis_total_kw"].astype(float).sum() * dt),
                "total_building_flex_energy_kwh": float(sub["building_flex_power_kw"].astype(float).sum() * dt),
                "total_load_shed_kwh": float(sub["P_shed_total_kw"].astype(float).sum() * dt),
                "total_pv_curtail_kwh": float(sub["pv_curtail_kw"].astype(float).sum() * dt),
                "warning": "",
            }
        )
    return pd.DataFrame(summaries)


def write_methodology_markdown(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# 问题 1 特殊事件响应分析：方法说明

## 1. 模型是否包含「事件触发」0-1 变量？

**不包含。** 协同调度 MILP 未为 `stress_event_1/2/3` 单独引入显式的事件触发变量或事件状态机。

## 2. 特殊事件在模型中如何体现？

场景说明见 `data/raw/scenario_notes.csv`（或备用的 `B_data/scenario_notes.csv`）中的 `stress_event_*` 行。对应扰动已**预先写入逐时输入数据**中，例如：

- **低辐照**：通过该时段 **光伏可用上限 `pv_upper(t)`**（或等效辐照–出力曲线）降低，压缩可行域；
- **进线受限**：通过该时段 **电网购电上限 `p_imp_max(t)`** 降低，在功率平衡下迫使优化器动用储能、EV、建筑柔性或弃光/削减等组合手段。

因此，事件是**时变边界参数**，而非优化过程中再判定的外生逻辑分支。

## 3. 「响应」如何理解？

在**统一目标函数与统一约束集**下，求解器对每个时段自动选择满足约束、使总成本（及惩罚项）最小的决策。事件窗口内的功率、能量轨迹即为模型对该时段参数集的自适应结果。

本模块 `event_response_analysis.py` 仅在**最优解导出之后**，按 `scenario_notes` 解析出的时间窗对轨迹做**后验统计**（购电量、峰值购电功率、售电与各类支撑功率对应的能量等），**不改变**原 MILP 的解。

## 4. 汇总指标口径（`event_response_summary.csv`）

- **总购电量 / 总售电量**：窗口内 `P_buy`、`P_sell` 对时间的积分（kWh），时间步长取自 `delta_t_h` 或相邻时间戳。
- **峰值购电功率**：窗口内 `P_buy` 的最大值（kW）。
- **总储能放电量 / 总 EV 放电量**：窗口内 `P_ess_dis`、各车放电功率合计对时间的积分（kWh）。
- **总建筑柔性调用量**：各建筑区块 **平移功率 + 恢复功率** 求和后对时间的积分（kWh），表征柔性资源的“动作强度”，不等价于净移位的单一方向能量。
- **总负荷削减量**：各区块削减功率对时间的积分（kWh）。
- **总弃光量**：`pv_upper - P_pv_use` 对时间的积分（kWh），即未利用的可发光伏。

## 5. 输出文件

- `event_response_summary.csv`：各 `stress_event_*` 窗口的汇总指标；
- 主程序在求得最优解时可同步写出 `p_1_5_timeseries.csv`（或与 `--timeseries` 指向的表结构一致），供本分析读取。

## 6. 与论文章节的对应关系

可在正文中表述为：**采用场景化时变参数刻画压力事件，在确定性多时段优化框架下实现隐式事件响应，事后按标注窗口提取运行指标。**
""",
        encoding="utf-8",
    )


def run_event_response_pipeline(
    *,
    repo_root: Path,
    timeseries_df: pd.DataFrame | None = None,
    timeseries_csv: Path | None = None,
    scenario_csv: Path | None = None,
    summary_csv: Path | None = None,
    methodology_md: Path | None = None,
    delta_t_hours: float | None = None,
) -> tuple[Path, Path]:
    """
    解析场景事件、汇总指标、写 event_response_summary.csv 与方法说明 Markdown。
    返回 (summary_csv, methodology_md) 绝对路径。
    """
    repo_root = repo_root.resolve()
    scen = Path(scenario_csv) if scenario_csv is not None else _pick_scenario_notes(repo_root)
    events = parse_stress_events_from_scenario(scen)

    if timeseries_df is not None:
        ts_df = timeseries_df.copy()
    elif timeseries_csv is not None:
        ts_df = pd.read_csv(Path(timeseries_csv))
    else:
        raise ValueError("必须提供 timeseries_df 或 timeseries_csv")

    summary = summarize_events_for_timeseries(ts_df, events, delta_t_hours=delta_t_hours)

    out_csv = (
        Path(summary_csv)
        if summary_csv is not None
        else repo_root / "results" / "tables" / "event_response_summary.csv"
    )
    out_md = (
        Path(methodology_md)
        if methodology_md is not None
        else repo_root / "docs" / "problem1_special_event_implicit_modeling.md"
    )
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_csv, index=False, encoding="utf-8-sig")
    write_methodology_markdown(out_md)
    return out_csv.resolve(), out_md.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="特殊事件窗口响应指标汇总（后处理）")
    parser.add_argument("--repo-root", type=Path, default=None, help="仓库根目录（默认从本文件推断）")
    parser.add_argument("--timeseries", type=Path, required=True, help="主模型导出的时序 CSV")
    parser.add_argument("--scenario", type=Path, default=None, help="scenario_notes.csv 路径")
    parser.add_argument("--summary-out", type=Path, default=None, help="event_response_summary.csv 输出路径")
    parser.add_argument("--methodology-out", type=Path, default=None, help="方法说明 Markdown 输出路径")
    parser.add_argument("--delta-t-hours", type=float, default=None, help="时段长度（小时），默认识别自表")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = args.repo_root.resolve() if args.repo_root else here.parents[2]
    try:
        csv_p, md_p = run_event_response_pipeline(
            repo_root=repo,
            timeseries_csv=args.timeseries,
            scenario_csv=args.scenario,
            summary_csv=args.summary_out,
            methodology_md=args.methodology_out,
            delta_t_hours=args.delta_t_hours,
        )
    except (FileNotFoundError, KeyError, ValueError, OSError) as exc:
        print(f"错误: {exc}", flush=True)
        return 2
    print(f"已写入: {csv_p}", flush=True)
    print(f"已写入: {md_p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
