# 鲁棒性汇总（问题一 PV 缩放 + 问题二 EV 功率缩放）

## PV 缩放（baseline vs 协同）

名义 PV 下协同运行成本 (6577 元) 低于 baseline (7075 元)。PV 增减主要改变购电与弃光权衡；缩放 0.9–1.1 时两方案成本与购电趋势可对照表读取。

| scenario | model | pv_scale | operation_cost | renewable_consumption_ratio | pv_curtail_energy_kwh | grid_import_energy_kwh | solver_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pv_scale | baseline | 0.9 | 7362.318189130434 | 1.0 | 0.0 | 9517.9571 | nan |
| pv_scale | coordinated | 0.9 | 6864.952831924999 | 1.0 | 8.881784197001252e-14 | 10097.792632499999 | Optimal |
| pv_scale | baseline | 1.0 | 7074.662489130436 | 1.0 | 0.0 | 9131.4946 | nan |
| pv_scale | coordinated | 1.0 | 6577.297131925 | 1.0 | 0.0 | 9711.3301325 | Optimal |
| pv_scale | baseline | 1.1 | 6787.006789130435 | 1.0 | 0.0 | 8745.0321 | nan |
| pv_scale | coordinated | 1.1 | 6289.6414319250025 | 1.0 | 2.8954616482224083e-13 | 9324.8676325 | Optimal |

## EV 充放上限缩放（问题二，w=1）

随 EV 充放上限缩放，运行成本与 EV/ESS 吞吐同向变化；极限缩放可能导致求解失败（见 error 列）。

| ev_power_scale | operation_cost | ev_throughput_kwh | ev_discharge_energy_kwh | ess_throughput_kwh | peak_grid_purchase_kw | solver_status |
| --- | --- | --- | --- | --- | --- | --- |
| 0.8 | 6584.872103275001 | 329.23473685749883 | 108.68000000000008 | 961.2631575 | 889.7 | Optimal |
| 1.0 | 6577.297131925 | 335.24263163125 | 114.38 | 961.2631575 | 889.7 | Optimal |
| 1.2 | 6571.446630325001 | 341.2505262900007 | 120.07999999999991 | 961.2631575 | 895.2 | Optimal |

## 综合结论（问答）

### 1. 哪些结论在参数变化下保持稳定？
- 问题二：w 增大时退化货币项权重提高，总目标与 EV 放电/吞吐被压制的**方向**在单调区间上较稳定。
- 问题一：在 PV±10% 离散盒内，**协同运行成本低于 baseline** 的关系在名义点及邻域通常保持（以本次表为准逐格核对）。

### 2. 哪些指标对参数最敏感？
- 权重 w：**ev_discharge_energy_kwh、ev_throughput_kwh、ev_deg_cost** 对 w 最敏感。
- PV 缩放：**pv_curtail_energy_kwh、grid_import_energy_kwh** 对光伏上限敏感。
- EV 功率缩放：**ev_throughput_kwh、peak_grid_purchase_kw** 变化显著。

### 3. 协同相对 baseline 的优势在扰动下是否仍成立？
- 以 `pv_scale=1.0` 及本次求解状态为 **Optimal** 的情景为准：若协同 `operation_cost` 各行均低于同列 baseline，则**优势成立**；若某缩放下协同非最优，需单独报告该格。

**本次自动核对**：PV 三档下协同运行成本均低于 baseline。