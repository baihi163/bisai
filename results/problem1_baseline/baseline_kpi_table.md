# Baseline KPI 汇总表

| 指标键名 | 指标名称 | 数值 | 单位 | 含义说明 |
|----------|----------|------|------|----------|
| `total_grid_import_kwh` | 电网总购电量 | 63760.3 | kWh | 全周从电网购入的有功电量累计。 |
| `total_grid_export_kwh` | 电网总售电量 | 0 | kWh | 全周向电网送出的有功电量累计。 |
| `total_pv_curtailed_kwh` | 光伏总弃电量 | 0 | kWh | 全周弃光能量累计。 |
| `total_cost_cny` | 总运行费用 | 46304.5 | 元 | 购电支出减售电收入（按时段电价折算）。 |
| `pv_utilization_rate` | 光伏利用率 | 1 | — | 1 − 弃光电量/可发电量；无量纲，范围约 [0,1]。 |
| `ev_demand_met_rate` | EV 离站需求满足率 | 0.980392 | — | 离站时能量达标的车辆占比；无量纲。 |
| `peak_grid_import_kw` | 峰值购电功率 | 624.8 | kW | 单时段最大购电功率。 |
| `total_unmet_load_kwh` | 未供能缺电量 | 0 | kWh | 购电达上限后仍不足的功率缺口折算电量。 |
| `ess_total_charge_throughput_kwh` | 储能总充电量 | 0 | kWh | 储能交流侧充电能量累计。 |
| `ess_total_discharge_throughput_kwh` | 储能总放电量 | 456 | kWh | 储能交流侧放电能量累计。 |
| `total_ev_charge_kwh` | EV 总充电量（交流侧） | 2164.07 | kWh | ∑ ev_total_charge_kw×Δt。 |
| `total_pv_used_locally_kwh` | 光伏本地消纳电量 | 22969.3 | kWh | ∑ pv_used_locally_kw×Δt。 |
| `total_pv_to_ess_kwh` | 光伏入储电量 | 0 | kWh | ∑ pv_to_ess_kw×Δt。 |
| `total_sell_revenue_cny` | 总售电收入 | 0 | 元 | ∑ grid_export_kw×sell_price×Δt。 |
| `average_grid_import_kw` | 平均购电功率 | 379.525 | kW | 全时段 grid_import_kw 算术平均。 |
| `ess_min_energy_kwh` | 储能能量最小值 | 120 | kWh | ess_energy_kwh 全周最小。 |
| `ess_max_energy_kwh` | 储能能量最大值 | 600 | kWh | ess_energy_kwh 全周最大。 |
| `ev_average_completion_ratio` | EV 平均能量完成比 | 0.995408 | — | 各车离站 energy_completion_ratio 均值（有效值）。 |
| `unmet_load_slots_count` | 未供能时段数 | 0 | — | unmet_load_kw>0 的时段个数。 |
