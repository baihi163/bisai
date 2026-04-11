# 模型评价证据摘要

> 本文档从仓库内**已落盘结果、汇总表与代码说明**抽取事实与数字，供后续人工归纳“优点 / 缺点 / 改进方向”。**不**给出定稿式“模型优缺点”论述。  
> 主要数据源：`results/tables/p1_baseline_vs_coordinated.csv`、`results/problem1_baseline/baseline_kpi_summary.json`、`results/tables/problem2_main_results.csv`、`results/problem2_lifecycle/scans/scan_auto_weight_scan/w_*`、`results/robustness/pv_scale_results.csv`、`results/robustness/ev_availability_results.csv`、`results/sensitivity/tornado_operation_cost_summary.csv`、`data/raw/scenario_notes.csv`、`code/python/problem_2/p_2_lifecycle_coordinated.py.code.py`、`code/python/problem_1/p_1_5_ultimate.py`、`operational_metrics.json` / `objective_breakdown.json` 等。

---

## 1. 协同调度相对基线方案的效果证据

### 1.1 数据来源与口径

- **基线**：非协同规则仿真 `baseline_noncooperative`（`results/tables/p1_baseline_vs_coordinated.csv` + `baseline_kpi_summary.json`）。  
- **协同（主场景）**：与表中 `p1_coordinated` 及问题二 `w=1` 主结果在**运行成本、购电量**上对齐（`38973.219` 元、`65263.896` kWh）；峰值为 `timeseries.csv` 中 `P_buy_kw` 最大（`results/tables/problem2_main_results.csv` 已交叉引用）。  
- **ESS 吞吐**：协同侧取 `operational_metrics.json` 中 `ess_throughput_kwh`（= 充、放电量算术平均，与全周能量闭合一致）；基线侧 KPI 仅有单向放电量 `456 kWh`、充电量 `0`，按同一吞吐定义取 **(0+456)/2 = 228 kWh** 以便与协同口径可比。  
- **EV 吞吐**：基线对 `baseline_timeseries_results.csv` 计算 `∑(|P_ev,ch|+|P_ev,dis|)·Δt` ≈ **2164.07 kWh**（以充电为主，放电接近 0）；协同取 `w=1` 的 `ev_throughput_kwh` = **1441.38 kWh**。

### 1.2 原始值与相对改进率（协同相对基线）

| 指标 | 基线 | 协同 (w=1) | 相对改进率* |
|------|------|------------|-------------|
| operation_cost（元） | 46304.527 | 38973.219 | **+15.83%**（协同更低） |
| grid_import_energy_kwh | 63760.265 | 65263.896 | **−2.36%**（协同购电量更高） |
| renewable_consumption_ratio | 1.0 | 1.0 | **0%**（两方案表中均为 1.0） |
| pv_curtail_energy_kwh | 0.0 | 0.0 | **0%** |
| peak_grid_purchase_kw | 624.8 | 863.7 | **−38.2%**（协同峰值更高，数值上为负向“改进”） |
| ess_throughput_kwh | 228（由 0/456 折合） | 6716.19 | 量级上升（约 **29.5×**） |
| ev_throughput_kwh | 2164.07（时序积分） | 1441.38 | **−33.4%**（总吞吐降低；协同含 V2G 放电，结构不同） |
| 可调负荷 | 基线时序无平移列；**building_shift_penalty**（元） | — / **338.70**（`w=1` objective_breakdown） | 基线无该项惩罚 |

\*相对改进率按 **(基线−协同)/基线×100%** 定义：购电 kWh、峰值功率在此处协同均**不优于**基线数值，需在论文中如实解释（分时电价、储能/EV/柔性套利等使**元/kWh 加权成本**下降）。

### 1.3 简短概括（事实层）

- 主场景下 **运行费用下降约 15.8%**（同上表）。  
- **全周购电量与峰值购电功率在数值上高于基线**，与“总 kWh 更低”类表述不可混用；若强调经济性，应绑定 **operation_cost** 与电价/柔性惩罚分项。  
- **弃光为 0、可再生就地消纳率表值为 1.0**（两方案相同）。  
- 协同方案 **ESS 吞吐显著激活**；**建筑柔性**在目标函数中产生明确惩罚项（约 338.7 元，`w=1`）。

---

## 2. 引入寿命损耗后的策略变化证据

### 2.1 权重扫描设定

- `scan_auto_weight_scan`：`ess_deg_weight` = `ev_deg_weight` ∈ {0, 1, 2}（`run_meta.json`）。  
- 汇总表：`results/problem2_lifecycle/tables/weight_scan_summary_auto_weight_scan.csv`；角色份额：`results/tables/problem2_weight_sensitivity_and_roles.csv`。

### 2.2 关键指标表（w = 0 / 1 / 2）

