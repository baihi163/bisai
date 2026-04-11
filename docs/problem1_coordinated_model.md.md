# 针对问题一的园区微电网协同调度确定性建模思路

## 1. 问题分析
问题一要求在不考虑预测误差（即完美预测）的条件下，建立园区“微电网—电动车—建筑”系统的**确定性协同调度模型**。该问题本质上是一个**混合整数线性规划（MILP）**问题。
我们需要以 15 分钟为时间步长，在满足园区内各类物理和运行约束的前提下，统筹规划外网购售电、固定储能充放电、电动车（EV）充放电（V2B/V2G）以及建筑柔性负荷的调节，以实现园区运行的经济性、低碳性和高新能源消纳率。同时，需要设计一套非协同的规则型基准策略，通过对比实验突出协同优化的优势。

## 2. 模型假设
1. **完美预测假设**：假设日前或日内对光伏出力、基础负荷、电价及 EV 行程（到离站时间、初始与目标电量）的预测完全准确。
2. **能量守恒与无损耗假设**：假设园区微电网内部的能量传输无损耗，仅在储能和 EV 电池充放电环节考虑交直流转换及化学损耗（即充放电效率）。
3. **离散化时间假设**：调度周期分为 $$T$$ 个时段，每个时段时长 $$\Delta t = 0.25$$ 小时，时段内功率保持恒定。

## 3. 符号说明

| 符号 | 含义 | 符号 | 含义 |
| :--- | :--- | :--- | :--- |
| $$t \in T$$ | 调度时段集合 | $$P_{buy,t}, P_{sell,t}$$ | 时段 $$t$$ 的购电、售电功率 |
| $$i \in N_{ev}$$| 电动汽车集合 | $$P_{ess\_ch,t}, P_{ess\_dis,t}$$ | 固定储能充、放电功率 |
| $$b \in B$$ | 建筑区块集合 | $$P_{ev\_ch,i,t}, P_{ev\_dis,i,t}$$ | EV $$i$$ 的充、放电功率 |
| $$\Delta t$$ | 时间步长 (0.25h) | $$P_{shift,b,t}, P_{shed,b,t}$$ | 建筑 $$b$$ 的平移、削减负荷功率 |
| $$c_{buy,t}, c_{sell,t}$$| 分时购、售电价 | $$P_{pv\_use,t}$$ | 实际利用的光伏功率 |
| $$E_{ess,t}, E_{ev,i,t}$$| 储能、EV 在时段 $$t$$ 末的电量 | $$P_{recover,b,t}$$ | 建筑 $$b$$ 的负荷反弹/恢复功率 |

## 4. 协同调度优化模型建立 (Coordinated Model)

### 4.1 目标函数
以园区微电网综合运行成本最小化为目标，目标函数包含：购售电成本、碳排放成本、弃光惩罚、柔性负荷调节惩罚以及设备（储能/EV）的基础折旧成本。

$$
\min F = C_{grid} + C_{carbon} + C_{curtail} + C_{flex} + C_{deg}
$$

各分项展开如下：
1. **电网交互成本**：$$C_{grid} = \sum_{t \in T} (c_{buy,t} P_{buy,t} - c_{sell,t} P_{sell,t}) \Delta t$$
2. **碳排放成本**：$$C_{carbon} = \sum_{t \in T} p_{carbon} \cdot e_{grid,t} \cdot P_{buy,t} \Delta t$$ （$$p_{carbon}$$ 为碳价，$$e_{grid,t}$$ 为电网碳排放因子）
3. **弃光惩罚**：$$C_{curtail} = \sum_{t \in T} \lambda_{curtail} (P_{pv\_max,t} - P_{pv\_use,t}) \Delta t$$
4. **柔性负荷惩罚**：$$C_{flex} = \sum_{t \in T} \sum_{b \in B} \left[ \lambda_{shift}(P_{shift,b,t} + P_{recover,b,t}) + \lambda_{shed} P_{shed,b,t} \right] \Delta t$$
5. **电池折旧成本**（线性简化版，为问题二做铺垫）：$$C_{deg} = \sum_{t \in T} \left[ c_{deg}^{ess} \frac{P_{ess\_ch,t} + P_{ess\_dis,t}}{2} + \sum_{i \in N_{ev}} c_{deg}^{ev} \frac{P_{ev\_ch,i,t} + P_{ev\_dis,i,t}}{2} \right] \Delta t$$

### 4.2 约束条件

#### 1. 园区功率平衡约束
任何时段，系统的总供给必须等于总需求：
$$
P_{pv\_use,t} + P_{buy,t} + P_{ess\_dis,t} + \sum_{i} P_{ev\_dis,i,t} = P_{load\_served,t} + P_{sell,t} + P_{ess\_ch,t} + \sum_{i} P_{ev\_ch,i,t}
$$
其中，实际服务的建筑负荷为：
$$
P_{load\_served,t} = \sum_{b \in B} (P_{native,b,t} - P_{shift,b,t} + P_{recover,b,t} - P_{shed,b,t})
$$

