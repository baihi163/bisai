# 特殊事件汇总（special_events_summary）

数据来源：`data/raw/timeseries_15min.csv`，事件定义见 `data/raw/scenario_notes.csv`。

| event_id | event_name | start_time | end_time | duration_hours | affected_variable_primary | affected_variable_secondary | event_period_mean_load_kw | event_period_peak_load_kw | event_period_mean_pv_kw | event_period_min_pv_kw | event_period_mean_grid_limit_kw | weekly_mean_load_kw | weekly_mean_pv_kw | weekly_mean_grid_limit_kw | event_period_mean_net_load_kw | weekly_mean_net_load_kw | relative_change_vs_weekly_mean | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Low irradiance (storm clouds) | 2025-07-16 11:00:00 | 2025-07-16 14:00:00 | 3.0 | solar_irradiance_wm2 | pv_available_kw | 678.2417 | 718.9 | 158.575 | 149.9 | 1200.0 | 506.0804 | 136.722 | 1184.2262 | 519.6667 | 369.3583 | solar_irradiance_wm2: -64.1% (vs 11:00–14:00 on other days); pv_available_kw: -64.1% (vs same window) | 暴雨云导致该午间窗口内辐照度与光伏可用出力相对同周其他日同一时段明显偏低，净负荷抬升，放大对购电/储能的依赖。 |
| 2 | Midday grid import cap (650 kW) | 2025-07-17 13:00:00 | 2025-07-17 16:00:00 | 3.0 | grid_import_limit_kw | total_native_load_kw | 712.0667 | 746.4 | 317.75 | 229.7 | 650.0 | 506.0804 | 136.722 | 1184.2262 | 394.3167 | 369.3583 | grid_import_limit_kw: -45.1% | 午间时段电网购电上限降至650 kW，在负荷与光伏叠加下更易出现购电越限或需依赖储能/削减。 |
| 3 | Evening peak grid import cap (700 kW) | 2025-07-18 17:00:00 | 2025-07-18 19:00:00 | 2.0 | grid_import_limit_kw | total_native_load_kw | 664.0875 | 734.0 | 89.3875 | 11.3 | 700.0 | 506.0804 | 136.722 | 1184.2262 | 574.7 | 369.3583 | grid_import_limit_kw: -40.9% | 晚高峰时段购电上限收紧至700 kW，与负荷上升叠加，形成“负荷高+外网紧”的复合压力。 |
