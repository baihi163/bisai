# 鲁棒性分析汇总表（PV 扰动）

## 可再生能源消纳率说明

可再生能源本地消纳率（renewable_consumption_ratio）在各 PV 缩放下数值几乎恒定（见表），未单独绘制消纳率提升图。

## 自动生成结论（PV 扰动）

在 PV=0.9、1.0、1.1 的离散扰动下，协同相对 baseline 的运行成本改进率 （(baseline−协同)/baseline×100%）三档分别为 6.76%, 7.03%, 7.33%；各档均为正，说明协同在运行成本上相对 baseline 的优势在该 PV 盒内稳定。 购电量改进率同式定义：为正表示协同全周购电少于 baseline，为负则相反（成本最优未必同步减少购电量）。 可再生能源本地消纳率（renewable_consumption_ratio）在各 PV 缩放下数值几乎恒定（见表），未单独绘制消纳率提升图。

## 明细表（节选）

| parameter | scenario | metric | raw_value | relative_change_pct | baseline_reference |
| --- | --- | --- | --- | --- | --- |
| pv_scale=0.9 | baseline | operation_cost | 7362.318189130434 | 0.0 | pv_scale=1.0 baseline operation_cost |
| pv_scale=0.9 | coordinated | operation_cost | 6864.952831924999 | 4.3734636619010425 | pv_scale=1.0 coordinated operation_cost |
| pv_scale=0.9 | baseline | grid_import_energy_kwh | 9517.9571 | 0.0 | pv_scale=1.0 baseline grid_import_energy_kwh |
| pv_scale=0.9 | coordinated | grid_import_energy_kwh | 10097.7926325 | 3.9795012086620716 | pv_scale=1.0 coordinated grid_import_energy_kwh |
| pv_scale=0.9 | baseline | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 baseline renewable_consumption_ratio |
| pv_scale=0.9 | coordinated | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 coordinated renewable_consumption_ratio |
| pv_scale=0.9 | improvement_cost_pct | improvement_cost_pct | 6.755553677912671 | 6.755553677912671 | (baseline−协同)/baseline×100 |
| pv_scale=0.9 | improvement_grid_pct | improvement_grid_pct | -6.092016662903442 | -6.092016662903442 | (baseline−协同)/baseline×100 |
| pv_scale=1.0 | baseline | operation_cost | 7074.662489130436 | 0.0 | pv_scale=1.0 baseline operation_cost |
| pv_scale=1.0 | coordinated | operation_cost | 6577.297131925 | 0.0 | pv_scale=1.0 coordinated operation_cost |
| pv_scale=1.0 | baseline | grid_import_energy_kwh | 9131.4946 | 0.0 | pv_scale=1.0 baseline grid_import_energy_kwh |
| pv_scale=1.0 | coordinated | grid_import_energy_kwh | 9711.3301325 | 0.0 | pv_scale=1.0 coordinated grid_import_energy_kwh |
| pv_scale=1.0 | baseline | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 baseline renewable_consumption_ratio |
| pv_scale=1.0 | coordinated | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 coordinated renewable_consumption_ratio |
| pv_scale=1.0 | improvement_cost_pct | improvement_cost_pct | 7.030234417113072 | 7.030234417113072 | (baseline−协同)/baseline×100 |
| pv_scale=1.0 | improvement_grid_pct | improvement_grid_pct | -6.349842582177066 | -6.349842582177066 | (baseline−协同)/baseline×100 |
| pv_scale=1.1 | baseline | operation_cost | 6787.006789130435 | 0.0 | pv_scale=1.0 baseline operation_cost |
| pv_scale=1.1 | coordinated | operation_cost | 6289.6414319250025 | -4.373463661901015 | pv_scale=1.0 coordinated operation_cost |
| pv_scale=1.1 | baseline | grid_import_energy_kwh | 8745.0321 | 0.0 | pv_scale=1.0 baseline grid_import_energy_kwh |
| pv_scale=1.1 | coordinated | grid_import_energy_kwh | 9324.8676325 | -3.979501208662053 | pv_scale=1.0 coordinated grid_import_energy_kwh |
| pv_scale=1.1 | baseline | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 baseline renewable_consumption_ratio |
| pv_scale=1.1 | coordinated | renewable_consumption_ratio | 1.0 | 0.0 | pv_scale=1.0 coordinated renewable_consumption_ratio |
| pv_scale=1.1 | improvement_cost_pct | improvement_cost_pct | 7.328198905030948 | 7.328198905030948 | (baseline−协同)/baseline×100 |
| pv_scale=1.1 | improvement_grid_pct | improvement_grid_pct | -6.6304563078733505 | -6.6304563078733505 | (baseline−协同)/baseline×100 |

*完整数据见 `robustness_analysis_summary.csv`。*