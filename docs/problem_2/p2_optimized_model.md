# 问题 2 生命周期协同调度（优化版 `p2.py`）说明文档

本文档面向**论文附录**与**仓库技术说明**，对应实现脚本为 `code/python/problem_2/p2.py`。模型输入与问题 1 协同框架一致，经 `load_problem_data` 读入微网边界、建筑块、光伏上界、电价与 EV 会话等结构化数据。

---

## 1. 模型功能概述

本实现建立**单阶段、混合整数线性**的园区微网—电动汽车协同调度模型。目标函数综合**购售电与碳成本**、**弃光惩罚**、**建筑柔性负荷（移位与恢复）及切负荷惩罚**、**储能（ESS）与电动汽车吞吐退化成本**，并可对建筑**恢复功率**施加与功率成正比的**额外线性惩罚**。决策变量包括各时段购售电功率、光伏利用功率、ESS 充放电功率与荷电状态、建筑移位/恢复/削减功率及柔性 backlog、各 EV 在站时段的充放电功率与能量状态等；对允许车网互动（V2B）的会话，通过二进制变量施加充放电互斥。模型由 **PuLP** 建模、**CBC** 求解，支持单次全周期求解与**对角退化权重扫描**；求解结束后导出目标分项重算、运行指标、按车型汇总的 EV 统计、时序功率—能量轨迹及求解元数据，便于与论文图表及复现实验对齐。

---

## 2. 相比基础版 problem2 的增强点

| 增强项 | 技术说明 | 工程意义 |
|--------|----------|----------|
| ESS 终端 SOC 模式 | 支持 `ge`（周期末 SOC 不低于初值）与 `eq`（周期末 SOC 等于初值）。 | 刻画“周期净储能公平”或“日初日末电量一致”等运行策略，避免为压低运行成本而无约束地透支储能，利于与寿命或调度可重复性论述衔接。 |
| EV 最小 SOC | 在站全时段约束能量不低于 `ev_min_soc_ratio ×` 电池额定容量。 | 保障用户可感知的最小可用电量与电池工作区下限，降低模型为套利而过度放电导致的不合理方案。 |
| 建筑恢复功率惩罚 | 在既有移位惩罚之外，对 `P_recover` 乘以系数 `recover_penalty_weight` 进入目标；分解中单列 `recover_penalty_cost`。 | 将“反弹用能/舒适度”与纯经济移位区分建模，抑制仅靠高恢复功率快速清偿 backlog 的路径，使柔性负荷轨迹更贴近实际运行顾虑。 |
| 求解元数据 | 将求解器状态、耗时、目标值及关键 CLI 策略参数等写入 `run_meta.json`（含展平的 `solve_meta`）。 | 支撑实验审计、附录参数表与多机复现，避免仅凭控制台输出追溯实验条件。 |
| EV 异质性实验 | 基于车型汇总表对会话级 `deg_cost` 进行覆盖或按车型缩放；可选仅允许指定车型保留放电与 V2B；预处理作用于 `fork` 后的工作副本。 | 在不改变 MILP 结构的前提下嵌入**车型级统计先验**与**车网互动策略消融**，并避免多次扫描污染共享数据。 |
| 权重扫描与汇总 | 对角扫描 `ess_deg_weight = ev_deg_weight = w`；可选不写各 `w` 子目录的 `timeseries.csv`；汇总同步至 `results/tables/`。 | 系统评估运行成本与寿命项的权衡曲线，控制磁盘与 I/O；便于与全仓结果表统一归档。 |

---

## 3. CLI 参数说明表

下列参数按功能分组；类型中“开关”表示 `store_true`，无需取值。默认值以脚本 `argparse` 为准。

