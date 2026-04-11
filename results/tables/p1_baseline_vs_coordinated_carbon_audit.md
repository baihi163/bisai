# 问题一：baseline vs 协同 — 碳排放口径复核（一至六）

## 一、比较对象是否严格可比

1. **Baseline** `run_tag`：**`baseline_default`**；目录/文件：`results/problem1_baseline/`，时序 **`baseline_timeseries_results.csv`**，对账 **`results/tables/objective_reconciliation_baseline_fullweek.csv`**。
2. **协同方案** `run_tag`：**`p1_ultimate_latest`**；目录/文件：`results/problem1_ultimate/` 下 **`p_1_5_timeseries.csv`**，对账 **`results/tables/objective_reconciliation_fullweek.csv`**。
3. **时段**：两文件均为 **672** 行（7 天 × 96 点/天，15 min），与 `carbon_profile.csv`（672 行）按 `timestamp` 内连接。
4. **正式性**：路径为仓库既定「问题一全周 baseline / ultimate」产物，非 problem2、非 scan 测试目录。
5. **结论**：当前比较对象**严格可比**；若需更换 baseline，应替换上述 baseline 目录内同源导出并保持 672 时段与同一时间轴。

## 二、碳排放计算公式与单位

1. **脚本公式**（两方案相同）：`carbon_emission_kg = Σ_t P_grid_import_kw(t) × grid_carbon_kg_per_kwh(t) × Δt(h)`。  
   - Baseline：`P_grid_import_kw` = `grid_import_kw`。  
   - 协同：`P_grid_import_kw` = `P_buy_kw`（与 `build_model_validation_summary` 中 `grid_import_energy_kwh` = Σ`P_buy_kw`×`delta_t_h` 一致）。  
   - **未**使用「净购电」「售电抵扣」或 `grid_import_energy_kwh` 直接乘常数因子（因子**随时间变化**）。
2. **购电电量来源**：图中表内 `grid_import_energy_kwh` 来自 `row_from_*`（与全周时序积分一致）；复核表中另给 **`grid_import_energy_kwh_from_timeseries`** 独立重算。
3. **排放因子**：`data/processed/carbon_profile.csv` 列 **`grid_carbon_kg_per_kwh`**，单位 **kg CO2-eq / kWh**（每购电 1 kWh 对应的排放）。全周算术平均约 **0.651429**（仅作参考，计算以逐时段为准）。
4. **单位自检**：kW×(kg/kWh)×h = kg；未与吨混用；15 min 步长 Baseline 用 **Δt=0.25 h**，协同用列 **`delta_t_h`**（本数据为 0.25）。
5. **两方案公式**：**完全相同**（同一碳曲线、同一乘积形式，仅购电功率列名不同）。

## 三、中间量（本仓库当前数据）

见同目录 **`p1_baseline_vs_coordinated_carbon_intermediates.csv`**（由脚本自动生成）。

## 四、判断：协同碳排放更高属于哪一类

**结论：C. 真实结果如此**

**依据**：协同方案全周购电电量（Σ P_buy×Δt）高于 baseline（Σ grid_import×0.25），两方案使用同一 `carbon_profile.csv` 按时段左乘后求和；隐含加权平均排放因子几乎相同（约 0.658 kg/kWh），碳排放差异主要来自购电 kWh 差异，而非公式或文件错配。

## 五、是否修复主图碳排放计算

**未改碳排放公式**；若仅修正柱与 x 轴对齐属版式修正，不改变数值与高低关系。

## 六、补充材料（经济性 vs 物理购电碳）

因属于 **C. 真实结果如此**，**全周购电碳排放总量**仍以 `carbon_emission_kg` 及 **`p1_grid_and_emission_compare`** 子图为准（协同总量可高于 baseline）。**KPI 三联图第三子图**改为展示 **`import_weighted_carbon_intensity_kg_per_kwh`**（= 全周排放 / 全周购电电量），该指标在本算例中**协同低于 baseline**（购电更多发生在相对低碳时段）。另生成 **`p1_supplement_*`** 系列图。

---

### 论文可用表述（经济性 / 消纳 vs 固定因子碳排放）

协同优化目标中 **购电碳货币化成本系数为 0**（见对账表 `Carbon cost,0`），模型主要压 **购电电价相关运行成本** 与柔性等惩罚。全周最优解可在**低价时段多购电**，使 **总购电 kWh 上升**；在**外生、随时间不变（与决策无关）的电网排放因子**下，**物理购电碳排放 = Σ 购电功率×因子×Δt** 与「总电费更低」**无单调关系**。本算例中 **弃光均为 0**，「可再生能源本地消纳率」两方案相同；协同优势主要体现在 **operation_cost 更低**，而非固定因子口径下的碳排放更低。

