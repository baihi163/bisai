## 四、固定储能与电动车在削峰、储能和供能中的分工比例

为回答题目中“优化固定储能设备与电动车在削峰、储能和供能中的分工比例”的要求，本文进一步对两类资源的角色分工进行量化分析。考虑到仓库中未直接提供现成的“分工比例”指标，本文基于全周时序结果和运行指标进行后处理定义。

### 1. 储能分工比例

“储能分工”反映两类资源承担系统能量缓冲任务的相对份额。本文采用全周吞吐量占比进行定义：

$$
R_{\mathrm{ESS,store}}
=
\frac{E_{\mathrm{ESS,through}}}
{E_{\mathrm{ESS,through}} + E_{\mathrm{EV,through}}}
$$

$$
R_{\mathrm{EV,store}}
=
\frac{E_{\mathrm{EV,through}}}
{E_{\mathrm{ESS,through}} + E_{\mathrm{EV,through}}}
$$

在主场景 $$w = 1$$ 下，固定储能吞吐量为 $$6716.19\ \mathrm{kWh}$$，电动车吞吐量为 $$1441.38\ \mathrm{kWh}$$，因此固定储能储能分工占比约为 $$82.3\%$$，电动车约为 $$17.7\%$$。这说明系统主要依赖固定储能承担能量吸纳与转移任务。

### 2. 供能分工比例

“供能分工”反映两类资源对负荷侧放电支撑的相对贡献。本文采用全周放电能量占比定义：

$$
R_{\mathrm{ESS,supply}}
=
\frac{E_{\mathrm{ESS,dis}}}
{E_{\mathrm{ESS,dis}} + E_{\mathrm{EV,dis}}}
$$

$$
R_{\mathrm{EV,supply}}
=
\frac{E_{\mathrm{EV,dis}}}
{E_{\mathrm{ESS,dis}} + E_{\mathrm{EV,dis}}}
$$

在主场景 $$w = 1$$ 下，固定储能全周放电量为 $$6372.0\ \mathrm{kWh}$$，电动车全周放电量为 $$397.235\ \mathrm{kWh}$$，由此得到固定储能供能占比约为 $$94.1\%$$，电动车供能占比约为 $$5.9\%$$。可见在系统供能职责上，固定储能远高于电动车，是削峰补能的核心执行者。

### 3. 削峰分工比例

“削峰分工”主要体现两类资源在高价高负荷时段替代外网购电、缓解电网压力的能力。本文将购电价处于全周前 $$20\%$$ 分位以上的时段定义为峰时段，共得到 $$144$$ 个峰时段；并以峰时段内的净放电能量作为削峰贡献度量。

固定储能与电动车的峰段净放电能量分别定义为：

$$
E_{\mathrm{ESS,peak}}
=
\sum_{t \in \mathcal{T}_{\mathrm{peak}}}
\left(P_t^{\mathrm{ESS,dis}} - P_t^{\mathrm{ESS,ch}}\right)\Delta t
$$

$$
E_{\mathrm{EV,peak}}
=
\sum_{t \in \mathcal{T}_{\mathrm{peak}}}
\left(P_t^{\mathrm{EV,dis}} - P_t^{\mathrm{EV,ch}}\right)\Delta t
$$

据此，可定义削峰分工比例为：

$$
R_{\mathrm{ESS,peak}}
=
\frac{E_{\mathrm{ESS,peak}}}
{E_{\mathrm{ESS,peak}} + E_{\mathrm{EV,peak}}}
$$

$$
R_{\mathrm{EV,peak}}
=
\frac{E_{\mathrm{EV,peak}}}
{E_{\mathrm{ESS,peak}} + E_{\mathrm{EV,peak}}}
$$

在问题一主场景下，固定储能峰段净放电能量为 $$6360.0\ \mathrm{kWh}$$，电动车峰段净放电能量为 $$381.301\ \mathrm{kWh}$$；在寿命权重强化至 $$w = 2$$ 时，固定储能峰段净放电能量保持在 $$6360.0\ \mathrm{kWh}$$，而电动车峰段净放电能量下降至 $$376.482\ \mathrm{kWh}$$。这说明随着寿命惩罚增强，电动车在高峰削峰任务中的参与程度进一步下降，而固定储能继续承担绝大多数峰段支撑任务。

因此，从削峰、储能和供能三个维度来看，第二题优化后系统形成了较清晰的分工结构：**固定储能负责主力削峰和主力供能，电动车承担补充型储能与辅助型供能角色**。随着寿命权重提高，这种分工进一步强化。
