# 问题1 MATLAB 可视化说明（与 Python 分工）

## 协作规范

| 职责 | 语言 | 说明 |
|------|------|------|
| 仿真、KPI、结果文件 | Python | `code/python/baseline/run_baseline_noncooperative.py`、`export_baseline_reports.py` 等 |
| 论文级作图 | MATLAB | 仅读取 `results/` 下 CSV，**不**重复 baseline 数值推演 |

## 目录结构

```text
code/matlab/
├── utils/
│   └── get_project_root.m      # 仓库根目录（相对 utils 向上三级）
├── visualization/
│   └── set_plot_style.m        # 默认线宽、字号、网格等
└── problem1/
    ├── main_problem1_figures.m # 入口：生成三张核心图
    ├── plot_baseline_overview.m
    ├── plot_baseline_ess.m
    └── plot_baseline_ev_summary.m
```

## 各脚本作用与输入输出

### `utils/get_project_root.m`

- **作用**：定位仓库根目录（要求存在 `results` 与 `code`）。
- **输入**：无。
- **输出**：根目录绝对路径（`char`）。

### `visualization/set_plot_style.m`

- **作用**：设置 `Default*` 绘图默认值（Times New Roman、线宽、白底、网格等）。
- **输入**：无。
- **输出**：无（全局图形默认值）。

### `problem1/main_problem1_figures.m`

- **作用**：将 `utils`、`visualization` 加入路径；创建输出目录；调用三张绘图函数。
- **输入**：无（隐式依赖 Python 已生成的结果文件）。
- **输出目录**：`results/problem1_baseline/figures_matlab/`

### `problem1/plot_baseline_overview.m`

- **作用**：全周总览——原生负荷、EV 总充电、光伏可用（左轴）；购电功率（右轴）。
- **输入文件**：`results/problem1_baseline/baseline_plot_data.csv`
- **输出文件**：`figures_matlab/baseline_overview_matlab.png`（300 dpi PNG）

### `problem1/plot_baseline_ess.m`

- **作用**：储能能量轨迹与充、放电功率（双轴）。
- **输入文件**：`results/problem1_baseline/baseline_plot_data.csv`
- **输出文件**：`figures_matlab/baseline_ess_matlab.png`（300 dpi PNG）

### `problem1/plot_baseline_ev_summary.m`

- **作用**：左：离站需求满足/未满足会话数；右：能量缺口 `max(0, required−final)` 直方图。
- **输入文件**：`results/problem1_baseline/baseline_ev_session_summary.csv`
- **输出文件**：`figures_matlab/baseline_ev_summary_matlab.png`（300 dpi PNG）

## MATLAB 版本建议

- 推荐 **R2018b 及以上**（`yyaxis`、`sgtitle`、`detectImportOptions` + `Encoding`）。
- 作图使用 `print(..., '-dpng', '-r300')` 输出约 300 dpi PNG，便于论文插入。

## 运行前准备

1. 在仓库根目录已运行 Python baseline 仿真与导出，至少存在：
   - `baseline_plot_data.csv`
   - `baseline_ev_session_summary.csv`
2. MATLAB 中执行：
   ```matlab
   cd('你的仓库路径\code\matlab\problem1')
   main_problem1_figures
   ```

## 与协同模型对比（后续）

- 协同模型可在 Python 侧导出**相同列结构**的 `*_plot_data.csv` 与同构 KPI 表；MATLAB 中复制绘图函数并切换数据路径，即可叠加曲线或并排出图。
- 避免在 MATLAB 中根据物理公式重算 baseline，以保证与 Python 单一数据源一致。

---
*文档随 `code/matlab/problem1/` 脚本一并维护。*
