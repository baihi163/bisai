# Baseline 非协同仿真 — 结果核查报告

本报告由 `code/python/baseline/validate_baseline.py` 根据仿真输出与 `final_model_inputs` 自动生成。

输入合法性预检见：`baseline_input_validation_report.md`（由主脚本在仿真前生成）。

## 1. EV：到站即充、不向园区放电

- **ev_total_discharge_kw 全为 0**：通过（容差 1e-06）。
- **各时段总充电功率与规则回放一致**：通过（与输入矩阵/会话重放 `simulate_ev_baseline` 逐时段比对，容差 1e-3 kW）。

## 2. 建筑负荷未参与调节

- **native_load_kw 与输入 `total_native_load_kw` 逐时段一致**：通过（容差 1e-3 kW）。

## 3. 储能：与声明规则一致（非全局优化）

- **说明**：无法从数值结果单独「证明」未做全局优化；此处校验输出是否与**已实现的规则**一致。
- **pv_to_ess_kw 与 ess_charge_kw 一致（光伏充电路径）**：通过。
- **放电仅出现在购电高价区间（分位阈值以上）且存在本地缺口**（`total_load_with_ev > pv_used_locally`）：通过。
- **充电仅在有剩余光伏时**（`pv_available > pv_used_locally`）：通过。

## 4. 电网购电功率上限

- **grid_import_kw ≤ grid_import_limit_kw（输入）**：通过。

## 5. 未供能缺口 unmet_load_kw

- **全周折算电量**（∑ unmet×Δt）：0.0000 kWh。
- **unmet > 0 的时段数**：0。

## 6. 光伏分配：本地 → 储能 → 售电 → 弃光

- **功率平衡**：`pv_used_locally + pv_to_ess + pv_export + pv_curtailed = pv_available`：通过（容差 0.02 kW）。
- **本地消纳**：`pv_used_locally = min(pv_available, total_load_with_ev)`：通过。
- **剩余光伏先上网（受出口限）再弃光**：与逐时段公式一致：通过。

## 7. 主要 KPI 汇总与含义

| KPI | 数值 | 含义 |
|-----|------|------|
| `total_grid_import_kwh` | 63760.2652 | 全周从电网购入的有功电量（kWh）。 |
| `total_grid_export_kwh` | 0.0 | 全周向电网送出的有功电量（kWh）。 |
| `total_pv_curtailed_kwh` | 0.0 | 全周弃光电量（kWh）。 |
| `total_cost_cny` | 46304.5273 | 购电成本减售电收入的近似总费用（元）。 |
| `pv_utilization_rate` | 1.0 | 光伏利用程度：1 − 弃光电量/可发电量（见 baseline 说明）。 |
| `ev_demand_met_rate` | 0.980392 | 离站能量需求达标的车辆比例。 |
| `peak_grid_import_kw` | 624.8 | 单时段最大购电功率（kW）。 |
| `total_unmet_load_kwh` | 0.0 | 购电达上限后仍不足的缺电量折算（kWh）。 |
| `ess_total_charge_throughput_kwh` | 0.0 | 储能交流侧充电能量累计（kWh）。 |
| `ess_total_discharge_throughput_kwh` | 456.0 | 储能交流侧放电能量累计（kWh）。 |
| `total_ev_charge_kwh` | 2164.0652 | EV 交流侧充电电量累计（kWh）。 |
| `total_pv_used_locally_kwh` | 22969.3 | 光伏本地直接消纳电量（kWh）。 |
| `total_pv_to_ess_kwh` | 0.0 | 光伏充入储能的电量（kWh）。 |
| `total_sell_revenue_cny` | 0.0 | 售电收入（元，∑ 上网功率×售电价×Δt）。 |
| `average_grid_import_kw` | 379.5254 | 全时段平均购电功率（kW）。 |
| `ess_min_energy_kwh` | 120.0 | 储能 SOC 轨迹最小值（kWh）。 |
| `ess_max_energy_kwh` | 600.0 | 储能 SOC 轨迹最大值（kWh）。 |
| `ev_average_completion_ratio` | 0.995408 | EV 离站能量完成比（均值）。 |
| `unmet_load_slots_count` | 0 | 存在未供能缺口的时段数。 |

## 总判定

**全部数值核查项通过。**
