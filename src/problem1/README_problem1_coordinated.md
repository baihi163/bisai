# 问题 1：确定性协同调度主模型（Python / Gurobi）

本目录实现 `docs/problem1_coordinated_model.md` 中的**协同调度 MILP/QP**，与 baseline 规则仿真相对照。

## 依赖

- Python 3.10+
- `gurobipy` + 有效 Gurobi 许可证
- `numpy`, `pandas`

```bash
pip install numpy pandas gurobipy
```

若无法安装 Gurobi，可仅参考本目录代码结构，自行用 Pyomo（`glpk`/`cbc`）重写 `coordinated_model.py` 中的变量与约束对应关系。

## 运行方式

在仓库根目录 `D:\数维杯比赛\` 下执行：

```bash
python -m src.problem1.run_coordinated
```

或：

```bash
python src/problem1/run_coordinated.py
```

### Gurobi 规模受限许可证（免费版）

若提示 `Model too large for size-limited license`，请缩小问题规模，例如：

```bash
python -m src.problem1.run_coordinated --max-periods 48 --max-ev-sessions 4
```

全时段、全会话需使用学术/商业许可证或 Gurobi 云端不受限实例。

## 输出

默认写入 `results/problem1_coordinated/`：

| 文件 | 说明 |
|------|------|
| `time_series_results.csv` | 逐时段购售电、储能、弃光、缺电、建筑柔性、负荷 |
| `ev_results.csv` | 各 EV 会话逐时段充放电与能量 |
| `summary_metrics.csv` | 总购售电量、弃光、缺电、峰值购电、目标值等 |

## 配置

编辑 `config.py`：

- `DEFAULT_PATHS`：输入 CSV/JSON 路径（相对仓库根）
- `ENABLE_ESS_CHARGE_DISCHARGE_MUTEX` / `ENABLE_GRID_IMPORT_EXPORT_MUTEX`
- `ENABLE_UNSERVED_LOAD`、`CURTAILMENT_PENALTY_*`、`UNSERVED_PENALTY_*`
- `ENABLE_FLEX_ENERGY_NEUTRAL`：是否施加 ΣΔP·Δt=0
- `FLEX_COST_MODE`：`abs_linear` 或 `quadratic`
- `GUROBI_PARAMS`：时间限制、MIPGap 等

## 不可行诊断

若模型不可行，入口脚本会尝试将 IIS 写入 `results/problem1_coordinated/coordinated_model_infeasible.ilp`，可用 Gurobi 打开分析。

## 问题 2 扩展

退化/寿命成本可在 `coordinated_model.py` 目标函数中 `ENABLE_DEGRADATION_COST_IN_OBJECTIVE` 分支内追加（当前占位）。
