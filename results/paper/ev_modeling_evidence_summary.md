# EV 建模细节证据摘要

> 仅供论文“考虑电动车个体异质性 / 会话细节”类表述的事实支撑；**不含**最终优点评述。  
> 主要依据：`data/raw/ev_sessions.csv`、`data/processed/final_model_inputs/ev_sessions_model_ready.csv`、`data/processed/final_model_inputs/ev_*_matrix*.csv`、`code/python/preprocess_b.py`、`code/python/problem_1/p_1_5_ultimate.py`、`code/python/problem_2/p_2_lifecycle_coordinated.py.code.py`、`code/python/problem_2/p_2_ev_type_policy.py`。

---

## 1. EV 建模对象的粒度

### 1.1 单车 / 单次会话 / 聚合车队？

- **MILP 主模型**：以 **`ev_sessions` 列表中的每一条记录为一个“会话”（`session_id`）** 作为索引对象 `i`，不是“全车队一个状态变量”。  
- **数据表**：`ev_sessions_model_ready.csv` 每行对应 **`session_id` + `ev_index`**（与功率矩阵列 `ev_k` 对齐）；同一物理车辆在多会话场景下会表现为**多行**（本赛题数据中主要为“一车一会话”式编号，但**建模结构是会话级**）。  
- **非 MILP 的聚合曲线**：预处理另外生成 **`ev_aggregate_profile.csv`**（按时间聚合的 `online_count`、`p_ev_ch_max_kw` 之和等），用于基线/分析通路；**与 `p_1_5_ultimate` / `p_2_lifecycle` 中逐会话稀疏变量不是同一套对象**（见 `preprocess_b.py` 中 `_aggregate_ev`）。

### 1.2 决策变量是否在车辆/会话层面定义，再聚合成总功率？

- **是（会话 × 在网时段）**：对每个会话 `i`、其在网时段 `t∈park_ts`，定义 `P_ev_ch[(i,t)]`、`P_ev_dis[(i,t)]`、`E_ev[(i,t)]`（可选 `Y_ev_conn`、`Y_ev_dis` 二进制）。  
- **功率平衡中聚合**：每个时段 `t` 的总充/放为  
  `ev_ch_t = lpSum(P_ev_ch[k] for k in ev_keys_by_t[t])`（`ev_dis_t` 同理），即**变量在会话层，母线功率为求和**（`p_1_5_ultimate.py` 中 `Bal_{t}` 约束）。

### 1.3 代码与数据字段依据（可查）

| 依据类型 | 位置 |
|----------|------|
| 会话列表构建 | `load_problem_data` 中读取 `ev_sessions_indexed.csv` / `ev_sessions_model_ready.csv`，循环 `session_id`、`arrival_slot`、`departure_slot` 等，生成 `ev_sessions` 字典列表（`p_1_5_ultimate.py`）。 |
| 稀疏键与变量 | `ev_keys` / `ev_keys_by_t` / `ev_ts_by_i`；`P_ev_ch`、`P_ev_dis`、`E_ev` 以 `(i,t)` 为键（`p_1_5_ultimate.py`）。 |
| 原始/清洗字段 | `ev_sessions.csv`、`ev_sessions_model_ready.csv` 表头（`session_id`、`battery_capacity_kwh`、`initial_energy_kwh` 等）。 |

---

## 2. 已纳入的车辆异质性因素（显式 / 不显式）

下列按“是否在优化模型中**显式**出现（数据字段或约束）”勾选。

