# 项目 Python 目录整理说明

整理日期：以仓库内本次变更为准。

## 1. 移动的 Python 文件（baseline）

| 原路径 | 新路径 | 处理方式 |
|--------|--------|----------|
| `scripts/run_baseline_noncooperative.py` | `code/python/baseline/run_baseline_noncooperative.py` | **已迁移**；原 `scripts/` 下文件**已删除**，请勿再从旧路径运行。 |

## 2. 非重复占位文件

| 路径 | 说明 |
|------|------|
| `code/python/baseline.py` | 仅占位与索引说明（一行注释指向 `baseline/run_baseline_noncooperative.py`），**不是**可执行 baseline 实现，与 `baseline/` 子目录**不重复**。 |

## 3. baseline 唯一运行入口

```text
code/python/baseline/run_baseline_noncooperative.py
```

在仓库根目录执行示例：

```bash
python code/python/baseline/run_baseline_noncooperative.py
```

## 4. 输出目录

```text
results/problem1_baseline/
```

## 5. 输入数据目录（优先）

```text
data/processed/final_model_inputs/
```

若该目录不存在，脚本会回退尝试 `data/processed/`（与实现内 `_resolve_input_dir` 一致）。

## 6. 当前项目 Python 目录规范

- **所有 Python 源码**应放在 `code/python/` 及其子目录下。
- **禁止**在仓库根目录新增 `.py` 文件。
- **禁止**在 `scripts/` 或其他非 `code/python/` 路径新增 Python 源码（历史遗留见下节）。
- 新增文件前应先确定路径（例如 `code/python/<模块>/xxx.py`），再创建。

## 7. 历史遗留（尚未迁移，与本次 baseline 无关）

以下文件仍在 `scripts/` 下，**不属于**本次 baseline 整理范围；后续若统一迁往 `code/python/`，应单独开任务并更新引用。

- `scripts/visualize_special_events.py`
- `scripts/optimization/problem1_deterministic_dispatch.py`

## 8. 后续新增代码约定

1. 仅可在 `code/python/` 及其子目录下创建 `.py` 文件。  
2. 创建前先说明（或文档中写明）目标路径。  
3. 不得在根目录或 `scripts/` 下新增 `.py` 文件。
