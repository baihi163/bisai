"""
问题1 协同调度 — 通用工具：路径解析、数组校验、Gurobi 可用性探测。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np


def project_root_from_here(here: Path) -> Path:
    """由当前模块文件路径推断仓库根目录（src/problem1 的上两级）。"""
    return here.resolve().parents[2]


def resolve_under_root(root: Path, rel: Path) -> Path:
    """将相对 root 的路径解析为绝对路径。"""
    return (root / rel).resolve()


def ensure_dir(path: Path) -> None:
    """若目录不存在则创建。"""
    path.mkdir(parents=True, exist_ok=True)


def as_1d_float_array(x: Any, n: int, name: str) -> np.ndarray:
    """
    将输入转为 shape (n,) 的 float64 数组并校验长度。

    Args:
        x: 可迭代或 ndarray。
        n: 期望长度。
        name: 字段名（用于报错）。

    Returns:
        np.ndarray: 一维 float 数组。
    """
    arr = np.asarray(x, dtype=float).reshape(-1)
    if arr.shape[0] != n:
        raise ValueError(f"{name} 长度 {arr.shape[0]} 与期望 {n} 不一致")
    return arr


def gurobipy_available() -> bool:
    """检测当前环境是否已安装 gurobipy。"""
    return importlib.util.find_spec("gurobipy") is not None


def stack_ev_chi(n_sessions: int, n_periods: int, chi: np.ndarray) -> None:
    """校验 EV 可用性矩阵形状。"""
    if chi.shape != (n_sessions, n_periods):
        raise ValueError(
            f"chi 形状应为 ({n_sessions}, {n_periods})，实际为 {chi.shape}"
        )
