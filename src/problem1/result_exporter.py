"""
问题1 协同调度 — 求解结果导出为 CSV（time_series / EV / summary）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .coordinated_model import CoordinatedModelArtifacts
from .data_loader import CoordinatedInputData


def _arr1(gp_vars: Any, n: int) -> np.ndarray:
    """从 Gurobi Var 对象列表或 tupledict 取长度 n 的一维值。"""
    out = np.zeros(n, dtype=float)
    for t in range(n):
        out[t] = float(gp_vars[t].X)
    return out


def _arr2(gp_vars: Any, v: int, n: int) -> np.ndarray:
    out = np.zeros((v, n), dtype=float)
    for i in range(v):
        for t in range(n):
            out[i, t] = float(gp_vars[i, t].X)
    return out


def build_time_series_dataframe(
    data: CoordinatedInputData, art: CoordinatedModelArtifacts
) -> pd.DataFrame:
    """
    构造逐时段主结果表。

    Args:
        data: 输入数据。
        art: 模型工件（已最优求解）。

    Returns:
        pandas.DataFrame
    """
    n = art.n_periods
    B = art.n_buildings
    rows: dict[str, Any] = {}
    if data.timestamps is not None:
        rows["timestamp"] = data.timestamps
    rows["slot_id"] = data.slot_ids
    rows["P_imp_kw"] = _arr1(art.P_imp, n)
    rows["P_exp_kw"] = _arr1(art.P_exp, n)
    rows["P_ch_ess_kw"] = _arr1(art.P_ch_ess, n)
    rows["P_dis_ess_kw"] = _arr1(art.P_dis_ess, n)
    rows["E_ess_kwh"] = _arr1(art.E_ess, n)
    rows["P_curt_kw"] = _arr1(art.P_curt, n)
    rows["P_uns_kw"] = _arr1(art.P_uns, n)
    rows["pv_available_kw"] = data.pv_available_kw
    rows["pv_used_kw"] = data.pv_available_kw - rows["P_curt_kw"]

    for b in range(B):
        key = data.building_ids[b]
        rows[f"delta_flex_{key}_kw"] = np.array(
            [float(art.delta_flex[b, t].X) for t in range(n)], dtype=float
        )
        rows[f"P_load_{key}_kw"] = data.load_base_kw[b, :] + rows[f"delta_flex_{key}_kw"]

    return pd.DataFrame(rows)


def build_ev_results_dataframe(
    data: CoordinatedInputData, art: CoordinatedModelArtifacts
) -> pd.DataFrame:
    """构造 EV 逐会话逐时段结果。"""
    n = art.n_periods
    V = art.n_ev
    pch = _arr2(art.P_ev_ch, V, n)
    pdis = _arr2(art.P_ev_dis, V, n)
    eev = _arr2(art.E_ev, V, n)

    recs: list[dict[str, Any]] = []
    for v in range(V):
        s = data.ev_sessions[v]
        for t in range(n):
            recs.append(
                {
                    "session_id": s.session_id,
                    "ev_index": v,
                    "slot_id": int(data.slot_ids[t]),
                    "chi": float(art.chi[v, t]),
                    "P_ev_ch_kw": pch[v, t],
                    "P_ev_dis_kw": pdis[v, t],
                    "E_ev_kwh": eev[v, t],
                    "E_required_kwh": s.E_required_departure_kwh,
                    "v2b_allowed": int(s.v2b_allowed),
                }
            )
    return pd.DataFrame.from_records(recs)


def compute_summary_metrics(
    data: CoordinatedInputData,
    art: CoordinatedModelArtifacts,
    objective_value: float,
) -> pd.DataFrame:
    """
    计算汇总指标：总购售电量、弃光、缺电、峰值购电、目标值等。

    Args:
        data: 输入。
        art: 工件。
        objective_value: 模型.ObjVal。

    Returns:
        单行 DataFrame。
    """
    n = art.n_periods
    dt = art.delta_t
    P_imp = _arr1(art.P_imp, n)
    P_exp = _arr1(art.P_exp, n)
    P_curt = _arr1(art.P_curt, n)
    P_uns = _arr1(art.P_uns, n)

    energy_import_mwh = float(np.sum(P_imp) * dt / 1000.0)
    energy_export_mwh = float(np.sum(P_exp) * dt / 1000.0)
    energy_curt_mwh = float(np.sum(P_curt) * dt / 1000.0)
    energy_uns_mwh = float(np.sum(P_uns) * dt / 1000.0)

    row = {
        "objective_cny": float(objective_value),
        "total_import_energy_mwh": energy_import_mwh,
        "total_export_energy_mwh": energy_export_mwh,
        "total_curtailment_energy_mwh": energy_curt_mwh,
        "total_unserved_energy_mwh": energy_uns_mwh,
        "peak_import_kw": float(np.max(P_imp)),
        "peak_export_kw": float(np.max(P_exp)),
        "n_periods": n,
        "delta_t_hours": dt,
    }
    return pd.DataFrame([row])


def export_all(
    out_dir: Path,
    data: CoordinatedInputData,
    art: CoordinatedModelArtifacts,
    objective_value: float,
) -> dict[str, Path]:
    """
    写出三个 CSV 文件。

    Returns:
        文件名到绝对路径的映射。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    ts = build_time_series_dataframe(data, art)
    p1 = out_dir / "time_series_results.csv"
    ts.to_csv(p1, index=False, encoding="utf-8-sig")
    paths["time_series_results.csv"] = p1.resolve()

    ev = build_ev_results_dataframe(data, art)
    p2 = out_dir / "ev_results.csv"
    ev.to_csv(p2, index=False, encoding="utf-8-sig")
    paths["ev_results.csv"] = p2.resolve()

    sm = compute_summary_metrics(data, art, objective_value)
    p3 = out_dir / "summary_metrics.csv"
    sm.to_csv(p3, index=False, encoding="utf-8-sig")
    paths["summary_metrics.csv"] = p3.resolve()

    return paths
