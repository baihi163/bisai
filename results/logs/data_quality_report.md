# 数据质量检查报告

## 输入文件检查
- OK: `D:/数维杯比赛/data/raw/timeseries_15min.csv`
- OK: `D:/数维杯比赛/data/raw/asset_parameters.csv`
- OK: `D:/数维杯比赛/data/raw/ev_sessions.csv`
- OK: `D:/数维杯比赛/data/raw/flexible_load_parameters.csv`
- OK: `D:/数维杯比赛/data/raw/daily_summary.csv`
- OK: `D:/数维杯比赛/data/raw/ev_summary_stats.csv`
- OK: `D:/数维杯比赛/data/raw/scenario_notes.csv`
- OK: `D:/数维杯比赛/data/raw/README.txt`

## 结构与一致性检查
- 统一时段总数: 672（预期 672）
- timeseries 处理后行数: 672
- EV 清洗后会话数: 102
- EV 聚合后行数: 672
- 柔性负荷参数条数: 3

## 风险提示
- 未发现显著结构性异常。

## 输出文件写入情况
- WRITE: `D:/数维杯比赛/data/processed/load_profile.csv`
- WRITE: `D:/数维杯比赛/data/processed/pv_profile.csv`
- WRITE: `D:/数维杯比赛/data/processed/price_profile.csv`
- WRITE: `D:/数维杯比赛/data/processed/carbon_profile.csv`
- WRITE: `D:/数维杯比赛/data/processed/grid_limits.csv`
- WRITE: `D:/数维杯比赛/data/processed/ess_params.json`
- WRITE: `D:/数维杯比赛/data/processed/ev_sessions_clean.csv`
- WRITE: `D:/数维杯比赛/data/processed/ev_aggregate_profile.csv`
- WRITE: `D:/数维杯比赛/data/processed/flexible_load_params.csv`
