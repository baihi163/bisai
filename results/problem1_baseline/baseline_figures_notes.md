# Baseline 图表与数据说明（供 MATLAB 与论文对照）

## 输出文件一览

| 文件 | 类型 | 用途 |
|------|------|------|
| `baseline_kpi_table.csv` / `.md` | 表 | KPI 指标键名、中文名、数值、单位与含义，便于报告与 MATLAB 读表。 |
| `baseline_strategy_table.md` | 表 | 非协同策略文字说明，与协同模型策略对比时用。 |
| `baseline_plot_data.csv` | 时序 | **MATLAB 主作图源**：UTF-8 CSV，列名英文化，可直接 `readtable` / `readmatrix`。 |
| `figures/baseline_*_preview.png` | 图 | Python 预览，检查趋势与数量级；**论文终稿建议用 MATLAB 重绘**。 |

## 各预览图含义

1. **baseline_overview_preview.png**  
   - 原生负荷、EV 总充电、光伏可用、购电功率同屏（购电为右轴）。  
   - 用于快速查看供需与购电是否随负荷/光伏联动。

2. **baseline_ess_preview.png**  
   - 储能能量（kWh）与充、放电功率（kW）。  
   - 用于检查 SOC 轨迹及高价放电、光伏充电等行为是否与策略一致。

3. **baseline_price_grid_preview.png**  
   - 购电功率与购电电价。  
   - 用于对照电价时段与购电/储能逻辑。

4. **baseline_ev_summary_preview.png**  
   - 左：离站需求满足/未满足车辆数；右：离站能量缺口 `max(0, 需求−实际)` 直方图。  
   - 用于评估到站即充规则下的 EV 达标情况。

## MATLAB 读取建议

- 使用 `baseline_plot_data.csv`，注意编码为 **UTF-8**（必要时指定 `Encoding`）。  
- `timestamp` 列为字符串或解析为 `datetime`。  
- 功率类列为 kW，能量列为 kWh，电价为 元/kWh。

## 与协同模型比较时的用法

1. **KPI 表**：协同模型运行后生成同结构 `*_kpi_table.csv`，按 `metric_key` 对齐逐行对比。  
2. **时序作图数据**：协同模型导出相同列名的 `*_plot_data.csv`，在 MATLAB 中叠加曲线或计算差分序列（购电、弃光、成本等）。  
3. **策略表**：论文中可用两列表格并列描述 baseline 规则与协同优化差异。  
4. **预览图**：仅作开发检查；对比图建议在 MATLAB 中统一线型、色板与分辨率后出图。

---
*由 `code/python/baseline/export_baseline_reports.py` 生成*
