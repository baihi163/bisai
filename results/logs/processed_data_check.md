# Processed Data Check

- 生成时间: 2026-04-10 16:00:38
- 数据目录: `D:/数维杯比赛/data/processed`

## 严重问题（Fatal）
- <span style='color:red'>🔴 ess_params.json: 缺少关键字段 ['soc_min_frac', 'soc_max_frac']</span>

## 警告（Warning）
- 无

## 通过项（OK）
- ✅ load_profile.csv: 行数为 672
- ✅ load_profile.csv: 包含 timestamp
- ✅ pv_profile.csv: 行数为 672
- ✅ pv_profile.csv: 包含 timestamp
- ✅ price_profile.csv: 行数为 672
- ✅ price_profile.csv: 包含 timestamp
- ✅ carbon_profile.csv: 行数为 672
- ✅ carbon_profile.csv: 包含 timestamp
- ✅ grid_limits.csv: 行数为 672
- ✅ grid_limits.csv: 包含 timestamp
- ✅ ev_aggregate_profile.csv: 行数为 672
- ✅ ev_aggregate_profile.csv: 包含 timestamp
- ✅ load_profile.csv: 负荷均非负
- ✅ pv_profile.csv: 光伏非负
- ✅ pv_profile.csv: 夜间基本为0（非零占比 2.50%）
- ✅ price_profile.csv: 购/售电价字段完整
- ✅ price_profile.csv: 售电价不高于购电价
- ✅ carbon_profile.csv: 碳排因子非负
- ✅ grid_limits.csv: 购/售电功率上限存在且非负
- ✅ ev_sessions_clean.csv: 时间顺序正确
- ✅ ev_sessions_clean.csv: 能量未超过电池容量
- ✅ ev_sessions_clean.csv: V2B 一致性通过
- ✅ ev_aggregate_profile.csv: 关键聚合字段均非负
- ✅ flexible_load_params.csv: 关键参数无缺失

## 总结
- Fatal: 1
- Warning: 0
- OK: 24