| 因素 | 是否显式纳入 | 说明（事实） |
|------|--------------|--------------|
| **到站时间差异** | 是 | CSV 有 `arrival_time` / `arrival_slot`；入模时用 `arrival_slot`…`departure_slot` 生成 `park_from_csv`，再与可用性矩阵求交得 `park_ts`（`p_1_5_ultimate.py`）。 |
| **离站时间差异** | 是 | `departure_time` / `departure_slot`；同上决定 `park_ts` 长度与末时段。 |
| **初始 SOC 差异** | 是（kWh） | 字段 `initial_energy_kwh`；每个会话在 `park_ts` 首段的能量递推以该值为初值（约束 `E_ev[...] == initial_energy_kwh + ...`）。**非无量纲 SOC 分数**，而是能量 kWh。 |
| **离站目标电量 / SOC 差异** | 是（kWh） | 字段 `required_energy_at_departure_kwh`，入模映射为 `required_energy_kwh`（含截断 horizon 时的比例修正 `ereq_model`）；末在网时段约束 `E_ev[(i, ts[-1])] >= required_energy_kwh`。 |
| **是否允许 V2G（数据名 v2b）差异** | 是 | 字段 `v2b_allowed`；`v2b_allowed==0` 时预处理将 `max_discharge_power_kw` 置 0，且在矩阵加载后将对应列 `dis_mat[:, j] = 0`；模型中放电上界与 `Y_ev_dis` 逻辑依赖 `v2b_allowed`（`preprocess_b.py`、`p_1_5_ultimate.py`）。 |
| **充放电功率上限差异** | 是（且**时变**） | 会话级向量 `charge_limits_kw[t]`、`discharge_limits_kw[t]` 来自 `ev_charge_power_limit_matrix_kw.csv`、`ev_discharge_power_limit_matrix_kw.csv` 与可用性矩阵逐元乘积后的列（`p_1_5_ultimate.py`）；约束 `P_ev_ch[(i,t)] <= ...`、`P_ev_dis[(i,t)] <= ...`。 |
| **电池容量差异** | 是 | 字段 `battery_capacity_kwh`；约束 `E_ev <= battery_capacity_kwh`。 |
| **会话持续时间差异** | 是 | 由 `park_ts` 长度（及 CSV `dwell_slots`）体现；在网时段数随会话变化；若矩阵与 CSV 停车窗交集为空则该会话被剔除（`ev_skipped` 原因可查）。 |
| **充电效率 / 放电效率** | 部分 | 模型支持每会话 `eta_ch`、`eta_dis`（`row.get("charge_efficiency", 0.95)` 等）；**当前 `ev_sessions_model_ready.csv` 表头未含该列时，代码走默认值 0.95**（事实：以表结构为准）。 |
| **车型标签 `ev_type`** | 数据有；核心 MILP 目标默认用 **会话级 `deg_cost`** | `ev_sessions_model_ready.csv` 含 `ev_type`；`p_1_5_ultimate` 构建 `ev_sessions` 时**未把 `ev_type` 写入该字典**；问题二求解前 `enrich_ev_sessions_with_ev_type` 从同路径 CSV 合并 `ev_type` 供后处理/策略脚本使用（`p_2_lifecycle_coordinated.py.code.py`）。可选规则 `apply_deg_cost_from_type_summary` 才把车类均值映射到 `deg_cost`（`p_2_ev_type_policy.py`）。 |
| **物理车牌 / 车主身份** | 无独立字段 | 仅有 `session_id` 作为会话标识；**不能**从当前表直接读出“同一车牌跨周重复”。 |

---

## 3. 相关数据字段或约束证据

### 3.1 数据表（列名级）

**原始**：`data/raw/ev_sessions.csv`  
`session_id, ev_type, arrival_time, departure_time, battery_capacity_kwh, initial_energy_kwh, required_energy_at_departure_kwh, max_charge_power_kw, max_discharge_power_kw, v2b_allowed, degradation_cost_cny_per_kwh_throughput`

**入模前处理**：`data/processed/final_model_inputs/ev_sessions_model_ready.csv`  
在以上基础上增加（节选）：`ev_index, arrival_slot, departure_slot, dwell_slots, feasibility_flag, issue_note` 等（见文件首行表头）。

**时变边界矩阵**（按时段 × 会话列）：  
- `data/processed/final_model_inputs/ev_availability_matrix.csv`  
- `data/processed/final_model_inputs/ev_charge_power_limit_matrix_kw.csv`  
- `data/processed/final_model_inputs/ev_discharge_power_limit_matrix_kw.csv`

### 3.2 预处理中的硬规则（可核对日志）

- 到站/离站对齐 15 min：`arrival_slot = ceil(15min)`，`departure_slot = floor(15min)`（`preprocess_b.py` `_clean_ev_sessions`）。  
- `v2b_allowed == 0` → `max_discharge_power_kw = 0`（同上）。  
- 能量边界裁剪：`initial_energy_kwh`、`required_energy_at_departure_kwh` 与 `battery_capacity_kwh` 协调（同上）。

### 3.3 优化模型中的关键约束 / 命名（PuLP）

| 名称或模式 | 含义（事实） |
|------------|--------------|
| `P_ev_ch[(i,t)]`, `P_ev_dis[(i,t)]`, `E_ev[(i,t)]` | 会话 `i`、时段 `t` 的充放功率与站内能量。 |
| `E_ev` 递推 | 仅在 `park_ts` 连续段上递推；非连续会 `raise ValueError`（代码显式检查）。 |
| `E_ev[(i, ts[-1])] >= required_energy_kwh` | 离站能量下界（末在网时段）。 |
| `0 <= E_ev <= battery_capacity_kwh` | 容量上界。 |
| `Bal_{t}` | 母线平衡中含 `ev_ch_t`、`ev_dis_t` 为各会话求和。 |
| `Y_ev_conn` / `Y_ev_dis`（当 `enforce_ev_limit`） | 会话级在网/放电二进制；并加 **`sum_t Y_ev_conn <= max_simultaneous_ev_connections`**（及双向桩数上界）类**车队层面**并发约束（`p_1_5_ultimate.py`）。 |