#### 2. 电网与光伏交互约束
$$
0 \le P_{buy,t} \le P_{imp\_max,t} \cdot U_{grid,t}
$$
$$
0 \le P_{sell,t} \le P_{exp\_max,t} \cdot (1 - U_{grid,t})
$$
$$
0 \le P_{pv\_use,t} \le P_{pv\_max,t}
$$
*(注：$$U_{grid,t} \in \{0,1\}$$ 为防止同时购售电的互斥变量)*

#### 3. 固定储能 (ESS) 运行约束
功率与状态互斥约束：
$$
0 \le P_{ess\_ch,t} \le P_{ess\_ch\_max} \cdot U_{ess,t}
$$
$$
0 \le P_{ess\_dis,t} \le P_{ess\_dis\_max} \cdot (1 - U_{ess,t})
$$
电量(SOC)连续性及边界约束：
$$
E_{ess,t} = E_{ess,t-1} + ( \eta_{ess\_ch} P_{ess\_ch,t} - \frac{P_{ess\_dis,t}}{\eta_{ess\_dis}} ) \Delta t
$$
$$
E_{ess\_min} \le E_{ess,t} \le E_{ess\_max}
$$
$$
E_{ess,T} \ge E_{ess,0} \quad \text{(保证调度周期末电量不低于初始值)}
$$

#### 4. 电动汽车 (EV) 协同约束 (V2B/V2G)
*降维建模技巧：仅在 EV $$i$$ 处于在站状态集合 $$T_i^{park}$$ 时定义变量。*
$$
0 \le P_{ev\_ch,i,t} \le P_{ev\_ch\_max,i,t} \quad \forall t \in T_i^{park}
$$
$$
0 \le P_{ev\_dis,i,t} \le P_{ev\_dis\_max,i,t} \cdot V2B_{allow,i} \quad \forall t \in T_i^{park}
$$
电量演变与离站需求满足：
$$
E_{ev,i,t} = E_{ev,i,t-1} + ( \eta_{ev\_ch} P_{ev\_ch,i,t} - \frac{P_{ev\_dis,i,t}}{\eta_{ev\_dis}} ) \Delta t
$$
$$
0 \le E_{ev,i,t} \le E_{ev\_cap,i}
$$
$$
E_{ev,i,t_{depart}} \ge E_{req,i} \quad \text{(离站时必须满足目标电量)}
$$

#### 5. 建筑柔性负荷约束
可平移、可削减容量上限：
$$
P_{shift,b,t} + P_{shed,b,t} \le (1 - \alpha_{non\_int,b}) P_{native,b,t}
$$
负荷平移的能量守恒（反弹机制）：
$$
E_{backlog,b,t} = E_{backlog,b,t-1} + P_{shift,b,t} \Delta t - \frac{P_{recover,b,t} \Delta t}{\gamma_{rebound}}
$$
$$
E_{backlog,b,T} = 0 \quad \text{(周期末平移负荷必须全部恢复)}
$$

---

## 5. 非协同基准策略设计 (Baseline Strategy)
为了凸显协同调度的优势，设计如下基于规则的非协同（Non-cooperative）基准策略：

1. **电动汽车（无序充电，无 V2B）**：
   采取“到站即充”策略。EV 接入电网后，立即以最大允许功率充电，直至达到离站目标电量或电池充满。不考虑电价高低，且**绝对不参与反向放电**（$$P_{ev\_dis} \equiv 0$$）。
2. **固定储能（被动响应）**：
   - **充电**：仅吸收满足基础负荷和 EV 充电后的**剩余光伏**。
   - **放电**：仅在购电价格处于全周高价区间（如前 20% 分位数），且系统存在功率缺口时放电。不主动进行跨时段的电价套利。
3. **建筑负荷（刚性不可调）**：
   不启用柔性负荷调节机制，$$P_{shift} = P_{shed} = P_{recover} \equiv 0$$。
4. **光伏与电网交互**：
   光伏优先满足本地需求，余电优先充储能，再余则上网，受限于电网容量，超出的部分直接弃光。

## 6. 模型求解与对比分析思路
1. **求解方法**：将上述数学模型在 Python 环境下使用 PuLP 等建模工具构建，并调用 CBC / Gurobi 等商用或开源 MILP 求解器进行全局寻优。
2. **对比维度**：
   - **经济性**：对比总运行成本、购电成本、峰值购电功率。
   - **环保与消纳**：对比光伏消纳率（PV Utilization Rate）、总碳排放量。
   - **系统行为**：绘制典型日的功率平衡堆叠图（Stacked Area Chart），直观展示协同模型如何利用 EV 和储能进行“低储高放”、如何利用柔性负荷“削峰填谷”，以及基准模型中 EV 集中充电导致的“峰上加峰”现象。