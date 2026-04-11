# 第二题主结果汇总（w=1）

| 指标 | 数值 | 来源 |
|------|------|------|
| objective_total | 39467.456087846964 | `objective_breakdown.json` → `objective_from_solver` |
| operation_cost | 38973.21927565004 | `objective_breakdown.json` → `operation_cost` |
| ess_degradation_cost | 369.39066470624994 | `objective_breakdown.json` |
| ev_degradation_cost | 124.84614749094287 | `objective_breakdown.json` |
| grid_import_energy_kwh | 65263.89581499998 | `operational_metrics.json` |
| peak_grid_import_kw | 863.7 | `timeseries.csv` 列 `P_buy_kw` 全周 max |
| ess_throughput_kwh | 6716.193903749999 | `operational_metrics.json` |
| ev_throughput_kwh | 1441.3765029112503 | `operational_metrics.json` |

文件：`results\problem2_lifecycle\scans\scan_auto_weight_scan\w_1\objective_breakdown.json`、`results\problem2_lifecycle\scans\scan_auto_weight_scan\w_1\operational_metrics.json`、`results\problem2_lifecycle\scans\scan_auto_weight_scan\w_1\timeseries.csv`。