| w | operation_cost（元） | total_degradation_cost（元）* | ev_discharge_energy_kwh | ev_throughput_kwh | ess_throughput_kwh | peak_grid_purchase_kw |
|---|----------------------|-------------------------------|-------------------------|-------------------|--------------------|-----------------------|
| 0 | 38962.113 | 0.0 | 562.245 | 1615.300 | 6728.842 | 863.7 |
| 1 | 38973.219 | 494.237† | 397.235 | 1441.377 | 6716.194 | 863.7 |
| 2 | 38973.540 | 987.854‡ | 392.415 | 1436.296 | 6716.194 | 863.7 |

\*`total_degradation_cost` = `ess_degradation_cost` + `ev_degradation_cost`（`objective_breakdown.json`）；w=0 时两项均为 0。  
†369.391 + 124.846 ‡738.781 + 249.072  

**ESS 在车队中的角色份额（表中已有，非能量占比）**（`problem2_weight_sensitivity_and_roles.csv`）：

| w | ess_share_throughput_pct | ess_share_supply_pct |
|---|--------------------------|----------------------|
| 0 | 80.6415 | 91.9058 |
| 1 | 82.3308 | 94.1318 |
| 2 | 82.3821 | 94.1988 |

> 仓库中**未**单独给出 “store / peak share” 列名；若论文需要 peak 份额，需从时序后处理定义（例如分时段购电占比）另行计算。

### 2.3 策略变化：事实描述

- **寿命项权重由 0→1**：`objective_total` 上升约 **505.34**（38962.11→39467.46）；`operation_cost` 仅升 **~11.1 元**（+0.029% 相对 w=0），但 **EV 放电能量与总吞吐明显下降**（562→397 kWh；1615→1441 kWh），ESS 吞吐略降（6729→6716 kWh）。  
- **权重 1→2**：`total_degradation_cost` 约翻倍（494→988），**`operation_cost` 几乎不变**（38973.22→38973.54，+0.0008%）；EV/ESS 吞吐与峰值购电 **基本稳定**。  
- **peak_grid_purchase_kw** 三档均为 **863.7**，权重扫描未改变峰值购电（就已有结果文件而言）。

### 2.4 “变化大 / 变化小”归纳（仅对数值幅度）

- **变化大**：加权目标中 **退化货币化项**（w=0→2 从 0 增至约 988 元量级）；**EV 放电能量**（w=0→1 降幅大）。  
- **变化小**：**运行电费主项 operation_cost**（三档差异 <12 元，相对 w=0 约 0.03%）；**峰值购电**；**ESS 吞吐**（w≥0.5 后稳定在 ~6716 kWh）。

---

## 3. 灵敏度分析与鲁棒性证据

### 3.1 PV 扰动（`results/robustness/pv_scale_results.csv`）

| pv_scale | baseline_cost | coordinated_cost | cost_improvement_pct* | baseline_grid_kwh | coordinated_grid_kwh | grid_improvement_pct* | renewable_consumption_ratio（B / C） |
|----------|---------------|------------------|----------------------|-------------------|----------------------|-------------------------|----------------------------------------|
| 0.9 | 7362.318 | 6864.953 | **6.756%** | 9517.957 | 10097.793 | **−6.092%** | 1.0 / 1.0 |
| 1.0 | 7074.662 | 6577.297 | **7.030%** | 9131.495 | 9711.330 | **−6.350%** | 1.0 / 1.0 |
| 1.1 | 6787.007 | 6289.641 | **7.328%** | 8745.032 | 9324.868 | **−6.630%** | 1.0 / 1.0 |

\*`cost_improvement_pct` = (baseline_cost−coordinated_cost)/baseline_cost×100%；`grid_improvement_pct` 同式（当前数据下为**负**，表示协同购电 kWh 更高）。

### 3.2 EV 可用性缩放（`results/robustness/ev_availability_results.csv`，相对 **ev_power_scale=1.0**）

| ev_power_scale | operation_cost relative_change_pct | ev_throughput relative_change_pct | ev_discharge_energy relative_change_pct | ess_throughput relative_change_pct |
|----------------|--------------------------------------|-----------------------------------|----------------------------------------|-------------------------------------|
| 0.8 | **+0.115%** | **−1.792%** | **−4.983%** | **0%** |
| 1.2 | **−0.089%** | **+1.792%** | **+4.983%** | **0%** |

（协同侧 `peak_grid_purchase_kw`：0.8 与 1.0 为 889.7；1.2 为 895.2。）

### 3.3 寿命权重对 operation_cost（相对 **w=1**）

| 对比 | operation_cost（元） | relative_change_pct |
|------|------------------------|---------------------|
| w=0 | 38962.113 | **−0.0285%** |
| w=1 | 38973.219 | 0% |
| w=2 | 38973.540 | **+0.00082%** |

