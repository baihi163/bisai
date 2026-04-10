# 数据总览报告

## 1. 原始数据文件清单

### `timeseries_15min.csv`
- 行数/列数：672 / 13
- 主要字段：`timestamp`, `ambient_temp_c`, `solar_irradiance_wm2`, `office_building_kw`, `wet_lab_kw`, `teaching_center_kw`, `total_native_load_kw`, `pv_available_kw`, `grid_buy_price_cny_per_kwh`, `grid_sell_price_cny_per_kwh`, `grid_carbon_kg_per_kwh`, `grid_import_limit_kw`, `grid_export_limit_kw`
- 大致含义：主时序驱动数据（负荷、光伏、电价、碳因子、电网边界）
- 是否包含时间列：是（`timestamp`）
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `asset_parameters.csv`
- 行数/列数：15 / 3
- 主要字段：`parameter`, `value`, `note`
- 大致含义：资产与系统参数字典（储能、光伏、充电设施、时间步长）
- 是否包含时间列：否
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `ev_sessions.csv`
- 行数/列数：102 / 11
- 主要字段：`session_id`, `ev_type`, `arrival_time`, `departure_time`, `battery_capacity_kwh`, `initial_energy_kwh`, `required_energy_at_departure_kwh`, `max_charge_power_kw`, `max_discharge_power_kw`, `v2b_allowed`, `degradation_cost_cny_per_kwh_throughput`
- 大致含义：EV 会话级数据（到离站时间、容量、功率、离站需求）
- 是否包含时间列：是（`arrival_time`, `departure_time`）
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `flexible_load_parameters.csv`
- 行数/列数：3 / 6
- 主要字段：`load_block`, `noninterruptible_share`, `max_shiftable_kw`, `max_sheddable_kw`, `rebound_factor`, `penalty_cny_per_kwh_not_served`
- 大致含义：柔性负荷参数（可转移、可削减、惩罚）
- 是否包含时间列：否
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `daily_summary.csv`
- 行数/列数：7 / 5
- 主要字段：`date`, `load_peak`, `load_energy_kwh`, `pv_peak`, `pv_energy_kwh`
- 大致含义：按日汇总（负荷与光伏峰值/日电量）
- 是否包含时间列：是（`date`）
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `ev_summary_stats.csv`
- 行数/列数：6 / 2
- 主要字段：`metric`, `value`
- 大致含义：EV 统计摘要
- 是否包含时间列：否
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `scenario_notes.csv`
- 行数/列数：7 / 2
- 主要字段：`item`, `value`
- 大致含义：场景元数据与 stress events 文本描述
- 是否包含时间列：间接包含（在 `value` 文本中）
- 数据质量：缺失值 0，重复行 0，未见明显异常

### `README.txt`
- 行数/列数：文本说明文件（非结构化）
- 主要内容：数据字段语义、时间范围、场景背景说明
- 是否包含时间列：文本中有说明
- 数据质量：不适用

## 2. 处理后数据文件清单

### `load_profile.csv`
- 行数/列数：672 / 5
- 字段含义：`office_building_kw`（办公楼负荷）、`wet_lab_kw`（湿实验楼负荷）、`teaching_center_kw`（教学中心负荷）、`total_native_load_kw`（总原生负荷）
- 建模用途：功率平衡中的需求侧输入

### `pv_profile.csv`
- 行数/列数：672 / 2
- 字段含义：`pv_available_kw`（光伏可用出力上限）
- 建模用途：本地可再生供给上限约束

### `price_profile.csv`
- 行数/列数：672 / 3
- 字段含义：`grid_buy_price_cny_per_kwh`（购电价）、`grid_sell_price_cny_per_kwh`（售电价）
- 建模用途：经济目标（购售电成本）

### `carbon_profile.csv`
- 行数/列数：672 / 2
- 字段含义：`grid_carbon_kg_per_kwh`（电网碳因子）
- 建模用途：低碳目标（排放核算）

### `grid_limits.csv`
- 行数/列数：672 / 3
- 字段含义：`grid_import_limit_kw`（进线购电上限）、`grid_export_limit_kw`（反送上限）
- 建模用途：电网交换约束

