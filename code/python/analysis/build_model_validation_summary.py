# -*- coding: utf-8 -*-
"""
统一结果汇总：从 p2 单次目录、p1 对账/时序、baseline KPI/全周对账 抽取可比字段，
写入 ``results/tables/model_validation_summary.{csv,json}``，
并默认写入 ``model_validation_summary_table_example.md``（baseline / p1 / p2 对比表示例）。

设计说明（摘要）
----------------
1. **p2（problem2_lifecycle/single_run/<tag>）**
   读 ``objective_breakdown.json``、``operational_metrics.json``、``run_meta.json``；
   ``operation_cost`` 与 ``recover_penalty_cost`` 与 p2 定义一致；``objective_total`` 取 ``objective_from_solver``。

2. **p1（p_1_5_ultimate）**
   优先读英文 ``objective_reconciliation_fullweek.csv``（若存在）；否则读中文
   ``objective_reconciliation_appendix.csv``，通过 ``objective_reconciliation.COST_ITEM_ROWS``
   与 ``cost_item_label_zh`` 建立 成本项中文 → 内部键 映射。
   ``operation_cost`` = 购电 − 售电收益 + 碳 + 弃光惩罚 + 建筑移位惩罚 + 切负荷（不含 ESS/EV 退化、无 recover）。
   ``objective_total`` = ``objective_from_solver``。
   能量类自 ``results/problem1_ultimate/p_1_5_timeseries.csv`` 按 ``delta_t_h`` 积分；缺失则填 null。
   求解器状态/耗时 p1 脚本未落盘，统一 null。

3. **baseline**
   读 ``objective_reconciliation_baseline_fullweek.csv``（与 p1 全周表同结构）及 ``baseline_kpi_summary.json``；
   能量优先用 KPI 中已有汇总字段；``recover_penalty_cost`` 恒 null。
   若无全周对账表，则仅从 KPI 填能量与 ``total_cost_cny`` 作为 ``objective_total`` 近似（脚注：不含退化等时需论文说明）。

用法
----
  python code/python/analysis/build_model_validation_summary.py
  python code/python/analysis/build_model_validation_summary.py --repo-root D:/数维杯比赛
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import math
from pathlib import Path
from typing import Any

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_PROBLEM1_DIR = (_HERE.parent / "problem_1").resolve()

OUTPUT_COLUMNS: list[str] = [
    "model_name",
    "run_tag",
    "objective_total",
    "operation_cost",
    "carbon_cost",
    "ess_deg_cost",
    "ev_deg_cost",
    "recover_penalty_cost",
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
]

# Markdown 对比表：每模型优先选取的 run_tag（缺失则退化为该 model 的首行）
_COMPARISON_CANONICAL: list[tuple[str, str]] = [
    ("baseline_noncooperative", "baseline_default"),
    ("p1_coordinated", "p1_ultimate_latest"),
    ("p2_lifecycle", "model_check_p2"),
]

# 对比表示例列（全量过宽，便于论文/附录引用）
_COMPARISON_MD_COLUMNS: list[str] = [
    "model_name",
    "run_tag",
    "objective_total",
    "operation_cost",
    "carbon_cost",
    "ess_deg_cost",
    "ev_deg_cost",
    "recover_penalty_cost",
    "grid_import_energy_kwh",
    "ev_charge_energy_kwh",
    "solver_status",
    "solve_time_seconds",
]


def _load_objective_reconciliation():
    path = _PROBLEM1_DIR / "objective_reconciliation.py"
    spec = importlib.util.spec_from_file_location("objective_reconciliation", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _empty_row(model_name: str, run_tag: str) -> dict[str, Any]:
    r: dict[str, Any] = {k: None for k in OUTPUT_COLUMNS}
    r["model_name"] = model_name
    r["run_tag"] = run_tag
    return r


def _normalize_scalar(v: Any) -> Any:
    """空串 / NaN → None，便于 CSV/JSON 统一缺失语义。"""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


def normalize_output_row(row: dict[str, Any]) -> dict[str, Any]:
    """保证仅含 OUTPUT_COLUMNS，且缺失为 None（JSON null / CSV 显式 null）。"""
    return {k: _normalize_scalar(row.get(k)) for k in OUTPUT_COLUMNS}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_reconciliation_csv_en(path: Path) -> dict[str, float] | None:
    """英文 cost_item / value_yuan 表 -> 内部键（与 COST_ITEM_ROWS 第二列一致）。"""
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except OSError:
        return None
    if "cost_item" not in df.columns or "value_yuan" not in df.columns:
        return None
    obr = _load_objective_reconciliation()
    en_to_key = {en: key for en, key in obr.COST_ITEM_ROWS}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        en = str(row["cost_item"]).strip()
        if en in en_to_key:
            try:
                out[en_to_key[en]] = float(row["value_yuan"])
            except (TypeError, ValueError):
                pass
    return out if out else None


def _parse_appendix_csv_zh(path: Path) -> dict[str, float] | None:
    """附录中文两列表 -> 内部键。"""
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except OSError:
        return None
    cols = [str(c).strip() for c in df.columns]
    if len(cols) < 2:
        return None
    obr = _load_objective_reconciliation()
    zh_to_key: dict[str, str] = {}
    for en_label, key in obr.COST_ITEM_ROWS:
        zh = obr.cost_item_label_zh(en_label)
        zh_to_key[zh] = key
    c0, c1 = df.columns[0], df.columns[1]
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        zh = str(row[c0]).strip()
        if zh not in zh_to_key:
            continue
        try:
            out[zh_to_key[zh]] = float(str(row[c1]).replace(",", ""))
        except (TypeError, ValueError):
            pass
    return out if out else None


def _p1_costs_from_any_appendix(repo: Path) -> dict[str, float] | None:
    tables = repo / "results" / "tables"
    fw = tables / "objective_reconciliation_fullweek.csv"
    ap = tables / "objective_reconciliation_appendix.csv"
    costs = _parse_reconciliation_csv_en(fw)
    if costs is None:
        costs = _parse_appendix_csv_zh(ap)
    return costs


def _operation_cost_from_components(costs: dict[str, float]) -> float | None:
    """与 p2.operation_cost 同口径：不含 ESS/EV 退化、不含 recover（p1/baseline 无 recover）。"""
    keys = [
        "grid_import_cost",
        "grid_export_revenue",
        "carbon_cost",
        "pv_curtail_penalty",
        "building_shift_penalty",
        "load_shed_penalty",
    ]
    if not all(k in costs for k in keys):
        return None
    return (
        float(costs["grid_import_cost"])
        - float(costs["grid_export_revenue"])
        + float(costs["carbon_cost"])
        + float(costs["pv_curtail_penalty"])
        + float(costs["building_shift_penalty"])
        + float(costs["load_shed_penalty"])
    )


_ENERGY_KEYS = (
    "grid_import_energy_kwh",
    "grid_export_energy_kwh",
    "pv_curtail_energy_kwh",
    "load_shed_energy_kwh",
    "ess_charge_energy_kwh",
    "ess_discharge_energy_kwh",
    "ev_charge_energy_kwh",
    "ev_discharge_energy_kwh",
)


def _aggregate_p1_timeseries(ts_path: Path) -> dict[str, float | None]:
    empty = {k: None for k in _ENERGY_KEYS}
    if not ts_path.is_file():
        return empty
    try:
        df = pd.read_csv(ts_path, encoding="utf-8-sig")
    except OSError:
        return empty
    if "delta_t_h" not in df.columns:
        return empty
    dt = float(df["delta_t_h"].iloc[0])

    def col_sum(name: str) -> float | None:
        if name not in df.columns:
            return None
        return float((pd.to_numeric(df[name], errors="coerce").fillna(0.0) * dt).sum())

    return {
        "grid_import_energy_kwh": col_sum("P_buy_kw"),
        "grid_export_energy_kwh": col_sum("P_sell_kw"),
        "pv_curtail_energy_kwh": col_sum("pv_curtail_kw"),
        "load_shed_energy_kwh": col_sum("P_shed_total_kw"),
        "ess_charge_energy_kwh": col_sum("P_ess_ch_kw"),
        "ess_discharge_energy_kwh": col_sum("P_ess_dis_kw"),
        "ev_charge_energy_kwh": col_sum("P_ev_ch_total_kw"),
        "ev_discharge_energy_kwh": col_sum("P_ev_dis_total_kw"),
    }


def row_from_p2_single_run(repo: Path, run_dir: Path) -> dict[str, Any]:
    tag = run_dir.name
    row = _empty_row("p2_lifecycle", tag)
    bd = _read_json(run_dir / "objective_breakdown.json")
    met = _read_json(run_dir / "operational_metrics.json")
    meta = _read_json(run_dir / "run_meta.json")
    if bd:
        row["objective_total"] = bd.get("objective_from_solver")
        row["operation_cost"] = bd.get("operation_cost")
        row["carbon_cost"] = bd.get("carbon_cost")
        row["ess_deg_cost"] = bd.get("ess_degradation_cost")
        row["ev_deg_cost"] = bd.get("ev_degradation_cost")
        row["recover_penalty_cost"] = bd.get("recover_penalty_cost")
    if met:
        row["grid_import_energy_kwh"] = met.get("grid_import_energy_kwh")
        row["grid_export_energy_kwh"] = met.get("grid_export_energy_kwh")
        row["pv_curtail_energy_kwh"] = met.get("pv_curtail_energy_kwh")
        row["load_shed_energy_kwh"] = met.get("load_shed_energy_kwh")
        row["ess_charge_energy_kwh"] = met.get("ess_charge_energy_kwh")
        row["ess_discharge_energy_kwh"] = met.get("ess_discharge_energy_kwh")
        row["ev_charge_energy_kwh"] = met.get("ev_charge_energy_kwh")
        row["ev_discharge_energy_kwh"] = met.get("ev_discharge_energy_kwh")
    if meta:
        row["solver_status"] = meta.get("solver_status")
        row["solve_time_seconds"] = meta.get("solve_time_seconds")
    return row


def row_from_p1(repo: Path, run_tag: str = "p1_ultimate_latest") -> dict[str, Any]:
    row = _empty_row("p1_coordinated", run_tag)
    costs = _p1_costs_from_any_appendix(repo)
    if costs:
        row["objective_total"] = costs.get("objective_from_solver")
        row["operation_cost"] = _operation_cost_from_components(costs)
        row["carbon_cost"] = costs.get("carbon_cost")
        row["ess_deg_cost"] = costs.get("ess_degradation_cost")
        row["ev_deg_cost"] = costs.get("ev_degradation_cost")
        row["recover_penalty_cost"] = None
    ts_path = repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv"
    ene = _aggregate_p1_timeseries(ts_path)
    row.update(ene)
    return row


def row_from_baseline(repo: Path, run_tag: str = "baseline_default") -> dict[str, Any]:
    row = _empty_row("baseline_noncooperative", run_tag)
    tables = repo / "results" / "tables"
    base_dir = repo / "results" / "problem1_baseline"
    costs = _parse_reconciliation_csv_en(tables / "objective_reconciliation_baseline_fullweek.csv")
    if costs:
        row["objective_total"] = costs.get("objective_from_solver")
        row["operation_cost"] = _operation_cost_from_components(costs)
        row["carbon_cost"] = costs.get("carbon_cost")
        row["ess_deg_cost"] = costs.get("ess_degradation_cost")
        row["ev_deg_cost"] = costs.get("ev_degradation_cost")
    kpi_path = base_dir / "baseline_kpi_summary.json"
    kpi = _read_json(kpi_path)
    if kpi:
        if row["objective_total"] is None:
            row["objective_total"] = kpi.get("total_cost_cny")
        row["grid_import_energy_kwh"] = kpi.get("total_grid_import_kwh")
        row["grid_export_energy_kwh"] = kpi.get("total_grid_export_kwh")
        row["pv_curtail_energy_kwh"] = kpi.get("total_pv_curtailed_kwh")
        row["load_shed_energy_kwh"] = kpi.get("total_unmet_load_kwh")
        row["ess_charge_energy_kwh"] = kpi.get("ess_total_charge_throughput_kwh")
        row["ess_discharge_energy_kwh"] = kpi.get("ess_total_discharge_throughput_kwh")
        row["ev_charge_energy_kwh"] = kpi.get("total_ev_charge_kwh")
        row["ev_discharge_energy_kwh"] = 0.0
    row["recover_penalty_cost"] = None
    return row


def discover_p2_runs(repo: Path) -> list[Path]:
    root = repo / "results" / "problem2_lifecycle" / "single_run"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "objective_breakdown.json").is_file():
            out.append(d)
    return out


def build_rows(repo: Path, *, include_p1: bool, include_baseline: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in discover_p2_runs(repo):
        rows.append(row_from_p2_single_run(repo, d))
    if include_p1:
        costs = _p1_costs_from_any_appendix(repo)
        ts_ok = (repo / "results" / "problem1_ultimate" / "p_1_5_timeseries.csv").is_file()
        if costs is not None or ts_ok:
            rows.append(row_from_p1(repo))
    if include_baseline:
        kpi = repo / "results" / "problem1_baseline" / "baseline_kpi_summary.json"
        bcsv = repo / "results" / "tables" / "objective_reconciliation_baseline_fullweek.csv"
        if kpi.is_file() or bcsv.is_file():
            rows.append(row_from_baseline(repo))
    return rows


def _md_escape_cell(v: Any) -> str:
    if v is None:
        return "null"
    s = str(v).replace("|", "\\|").replace("\n", " ")
    return s


def markdown_comparison_example(rows: list[dict[str, Any]]) -> str:
    """baseline / p1 / p2 各一行对比表示例（Markdown）。"""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    first_by_model: dict[str, dict[str, Any]] = {}
    for r in rows:
        mn = str(r.get("model_name", ""))
        rt = str(r.get("run_tag", ""))
        by_key[(mn, rt)] = r
        if mn and mn not in first_by_model:
            first_by_model[mn] = r

    picked: list[dict[str, Any]] = []
    for mn, prefer_tag in _COMPARISON_CANONICAL:
        r = by_key.get((mn, prefer_tag)) or first_by_model.get(mn)
        if r is not None:
            picked.append(r)

    if not picked:
        return "# model_validation_summary — 对比表示例\n\n（无可用行）\n"

    header = "| " + " | ".join(_COMPARISON_MD_COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in _COMPARISON_MD_COLUMNS) + " |"
    lines = [
        "# model_validation_summary — 对比表示例",
        "",
        "由 `build_model_validation_summary.py` 生成；每模型优先 `run_tag`："
        + "、".join(f"`{a}/{b}`" for a, b in _COMPARISON_CANONICAL) + "。",
        "",
        header,
        sep,
    ]
    for r in picked:
        cells = [_md_escape_cell(r.get(c)) for c in _COMPARISON_MD_COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 p2 / p1 / baseline 校验用指标表")
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT, help="仓库根目录")
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help="输出 CSV（默认 <repo>/results/tables/model_validation_summary.csv）",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="输出 JSON（默认 <repo>/results/tables/model_validation_summary.json）",
    )
    parser.add_argument("--skip-p1", action="store_true", help="不包含 p1 行")
    parser.add_argument("--skip-baseline", action="store_true", help="不包含 baseline 行")
    parser.add_argument(
        "--out-md",
        type=Path,
        default=None,
        help="Markdown 对比表示例（默认 <repo>/results/tables/model_validation_summary_table_example.md）",
    )
    parser.add_argument("--no-md", action="store_true", help="不写入 Markdown 对比表")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    out_csv = (args.out_csv or (repo / "results" / "tables" / "model_validation_summary.csv")).resolve()
    out_json = (args.out_json or (repo / "results" / "tables" / "model_validation_summary.json")).resolve()
    out_md = (
        None
        if args.no_md
        else (args.out_md or (repo / "results" / "tables" / "model_validation_summary_table_example.md")).resolve()
    )

    rows = build_rows(
        repo,
        include_p1=not args.skip_p1,
        include_baseline=not args.skip_baseline,
    )
    if not rows:
        print("未发现任何可汇总行（检查 results/problem2_lifecycle/single_run 等路径）。", file=sys.stderr)
        return 1

    rows = [normalize_output_row(r) for r in rows]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig", na_rep="null")
    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out_csv}")
    print(f"已写入: {out_json}")
    if out_md is not None:
        out_md.write_text(markdown_comparison_example(rows), encoding="utf-8")
        print(f"已写入: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
