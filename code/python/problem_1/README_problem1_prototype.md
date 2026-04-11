# 问题1 协同调度「简化原型」说明（`p_1_0.py` / `p_1_1.py`）

## 定位（必读）

| 项目 | 说明 |
|------|------|
| **本目录脚本性质** | **简化原型**，不是问题1的**最终主模型**或唯一交付代码。 |
| **求解器** | PuLP + CBC，便于**快速验证数据、轻量求解**，无需 Gurobi 许可证。 |
| **与正式主模型关系** | 问题1 **正式协同调度主模型**以仓库内 **`src/problem1/coordinated_model.py`**（及 `run_coordinated.py`、`docs/problem1_coordinated_model.md`）为准。 |
| **建筑侧** | 使用**总负荷**（或列求和）+ **聚合移峰**与**削减惩罚**，不是主模型中的多栋建筑分项 `ΔP_{b,t}` 与可选爬坡等完整写法。 |

### `p_1_0.py`（无 EV 显式项）

- 功率平衡中**不含** EV 充放电；适合最轻量联通性测试。

### `p_1_1.py`（含 EV 聚合项）

- 从 **`ev_sessions_model_ready.csv`** 读会话，按 **slot** 构造停车时段；含 **V2B 开关**、**净能量下界**（到站至离站净充入 ≥ `E_req - E_arr`）。
- **仍为简化**：**未**实现主模型中 **逐时段车载能量状态 `E_{v,t}`** 的完整递推与离站时刻严格对齐；正式论文与完整复现请以 **`coordinated_model.py`** 为准。
- 详见：`docs/problem1_simplified_vs_full_model.md`

## 适用场景

- 检查 CSV 路径、时间长度、功率平衡是否可解；
- 教学演示、草稿、与 CBC 对接的轻量实验；
- 无 Gurobi 环境下的近似经济性趋势（**不能**替代主模型用于赛题「协同调度」完整论证）。

## 不适用场景

- 作为赛题问题1 **唯一**优化内核撰写论文「完整模型」；
- 与 **非协同 baseline** 做严格公平对照且未核对 EV/建筑假设；
- 需要与 `problem1_coordinated_model.md` **符号一一对应**的可复现结果。

## 相关文档

- 正式数学模型：`docs/problem1_coordinated_model.md`
- 简化版 vs 完整版对照：`docs/problem1_simplified_vs_full_model.md`
- 主模型代码结构说明：`docs/problem1_code_structure_explained.md`

## 运行示例

在仓库根目录：

```bash
python code/python/problem_1/p_1_0.py
python code/python/problem_1/p_1_0.py --max-periods 96

python code/python/problem_1/p_1_1.py
python code/python/problem_1/p_1_1.py --max-periods 96
```

结果默认写入 `results/problem1_pulp/`：`p_1_0_timeseries.csv`、`p_1_1_timeseries.csv`。