### `ess_params.json`
- 参数个数：9
- 关键字段：`energy_capacity_kwh`, `p_charge_max_kw`, `p_discharge_max_kw`, `eta_charge`, `eta_discharge`, `soc_init_kwh`, `soc_min_frac`, `soc_max_frac`, `delta_t_hours`
- 建模用途：储能状态方程与 SOC/功率约束参数

### `ev_sessions_clean.csv`
- 行数/列数：102 / 13
- 字段含义（核心）：`arrival_slot`, `departure_slot`, `max_charge_power_kw`, `max_discharge_power_kw`, `required_energy_at_departure_kwh`
- 建模用途：会话级 EV 可行域与离站需求约束

### `ev_aggregate_profile.csv`
- 行数/列数：672 / 6
- 字段含义（核心）：`online_count`, `p_ev_ch_max_kw`, `p_ev_dis_max_kw`, `e_ev_init_inflow_kwh`, `e_ev_req_outflow_kwh`
- 建模用途：聚合 EV 边界输入（规模、功率、能量流）

### `flexible_load_params.csv`
- 行数/列数：3 / 6
- 字段含义（核心）：`noninterruptible_share`, `max_shiftable_kw`, `max_sheddable_kw`, `rebound_factor`, `penalty_cny_per_kwh_not_served`
- 建模用途：柔性负荷约束与舒适度惩罚参数

## 3. 时间信息总结

- 时间范围：`2025-07-14 00:00:00` ~ `2025-07-20 23:45:00`
- 时间分辨率：15 分钟
- 总时段数：672
- 是否连续完整：是

## 4. EV 数据总结

- 原始会话数：102
- 清洗后会话数：102
- 被删除会话的主要原因（复核结果）：
  - 缺失关键字段/时间不可解析：0 条
  - 会话 ID 重复：0 条
  - 离站时间早于或等于到站时间：0 条
  - 15 分钟对齐后无有效停留时段：0 条
- 在线车辆数统计特征（`ev_aggregate_profile.csv`）：
  - 均值：5.13
  - 最小值：0
  - 最大值：20
- 聚合充/放电上限统计特征：
  - `p_ev_ch_max_kw`：均值 44.53，最大 176.00
  - `p_ev_dis_max_kw`：均值 29.84，最大 133.00

## 5. 建模视角总结

### 可直接作为模型输入的文件
- `load_profile.csv`, `pv_profile.csv`, `price_profile.csv`, `carbon_profile.csv`, `grid_limits.csv`
- `ev_aggregate_profile.csv`, `flexible_load_params.csv`
- `ess_params.json`（参数输入）

### 可作为约束参数的字段
- 电网边界：`grid_import_limit_kw`, `grid_export_limit_kw`
- 储能边界：`energy_capacity_kwh`, `p_charge_max_kw`, `p_discharge_max_kw`, `soc_min_frac`, `soc_max_frac`, `eta_charge`, `eta_discharge`
- EV 聚合边界：`online_count`, `p_ev_ch_max_kw`, `p_ev_dis_max_kw`, `e_ev_init_inflow_kwh`, `e_ev_req_outflow_kwh`
- 柔性负荷边界：`noninterruptible_share`, `max_shiftable_kw`, `max_sheddable_kw`, `rebound_factor`

### 可用于目标函数的字段
- 经济目标：`grid_buy_price_cny_per_kwh`, `grid_sell_price_cny_per_kwh`
- 低碳目标：`grid_carbon_kg_per_kwh`
- 舒适度/负荷损失项：`penalty_cny_per_kwh_not_served`
- （可扩展）电池老化项：来自 `asset_parameters.csv` 与 `ev_sessions_clean.csv` 中退化成本参数

### 需在论文中说明的预处理假设
- 时间索引统一到固定 672 个 15 分钟时段；缺失时段使用插值与前后填充。
- EV 时间对齐规则：到站上取整至 15 分钟、离站下取整至 15 分钟。
- EV 能量修正到物理可行域（0~容量，且离站需求不低于初始电量）。
- `v2b_allowed = 0` 时，放电能力强制置零。
- ESS 的 `soc_min_frac/soc_max_frac` 由 `min/max_energy_kwh` 与容量换算得到。
