"""
问题1 协同调度 — 数据读取与预处理。

将建筑负荷、光伏、电价、电网限额、EV 会话、储能参数、建筑柔性参数整理为统一数据结构，
供 coordinated_model 直接使用。列名与仓库内 `data/processed/final_model_inputs/` 对齐；
若竞赛附件字段不同，请在 `load_coordinated_inputs()` 中替换映射（已用 TODO 标出）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import config
from .utils import project_root_from_here, resolve_under_root, as_1d_float_array


@dataclass
class EssParameters:
    """固定储能参数（对应文档 7.2）。"""

    energy_capacity_kwh: float
    initial_energy_kwh: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float
    min_energy_kwh: float
    max_energy_kwh: float


@dataclass
class EvSessionParams:
    """单车/单会话 EV 参数（会话级建模，对应文档 7.3）。"""

    session_index: int
    session_id: str
    arrival_slot_1based: int  # 到站时段 slot_id（含）
    departure_slot_1based: int  # 离站时段 slot_id（不含，与 dwell 计算一致）
    E_arrival_kwh: float
    E_required_departure_kwh: float
    E_max_kwh: float  # 电池容量上界
    P_charge_max_kw: float
    P_discharge_max_kw: float  # 非 V2B 时应为 0
    v2b_allowed: bool
    eta_charge: float = 0.95
    eta_discharge: float = 0.95
    # TODO 问题2：单位能量吞吐退化成本（元/kWh），当前仅存储
    degradation_cost_cny_per_kwh_throughput: float = 0.0


@dataclass
class BuildingFlexParams:
    """单栋建筑柔性边界与代价系数。"""

    building_key: str
    flex_lower_kw: float  # ΔP 下界（通常为负）
    flex_upper_kw: float
    penalty_cny_per_kw: float  # 单位 |ΔP| 或 ΔP² 的系数，见模型中解释


@dataclass
class CoordinatedInputData:
    """协同调度模型输入（确定性多时段）。"""

    n_periods: int
    delta_t_hours: float
    timestamps: list[str] | None
    slot_ids: np.ndarray  # shape (N,), 通常 1..N

    pv_available_kw: np.ndarray
    grid_import_limit_kw: np.ndarray
    grid_export_limit_kw: np.ndarray
    price_buy_cny_per_kwh: np.ndarray
    price_sell_cny_per_kwh: np.ndarray

    building_ids: list[str]
    load_base_kw: np.ndarray  # shape (n_b, N)

    buildings_flex: list[BuildingFlexParams]

    ess: EssParameters
    ev_sessions: list[EvSessionParams]

    curtailment_penalty_cny_per_kwh: np.ndarray
    unserved_penalty_cny_per_kwh: np.ndarray

    meta: dict[str, Any] = field(default_factory=dict)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"缺少数据文件: {path}")
    return pd.read_csv(path)


def build_ev_chi_matrix(
    n_periods: int, sessions: list[EvSessionParams]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    构造 χ_{v,t}：在站停车且允许充放电的时段为 1。

    约定：slot_id 与 CSV 一致为 1..N；停车时段为 arrival <= slot < departure。
    对应 period 索引 t = slot_id - 1。
    """
    n_v = len(sessions)
    chi = np.zeros((n_v, n_periods), dtype=float)
    t_first = np.zeros(n_v, dtype=int)
    t_last_park = np.zeros(n_v, dtype=int)  # 最后一个在站时段的 period 索引

    for v, s in enumerate(sessions):
        arr = s.arrival_slot_1based
        dep = s.departure_slot_1based
        if not (1 <= arr <= n_periods and 1 <= dep <= n_periods + 1):
            raise ValueError(
                f"会话 {s.session_id} 到离站索引越界: arr={arr}, dep={dep}, N={n_periods}"
            )
        if dep <= arr:
            raise ValueError(f"会话 {s.session_id} departure_slot 必须大于 arrival_slot")
        for slot in range(arr, dep):
            t = slot - 1
            chi[v, t] = 1.0
        t_first[v] = arr - 1
        t_last_park[v] = dep - 2  # 最后一个在站 slot 对应 period 索引

    return chi, t_first, t_last_park


