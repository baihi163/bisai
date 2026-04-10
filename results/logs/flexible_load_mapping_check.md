# 柔性负荷映射检查报告（建模视角）

## 1) `flexible_load_parameters.csv` 字段及含义

| 字段名 | 可能含义 | 建模角色 |
|---|---|---|
| `load_block` | 负荷块名称（对象标识） | 决策变量分块索引 |
| `noninterruptible_share` | 不可中断比例 | 刚性负荷下界约束 |
| `max_shiftable_kw` | 最大可时移功率 | 时移上界约束 |
| `max_sheddable_kw` | 最大可削减功率 | 削减上界约束 |
| `rebound_factor` | 反弹系数 | 时移后补偿/守恒约束 |
| `penalty_cny_per_kwh_not_served` | 未满足负荷惩罚成本 | 目标函数惩罚项 |

## 2) `load_profile.csv` 建筑负荷字段

- `office_building_kw`
- `wet_lab_kw`
- `teaching_center_kw`
- `total_native_load_kw`

## 3) `load_block` 对象与建筑负荷对应关系

当前 `flexible_load_parameters.csv` 的 `load_block` 为：
- `office_building`
- `wet_lab`
- `teaching_center`

与 `load_profile.csv` 可形成自然映射：
- `office_building` -> `office_building_kw`
- `wet_lab` -> `wet_lab_kw`
- `teaching_center` -> `teaching_center_kw`

`total_native_load_kw` 是聚合结果，不建议直接作为柔性参数对象；应由分块调节结果求和得到。

## 4) 各参数更适合进入哪些约束/目标

- `max_shiftable_kw`：进入时移决策变量上限约束。
- `max_sheddable_kw`：进入削减决策变量上限约束。
- `noninterruptible_share`：进入“最小服务负荷”约束（保障刚性需求）。
- `rebound_factor`：进入跨时段反弹约束（时移后补偿负荷）。
- `penalty_cny_per_kwh_not_served`：进入目标函数中的舒适度/未服务损失惩罚项。

## 5) 柔性负荷调节建模粒度判断

推荐采用：**对若干负荷块分别调节**（而不是对总负荷统一调节）。

理由：
1. 参数已按 `load_block` 分块提供，天然支持异质性建模；  
2. 不同建筑可拥有不同刚性比例与调节能力；  
3. 便于后续分析“哪类建筑贡献了主要灵活性”。

## 6) 若不能严格一一对应时的最简解释方案

本数据中可直接一一对应；若未来字段不一致，建议采用以下最简方案：
- 先定义“块到建筑”的映射表；
- 按块施加柔性约束，按映射聚合回总负荷；
- 在论文中明确该映射属于业务先验假设。

## 结论（用于问题1约束搭建）

- 当前数据支持“建筑分块柔性调节”建模框架；  
- 建议在问题1中对 `office/wet_lab/teaching` 分别设置时移、削减、反弹、惩罚约束；  
- `total_native_load_kw` 应作为结果汇总量，而非直接分配柔性参数的对象。
