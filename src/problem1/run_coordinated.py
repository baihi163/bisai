"""
问题1 确定性协同调度主模型 — 入口脚本。

流程：加载数据 → 构建 Gurobi 模型 → 求解 → 导出结果；若不可行则尝试 IIS 诊断。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许以脚本方式运行：python src/problem1/run_coordinated.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.problem1 import config  # noqa: E402
from src.problem1.coordinated_model import (  # noqa: E402
    apply_gurobi_params,
    build_gurobi_model,
    solve_model,
    write_iis,
)
from src.problem1.data_loader import (  # noqa: E402
    crop_horizon_and_sessions,
    load_coordinated_inputs,
    validate_inputs,
)
from src.problem1.result_exporter import export_all  # noqa: E402
from src.problem1.utils import ensure_dir, gurobipy_available, resolve_under_root  # noqa: E402

try:
    from gurobipy import GRB  # noqa: E402
except ImportError:
    GRB = None


def main() -> int:
    """主函数：返回进程退出码。"""
    parser = argparse.ArgumentParser(description="问题1 协同调度主模型（Gurobi）")
    parser.add_argument(
        "--max-periods",
        type=int,
        default=None,
        help="仅调度前 N 个时段（用于小规模许可证调试；默认全时段）",
    )
    parser.add_argument(
        "--max-ev-sessions",
        type=int,
        default=None,
        help="仅保留前 K 条 EV 会话（默认可选；与 --max-periods 联用）",
    )
    args = parser.parse_args()

    if not gurobipy_available():
        print("错误：未安装 gurobipy。请先安装 Gurobi Python 接口并配置许可证。")
        print("备选：可参考 README_problem1_coordinated.md 中的 Pyomo 迁移说明。")
        return 2

    root = _REPO_ROOT
    data = load_coordinated_inputs(project_root=root)
    if args.max_periods is not None or args.max_ev_sessions is not None:
        data = crop_horizon_and_sessions(
            data,
            max_periods=args.max_periods,
            max_ev_sessions=args.max_ev_sessions,
        )
    validate_inputs(data)

    out_dir = resolve_under_root(root, config.OUTPUT_DIR_REL)
    ensure_dir(out_dir)

    model, art = build_gurobi_model(data)
    apply_gurobi_params(model)
    solve_model(model)

    status = model.Status
    status_name = {
        GRB.LOADED: "LOADED",
        GRB.OPTIMAL: "OPTIMAL",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.UNBOUNDED: "UNBOUNDED",
        GRB.CUTOFF: "CUTOFF",
        GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
        GRB.NODE_LIMIT: "NODE_LIMIT",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
        GRB.INTERRUPTED: "INTERRUPTED",
        GRB.NUMERIC: "NUMERIC",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
        GRB.INPROGRESS: "INPROGRESS",
        GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
    }.get(status, f"UNKNOWN({status})")

    print(f"求解结束：Status={status} ({status_name})")
    sol_count = int(getattr(model, "SolCount", 0) or 0)
    export_ok = status == GRB.OPTIMAL or (
        status in (GRB.TIME_LIMIT, GRB.SUBOPTIMAL) and sol_count > 0
    )
    if export_ok:
        if status != GRB.OPTIMAL:
            print("警告：非最优终止（如时间限制/次优），结果供参考。")
        print(f"目标函数值（元）: {model.ObjVal:.6g}")
        if getattr(model, "IsMIP", 0):
            print(f"最优性间隙: {getattr(model, 'MIPGap', 0.0):.6g}")
        paths = export_all(out_dir, data, art, float(model.ObjVal))
        for _, p in paths.items():
            print(f"已写出: {p}")
    else:
        print("未获得可行解。")
        if status == GRB.INFEASIBLE or status == GRB.INF_OR_UNBD:
            iis_path = str(out_dir / "coordinated_model_infeasible.ilp")
            try:
                write_iis(model, iis_path)
                print(f"IIS 已写入: {iis_path}")
            except Exception as exc:  # pragma: no cover
                print(f"IIS 写出失败: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
