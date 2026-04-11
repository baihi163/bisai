# 灵敏度分析汇总表

## 自动生成结论（EV 与权重及龙卷风）

在 EV 充放功率上限缩放条件下，以缩放系数 1.0 为基准，运行成本相对变化在 -0.089%～0.115% 量级；EV 吞吐与放电量随可用功率放宽而上升、收紧而下降，符合可调资源约束收紧时运行域收缩的直觉。图中 x=1.0 与 y=0% 参考线便于对照名义设计点。

在统一基准运行成本（约 38973.22 元）下，**PV出力缩放** 对运行成本最为敏感：低值（PV=0.9）与高值（PV=1.1）相对基准的最大绝对变化率约为 **4.37%**。

**寿命权重** 的影响相对最弱，其低/高端点相对基准的最大绝对变化率约为 **0.03%**。

寿命权重支路在全周模型上直接改变退化惩罚权重，优化器主要通过 **抑制 EV/ESS 吞吐与放电形态** 来降低退化货币化成本，因而在 w=0 与 w=2 端点之间，**运行成本** `operation_cost` 的相对波动幅度通常较小（本算例约 **0.03%** 量级），明显弱于 **PV 出力缩放** 通过改变可再生可用功率与购电结构所带来的成本杠杆（约 **4.37%** 量级）。换言之，寿命权重更显著地体现在 **资源调用轨迹与退化分项** 的再分配上，而非短期电费账面的剧烈跳变。

## 明细表

