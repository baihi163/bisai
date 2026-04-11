# -*- coding: utf-8 -*-
"""
问题2：按车型汇总表（problem2_ev_type_summary.csv）调整会话级退化成本，
以及「仅部分车型允许放电（V2B）」类实验策略。

不改变 load_problem_data 本体；由调用方在 fork 后的 ev_sessions 上应用。

说明：主模型中 EV/ESS 退化仍为**线性吞吐单价**；本模块只改单价取值或放电可行域，
不引入非线性老化曲线。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SUMMARY_TYPE_COL = "ev_type"
SUMMARY_DEG_COL = "mean_degradation_cost_cny_per_kwh_throughput"


def normalize_ev_type_key(t: object) -> str:
    """与异质性汇总表 ev_type 列对齐：suv -> SUV，其余小写。"""
    s = str(t).strip()
    if not s or s.lower() == "nan":
        return "unknown"
    if s.lower() == "suv":
        return "SUV"
    return s.lower()


def fork_data_for_ev_policies(data: dict[str, Any]) -> dict[str, Any]:
    """浅拷贝 data，深拷贝各 ev 会话中的功率向量，避免多次扫描互相污染。"""
    out = dict(data)
    new_ev: list[dict[str, Any]] = []
    for ev in data["ev_sessions"]:
        e = dict(ev)
        e["charge_limits_kw"] = np.asarray(ev["charge_limits_kw"], dtype=float).copy()
        e["discharge_limits_kw"] = np.asarray(ev["discharge_limits_kw"], dtype=float).copy()
        new_ev.append(e)
    out["ev_sessions"] = new_ev
    return out


def load_type_summary_deg_map(csv_path: Path) -> dict[str, float]:
    """读取 problem2_ev_type_summary.csv，返回 ev_type -> 表内平均吞吐退化成本。"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if SUMMARY_TYPE_COL not in df.columns or SUMMARY_DEG_COL not in df.columns:
        raise KeyError(f"汇总表需含列 {SUMMARY_TYPE_COL!r} 与 {SUMMARY_DEG_COL!r}，实际: {list(df.columns)}")
    m: dict[str, float] = {}
    for _, row in df.iterrows():
        k = normalize_ev_type_key(row[SUMMARY_TYPE_COL])
        m[k] = float(row[SUMMARY_DEG_COL])
    return m


def apply_deg_cost_from_type_summary(
    ev_sessions: list[dict[str, Any]],
    deg_by_type: dict[str, float],
    *,
    rule: str,
) -> None:
    """
    rule:
      - override_mean: 每车 deg_cost 替换为汇总表中该车型均值（无匹配类型则保持原值）
      - scale_to_type_mean: 按车型把当前样本内 deg_cost 均值对齐到表均值（保留车内相对差异）
    """
    if rule == "override_mean":
        for ev in ev_sessions:
            k = normalize_ev_type_key(ev.get("ev_type", "unknown"))
            if k in deg_by_type:
                ev["deg_cost"] = float(deg_by_type[k])
        return

    if rule == "scale_to_type_mean":
        by_t: dict[str, list[float]] = {}
        for ev in ev_sessions:
            k = normalize_ev_type_key(ev.get("ev_type", "unknown"))
            by_t.setdefault(k, []).append(float(ev["deg_cost"]))
        mean_data: dict[str, float] = {}
        for k, vals in by_t.items():
            mean_data[k] = float(np.mean(vals)) if vals else 0.0
        for ev in ev_sessions:
            k = normalize_ev_type_key(ev.get("ev_type", "unknown"))
            target = deg_by_type.get(k)
            m0 = mean_data.get(k, 0.0)
            if target is None or m0 < 1e-12:
                continue
            ev["deg_cost"] = float(ev["deg_cost"]) * (float(target) / m0)
        return

    raise ValueError(f"未知 rule: {rule!r}")


def restrict_v2b_discharge_to_types(ev_sessions: list[dict[str, Any]], allowed_types: set[str]) -> None:
    """
    仅 allowed_types 中的车型保留放电能力与 v2b_allowed；其余车型放电上限置 0 且 v2b_allowed=0。
    allowed_types 内元素可为 'SUV'、'compact' 等，大小写不敏感。
    """
    allowed_norm = {normalize_ev_type_key(x) for x in allowed_types}
    for ev in ev_sessions:
        kt = normalize_ev_type_key(ev.get("ev_type", "unknown"))
        if kt not in allowed_norm:
            ev["discharge_limits_kw"] = np.zeros_like(ev["discharge_limits_kw"], dtype=float)
            ev["v2b_allowed"] = 0