### 3.1 目标与退化权重

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--ess-deg-weight` | float，`1.0` | ESS 退化项权重，乘 ESS 基元退化单价（元/kWh 吞吐口径）。 |
| `--ev-deg-weight` | float，`1.0` | EV 退化项权重，乘各会话 `deg_cost`。 |
| `--carbon-price` | float，`0.0` | 碳价系数，用于购电功率与电网碳强度乘积项。 |

### 3.2 储能、电动汽车与建筑柔性（优化版专有）

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--ess-terminal-mode` | `ge` / `eq`，默认 `ge` | ESS 周期末 SOC 相对初值：`ge` 为下界约束，`eq` 为等式约束。 |
| `--ev-min-soc-ratio` | float，`0.0` | EV 在站最低 SOC 比例，取值 `[0, 1]`。 |
| `--recover-penalty-weight` | float，`0.0` | 建筑恢复功率额外惩罚系数，须 `≥ 0`；与目标分解中 `recover_penalty_cost` 对账。 |

### 3.3 电网与数据加载

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--no-grid-mutex` | 开关 | 关闭购售电互斥（消融实验）。 |
| `--max-periods` | int，可选 | 截断调度时段数 `T`，传入数据加载层。 |
| `--no-skip-infeasible-ev` | 开关 | 禁止数据层跳过不可行 EV 会话（用于完整性或调试）。 |

### 3.4 求解器控制

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--time-limit` | int，`600` | CBC  wall-clock 时间上限（秒）。 |
| `--gap-rel` | float，`0.01` | CBC 相对最优间隙，须在 `(0, 1]`。 |
| `--solver-msg` | 开关 | 输出 CBC 求解日志。 |

