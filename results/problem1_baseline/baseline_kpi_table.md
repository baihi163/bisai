# Baseline KPI 汇总表

| 指标键名 | 指标名称 | 数值 | 单位 | 含义说明 |
|----------|----------|------|------|----------|
| `total_grid_import_kwh` | 电网总购电量 | 63591.1 | kWh | 全周从电网购入的有功电量累计。 |
| `total_grid_export_kwh` | 电网总售电量 | 0 | kWh | 全周向电网送出的有功电量累计。 |
| `total_pv_curtailed_kwh` | 光伏总弃电量 | 0 | kWh | 全周弃光能量累计。 |
| `total_cost_cny` | 总运行费用 | 45976.4 | 元 | 购电支出减售电收入（按时段电价折算）。 |
| `pv_utilization_rate` | 光伏利用率 | 1 | — | 1 − 弃光电量/可发电量；无量纲，范围约 [0,1]。 |
| `ev_demand_met_rate` | EV 离站需求满足率 | 0.990196 | — | 离站能量达标的车辆占比；无量纲。 |
| `peak_grid_import_kw` | 峰值购电功率 | 624.8 | kW | 单时段最大购电功率。 |
| `total_unmet_load_kwh` | 未供能缺电量 | 0 | kWh | 购电达上限后仍不足的功率缺口折算电量。 |
| `ess_total_charge_throughput_kwh` | 储能总充电量 | 0 | kWh | 储能交流侧充电能量累计。 |
| `ess_total_discharge_throughput_kwh` | 储能总放电量 | 456 | kWh | 储能交流侧放电能量累计。 |