### 3.4 龙卷风图排序（`results/sensitivity/tornado_operation_cost_summary.csv`）

| parameter | low_scenario | high_scenario | low_change_pct | high_change_pct | max_abs_change_pct |
|-----------|--------------|---------------|----------------|-----------------|-------------------|
| PV出力缩放 | PV=0.9 | PV=1.1 | **+4.373** | **−4.373** | **4.373** |
| EV可用性缩放 | EV=0.8 | EV=1.2 | **+0.115** | **−0.089** | **0.115** |
| 寿命权重 | w=0 | w=2 | **−0.0285** | **+0.000823** | **0.0285** |

### 3.5 稳定性 / 敏感性（短句）

- **费用对 PV 缩放最敏感**（`max_abs_change_pct` 约 4.37%，来自表内聚合口径）。  
- **费用对 EV 可用性缩放不敏感**（最大绝对变化约 0.12%）。  
- **费用对 w∈{0,2} 扰动极不敏感**（最大绝对变化约 0.03% 量级，与第 2 节一致）。  
- 扫描表中 **coordinated** 求解状态均为 **Optimal**（`pv_scale_results.csv` / `ev_availability_results.csv`）。

---

## 4. 特殊事件下的调度行为证据

**场景定义**：`data/raw/scenario_notes.csv` 与 `code/python/analyze_scenarios.py` 中事件时间一致。  
**分析对象**：`results/problem2_lifecycle/scans/scan_auto_weight_scan/w_1/timeseries.csv`，Δt=0.25 h。

### 4.1 窗口内汇总（功率均值/最大值为 kW，能量为 kWh）

| 窗口 | slots | grid_kwh (∑P_buy·Δt) | P_buy_mean | P_buy_max | ess_ch_kwh | ess_dis_kwh | ev_ch_kwh | ev_dis_kwh | \|P_shift_out\|·Δt (kWh) |
|------|-------|----------------------|------------|-----------|------------|-------------|-----------|------------|---------------------------|
| **E1** 2025-07-16 11:00–14:00 低辐照 | 12 | 1580.01 | 526.67 | 573.75 | 0 | 0 | 259.39 | 0 | 238.48 |
| **E2** 2025-07-17 13:00–16:00 购电上限 650 kW | 12 | 1245.94 | 415.31 | **600.99** | 0 | 0 | 292.58 | 0 | 229.59 |
| **E3** 2025-07-18 17:00–19:00 晚高峰上限 700 kW | 8 | 318.88 | 159.44 | **464.12** | 0 | **525.0** | 0 | **71.97** | 233.55 |
| **对照** 2025-07-15 11:00–14:00（同小时普通日） | 12 | 701.70 | 233.90 | 266.84 | 0 | 0 | 239.76 | 0 | 245.91 |

**光伏可用性（窗内 `pv_upper_kw` 均值）**：E1 约 **158.6 kW**；对照日约 **461.3 kW**（同脚本读取时序列计算）。

### 4.2 购电上限是否“顶格”

- E2 窗内 **P_buy 最大约 601 kW**，低于场景说明中的 **650 kW** 上限；**未观察到 P_buy≥649 kW**。  
- E3 窗内 **P_buy 最大约 464 kW**，低于 **700 kW** 上限。  
- 全周 **P_buy 全局最大为 863.7 kW**，出现在其他时段（非上述三窗之一）。

### 4.3 与普通时段对比的客观差异

- **E1**：光伏上界均值约为对照日的 **34%**；**平均购电与购电量均显著高于对照中午窗**，储能在该窗内充放为 0；EV 仍以充电为主。  
- **E2**：平均购电介于 E1 与对照之间；**峰值购电接近 600 kW** 但仍低于 650 kW 政策上限；储能为 0。  
- **E3**：**ESS 大量放电（525 kWh/2h 窗）**、**EV 放电约 72 kWh**，**购电均值显著低于对照中午窗**；为晚高峰压力响应型结构。

---

## 5. 模型假设与简化项清单（有据可查）

