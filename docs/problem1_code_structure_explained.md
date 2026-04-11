# 问题1 协同调度工程：代码结构压缩解释（建模视角）

本文从**比赛建模与公式核查**角度说明 `src/problem1/` 下五个核心文件的职责分工，便于快速对照 `docs/problem1_coordinated_model.md` 中的符号与约束，而非从软件分层或设计模式角度展开。

---

## 1. 建模视角下的五文件分工

在数学规划语境中，一次完整的“建模—求解—出结果”通常包含：**已知参数**、**决策变量**、**约束**、**目标函数**、**求解器调用**、**最优解提取**。当前实现将这些内容映射到文件时，大致对应关系如下。

| 建模环节 | 主要负责文件 | 说明 |
|----------|--------------|------|
| **参数输入（外生数据 + 部分经济/开关参数）** | `config.py` + `data_loader.py` | `config` 提供路径、$\Delta t$、惩罚系数、互斥开关、Gurobi 参数等；`data_loader` 从 CSV/JSON 读入 $P^{\mathrm{pv,avail}}_t$、电价、电网限额、建筑基准负荷、EV 会话、储能参数、柔性边界等，并整理为 `CoordinatedInputData`。 |
| **决策变量定义** | `coordinated_model.py` 中 `build_gurobi_model()` 前半段 | `m.addVar(s)` / `addVars`：$P^{\mathrm{imp}}, P^{\mathrm{exp}}$、储能充放与 $E_{\mathrm{ess}}$、$\Delta P^{\mathrm{flex}}$、弃光与缺电、EV 充放电与 $E_{v,t}$、可选 $u^{\mathrm{ess}}_t,u^{\mathrm{grid}}_t$、柔性绝对值辅助变量等。 |
| **目标函数** | `coordinated_model.py` 中 `build_gurobi_model()` 末尾 | 购电成本、售电收益、弃光/缺电惩罚、柔性代价（$\lvert\Delta P\rvert$ 或 $\Delta P^2$），`m.setObjective(..., GRB.MINIMIZE)`。 |
| **各类约束** | `coordinated_model.py` 中 `build_gurobi_model()` 中段 | 按文档 §7.1–§7.6 分块：`addConstr`；EV 停车矩阵 $\chi_{v,t}$ 由 `data_loader.build_ev_chi_matrix()` **预先算好参数**再传入约束。 |
| **求解** | `coordinated_model.py`（`solve_model` / `apply_gurobi_params`）+ `run_coordinated.py`（调用链） | `model.optimize()`；入口里还负责裁剪时域、打印状态、不可行时 IIS。 |
| **结果输出** | `result_exporter.py` | 从已求解的变量取值构造 DataFrame 并写 CSV，**不包含**新的建模约束。 |

**小结**：真正承载“数学模型长什么样”的代码几乎都在 **`coordinated_model.py`**；`config`/`data_loader` 解决“数字从哪来、符号对应哪些列”，`run_coordinated` 解决“按什么顺序跑通”，`result_exporter` 解决“解向量如何变成表格”。

---

## 2. 数学模型 → 代码位置映射表

下列行号以当前仓库版本为参考，若后续增删代码，以文件中 **§ 文档章节注释** 与 **约束名称 `name=`** 为准。