| parameter | scenario | metric | raw_value | relative_change_pct | baseline_reference |
| --- | --- | --- | --- | --- | --- |
| ev_power_scale=0.8 | problem2_lifecycle_ev_scale | operation_cost | 6584.872103275001 | 0.1151684529080087 | ev_power_scale=1.0, operation_cost=6577.297131925 |
| ev_power_scale=0.8 | problem2_lifecycle_ev_scale | ev_throughput_kwh | 329.23473685749883 | -1.792103451914058 | ev_power_scale=1.0, ev_throughput_kwh=335.24263163125 |
| ev_power_scale=0.8 | problem2_lifecycle_ev_scale | ev_discharge_energy_kwh | 108.68000000000008 | -4.983388704318865 | ev_power_scale=1.0, ev_discharge_energy_kwh=114.38 |
| ev_power_scale=0.8 | problem2_lifecycle_ev_scale | ess_throughput_kwh | 961.2631575 | 0.0 | ev_power_scale=1.0, ess_throughput_kwh=961.2631575 |
| ev_power_scale=1.0 | problem2_lifecycle_ev_scale | operation_cost | 6577.297131925 | 0.0 | ev_power_scale=1.0, operation_cost=6577.297131925 |
| ev_power_scale=1.0 | problem2_lifecycle_ev_scale | ev_throughput_kwh | 335.24263163125 | 0.0 | ev_power_scale=1.0, ev_throughput_kwh=335.24263163125 |
| ev_power_scale=1.0 | problem2_lifecycle_ev_scale | ev_discharge_energy_kwh | 114.38 | 0.0 | ev_power_scale=1.0, ev_discharge_energy_kwh=114.38 |
| ev_power_scale=1.0 | problem2_lifecycle_ev_scale | ess_throughput_kwh | 961.2631575 | 0.0 | ev_power_scale=1.0, ess_throughput_kwh=961.2631575 |
| ev_power_scale=1.2 | problem2_lifecycle_ev_scale | operation_cost | 6571.446630325001 | -0.08894993616149313 | ev_power_scale=1.0, operation_cost=6577.297131925 |
| ev_power_scale=1.2 | problem2_lifecycle_ev_scale | ev_throughput_kwh | 341.2505262900007 | 1.792103417610416 | ev_power_scale=1.0, ev_throughput_kwh=335.24263163125 |
| ev_power_scale=1.2 | problem2_lifecycle_ev_scale | ev_discharge_energy_kwh | 120.07999999999991 | 4.983388704318865 | ev_power_scale=1.0, ev_discharge_energy_kwh=114.38 |
| ev_power_scale=1.2 | problem2_lifecycle_ev_scale | ess_throughput_kwh | 961.2631575 | 0.0 | ev_power_scale=1.0, ess_throughput_kwh=961.2631575 |
| lifetime_weight_w=0.0 | problem2_lifecycle_weight_scan | operation_cost | 38962.11295492504 | -0.028497314133698697 | w=1.0, operation_cost=38973.21927565004 |
| lifetime_weight_w=0.0 | problem2_lifecycle_weight_scan | objective_total | 38962.11295492475 | -1.2804046245023015 | w=1.0, objective_total=39467.45608784696 |
| lifetime_weight_w=0.0 | problem2_lifecycle_weight_scan | ev_throughput | 1615.29978544 | 12.066471333302891 | w=1.0, ev_throughput=1441.3765029112503 |
| lifetime_weight_w=0.0 | problem2_lifecycle_weight_scan | ess_throughput | 6728.842102499999 | 0.1883239068326776 | w=1.0, ess_throughput=6716.193903749999 |
| lifetime_weight_w=0.1 | problem2_lifecycle_weight_scan | operation_cost | 38962.11295847503 | -0.02849730502490369 | w=1.0, operation_cost=38973.21927565004 |
| lifetime_weight_w=0.1 | problem2_lifecycle_weight_scan | objective_total | 39013.09060169 | -1.1512408733555801 | w=1.0, objective_total=39467.45608784696 |
| lifetime_weight_w=0.1 | problem2_lifecycle_weight_scan | ev_throughput | 1615.29978544 | 12.066471333302891 | w=1.0, ev_throughput=1441.3765029112503 |
| lifetime_weight_w=0.1 | problem2_lifecycle_weight_scan | ess_throughput | 6728.842102499999 | 0.1883239068326776 | w=1.0, ess_throughput=6716.193903749999 |
| lifetime_weight_w=0.5 | problem2_lifecycle_weight_scan | operation_cost | 38962.23993782504 | -0.028171493217794774 | w=1.0, operation_cost=38973.21927565004 |
| lifetime_weight_w=0.5 | problem2_lifecycle_weight_scan | objective_total | 39216.78032843792 | -0.6351454698551682 | w=1.0, objective_total=39467.45608784696 |
| lifetime_weight_w=0.5 | problem2_lifecycle_weight_scan | ev_throughput | 1615.29978544 | 12.066471333302891 | w=1.0, ev_throughput=1441.3765029112503 |
| lifetime_weight_w=0.5 | problem2_lifecycle_weight_scan | ess_throughput | 6716.193903749999 | 0.0 | w=1.0, ess_throughput=6716.193903749999 |
| lifetime_weight_w=1.0 | problem2_lifecycle_weight_scan | operation_cost | 38973.21927565004 | 0.0 | w=1.0, operation_cost=38973.21927565004 |
| lifetime_weight_w=1.0 | problem2_lifecycle_weight_scan | objective_total | 39467.45608784696 | 0.0 | w=1.0, objective_total=39467.45608784696 |
| lifetime_weight_w=1.0 | problem2_lifecycle_weight_scan | ev_throughput | 1441.3765029112503 | 0.0 | w=1.0, ev_throughput=1441.3765029112503 |
| lifetime_weight_w=1.0 | problem2_lifecycle_weight_scan | ess_throughput | 6716.193903749999 | 0.0 | w=1.0, ess_throughput=6716.193903749999 |
| lifetime_weight_w=2.0 | problem2_lifecycle_weight_scan | operation_cost | 38973.53998605003 | 0.0008228994318570657 | w=1.0, operation_cost=38973.21927565004 |
| lifetime_weight_w=2.0 | problem2_lifecycle_weight_scan | objective_total | 39961.39380651187 | 1.2515063488396725 | w=1.0, objective_total=39467.45608784696 |
| lifetime_weight_w=2.0 | problem2_lifecycle_weight_scan | ev_throughput | 1436.29614281125 | -0.35246586091413806 | w=1.0, ev_throughput=1441.3765029112503 |
| lifetime_weight_w=2.0 | problem2_lifecycle_weight_scan | ess_throughput | 6716.193903749999 | 0.0 | w=1.0, ess_throughput=6716.193903749999 |
| PV出力缩放｜PV=0.9 | p2_unified_tornado | operation_cost | nan | 4.373463661901026 | ref_operation_cost=38973.219276 |
| PV出力缩放｜PV=1.1 | p2_unified_tornado | operation_cost | nan | -4.373463661901007 | ref_operation_cost=38973.219276 |
| EV可用性缩放｜EV=0.8 | p2_unified_tornado | operation_cost | nan | 0.11516845290799574 | ref_operation_cost=38973.219276 |
| EV可用性缩放｜EV=1.2 | p2_unified_tornado | operation_cost | nan | -0.08894993616150014 | ref_operation_cost=38973.219276 |
| 寿命权重｜w=0 | p2_unified_tornado | operation_cost | nan | -0.028497314133698697 | ref_operation_cost=38973.219276 |
| 寿命权重｜w=2 | p2_unified_tornado | operation_cost | nan | 0.0008228994318570657 | ref_operation_cost=38973.219276 |

*完整数据见 `sensitivity_analysis_summary.csv`。*