| 主题 | 证据来源 | 内容摘要 |
|------|----------|----------|
| **预测误差** | 数据经 `data/processed` 时序直接入模；未见随机或滚动预测模块 | 当前算例为 **确定性单周优化**，输入曲线视为已知。 |
| **EV 到离站与 SOC** | `preprocess_b.py` 清洗 `arrival_time`/`departure_time`/能量边界；`p_1_5_ultimate` 在网时段建变量 | **到站、离站、初始/目标能量**由输入表给定，**非随机**；离站需求不满足率在基线 KPI 中有统计（≈0.98 车辆达标率）。 |
| **电池寿命** | `p_2_lifecycle_coordinated.py.code.py` 文档字符串 | **线性吞吐×单价**近似，**未**引入循环深度、温度、DOD 分布等非线性老化。 |
| **网络潮流 / 电压 / 线损** | `operational_metrics.json` 注释、`p_1_5` 单母线式功率平衡 | **未**建模支路潮流；注释说明无独立“潮流不可达未供电”变量。 |
| **用户行为不确定性** | 同上确定性输入 | **未**对到站率、需求随机性显式建模。 |
| **实时滚动优化** | 全周单次 MILP 输出 `timeseries.csv` | **未**见 MPC/滚动时域实现（单_horizon_ 结果）。 |
| **充电设施容量/并发** | `p_1_5_ultimate.py` 特性列表 vs `p_2_lifecycle` 文档 | 问题 1.5 说明含 **充电桩并发 0-1**；问题 2 脚本明确 **未纳入**该族约束，若与现场一致需移植。 |

---

## 6. 求解复杂度与实现性证据

| 项目 | 事实陈述 |
|------|----------|
| **模型类型** | **MILP**（PuLP 建模；购售互斥、ESS/EV 互斥等二进制变量，`p_2_lifecycle_coordinated.py.code.py`、`p_1_5_ultimate.py`）。 |
| **求解器** | 校验记录中为 **CBC / PuLP**（`results/tables/model_validation_checks.json` 等）。 |
| **规模（量级估计）** | `warn_heavy_model_instance`：`n` 为时段数；二进制量级约 `U_grid≈n`（若启用购售互斥）+ `U_ess≈n` + `U_ev≈Σ(在网时段)`（`p_2_lifecycle_coordinated.py.code.py` L90–110）。本主算例 `timeseries` **672 行**（15 min × 7 天量级）。 |
| **约束/连续变量精确计数** | **未**在 `run_meta.json` 中自动落盘；需从 PuLP 对象或单独计数脚本导出后才能写死数字。 |
| **求解时间** | 当前 `run_meta.json` **无 wall-clock 字段**；本文档**不臆造**秒级求解时间。 |
| **解状态** | `scan_auto_weight_scan` 各点 `solver_status`: **Optimal**；`model_validation_checks.json` 中多项一致性检查为 **pass**（购售互斥、ESS 互斥、SOC 边界等）。 |
| **最优性** | 在已有输出下为 **MILP 最优解标签**；若使用 `--gap-rel` 松弛，需以对应日志为准（默认扫描结果已为 Optimal）。 |

---

## 7. 可直接用于论文评价部分的事实要点

### 支撑“模型优点”的事实

- 主场景 **operation_cost** 相对非协同基线 **降低约 15.83%**（`p1_baseline_vs_coordinated.csv`）。  
- PV 缩放 0.9–1.1 范围内，**协同方案运行成本始终低于同尺度 baseline**，改进率约 **6.76%–7.33%**（`pv_scale_results.csv`）。  
- **全周无可观测弃光**（主表 `pv_curtail_energy_kwh` = 0；协同 `renewable_consumption_ratio` = 1.0）。  
- 引入退化权重后，**可在 operation_cost 几乎不变的前提下显著压低 EV 放电**（w=0→1：562→397 kWh）并抬升 **ESS 角色份额**（吞吐份额 80.64%→82.33%，供应份额 91.91%→94.13%）。  
- 特殊事件 **E3** 中呈现 **ESS+EV 协同放电、购电均值下降** 的时段结构（第 4 节表）。  
- **模型验证检查**中购售互斥、ESS 充放互斥、SOC 边界、弃光非负等多项目前为 **pass**（`model_validation_checks.json`）。

### 支撑“模型局限性”的事实

- 协同方案 **全周 grid_import_energy_kwh 高于基线约 2.36%**，**峰值购电高于基线约 38%**（第 1 节）；与“节电/kWh”叙事存在张力。  
- PV 扰动下 **coordinated_grid 始终高于 baseline_grid**（改进率约 **−6.09% ~ −6.63%**，第 3.1 节）。  
- **寿命退化为一阶线性经济惩罚**，非电化学机理模型（代码头部说明）。  
- **单母线、无潮流、无线路损耗**；`operational_metrics` 注释承认未建模支路不可达（第 5 节）。  
- **确定性输入**；**无滚动优化**实现于当前主结果管线（第 5 节）。  
- 问题 2 **未含**问题 1.5 中的 **充电桩并发 0-1** 约束（代码自述，第 5 节）。  
- 特殊事件窗内 **购电上限在 w=1 时序中未以“顶满 650/700 kW”形式出现**（第 4.2 节），若论文强调“约束紧绑定”需补充解释或换口径（如对 `grid_import_limit_kw` 原数据再验证）。

---

*文件生成说明：数值保留与仓库 CSV/JSON 显示精度一致；百分比由 Python 按双精度重算，四舍五入展示。*
