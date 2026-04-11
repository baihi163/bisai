"""
仅从已生成的全周对账 CSV 重写对比表（不重新求解）。

前置：
  - results/tables/objective_reconciliation_fullweek.csv（协同，T=672 求解后）
  - results/tables/objective_reconciliation_baseline_fullweek.csv（baseline 仿真后）

用法（仓库根目录）:
  python code/python/problem_1/run_cost_comparison_fullweek.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_PROBLEM1 = Path(__file__).resolve().parent


def main() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location("objective_reconciliation", _PROBLEM1 / "objective_reconciliation.py")
    if spec is None or spec.loader is None:
        print("无法加载 objective_reconciliation", file=sys.stderr)
        return 2
    obr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obr)
    out = obr.try_write_fullweek_comparison(ROOT)
    if out is None:
        print(
            "缺少 objective_reconciliation_fullweek.csv 或 objective_reconciliation_baseline_fullweek.csv，"
            "未生成对比表。",
            file=sys.stderr,
        )
        return 1
    print(out[0])
    print(out[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
