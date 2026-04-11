# 论文表格放置建议（自动生成）

## 建议放正文（精简、叙事强）

- **电网与光伏消纳摘要**（`paper_p1_grid_pv_digest_zh.md`）：明确列出 **`grid_export_energy_kwh = 0`**、**`pv_curtail_energy_kwh = 0`**，并采用「**光伏完全本地消纳、系统持续净购电**」一句定调，与图注口径一致。
- **调度能力统计表**（`paper_dispatch_capability_stats.csv`）：一行一指标、两列对比问题一与基线，最适合在「结果分析」中用 1 段文字 + 1 张小表说明**机制差异**（储能是否可充、EV 是否放电、高价/削峰/填谷代理量等）。
- **典型日小时表**（`paper_typical_day_hourly.csv`）：单页可展示 24 行，便于与**一张叠线图**（**外网购电**/储能/电价）对应，突出「削峰填谷在一天内的形状」。

## 建议放附录（完整但仍压缩）

- **关键调度时段摘要表**（`paper_dispatch_key_segments.csv`）：连续段合并后行数远小于 672，适合附录表；若段数仍偏多，可按 `duration_h` 降序只保留前 15～20 行 + 脚注「完整见补充材料」。

## 建议仅作补充材料 / 数据发布

- **全时段 672 行调度总表**：`problem1_dispatch_timeseries.csv`、`baseline_dispatch_timeseries.csv` 与 `problem1_baseline_dispatch_timeseries_long.csv`，供审稿人核查与复现，正文从略。
- **原始模型时序输出**：`results/problem1_ultimate/p_1_5_timeseries.csv`、`baseline_timeseries_results.csv`。

## 作图配合

- 正文图：典型日 24 h 曲线（由小时表列绘制）。
- 附录图：全周购电对比或按 `paper_dispatch_key_segments` 起止时间分段着色。