def load_coordinated_inputs(
    project_root: Path | None = None,
    paths: dict[str, Path] | None = None,
) -> CoordinatedInputData:
    """
    从默认或自定义路径加载协同调度所需全部输入。

    Args:
        project_root: 仓库根目录；默认由本包推断。
        paths: 覆盖 config.DEFAULT_PATHS 中的条目（值为相对 project_root 的路径）。

    Returns:
        CoordinatedInputData: 校验后的统一数据结构。
    """
    root = project_root or project_root_from_here(Path(__file__))
    p = dict(config.DEFAULT_PATHS)
    if paths:
        p.update(paths)

    load_csv = resolve_under_root(root, p["load_profile_csv"])
    pv_csv = resolve_under_root(root, p["pv_profile_csv"])
    price_csv = resolve_under_root(root, p["price_profile_csv"])
    grid_csv = resolve_under_root(root, p["grid_limits_csv"])
    ess_json = resolve_under_root(root, p["ess_params_json"])
    ev_csv = resolve_under_root(root, p["ev_sessions_csv"])
    flex_csv = resolve_under_root(root, p["flexible_load_params_csv"])

    df_load = _read_csv(load_csv)
    df_pv = _read_csv(pv_csv)
    df_price = _read_csv(price_csv)
    df_grid = _read_csv(grid_csv)
    df_ev = _read_csv(ev_csv)
    df_flex = _read_csv(flex_csv)

    # TODO: 附件若使用不同列名，仅改下列字段名即可。
    n = len(df_load)
    if len(df_pv) != n or len(df_price) != n or len(df_grid) != n:
        raise ValueError("时序文件行数不一致，请检查 load/pv/price/grid 对齐情况")

    slot_ids = df_load["slot_id"].to_numpy() if "slot_id" in df_load.columns else np.arange(1, n + 1)
    ts_col = "timestamp" if "timestamp" in df_load.columns else None
    timestamps = df_load[ts_col].astype(str).tolist() if ts_col else None

    pv_available_kw = df_pv["pv_available_kw"].to_numpy(dtype=float)

    price_buy = df_price["grid_buy_price_cny_per_kwh"].to_numpy(dtype=float)
    price_sell = df_price["grid_sell_price_cny_per_kwh"].to_numpy(dtype=float)

    grid_import_limit_kw = df_grid["grid_import_limit_kw"].to_numpy(dtype=float)
    grid_export_limit_kw = df_grid["grid_export_limit_kw"].to_numpy(dtype=float)

    # 建筑原生负荷：聚合为多栋；保留 total 用于校验
    building_cols = [
        c
        for c in ("office_building_kw", "wet_lab_kw", "teaching_center_kw")
        if c in df_load.columns
    ]
    if not building_cols:
        # TODO: 若仅有总负荷列，可改为单列 'total_native_load_kw'
        if "total_native_load_kw" in df_load.columns:
            building_ids = ["campus_total"]
            load_base_kw = df_load[["total_native_load_kw"]].to_numpy(dtype=float).T
        else:
            raise ValueError("load_profile 中未找到建筑分项或 total_native_load_kw")
    else:
        building_ids = [c.replace("_kw", "") for c in building_cols]
        load_base_kw = df_load[building_cols].to_numpy(dtype=float).T

    # 柔性参数：与 load_block 名称对齐（CSV: office_building / wet_lab / teaching_center）
    flex_by_block: dict[str, pd.Series] = {
        str(r["load_block"]): r for _, r in df_flex.iterrows()
    }
    buildings_flex_ordered: list[BuildingFlexParams] = []
    for bid in building_ids:
        row = flex_by_block.get(bid)
        if row is None:
            raise ValueError(
                f"flexible_load_params 中缺少 load_block={bid}，"
                f"请对齐 load_profile 建筑列与柔性表。TODO: 附件字段映射。"
            )
        ms = float(row["max_shiftable_kw"])
        pen = float(row.get("penalty_cny_per_kwh_shift", np.nan))
        if np.isnan(pen):
            pen = 0.8  # TODO: 按赛题经济参数替换（元/kW 量级，与目标函数中 |ΔP| 一致）
        buildings_flex_ordered.append(
            BuildingFlexParams(
                building_key=bid,
                flex_lower_kw=-ms,
                flex_upper_kw=ms,
                penalty_cny_per_kw=pen,
            )
        )

    with open(ess_json, "r", encoding="utf-8") as f:
        ej = json.load(f)
    ess = EssParameters(
        energy_capacity_kwh=float(ej["energy_capacity_kwh"]),
        initial_energy_kwh=float(ej["initial_energy_kwh"]),
        max_charge_power_kw=float(ej["max_charge_power_kw"]),
        max_discharge_power_kw=float(ej["max_discharge_power_kw"]),
        charge_efficiency=float(ej["charge_efficiency"]),
        discharge_efficiency=float(ej["discharge_efficiency"]),
        min_energy_kwh=float(ej["min_energy_kwh"]),
        max_energy_kwh=float(ej["max_energy_kwh"]),
    )

    ev_sessions: list[EvSessionParams] = []
    for k, (_, row) in enumerate(df_ev.iterrows()):
        v2b = bool(int(row["v2b_allowed"])) if not isinstance(row["v2b_allowed"], bool) else row["v2b_allowed"]
        p_dis = float(row["max_discharge_power_kw"])
        if not v2b:
            p_dis = 0.0
        ev_sessions.append(
            EvSessionParams(
                session_index=k,
                session_id=str(row["session_id"]),
                arrival_slot_1based=int(row["arrival_slot"]),
                departure_slot_1based=int(row["departure_slot"]),
                E_arrival_kwh=float(row["initial_energy_kwh"]),
                E_required_departure_kwh=float(row["required_energy_at_departure_kwh"]),
                E_max_kwh=float(row["battery_capacity_kwh"]),
                P_charge_max_kw=float(row["max_charge_power_kw"]),
                P_discharge_max_kw=p_dis,
                v2b_allowed=v2b,
                degradation_cost_cny_per_kwh_throughput=float(
                    row.get("degradation_cost_cny_per_kwh_throughput", 0.0)
                ),
            )
        )

    curtail = np.full(n, config.CURTAILMENT_PENALTY_CNY_PER_KWH, dtype=float)
    unserved = np.full(n, config.UNSERVED_PENALTY_CNY_PER_KWH, dtype=float)

    data = CoordinatedInputData(
        n_periods=n,
        delta_t_hours=config.DELTA_T_HOURS,
        timestamps=timestamps,
        slot_ids=np.asarray(slot_ids, dtype=int),
        pv_available_kw=as_1d_float_array(pv_available_kw, n, "pv_available_kw"),
        grid_import_limit_kw=as_1d_float_array(grid_import_limit_kw, n, "grid_import_limit_kw"),
        grid_export_limit_kw=as_1d_float_array(grid_export_limit_kw, n, "grid_export_limit_kw"),
        price_buy_cny_per_kwh=as_1d_float_array(price_buy, n, "price_buy"),
        price_sell_cny_per_kwh=as_1d_float_array(price_sell, n, "price_sell"),
        building_ids=building_ids,
        load_base_kw=load_base_kw,
        buildings_flex=buildings_flex_ordered,
        ess=ess,
        ev_sessions=ev_sessions,
        curtailment_penalty_cny_per_kwh=curtail,
        unserved_penalty_cny_per_kwh=unserved,
        meta={
            "sources": {k: str(resolve_under_root(root, v)) for k, v in p.items()},
        },
    )
    return data


