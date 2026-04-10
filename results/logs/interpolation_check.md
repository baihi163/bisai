# 缺失值与插值修复检查报告

## 1) 数值列识别

`ambient_temp_c`, `solar_irradiance_wm2`, `office_building_kw`, `wet_lab_kw`, `teaching_center_kw`, `total_native_load_kw`, `pv_available_kw`, `grid_buy_price_cny_per_kwh`, `grid_sell_price_cny_per_kwh`, `grid_carbon_kg_per_kwh`, `grid_import_limit_kw`, `grid_export_limit_kw`

## 2) 全字段缺失与修复统计

| 列名 | 原始缺失值个数 | 重建完整索引后新增缺失值个数 | 最终通过插值/填充修复数量 | 最长连续缺失长度（时段） |
|---|---:|---:|---:|---:|
| `ambient_temp_c` | 0 | 0 | 0 | 0 |
| `solar_irradiance_wm2` | 0 | 0 | 0 | 0 |
| `office_building_kw` | 0 | 0 | 0 | 0 |
| `wet_lab_kw` | 0 | 0 | 0 | 0 |
| `teaching_center_kw` | 0 | 0 | 0 | 0 |
| `total_native_load_kw` | 0 | 0 | 0 | 0 |
| `pv_available_kw` | 0 | 0 | 0 | 0 |
| `grid_buy_price_cny_per_kwh` | 0 | 0 | 0 | 0 |
| `grid_sell_price_cny_per_kwh` | 0 | 0 | 0 | 0 |
| `grid_carbon_kg_per_kwh` | 0 | 0 | 0 | 0 |
| `grid_import_limit_kw` | 0 | 0 | 0 | 0 |
| `grid_export_limit_kw` | 0 | 0 | 0 | 0 |

## 3) 重点字段专项检查

| 字段 | 原始缺失 | 新增缺失 | 修复数量 | 最长连续缺失段 | 备注 |
|---|---:|---:|---:|---:|---|
| `pv_available_kw` | 0 | 0 | 0 | 0 | 无实际插值 |
| `grid_buy_price_cny_per_kwh` | 0 | 0 | 0 | 0 | 无实际插值 |
| `grid_sell_price_cny_per_kwh` | 0 | 0 | 0 | 0 | 无实际插值 |
| `grid_import_limit_kw` | 0 | 0 | 0 | 0 | 无实际插值 |
| `grid_export_limit_kw` | 0 | 0 | 0 | 0 | 无实际插值 |
| `grid_carbon_kg_per_kwh` | 0 | 0 | 0 | 0 | 无实际插值 |

## 4) 风险评估与论文建议

- 插值风险较低的列：本次全部数值列（原因：无缺失、无新增缺口、无修复动作）。
- 若未来数据存在缺失，风险相对更高的字段通常是：
  - `grid_import_limit_kw`, `grid_export_limit_kw`（物理约束边界，插值可能改变约束真实性）
  - 价格与碳因子字段（会影响目标函数系数）
- 本批数据中未发生实际插值，但建议在论文中明确写出：
  1) 重建标准时间索引；  
  2) 缺失检测；  
  3) 线性插值 + 前后填充作为兜底策略。  

这样能提升方法完整性与可复现性。
