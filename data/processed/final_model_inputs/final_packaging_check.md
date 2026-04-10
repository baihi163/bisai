# 最终封装检查报告（final_packaging_check）

- 生成时间（运行脚本时）由文件系统记录；源数据目录：`data/raw/`。
- 时序源行数（读入后）：672；是否与 672 网格强制对齐：否（原序已对齐）。

## 1. 输出文件是否生成

- **load_profile.csv**：已生成
- **pv_profile.csv**：已生成
- **price_profile.csv**：已生成
- **grid_limits.csv**：已生成
- **carbon_profile.csv**：已生成
- **ess_params.json**：已生成
- **ev_sessions_model_ready.csv**：已生成
- **ev_availability_matrix.csv**：已生成
- **ev_charge_power_limit_matrix_kw.csv**：已生成
- **ev_discharge_power_limit_matrix_kw.csv**：已生成
- **flexible_load_params_clean.csv**：已生成
- **flexible_load_mapping.csv**：已生成
- **final_model_inputs_readme.md**：已生成
- **final_packaging_check.md**：由本脚本末尾写入（即当前文件）。

## 2. 行数与列数

| 文件 | 行数 | 列数 | 备注 |
|------|------|------|------|
| load_profile.csv | 672 | 6 | OK 672 |
| pv_profile.csv | 672 | 3 | OK 672 |
| price_profile.csv | 672 | 4 | OK 672 |
| grid_limits.csv | 672 | 4 | OK 672 |
| carbon_profile.csv | 672 | 3 | OK 672 |
| ess_params.json | 1 个 JSON 对象 | 11 | 值为 null 的字段：无 |
| ev_sessions_model_ready.csv | 102 | 19 | EV 数 N=102 |
| ev_availability_matrix.csv | 672 | 104 | 期望列数 2+N=104，一致 |
| ev_charge_power_limit_matrix_kw.csv | 672 | 104 | 期望列数 2+N=104，一致 |
| ev_discharge_power_limit_matrix_kw.csv | 672 | 104 | 期望列数 2+N=104，一致 |
| flexible_load_params_clean.csv | 3 | 6 |  |
| flexible_load_mapping.csv | 3 | 4 |  |

## 3. 空值（NaN）检查

对 CSV 使用 `pandas.read_csv` 默认缺失值解析；`issue_note` 中空字符串在默认解析下可能显示为 NaN，**属正常现象**，以 `keep_default_na=False` 读取时均为空串。

- **load_profile.csv**：无 NaN。
- **pv_profile.csv**：无 NaN。
- **price_profile.csv**：无 NaN。
- **grid_limits.csv**：无 NaN。
- **carbon_profile.csv**：无 NaN。
- **ev_sessions_model_ready.csv**：无 NaN。
- **ev_availability_matrix.csv**：无 NaN。
- **ev_charge_power_limit_matrix_kw.csv**：无 NaN。
- **ev_discharge_power_limit_matrix_kw.csv**：无 NaN。
- **flexible_load_params_clean.csv**：无 NaN。
- **flexible_load_mapping.csv**：无 NaN。

## 4. 一致性校验

- EV 主表车辆数 N = **102**；三个矩阵数据列数均为 **102**（列名 `ev_1`…`ev_102`），与 `ev_index` 顺序一致。
- `issue_note` 非空行数：**0**（数据异常说明）。
- `feasibility_flag == 0` 行数：**1**（含 issue 导致强制 0 + 充电上界不足）。
- 时序类 CSV（负荷/光伏/电价/限额/碳）行数均为 672：**是**。

## 5. 是否适合作为问题1直接输入

- **结论**：结构完整，时序长度与 EV 矩阵维度一致，可作为问题1确定性/优化模型的**直接读取输入**。若某 EV `feasibility_flag=0`，建模时应对该会话施加额外松弛变量或剔除约束，需结合物理意义自行处理。
