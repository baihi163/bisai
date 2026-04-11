# 目标函数分项对账表（附录 / 补充材料）

与主模型 `p_1_5_ultimate.py` 中 `summarize_solution_costs` 及 `pulp.value(prob.objective)` 口径一致。
其中 **Objective affine constant** 为 PuLP 目标仿射表达式中的常数项；**Objective shown in CBC log style** 取 `pulp.value(prob.objective) - constant`，便于与 CBC 控制台 `Objective value` 对照。

| 项 | 数值（元） |
| --- | ---: |
| Grid import cost | 940.5795 |
| Grid export revenue | 0.0000 |
| PV curtailment penalty | 0.0000 |
| Load shed penalty | 0.0000 |
| Building shift penalty | 0.0000 |
| ESS degradation cost | 0.0000 |
| EV degradation cost | 0.0000 |
| Carbon cost | 0.0000 |
| Objective affine constant | 1.3375 |
| Objective from solver | 940.5795 |
| Objective recomputed from solution | 940.5795 |
| Objective shown in CBC log style | 939.2420 |
