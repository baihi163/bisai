# 问题1 建模输入封装说明（final_model_inputs）

本目录由 `code/python/package_final_model_inputs.py` 从 `data/raw/` 下原始表生成，**不修改原始文件**。

## 使用的原始文件

| 原始文件 | 用途 |
|----------|------|
| `timeseries_15min.csv` | 拆分为负荷、光伏、电价、网侧限额、碳强度等时序 |
| `asset_parameters.csv` | 固定储能（ESS）参数 → `ess_params.json` |
| `ev_sessions.csv` | EV 逐车表与 672×N 矩阵 |
| `flexible_load_parameters.csv` | 柔性负荷参数与映射说明 |

## 本封装未直接读取的原始文件（可留作校验/文档）

以下文件在本次“最终封装”中**未参与写入**，若建模需要日汇总或场景说明，请另行引用：

- `daily_summary.csv`
- `ev_summary_stats.csv`
- `scenario_notes.csv`

---

## 输出文件字段与用途

### `load_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp` | 15 min 时间戳，起 `2025-07-14 00:00:00` | 原始 |
| `slot_id` | 时段序号 1–672 | **新增** |
| `total_native_load_kw` | 园区不可调原生总负荷 | 原始 |
| `office_building_kw` | 办公楼分项 | 原始 |
| `wet_lab_kw` | 湿实验楼分项 | 原始 |
| `teaching_center_kw` | 教学中心分项 | 原始 |

**问题1用途**：基线负荷曲线；可与柔性块参数联立做移峰/削减。

**假设**：若原始时序与完整 672 网格不一致，脚本按网格 `reindex`，缺失行会出现 NaN（见检查报告）。

---

### `pv_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `pv_available_kw` | 可用光伏出力（已含站内约束后的可用值） | 原始 |

**问题1用途**：可再生供给上界。

---

### `price_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_buy_price_cny_per_kwh` | 购电电价 | 原始 |
| `grid_sell_price_cny_per_kwh` | 售电电价 | 原始 |

**问题1用途**：购售电成本/收益。

---

### `grid_limits.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_import_limit_kw` | 购电功率上限 | 原始 |
| `grid_export_limit_kw` | 售电/上网功率上限 | 原始 |

**问题1用途**：并网点功率约束。

---

### `carbon_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_carbon_kg_per_kwh` | 电网排放因子 | 原始 |

**问题1用途**：购电碳排放核算（若目标或约束中含碳）。

---

### `ess_params.json`

| 字段 | 说明 | 来源 |
|------|------|------|
| `energy_capacity_kwh` | 储能容量 | 原始 `stationary_battery_energy_capacity_kwh` |
| `initial_energy_kwh` | 初始电量 | 原始 |
| `max_charge_power_kw` / `max_discharge_power_kw` | 最大充/放电功率 | 原始 |
| `charge_efficiency` / `discharge_efficiency` | 单向效率 | 原始 |
| `min_energy_kwh` / `max_energy_kwh` | 能量上下界 | 原始 |
| `min_soc_ratio` / `max_soc_ratio` | SOC 比（由能量界/容量推导） | **派生** |
| `time_step_hours` | 时间步长（小时） | 原始 `default_time_step_hours` |
| `_missing_or_null_fields` | 缺失字段名列表 | **新增** |
| `_remarks` | 备注（如 SOC 推导说明） | **新增** |

未在 `asset_parameters.csv` 中出现的键**不虚构**，对应值为 `null` 并列入 `_missing_or_null_fields`。

**问题1用途**：站内电池状态方程与功率限值。

**说明**：`asset_parameters.csv` 中另有 PV、充电桩数量等条目，本 JSON **仅封装固定储能相关**字段及时间步长。

---

### `ev_sessions_model_ready.csv`

保留 `ev_sessions.csv` 全部原始列，并新增/处理如下。

| 字段 | 说明 | 来源 |
|------|------|------|
| `ev_index` | 车辆序号 1…N（与矩阵列顺序一致） | **新增** |
| `arrival_time` / `departure_time` | datetime 解析 | 原始（类型转换） |
| `arrival_time_discrete` | 到达时间 **向上** 取整到 15 min | **新增** |
| `departure_time_discrete` | 离开时间 **向下** 取整到 15 min | **新增** |
| `arrival_slot` / `departure_slot` | 上述离散时刻在 672 网格上的 1-based 槽位（起点对齐） | **新增** |
| `dwell_slots` | `departure_slot - arrival_slot`（与半开区间 `[t_arr, t_dep)` 内完整 15 min 段数一致） | **新增** |
| `feasibility_flag` | 1/0：在 **无数据异常** 前提下，若 `(required-initial)>0`，是否满足 `(required-initial) ≤ max_charge_power_kw × dwell_slots × 0.25h` | **新增** |
| `issue_note` | 能量上下界违规、停车窗无效或越出网格等说明；正常为空字符串 | **新增** |

**预处理假设（重要）**

- 时间网格：`2025-07-14 00:00:00` 至 `2025-07-20 23:45:00`，共 672 个时段。
- **保守离散化**：到达不早于实际到达（ceil），离开不晚于实际离开（floor），建模停车窗偏短。
- **在站时段与矩阵**：时段 `t` 与停车窗 `[arrival_time_discrete, departure_time_discrete)` 在时间上重叠则视为在站（与 `dwell_slots` 计数一致）。
- **`feasibility_flag`**：未使用车载充电效率；未考虑 V2B 向负荷送电；仅为**上界**意义上的可充性检查。若 `issue_note` 非空，则 `feasibility_flag` 强制为 0。

**问题1用途**：EV 能量约束、到离站、功率上限、V2B 是否允许。

---

### `ev_availability_matrix.csv` / `ev_charge_power_limit_matrix_kw.csv` / `ev_discharge_power_limit_matrix_kw.csv`

| 结构 | 说明 |
|------|------|
| 行 | 672 时段，含 `timestamp`、`slot_id` |
| 列 `ev_k` | 对应 `ev_index = k`（k=1…N） |

- **availability**：在站为 1，否则 0。
- **charge 上限**：在站为该车 `max_charge_power_kw`，否则 0。
- **discharge 上限**：仅当 `v2b_allowed=1` 时在站为 `max_discharge_power_kw`，否则 0。

**问题1用途**：逐车充放电决策的大M/上限约束。

---

### `flexible_load_params_clean.csv`

对 `flexible_load_parameters.csv` 列名做小写与去空格规范化，数值列 `to_numeric`。字段与原始一致：

- `load_block`, `noninterruptible_share`, `max_shiftable_kw`, `max_sheddable_kw`, `rebound_factor`, `penalty_cny_per_kwh_not_served`

**问题1用途**：分块柔性负荷建模参数。

---

### `flexible_load_mapping.csv`

| 字段 | 说明 |
|------|------|
| `load_block` | 块标识 |
| `mapping_to_timeseries_component` | 与 `timeseries_15min` 分项的对应关系说明 |
| `mapping_confidence` | 能否从原始表唯一确定 |
| `relation_to_total_native_load` | 与 `total_native_load_kw` 的关系说明 |

当前原始 `load_block` 命名与 `timeseries_15min` 列名一致，故三行均可**唯一**映射到办公楼/湿实验楼/教学中心分项；**未**将任一块等同于“园区总负荷”本身。

---

## 复现方式

```bash
python code/python/package_final_model_inputs.py
```

