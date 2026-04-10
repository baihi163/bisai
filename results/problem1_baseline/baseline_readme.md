# 问题1 非协同调度基准（baseline）

## 策略说明

1. **建筑负荷**：仅使用 `total_native_load_kw`，柔性负荷调节量为 0。
2. **电动汽车**：到站即充——在连接时段内若电量未达离站目标，则按交流侧功率
   `min(最大充电功率上限, 目标与容量约束折算后的需求功率)` 充电；电池侧能量
   **ΔE = η_ev × P_ac × Δt**，其中 **η_ev = 0.92**（见下「假设」）。
   **不向园区放电（无 V2B）**；不考虑电价与光伏余量；未达标会话仅标记，不中断仿真。
3. **固定储能**：
   - 仅使用**剩余光伏**（满足负荷与 EV 后的交流剩余）以效率 `charge_efficiency` 充电；
   - 当购电价落入**全周高价区间**——即不低于购电价样本的 **0.80 分位数**（约最贵 **20%** 时段）——且存在功率缺口时，按效率 `discharge_efficiency` 放电以降低购电；
   - 其余时段静置（不从电网充电）。
4. **光伏**：优先供本地（负荷+EV 充电）；剩余依次用于储能充电、上网（受出口上限）、弃光。
5. **电网**：缺口购电受进口上限约束；不足部分记为 `unmet_load_kw`，仿真继续。

## 时段内计算顺序

对每个 15 min：`EV 充电功率（交流）` → `总需求 = 原生负荷 + EV 充电` → `光伏供本地` → `高价区间则储能放电补缺口` → `购电` → `剩余光伏充储能` → `上网与弃光`。

## 输出字段（timeseries）

| 字段 | 含义 |
|------|------|
| native_load_kw | 园区原生总负荷 |
| ev_total_charge_kw | EV 总充电功率（**交流侧**，kW） |
| ev_total_discharge_kw | 基准为 0 |
| total_load_with_ev_kw | 原生负荷 + EV 充电 |
| pv_used_locally_kw | 光伏直接供负荷+EV 部分 |
| pv_to_ess_kw | 剩余光伏进储能的充电功率 |
| pv_export_kw | 再剩余经上网功率 |
| pv_curtailed_kw | 超上网上限的弃光 |
| net_load_before_ess_kw | 总需求 − 本地消纳光伏（储能动作前净需求） |
| net_load_after_ess_kw | 储能放电后的净需求（购电前） |
| residual_demand_after_pv_kw | 与 net_load_before_ess_kw 同义（表述用） |
| residual_demand_after_ess_kw | 与 net_load_after_ess_kw 同义（表述用） |
| ess_energy_kwh | **时段末**储能能量 |
| unmet_load_kw | 购电达上限后仍不足的功率缺口 |
| buy_price / sell_price | 电价（元/kWh） |

## KPI 说明

- **pv_utilization_rate**：`1 - 总弃光电量 / 总可发电量`（含本地、储能、上网，弃光以外均视为已利用）。
- **total_ev_charge_kwh**：交流侧 EV 充电电量累计。
- **ev_average_completion_ratio**：各车 `energy_completion_ratio`（离站时）的算术平均（仅对有效值）。

## 假设与局限

- **η_ev（EV_CHARGE_EFFICIENCY）**：输入未提供实测充电曲线，取 **0.92** 代表车载充电机 AC→电池的典型效率（工程文献常见约 0.90–0.95），用于统一折算交流充电功率与电池能量，保证状态方程物理一致。
- **高价区间**：由全周购电价 **0.80 分位**阈值确定，**非**全局优化；若全周电价完全相同，则阈值等于该常数，所有时段均落入高价区间（与分位定义一致）。
- 未建立交流潮流与损耗模型；功率瞬时平衡。
- 未考虑充电桩数量同时率等约束，仅用单车功率上限矩阵。

## 本数据周可能出现的现象

若全周每个时段均有「原生负荷 + EV 充电 ≥ 可用光伏」，则**剩余光伏为 0**，储能按规则**无法**从光伏充电（`pv_to_ess_kw` 恒为 0），仅能在高价时段放电直至触及 SOC 下界。此为数据与规则共同结果，非程序错误。

## 输入校验

仿真前写入 `baseline_input_validation_report.md`（与脚本同输出目录），汇总矩阵维度、SOC/功率边界及 V2B 与放电矩阵一致性等检查。

---
*生成脚本：`code/python/baseline/run_baseline_noncooperative.py`*
