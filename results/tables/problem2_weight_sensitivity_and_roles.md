# 寿命权重敏感性与 ESS/EV 分工比例（w=0,1,2）

**分工定义**：
- `ess_share_throughput_pct` = 100 × `ess_throughput_kwh` / (`ess_throughput_kwh` + `ev_throughput_kwh`)
- `ess_share_supply_pct` = 100 × `ess_discharge_energy_kwh` / (`ess_discharge_energy_kwh` + `ev_discharge_energy_kwh`)

| weight | objective_total | operation_cost | ev_discharge_energy_kwh | ev_throughput_kwh | ess_share_throughput_pct | ess_share_supply_pct | source_dir |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0 | 38962.11295492475 | 38962.11295492504 | 562.2449999999997 | 1615.29978544 | 80.6415 | 91.9058 | results\problem2_lifecycle\scans\scan_auto_weight_scan\w_0 |
| 1.0 | 39467.456087846964 | 38973.21927565004 | 397.23499999999996 | 1441.3765029112503 | 82.3308 | 94.1318 | results\problem2_lifecycle\scans\scan_auto_weight_scan\w_1 |
| 2.0 | 39961.39380651187 | 38973.53998605003 | 392.41499999999996 | 1436.29614281125 | 82.3821 | 94.1988 | results\problem2_lifecycle\scans\scan_auto_weight_scan\w_2 |

**数据**：各 `scan_auto_weight_scan/w_*/operational_metrics.json` 与 `objective_breakdown.json`。