| 数学对象 / 建模内容 | 代码位置（文件与函数/区域） |
|----------------------|-----------------------------|
| 时段数 $N$、$\Delta t$ | `config.py`：`DELTA_T_HOURS`；`data_loader.load_coordinated_inputs()` 得到 `CoordinatedInputData.n_periods`、`delta_t_hours` |
| 光伏可用上限 $P^{\mathrm{pv,avail}}_t$ | `data_loader.py`：`load_coordinated_inputs()` 读 `pv_profile.csv` → `CoordinatedInputData.pv_available_kw` |
| 购售电价 $\lambda^{\mathrm{buy}}_t,\lambda^{\mathrm{sell}}_t$ | `data_loader.py`：`price_profile.csv` → `price_buy_cny_per_kwh` / `price_sell_cny_per_kwh` |
| 电网进出口上限 | `data_loader.py`：`grid_limits.csv` → `grid_import_limit_kw` / `grid_export_limit_kw` |
| 建筑基准负荷 $P^{\mathrm{base}}_{b,t}$ | `data_loader.py`：`load_profile.csv` 分列 → `load_base_kw` |
| 建筑柔性界与惩罚系数 | `data_loader.py`：`flexible_load_params_clean.csv` → `BuildingFlexParams`；全局弃光/缺电惩罚常数在 `config.py` 并写入数组 |
| 储能参数（功率、效率、能量界、初值） | `data_loader.py`：`ess_params.json` → `EssParameters` |
| EV 会话参数（到离站、能量、功率、V2B） | `data_loader.py`：`ev_sessions_model_ready.csv` → `EvSessionParams` |
| 停车指示 $\chi_{v,t}$ 及 $t^{\mathrm{arr}}_0,\,t^{\mathrm{last}}$ | `data_loader.py`：`build_ev_chi_matrix()` |
| **购电变量 $P^{\mathrm{imp}}_t$** | `coordinated_model.py`：`build_gurobi_model()`，`P_imp = m.addVars(...)`（约第 83 行起） |
| **售电变量 $P^{\mathrm{exp}}_t$ | `coordinated_model.py`：同上，`P_exp` |
| **储能 $P^{\mathrm{ch}}_{\mathrm{ess}},P^{\mathrm{dis}}_{\mathrm{ess}},E_{\mathrm{ess}}$** | `coordinated_model.py`：`P_ch_ess`、`P_dis_ess`、`E_ess` |
| **弃光 $P^{\mathrm{curt}}_t$、缺电 $P^{\mathrm{uns}}_t$** | `coordinated_model.py`：`P_curt`、`P_uns`（缺电是否允许由 `config.ENABLE_UNSERVED_LOAD` 固定上界为 0） |
| **建筑柔性 $\Delta P^{\mathrm{flex}}_{b,t}$** | `coordinated_model.py`：`delta_flex[b,t] = m.addVar(...)` |
| **柔性 $ \lvert\Delta P\rvert $ 辅助变量** | `coordinated_model.py`：`flex_abs[b,t]`（当 `FLEX_COST_MODE == "abs_linear"`） |
| **EV $P^{\mathrm{ev,ch}}_{v,t},P^{\mathrm{ev,dis}}_{v,t},E_{v,t}$** | `coordinated_model.py`：`P_ev_ch`、`P_ev_dis`、`E_ev` |
| **可选互斥 $u^{\mathrm{ess}}_t,u^{\mathrm{grid}}_t$** | `coordinated_model.py`：依 `config.ENABLE_ESS_CHARGE_DISCHARGE_MUTEX` / `ENABLE_GRID_IMPORT_EXPORT_MUTEX` 创建 |
| 光伏弃光上界 $P^{\mathrm{curt}}_t \le P^{\mathrm{pv,avail}}_t$ | `coordinated_model.py`：§7.5 循环，`curtail_ub_*` |
| 储能功率界、SOC 递推、能量界、充放互斥 | `coordinated_model.py`：§7.2，`ess_ch_cap_*`、`ess_dyn_*`、`ess_e_lb/ub`、`ess_*_mutex_*` |
| EV 在站功率界、V2B 放电为 0 | `coordinated_model.py`：§7.3，`ev_ch_ub_*`、`ev_dis_ub_*`、`ev_no_v2b_*` |
| EV 能量递推、到站能量、**离站最低能量** | `coordinated_model.py`：§7.3，`ev_pre_arrival_*` / `ev_first_slot_*`、`ev_dyn_*`、`ev_dep_req_*`（离站约束为 `E_ev[v,t_end] >= E^{\mathrm{req}}`） |
| 建筑柔性盒约束、$\lvert\Delta P\rvert$ 线性化、爬坡、能量中性 | `coordinated_model.py`：§7.1，`flex_abs_*`（GenConstrAbs）、`flex_ramp_*`、`flex_energy_neutral` |
| 电网购售上下界、购售互斥 | `coordinated_model.py`：§7.4，`imp_cap_*`、`exp_cap_*`、`imp_mutex_*`、`exp_mutex_*` |
| **系统有功功率平衡（§7.6）** | `coordinated_model.py`：§7.6，`power_balance_*` |
| **目标函数（§6）** | `coordinated_model.py`：§6，`obj += ...`，`m.setObjective(obj, GRB.MINIMIZE)`（约第 279–306 行） |
| Gurobi 参数、调用 `optimize` | `coordinated_model.py`：`apply_gurobi_params`、`solve_model`；`run_coordinated.py` 主流程调用 |
| 不可行 IIS 诊断 | `coordinated_model.py`：`write_iis()`；`run_coordinated.py` 在无可行解分支调用 |
| 结果 CSV（时序 / EV / 汇总） | `result_exporter.py`：`build_time_series_dataframe`、`build_ev_results_dataframe`、`compute_summary_metrics`、`export_all` |
| 仅调试用：缩短时域与会话数 | `data_loader.py`：`crop_horizon_and_sessions()`；`run_coordinated.py` 命令行 `--max-periods`、`--max-ev-sessions` |

