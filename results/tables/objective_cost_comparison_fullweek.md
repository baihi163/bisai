# 协同模型 vs baseline：全周成本分项对比（正式版）

本表基于 **672 个 15 min 时段** 的完整优化 horizon 与 baseline 仿真结果汇总，非 `max-periods` 截断的演示算例。若某侧 CSV 由短 horizon 生成，请勿与本文标题混用。

## 论文中目标函数取值

- **协同模型**：论文中的「最优目标函数值」应采用 **Objective from solver**（即 `pulp.value(prob.objective)`，含 PuLP 目标仿射表达式中的 **Objective affine constant** 项）。
- **CBC 控制台**：`Objective value` 可能 **不含** 仿射常数项，仅用于与 **Objective shown in CBC log style** 对照调试。
- **baseline**：无 MILP；表中 **Objective from solver** 与 **Objective recomputed from solution** 均取与协同模型 **同一分项口径** 加总得到的等价总成本（affine constant 恒为 0）。该项可与 baseline KPI 中仅含「购电−售电」的 `total_cost_cny` 不同，后者不含退化/弃光惩罚/未供电惩罚等。

## 符号约定

- **Grid export revenue** 列为正值表示售电收入；重算总目标时按 **减项** 处理（与 MILP 中 `-sell·P·Δt` 一致）。
- **delta_baseline_minus_coordinated_yuan** = baseline − coordinated（正值表示 baseline 更高、协同更优）。
- **improvement_ratio** = (baseline − coordinated) / baseline；baseline 分项为 0 时记 **NA**（避免除零）。
- **Load shed penalty（baseline）**：非协同仿真仅有聚合 `unmet_load_kw`，无分建筑削减；为与协同分项对齐，按 `flexible_load_params_clean.csv` 中 **penalty_cny_per_kwh_not_served 的最大值** 乘以未供电量折算，不改变 baseline 既有 `total_cost_cny`（仅购售电）定义。

## 分项对比表

| cost_item | coordinated_model_yuan | baseline_yuan | delta_baseline_minus_coordinated_yuan | improvement_ratio |
| --- | ---: | ---: | ---: | --- |
| Grid import cost | 38634.519277 | 46304.527348 | 7670.008071 | 0.165643 |
| Grid export revenue | 0.0 | 0.0 | 0.0 | NA |
| PV curtailment penalty | 0.0 | 0.0 | 0.0 | NA |
| Load shed penalty | 0.0 | 0.0 | 0.0 | NA |
| Building shift penalty | 338.7 | 0.0 | -338.7 | NA |
| ESS degradation cost | 369.390665 | 12.54 | -356.850665 | -28.456991 |
| EV degradation cost | 124.846147 | 93.31062 | -31.535527 | -0.337963 |
| Carbon cost | 0.0 | 0.0 | 0.0 | NA |
| Objective affine constant | 11484.65 | 0.0 | -11484.65 | NA |
| Objective from solver | 39467.456089 | 46410.377967 | 6942.921878 | 0.149598 |
| Objective recomputed from solution | 39467.456089 | 46410.377967 | 6942.921878 | 0.149598 |
| Objective shown in CBC log style | 27982.806089 | 46410.377967 | 18427.571878 | 0.397057 |

## 简要结论（模板，可按结果改写）

- 全周等价总成本（分项重算口径）：协同 **39467.456089 元**，baseline **46410.377967 元**，差值 baseline−协同 **6942.921878 元**，相对改善率 **0.149598**（以 baseline 为分母）。
- 主要贡献项：请对照表中 `delta_baseline_minus_coordinated_yuan` 绝对值较大的行（如购电成本、弃光惩罚、未供电惩罚、退化成本等）撰写机理分析。
