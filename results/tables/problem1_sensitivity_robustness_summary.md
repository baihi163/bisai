# 问题一：灵敏度分析与鲁棒检验摘要

- **求解范围**：时段数 `n = 96`（由 `--max-periods` 控制）。
- **名义碳价**（build_and_solve）：`0.0` 元/kgCO₂ 当量（与主脚本一致时可传 `--carbon-price`）。

## 1. 灵敏度（单参数）

对购电价整体倍率、碳价、弃光惩罚、建筑柔性线性惩罚、储能退化单价分别做一步扰动，其余保持名义值。

- **名义重算目标**（元）：约 `6658.48`（以 `perturbation=nominal` 行为准）。
- **目标值范围**（元）：`6330.71` ~ `6986.22`。

完整数据见 `problem1_sensitivity_oneway.csv`。以下为预览：

```
          analysis          perturbation                      param_name  param_value solver_status  objective_pulp  objective_recomputed  grid_import_energy_kwh  peak_P_buy_kw  pv_curtail_energy_kwh  ess_charge_energy_kwh  ess_discharge_energy_kwh
sensitivity_oneway               nominal                baseline_nominal         1.00       Optimal     6658.484327           6658.484327             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway       buy_price_scale            buy_price_multiplier         0.95       Optimal     6330.709332           6330.709332             9709.198335          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway       buy_price_scale            buy_price_multiplier         1.05       Optimal     6986.224149           6986.224149             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway          carbon_price    carbon_price_cny_per_kwh_co2         0.05       Optimal     6658.484327           6658.484327             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway          carbon_price    carbon_price_cny_per_kwh_co2         0.12       Optimal     6658.484327           6658.484327             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway       penalty_curtail         penalty_curtail_per_kwh         0.35       Optimal     6658.484327           6658.484327             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway       penalty_curtail         penalty_curtail_per_kwh         0.75       Optimal     6658.484327           6658.484327             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway         penalty_shift penalty_shift_linear_cny_per_kw         0.01       Optimal     6644.420646           6644.420646             9720.405407          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway         penalty_shift penalty_shift_linear_cny_per_kw         0.04       Optimal     6677.050397           6677.050397             9705.298772          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway ess_degradation_scale      ess_degradation_multiplier         0.50       Optimal     6632.049590           6632.049590             9711.330132          895.2                    0.0            1010.526315                     912.0
sensitivity_oneway ess_degradation_scale      ess_degradation_multiplier         2.00       Optimal     6711.353801           6711.353801             9711.330132          895.2                    0.0            1010.526315                     912.0
```

## 2. 鲁棒性（负荷 × 光伏离散盒）

对每栋建筑负荷与 `pv_upper` 同步按比例缩放，考察最优目标与购电能量的波动。

- **可行情景数**（Optimal）：9 / 9。
- **重算目标**：均值 `6658.48` 元，标准差 `533.4188`，极差 `1527.71` 元。
- **购电能量（kWh）**：均值 `9711.33`，极差 `2024.98`。

完整数据见 `problem1_robustness_scenarios.csv`。以下为预览：

```
      analysis  load_scale  pv_scale solver_status  objective_pulp  objective_recomputed  grid_import_energy_kwh  peak_P_buy_kw  pv_curtail_energy_kwh  ess_charge_energy_kwh  ess_discharge_energy_kwh
robustness_box        0.94      0.94       Optimal     6239.814441           6239.814441             9162.595420        869.298           0.000000e+00            1010.526315                     912.0
robustness_box        0.94      1.00       Optimal     6067.221021           6067.221021             8930.717920        869.298           0.000000e+00            1010.526315                     912.0
robustness_box        0.94      1.06       Optimal     5894.627601           5894.627601             8698.840420        869.298           2.433609e-13            1010.526315                     912.0
robustness_box        1.00      0.94       Optimal     6831.077747           6831.077747             9943.207632        895.200           0.000000e+00            1010.526315                     912.0
robustness_box        1.00      1.00       Optimal     6658.484327           6658.484327             9711.330132        895.200           0.000000e+00            1010.526315                     912.0
robustness_box        1.00      1.06       Optimal     6485.890907           6485.890907             9479.452632        895.200           2.433609e-13            1010.526315                     912.0
robustness_box        1.06      0.94       Optimal     7422.341052           7422.341052            10723.819843        921.102           0.000000e+00            1010.526315                     912.0
robustness_box        1.06      1.00       Optimal     7249.747635           7249.747635            10491.942348        921.102           0.000000e+00            1010.526315                     912.0
robustness_box        1.06      1.06       Optimal     7077.154212           7077.154212            10260.064842        921.102           2.433609e-13            1010.526315                     912.0
```

## 3. 问题二补充说明

退化权重对角扫描已单独由 `code/python/problem_2/run_problem2_weight_scan.py` 驱动，属于问题二的**权重灵敏度**；本脚本聚焦问题一全周协同主模型。