---

## 3. 核查建模是否正确：建议阅读顺序

建议按“**从符号到方程再到实现**”的顺序阅读，与写论文时“集合→参数→变量→约束→目标”一致。

1. **`docs/problem1_coordinated_model.md`**  
   先固定全文符号、功率平衡式、EV 会话与储能写法，作为唯一对照标准。

2. **`config.py`**  
   弄清哪些量被设为**全局常数**（$\Delta t$、弃光/缺电惩罚、柔性模式、互斥开关、是否允许 $P^{\mathrm{uns}}$），这些会改变模型可行域或目标，但不出现在 CSV 里。

3. **`data_loader.py` 中的 dataclass 与 `load_coordinated_inputs()`**  
   核对：附件中的列名如何映射到 $P^{\mathrm{base}}_{b,t}$、$\chi$ 的构造规则（到站含、离站不含）、储能/EV 字段是否与论文一致。  
   若做全时段核查，可暂时忽略 `crop_horizon_and_sessions()`。

4. **`coordinated_model.py` 中的 `build_gurobi_model()`**  
   按文件内 **§7.x 注释块** 顺序核对：  
   先变量块（§5）→ 弃光（§7.5）→ 储能（§7.2）→ EV（§7.3）→ 柔性（§7.1）→ 电网（§7.4）→ **功率平衡（§7.6）** → **目标（§6）**。  
   功率平衡与目标最容易与论文逐行对照，建议重点手算一两个时段的系数符号。

5. **`run_coordinated.py`**  
   只确认调用顺序：读入 → 可选裁剪 → `build_gurobi_model` → `optimize` → 导出 / IIS，避免把流程逻辑误认为约束。

6. **`result_exporter.py`**  
   确认变量名与论文符号的**输出命名**（如 `P_imp_kw`），用于写表与画图；此处若与模型不一致，一般不影响优化，但会影响结果解读。

---

## 4. 是否“过度工程化”与是否压缩文件

### 4.1 是否过度工程化？

对**比赛写作与公式核查**而言，当前结构略偏细：

- **核查建模**时，核心几乎只需 **`coordinated_model.py` + `data_loader.py`（参数含义）**；`config`、`run_coordinated`、`result_exporter` 更多是工程化与可复现运行。
- 将“路径、惩罚、互斥”放在 `config.py` 有利于改参数跑实验，但对**第一次对照论文章节**会多一次跳转。

因此：**不是错误拆分，但对“只查公式”略多文件**；若团队更习惯单脚本，会产生“文件过多”的主观感受。

### 4.2 是否建议压缩为 2～3 个文件？

**建议在比赛冲刺阶段可考虑压缩**，理由：

- 评委或队友核查时，**一页代码内看到变量+约束+目标**更直观；
- 减少 import 与跳转，降低漏读某条约束的概率。

若长期维护或扩展问题2（退化成本等），保留 `config` + `model` + `data` 分离仍有价值。

### 4.3 压缩方案（仅建议，**不修改现有代码**）

| 方案 | 文件划分 | 内容 |
|------|----------|------|
| **三文件（推荐折中）** | `problem1_config_data.py`（或保留 `config.py` + 合并数据） | 合并：`config` 常量 + `data_loader` 全部读入与 `CoordinatedInputData`；第二文件 `problem1_model.py`：仅 `build_gurobi_model` + `solve` + `IIS`；第三文件 `problem1_run_export.py`：`main` + `result_exporter` 全部导出函数。 |
| **两文件（极简）** | `problem1_model.py` | 包含：config 常量、`load_coordinated_inputs`、`build_gurobi_model`、`solve`、`export` 的函数体顺序排列；`run_main()` 在末尾 `if __name__ == "__main__"`。 |
| **两文件（保留数据分离）** | `problem1_data.py` + `problem1_solve.py` | 数据与模型求解分离，仍比当前五文件少。 |

压缩时建议保留 **`build_gurobi_model()` 内 §7.x 注释块**，以便与论文章节一一对应。

---

*说明：本文档仅描述现有代码结构，不包含对实现正确性的证明；具体公式是否与赛题附件完全一致，仍需结合 `problem1_coordinated_model.md` 与数据字段逐项核对。*