---

## 4. 相比“完全聚合单电池模型”的客观对照

### 4.1 当前模型保留的个体（会话）层信息

- **每个会话独立的**：在网时段集合 `park_ts`、初末能量边界、容量、（时变）充/放功率上界、是否允许放电、`deg_cost`、充放效率（若 CSV 提供则非默认）。  
- **每个会话独立的 SOC 轨迹变量** `E_ev[(i,t)]`，而非全车队共享一个 SOC。  
- **可选**：充电桩并发、双向桩数对 **各会话二进制 `Y_ev_*`** 的耦合（仍为“会话 × 时段”粒度上的资源竞争，而非单池聚合）。

### 4.2 仍被聚合或简化的部分

- **母线层功率**：各会话充放功率在 `Bal_{t}` 中**加总**，不建模配电网潮流或单车到变压器支路。  
- **聚合时序产物**：`ev_aggregate_profile.csv` 将在线车辆数、功率上界等**按时间相加**，用于与 MILP 不同的基线通道。  
- **车型**：`ev_type` 存在于数据；**默认 MILP 目标项使用会话级 `deg_cost`**，车型仅通过问题二可选脚本改 `deg_cost` 或放电策略时进入模型。  
- **同一物理车多会话耦合**：当前数据结构未强制链接“车牌级”跨会话 SOC；**异质性主要体现在会话级参数**，而非车辆终身档案。

### 4.3 表述建议（仅事实判断，不作价值评价）

- **可辩护为**：模型在 **会话级（session-level）** 保留了时间窗、能量、功率边界与 V2B 许可等差异，并用 **稀疏 (i,t) 变量** 实现。  
- **不宜无条件允许说成**：已建模“任意两辆物理车在全生命周期内的个体轨迹耦合”，除非数据显式提供跨会话车辆 ID 并在模型中链接。  
- **与“完全聚合单电池”的差异**：后者通常仅 **一组** `(P_ch, P_dis, E)` 描述全车队；本仓库 MILP 为 **每会话多条能量轨迹与多条功率轨**，再在母线求和。

---

## 5. 可直接用于论文优点评价的事实 bullet（仅事实，无结论句）

- 优化变量 **`P_ev_ch`、`P_ev_dis`、`E_ev` 按 `(会话索引 i, 时段 t)` 稀疏定义**，仅在各会话 `park_ts` 上存在（`p_1_5_ultimate.py`）。  
- 输入数据 **`session_id` 逐行区分会话**，并带 **`arrival_slot` / `departure_slot` / `dwell_slots`** 等离散时间信息（`ev_sessions_model_ready.csv`）。  
- **每会话独立**的 `battery_capacity_kwh`、`initial_energy_kwh`、`required_energy_at_departure_kwh`（入模为 `required_energy_kwh`）进入边界与终端约束。  
- **每会话独立**的 `v2b_allowed` 与放电功率列：不允许 V2B 时会话放电上界为 0（预处理 + 模型双重约束路径）。  
- **时变**的 `charge_limits_kw[t]`、`discharge_limits_kw[t]` 来自 **矩阵 CSV × 可用性矩阵** 的会话列，约束逐时段功率（非全周常数上界一条）。  
- **退化成本默认按会话** `degradation_cost_cny_per_kwh_throughput` → 模型字典键 `deg_cost` 进入目标 `deg_cost * (P_ev_ch + P_ev_dis) * dt / 2`（每 `(i,t)`）。  
- **功率平衡**使用 **全会话在该时段的充放功率之和** `ev_ch_t`、`ev_dis_t` 与光伏、储能、购电等联立（`Bal_{t}`）。  
- **可选并发约束**：`sum Y_ev_conn` 与双向桩数上界限制**同一时段最多多少会话可同时占用接口/可放电**，相对“无个体计数、仅总功率上界”的聚合模型多了一层 **0-1 资源竞争**结构（当 `enforce_ev_limit` 启用且资产参数有效时）。  
- **问题二路径**下可从 `ev_sessions_model_ready.csv` **合并 `ev_type`**，并可通过 `problem2_ev_type_summary.csv` **改写或缩放**各会话 `deg_cost`（`p_2_ev_type_policy.py`），属于在会话粒度上叠加**类型维度**的扩展能力。

---

*若正文需引用“会话数”，请以当前 `ev_sessions_model_ready.csv` 可行行为准（剔除 `p_1_5_ultimate` 中 `ev_skipped` 后 `len(ev_sessions)` 与矩阵列数一致）。*