### 3.5 结果路径、单次与扫描

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--results-dir` | Path | 结果根目录；默认相对仓库根为 `results/problem2_lifecycle`。 |
| `--run-tag` | str，可选 | 单次或扫描批次子目录名；缺省为 UTC 时间戳。 |
| `--scan-weights` | float 列表，可选 | 若出现则进入扫描模式；每个标量 `w` 同时作为 ESS 与 EV 退化权重。 |
| `--scan-no-timeseries` | 开关 | 扫描时不写入各 `w_*` 子目录下的 `timeseries.csv`。 |

### 3.6 EV 异质性与 V2B 消融（可选）

| 参数 | 类型/默认 | 说明 |
|------|-----------|------|
| `--ev-type-summary-csv` | Path，可选 | 车型汇总表（如 `problem2_ev_type_summary.csv`）；若单独指定则须为有效路径。 |
| `--ev-deg-summary-rule` | `none` / `override_mean` / `scale_to_type_mean`，默认 `none` | 与汇总表联用的退化映射规则；非 `none` 时必须同时提供有效 `--ev-type-summary-csv`。 |
| `--v2b-discharge-only-types` | str，可选 | 逗号分隔车型标识，仅该类会话保留放电与 V2B，其余强制仅充电侧可行。 |

---

## 4. 关键输出文件说明表

记 `{base}` 为 `--results-dir` 的绝对路径，`{tag}` 为 `--run-tag` 或默认时间戳标签。

| 路径（模式） | 说明 |
|--------------|------|
| `{base}/single_run/{tag}/` | 单次求解主输出目录。 |
| `{base}/single_run/{tag}/objective_breakdown.json`、`.csv` | 目标分项重算：含电网、碳、弃光、建筑惩罚、`recover_penalty_cost`、ESS/EV 退化、`operation_cost`、`objective_recomputed` 及与求解器目标的绝对偏差等。 |
| `{base}/single_run/{tag}/operational_metrics.json`、`.csv` | 购售电能量、弃光、ESS/EV 吞吐、切负荷能量等标量指标。 |
| `{base}/single_run/{tag}/ev_type_summary.csv`、`.json` | 按 `ev_type` 聚合的充放电量、退化货币成本及 V2B 参与统计。 |
| `{base}/single_run/{tag}/run_meta.json` | 运行配置与求解元数据（策略参数与 `solve_meta` 展平字段）。 |
| `{base}/single_run/{tag}/timeseries.csv` | 单次默认导出全时序解；扫描模式下各 `w_*` 子目录是否写出取决于 `--scan-no-timeseries`。 |
| `{base}/tables/single_run_{tag}.csv` | 单次摘要一行，便于多批次对比。 |
| `{base}/scans/scan_{tag}/weight_scan_summary.csv`、`.json` | 权重扫描汇总。 |
| `{base}/scans/scan_{tag}/w_*/` | 各权重水平下的完整导出子目录（结构与单次一致）。 |
| `{base}/tables/weight_scan_summary_{tag}.csv` | 扫描汇总在结果根目录 `tables` 下的副本。 |
| `results/tables/problem2_weight_scan_{tag}.csv`、`.json` | 仓库级汇总副本，便于与论文表格及其他问题结果并列管理。 |

---

## 5. 推荐的主实验命令

在**仓库根目录**执行。下列命令采用与论文主实验一致的**推荐默认**：储能周期末 SOC **等于**初值（`eq`）、EV 最低 SOC **10%**、恢复惩罚系数 **0.01**、ESS/EV 退化权重均为 **1**；可按算力调整 `--time-limit` 与 `--gap-rel`。

**主实验（推荐默认参数）**

```bash
python code/python/problem_2/p2.py --run-tag main_exp --ess-deg-weight 1 --ev-deg-weight 1 --ess-terminal-mode eq --ev-min-soc-ratio 0.1 --recover-penalty-weight 0.01 --time-limit 600 --gap-rel 0.01
```

**主实验 + 车型汇总退化（路径按本机数据修改）**

```bash
python code/python/problem_2/p2.py --run-tag main_exp_evhet --ess-deg-weight 1 --ev-deg-weight 1 --ess-terminal-mode eq --ev-min-soc-ratio 0.1 --recover-penalty-weight 0.01 --ev-type-summary-csv results/tables/problem2_ev_type_summary.csv --ev-deg-summary-rule override_mean --time-limit 600 --gap-rel 0.01
```

---

## 6. 推荐的权重扫描命令

在仓库根目录执行，用于生成退化权重敏感性曲线；大模型可配合 `--max-periods` 缩短 horizon，或略放宽 `--gap-rel`、缩短 `--time-limit` 做预扫描。

```bash
python code/python/problem_2/p2.py --run-tag lambda_scan --ess-deg-weight 1 --ev-deg-weight 1 --ess-terminal-mode eq --ev-min-soc-ratio 0.1 --recover-penalty-weight 0.01 --scan-weights 0 0.25 0.5 1 2 --scan-no-timeseries --time-limit 300 --gap-rel 0.02
```

扫描完成后，建议核对：`results/tables/problem2_weight_scan_lambda_scan.csv` 与同名的 `.json`。

---

## 7. 论文中可直接使用的「模型描述」段落

本文研究园区级微网与多辆并网电动汽车的**日前协同调度**问题。以离散时间集合上的购售电功率、光伏利用功率、储能充放电功率与荷电状态、建筑可移位与可恢复及可削减负荷功率，以及各车辆在站时段的充放电功率与能量状态为主要决策变量，在功率平衡、设备技术限制与电动汽车离场能量需求等条件下，构建以**综合运行成本**（含可选碳成本）、**弃光惩罚**、**柔性负荷与切负荷惩罚**及**储能—电动汽车吞吐所致退化成本**为目标的优化模型；其中退化成本采用与充放电功率成线性关系的吞吐单价近似，以在可解性与寿命叙事之间取得平衡。目标函数中亦可对建筑恢复功率施加与功率成正比的额外惩罚项，用于反映反弹用能或用户舒适度等难以单独量纲化的运行顾虑。

在约束方面，储能荷电状态由分时段能量平衡递推，其周期末状态可约束为**不低于**或**严格等于**周期初值，以表征不同的日循环储能管理策略；电动汽车在站期间能量可约束为不低于额定容量的一定比例，以体现可用电量或安全运行下限。建筑柔性负荷通过移位、恢复功率与 backlog 状态变量描述，并施加期末 backlog 清零等条件；在允许车辆向建筑反向送电的情形下，对相应时段引入**充放电互斥**的混合整数约束，以避免非物理的大功率同时充放。上述问题经线性化后表述为混合整数线性规划，采用分支定界类算法在预设时间限制与最优性间隙内求解；求解后输出目标函数分项重算与关键运行指标，用于对比不同退化权重与策略参数下的调度方案。

---

*本文档与 `p2.py` 当前实现行为对齐；若命令行接口或导出逻辑变更，请以源码中 `argparse` 与 `export_bundle` 为准。*
