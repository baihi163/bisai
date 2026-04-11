# 论文合图重构说明

## 原 8 张时间散点图 → 新 4 张合图（压缩关系）

| 原图（8 张） | 并入新图 |
|--------------|-----------|
| `paper_tscatter_01_grid_*`（购电散点；售电本算例为 0 不绘） | **合图 1**：`paper_composite_01_grid_import_*` — 外网购电阶梯线为主，售电曲线省略 |
| `paper_tscatter_02_ess_*` | **合图 2** 第 1 行：储能净功率 |
| `paper_tscatter_03_ev_*` | **合图 2** 第 2 行：EV 净功率 |
| `paper_tscatter_04_flex_pv_*` 中建筑与弃光 | **合图 2** 第 3–4 行：建筑净移位、弃光 |

叙事上：**合图 1** 回答「外网结果是否削峰」；**合图 2** 回答「协同机制由哪些灵活资源在时间轴上承担」。

## 新图文件与建议标题

| 文件 | 建议图题 | 正文 / 附录 |
|------|-----------|-------------|
| `paper_composite_01_grid_import_typicalday.png` | 典型日外网购电功率时间分布（问题一 vs 基线） | **正文**（与削峰填谷叙述直接挂钩） |
| `paper_composite_01_grid_import_fullweek.png` | 全周外网购电功率时间分布（问题一 vs 基线） | **附录** |
| `paper_composite_02_flex_resources_net_typicalday.png` | 典型日灵活资源净功率协同总览 | **正文**（机制一张说清） |
| `paper_composite_02_flex_resources_net_fullweek.png` | 全周灵活资源净功率协同总览 | **附录** |

## 与旧脚本关系

- 旧脚本 `plot_paper_timeseries_scatters.py` 生成的 8 张 `paper_tscatter_*` 可保留作补充材料；**投稿排版以本目录 `paper_composite_*` 为主图**。
- 数据仍来自 `problem1_dispatch_timeseries.csv` / `baseline_dispatch_timeseries.csv`（经 `build_paper_timeseries_scatter_data.merge_aligned` 对齐）。

## 作图脚本

`code/python/analysis/plot_paper_dispatch_composite_figures.py`

可选合并净功率表：`paper_composite_merged_net_*.csv`。

## 图注建议（本算例）

合图 1 图下已自动生成脚注：售电全周为 0（`grid_export_energy_kwh=0`）故不绘售电；`pv_curtail_energy_kwh=0`，光伏完全本地消纳、系统持续净购电。详见 `paper_p1_grid_pv_digest_zh.md`。
