# 问题一全周算例：电网侧与光伏消纳（结果摘要，供正文/表引用）

以下数值来自 `results/tables/problem1_result_summary.csv`（行 `p1_coordinated` / `p1_ultimate_latest`）及与之一致的时序积分口径。

| 指标 | 数值 | 说明 |
|------|------|------|
| **grid_export_energy_kwh** | **0** | 全周向电网送出的有功电量累计；售电功率时序恒为 0。 |
| **pv_curtail_energy_kwh** | **0** | 全周弃光电量；与「光伏可用功率均被利用」一致。 |

**分析口径（建议正文表述）**

- **光伏完全本地消纳**：弃光电量为 0，可用光伏功率在各时段均被模型取为本地利用（与负荷、储能充电、EV 充电等共同满足功率平衡），无弃光、无外送富余。
- **系统持续净购电**：全周 `grid_export_energy_kwh = 0` 且购电能量为正，母线侧不存在需反送电网的净富余功率；**未出现售电并非缺少反送约束**，而是由本算例负荷—光伏—灵活资源的联合最优解决定。

基线（`baseline_noncooperative` / `baseline_default`）在 `model_validation_summary.csv` 中同样为 **grid_export_energy_kwh = 0**、**pv_curtail_energy_kwh = 0**，可与问题一并列说明「本数据周园区未出现上网与弃光」。
