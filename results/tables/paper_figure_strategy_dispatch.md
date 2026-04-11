# 论文图表方案：问题一 vs 基线「调度方案」展示（基于现有时序）

> **修订说明**：若以**问题一为时序主体**、基线仅保留购电对比与表格呈现，请优先阅读  
> **`paper_figure_strategy_p1_focused.md`**，并使用 `plot_paper_dispatch_p1_focused.py` 出图。

数据前提：`results/tables/problem1_dispatch_timeseries.csv` 与 `baseline_dispatch_timeseries.csv`（由 `build_dispatch_timeseries_tables.py` 生成，**不改模型**）。时间步长 15 min，功率在步内常视为常值，**优先用阶梯图（`steps-post`）** 表达调度断面。

---

## 1. 变量与图型适配（阶梯 / 折线 / 散点 / 热力）

| 变量/主题 | 推荐图型 | 理由 |
|-----------|----------|------|
| 购电、各设备功率（ESS/EV/建筑移位恢复/弃光/切负荷）；售电仅在为非零时另绘 | **阶梯图**（首选）或细折线 | 与离散时段常值假设一致；**本算例售电全周为 0**，图面以**外网购电**为主，见 `paper_p1_grid_pv_digest_zh.md`。 |
| 分时电价、峰/谷标记 | **阶梯图** | 电价本身为时段常数或分段常数。 |
| 储能能量 `ess_energy_end_kwh`（时段末） | **阶梯图** | SOC 在步末跳变，阶梯与模型输出一致。 |
| 原生负荷 `native_load_kw` | **阶梯图或折线** | 外生输入，阶梯与数据采样一致。 |
| 两连续变量关系（如电价–购电） | **散点或密度等高** | 看联合分布、尾部差异；**服务机制解释**时作**附录**更合适。 |
| 全周「多变量 × 时间」总览 | **热力图**（行为附录） | 行=变量、列=时段，色=功率；信息密但抽象，适合补充材料。 |

---

## 2. 正文图 + 附录图推荐方案（少而密）

| 位置 | 建议张数 | 内容 |
|------|----------|------|
| **正文** | **2～3 张** | ① 外网购电阶梯对比（典型日）；② 灵活资源净功率四行总览（典型日）；③（可选）储能 SOC 阶梯对比（典型日）。 |
| **附录** | **2～3 张** | 上述①②③的**全周**版本；或再加 1 张电价–购电散点/热力作敏感性对照。 |

叙事顺序建议：**先购电结果（削峰填谷「果」）→ 再灵活资源净功率（「因」与机制）→ 再 SOC（「能」的跨时转移）**。

---

## 3. 优先推荐的 3 张图（最值得画）

### 正文图 1：典型日外网购电功率阶梯对比（上下分面）

- **想证明什么**：在相同日历日与电价结构下，**协调优化显著改变购电曲线形状**（压低尖峰、改变谷段取电），直接对应「削峰填谷」的**网侧结果**。
- **图型**：上下两行子图，上行问题一、下行基线；**外网购电**为蓝色/橙色粗阶梯线；本算例售电恒为 0，**不绘售电曲线**（口径见 `paper_p1_grid_pv_digest_zh.md`）。
- **数据字段**：`timestamp`；`grid_import_kw`（两侧）；可选 `price_buy_yuan_per_kwh`（另图或附录叠放）。

### 正文图 2：典型日灵活资源净功率四行总览（共用时间轴）

- **想证明什么**：**机制差异**——协调模型在时间轴上同时动用 **ESS 净放/充、EV 净放/充、建筑移位−恢复、弃光**；基线 EV 净功率恒为负（仅充）、建筑与多数储能行为弱或缺失，**一张图讲完「多了哪些调节维度」**。
- **图型**：4 行子图 × 每行双线阶梯（问题一 vs 基线）；净功率定义见下。
- **数据字段**：  
  - `ess_net_kw = ess_discharge_kw - ess_charge_kw`  
  - `ev_net_kw = ev_discharge_kw - ev_charge_kw`  
  - `building_net_kw = building_shift_kw - building_recover_kw`  
  - `pv_curtail_kw`

### 正文图 3：典型日储能能量（时段末）阶梯对比

- **想证明什么**：**跨时备能**——协调模型在谷/低价段抬升 SOC、在峰段释放；基线 SOC 轨迹更平或缺乏「先充后放」的清晰相位，支撑「协同调度优化储能时间路径」。
- **图型**：单轴或轻分面双线阶梯；`ess_energy_end_kwh`。
- **数据字段**：`timestamp`；`ess_energy_end_kwh`（问题一、基线各一列）。

---

## 4. 阶梯图优先说明

15 min 最优解功率与时段末能量均为**分段常数或分段跳变**，用 `steps-post` 与「决策保持到下一时刻」的阅读习惯一致；折线连接中点易误导「线性过渡」，故**正文以阶梯为主**。

---

## 5. 各图数据字段来源（CSV 列名）

统一表 `problem1_dispatch_timeseries.csv` / `baseline_dispatch_timeseries.csv` 经 `timestamp` 对齐后：

| 图 | 问题一列名 | 基线列名 |
|----|------------|----------|
| 外网购电阶梯 | `grid_import_kw` | `grid_import_kw` |
| 售电（本算例为 0，可省略） | `grid_export_kw` | `grid_export_kw` |
| 电价（可选叠图） | `price_buy_yuan_per_kwh` | 同左（对齐后一致） |
| ESS 净功率 | `ess_discharge_kw`, `ess_charge_kw` 组合 | 同左 |
| EV 净功率 | `ev_discharge_kw`, `ev_charge_kw` | 同左 |
| 建筑净移位 | `building_shift_kw`, `building_recover_kw` | 同左（基线多为 0） |
| 弃光 | `pv_curtail_kw` | `pv_curtail_kw` |
| 储能 SOC | `ess_energy_end_kwh` | `ess_energy_end_kwh` |

---

## 6. 作图脚本

仓库脚本：`code/python/analysis/plot_paper_dispatch_strategy_bundle.py`  

```bash
python code/python/analysis/plot_paper_dispatch_strategy_bundle.py --repo-root "D:\数维杯比赛"
```

已生成：`results/figures/paper_strategy_01_grid_{typicalday,fullweek}.png`、`paper_strategy_02_flex_net_*.png`、`paper_strategy_03_ess_soc_*.png`；说明 `results/tables/paper_strategy_bundle_readme.txt`。

---

## 与原 8 张时间散点合图关系

- 原 `paper_tscatter_*` 强调「点云密度」；**本方案以阶梯/机制总览为主**，更适合「调度方案」叙事。
- 已实现的 `paper_composite_*` 可与本 bundle **择一使用**；本 bundle 增补 **SOC 图** 并统一命名 `paper_strategy_*`，便于投稿版本管理。