def validate_inputs(data: CoordinatedInputData) -> None:
    """对关键输入做一致性检查。"""
    n = data.n_periods
    assert data.load_base_kw.shape[1] == n
    assert data.pv_available_kw.shape[0] == n
    if data.delta_t_hours <= 0:
        raise ValueError("delta_t_hours 必须为正")


def crop_horizon_and_sessions(
    data: CoordinatedInputData,
    max_periods: int | None = None,
    max_ev_sessions: int | None = None,
) -> CoordinatedInputData:
    """
    将调度时域裁剪为前 `max_periods` 个时段，并可选只保留前若干条 EV 会话。

    用于 Gurobi 规模受限许可证下调试；全时段全会话请将两参数均置为 None。

    Args:
        data: 完整输入。
        max_periods: 保留的时段数 N'<=N；None 表示不裁剪。
        max_ev_sessions: 保留的会话条数；None 表示不裁剪。

    Returns:
        新的 CoordinatedInputData（浅拷贝数组切片 + 会话过滤）。
    """
    n0 = data.n_periods
    n = n0 if max_periods is None else int(min(max_periods, n0))
    if n <= 0:
        raise ValueError("max_periods 必须为正")

    def _slice1(a: np.ndarray) -> np.ndarray:
        return np.asarray(a, dtype=float).reshape(-1)[:n].copy()

    ts = data.timestamps[:n] if data.timestamps else None
    sid = data.slot_ids.reshape(-1)[:n].copy()

    ev_list = list(data.ev_sessions)
    if max_ev_sessions is not None:
        ev_list = ev_list[: int(max_ev_sessions)]

    ev_adj: list[EvSessionParams] = []
    for s in ev_list:
        arr = s.arrival_slot_1based
        dep = s.departure_slot_1based
        if arr > n:
            continue
        dep2 = min(dep, n + 1)
        if dep2 <= arr:
            continue
        ev_adj.append(
            EvSessionParams(
                session_index=len(ev_adj),
                session_id=s.session_id,
                arrival_slot_1based=arr,
                departure_slot_1based=dep2,
                E_arrival_kwh=s.E_arrival_kwh,
                E_required_departure_kwh=s.E_required_departure_kwh,
                E_max_kwh=s.E_max_kwh,
                P_charge_max_kw=s.P_charge_max_kw,
                P_discharge_max_kw=s.P_discharge_max_kw,
                v2b_allowed=s.v2b_allowed,
                eta_charge=s.eta_charge,
                eta_discharge=s.eta_discharge,
                degradation_cost_cny_per_kwh_throughput=s.degradation_cost_cny_per_kwh_throughput,
            )
        )

    return CoordinatedInputData(
        n_periods=n,
        delta_t_hours=data.delta_t_hours,
        timestamps=ts,
        slot_ids=sid,
        pv_available_kw=_slice1(data.pv_available_kw),
        grid_import_limit_kw=_slice1(data.grid_import_limit_kw),
        grid_export_limit_kw=_slice1(data.grid_export_limit_kw),
        price_buy_cny_per_kwh=_slice1(data.price_buy_cny_per_kwh),
        price_sell_cny_per_kwh=_slice1(data.price_sell_cny_per_kwh),
        building_ids=list(data.building_ids),
        load_base_kw=np.asarray(data.load_base_kw, dtype=float)[:, :n].copy(),
        buildings_flex=list(data.buildings_flex),
        ess=data.ess,
        ev_sessions=ev_adj,
        curtailment_penalty_cny_per_kwh=_slice1(data.curtailment_penalty_cny_per_kwh),
        unserved_penalty_cny_per_kwh=_slice1(data.unserved_penalty_cny_per_kwh),
        meta={**data.meta, "crop_max_periods": max_periods, "crop_max_ev": max_ev_sessions},
    )
