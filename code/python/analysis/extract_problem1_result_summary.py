# -*- coding: utf-8 -*-
"""
从问题一既有输出抽取论文用结果摘要（不重写 p_1_5_ultimate.py）。

数据来源（按优先级）：
- 成本分项与总目标：`results/tables/objective_reconciliation_fullweek.csv`（英文）
  或 `objective_reconciliation_appendix.csv`（中文附录，与全周表二选一由脚本写入顺序决定，
  本脚本优先读 fullweek，缺失再读 appendix）。
- 能量类：`results/problem1_ultimate/p_1_5_timeseries.csv`（功率 × delta_t_h 积分）。

说明：p_1_5_ultimate 未将 CBC 求解状态与耗时落盘，本脚本对应字段恒为 null，
      若论文必需，可在模型脚本末尾增加几行 JSON 写出（本脚本不修改模型）。

用法：
  python code/python/analysis/extract_problem1_result_summary.py
  python code/python/analysis/extract_problem1_result_summary.py --repo-root D:/数维杯比赛
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

_OUTPUT_COLUMNS: list[str] = [
    "model_name",
    "run_tag",
    "objective_total",
    "operation_cost",
    "carbon_cost",
    "ess_degradation_cost",
    "ev_degradation_cost",
    "grid_import_energy_kwh",
    "grid_export_energy_kwh",
    "pv_curtail_energy_kwh",
    "load_shed_energy_kwh",
    "ess_charge_energy_kwh",
    "ess_discharge_energy_kwh",
    "ev_charge_energy_kwh",
    "ev_discharge_energy_kwh",
    "solver_status",
    "solve_time_seconds",
    "source_reconciliation",
    "source_timeseries",
]


def _load_build_model_validation_summary():
    path = _HERE / "build_model_validation_summary.py"
    spec = importlib.util.spec_from_file_location("build_model_validation_summary", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_problem1_row(repo: Path) -> dict[str, Any]:
    bms = _load_build_model_validation_summary()
    costs = bms._p1_costs_from_any_appendix(repo)
    ts_path = repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
    ene = bms._aggregate_p1_timeseries(ts_path)

    tables = repo / "results" / "tables"
    fw = tables / "objective_reconciliation_fullweek.csv"
    ap = tables / "objective_reconciliation_appendix.csv"
    if fw.is_file() and bms._parse_reconciliation_csv_en(fw):
        rec_src = str(fw.relative_to(repo)) if fw.is_relative_to(repo) else str(fw)
    elif ap.is_file() and bms._parse_appendix_csv_zh(ap):
        rec_src = str(ap.relative_to(repo)) if ap.is_relative_to(repo) else str(ap)
    else:
        rec_src = ""

    row: dict[str, Any] = {k: None for k in _OUTPUT_COLUMNS}
    row["model_name"] = "p1_coordinated"
    row["run_tag"] = "p1_ultimate_latest"
    row["source_timeseries"] = (
        str(ts_path.relative_to(repo)) if ts_path.is_file() and ts_path.is_relative_to(repo) else ""
    )
    row["source_reconciliation"] = rec_src

    if costs:
        row["objective_total"] = costs.get("objective_from_solver")
        row["operation_cost"] = bms._operation_cost_from_components(costs)
        row["carbon_cost"] = costs.get("carbon_cost")
        row["ess_degradation_cost"] = costs.get("ess_degradation_cost")
        row["ev_degradation_cost"] = costs.get("ev_degradation_cost")

    for k in (
        "grid_import_energy_kwh",
        "grid_export_energy_kwh",
        "pv_curtail_energy_kwh",
        "load_shed_energy_kwh",
        "ess_charge_energy_kwh",
        "ess_discharge_energy_kwh",
        "ev_charge_energy_kwh",
        "ev_discharge_energy_kwh",
    ):
        row[k] = ene.get(k)

    # 未落盘（见模块说明）
    row["solver_status"] = None
    row["solve_time_seconds"] = None
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="抽取问题一结果摘要 CSV/JSON")
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    out_dir = repo / "results" / "tables"
    out_csv = out_dir / "problem1_result_summary.csv"
    out_json = out_dir / "problem1_result_summary.json"

    try:
        row = build_problem1_row(repo)
    except Exception as exc:
        print(f"抽取失败: {exc}", file=sys.stderr)
        return 2

    if row.get("objective_total") is None and not (repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv").is_file():
        print("未找到对账表与时序表，无法生成摘要。", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row], columns=_OUTPUT_COLUMNS).to_csv(out_csv, index=False, encoding="utf-8-sig", na_rep="null")
    out_json.write_text(json.dumps([row], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out_csv}")
    print(f"已写入: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
