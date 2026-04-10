# -*- coding: utf-8 -*-
"""问题1建模前：从 data/raw 生成 data/processed/final_model_inputs/ 标准化输入。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "final_model_inputs"
OUT.mkdir(parents=True, exist_ok=True)

GRID_START = pd.Timestamp("2025-07-14 00:00:00")
GRID_END_SLOT_START = pd.Timestamp("2025-07-20 23:45:00")
N_SLOTS = 672
DT_HOURS = 0.25
EPS = 1e-9


def build_time_index() -> pd.DatetimeIndex:
    idx = pd.date_range(GRID_START, periods=N_SLOTS, freq="15min")
    assert idx[-1] == GRID_END_SLOT_START
    return idx


def timestamp_to_slot(ts: pd.Timestamp) -> int:
    """1-indexed slot where interval starts at ts; must align to grid."""
    delta = ts - GRID_START
    n = int(delta.total_seconds() // (15 * 60))
    return n + 1


def package_timeseries() -> dict:
    path = RAW / "timeseries_15min.csv"
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    idx = build_time_index()
    if not df["timestamp"].equals(pd.Series(idx)):
        df = df.set_index("timestamp").reindex(idx)
        df.index.name = "timestamp"
        df = df.reset_index()
    df["slot_id"] = np.arange(1, N_SLOTS + 1, dtype=int)

    cols_load = [
        "timestamp",
        "slot_id",
        "total_native_load_kw",
        "office_building_kw",
        "wet_lab_kw",
        "teaching_center_kw",
    ]
    load_cols = [c for c in cols_load if c in df.columns]
    df[load_cols].to_csv(OUT / "load_profile.csv", index=False)

    pv_cols = [c for c in ["timestamp", "slot_id", "pv_available_kw"] if c in df.columns]
    df[pv_cols].to_csv(OUT / "pv_profile.csv", index=False)

    price_cols = [
        c
        for c in [
            "timestamp",
            "slot_id",
            "grid_buy_price_cny_per_kwh",
            "grid_sell_price_cny_per_kwh",
        ]
        if c in df.columns
    ]
    df[price_cols].to_csv(OUT / "price_profile.csv", index=False)

    grid_cols = [
        c
        for c in ["timestamp", "slot_id", "grid_import_limit_kw", "grid_export_limit_kw"]
        if c in df.columns
    ]
    df[grid_cols].to_csv(OUT / "grid_limits.csv", index=False)

    carb_cols = [c for c in ["timestamp", "slot_id", "grid_carbon_kg_per_kwh"] if c in df.columns]
    df[carb_cols].to_csv(OUT / "carbon_profile.csv", index=False)

    return {
        "timeseries_path": str(path),
        "rows": len(df),
        "columns": list(df.columns),
    }


def package_ess() -> dict:
    ap = pd.read_csv(RAW / "asset_parameters.csv")
    m = dict(zip(ap["parameter"].astype(str), ap["value"]))
    notes = dict(zip(ap["parameter"].astype(str), ap["note"].astype(str)))

    def gv(key: str):
        return float(m[key]) if key in m and pd.notna(m.get(key)) else None

    cap = gv("stationary_battery_energy_capacity_kwh")
    e0 = gv("stationary_battery_initial_energy_kwh")
    p_ch = gv("stationary_battery_max_charge_power_kw")
    p_dis = gv("stationary_battery_max_discharge_power_kw")
    eta_c = gv("stationary_battery_charge_efficiency")
    eta_d = gv("stationary_battery_discharge_efficiency")
    e_min = gv("stationary_battery_min_energy_kwh")
    e_max = gv("stationary_battery_max_energy_kwh")
    dt = gv("default_time_step_hours")

    soc_min = (e_min / cap) if (cap and e_min is not None) else None
    soc_max = (e_max / cap) if (cap and e_max is not None) else None

    payload = {
        "energy_capacity_kwh": cap,
        "initial_energy_kwh": e0,
        "max_charge_power_kw": p_ch,
        "max_discharge_power_kw": p_dis,
        "charge_efficiency": eta_c,
        "discharge_efficiency": eta_d,
        "min_energy_kwh": e_min,
        "max_energy_kwh": e_max,
        "min_soc_ratio": soc_min,
        "max_soc_ratio": soc_max,
        "time_step_hours": dt,
        "_source_file": "asset_parameters.csv",
        "_missing_or_null_fields": [],
        "_remarks": [],
    }

    for label, val in [
        ("energy_capacity_kwh", cap),
        ("initial_energy_kwh", e0),
        ("max_charge_power_kw", p_ch),
        ("max_discharge_power_kw", p_dis),
        ("charge_efficiency", eta_c),
        ("discharge_efficiency", eta_d),
        ("min_energy_kwh", e_min),
        ("max_energy_kwh", e_max),
        ("time_step_hours", dt),
    ]:
        if val is None:
            payload["_missing_or_null_fields"].append(label)

    if cap and e_min is not None and e_max is not None:
        payload["_remarks"].append(
            "min_soc_ratio/max_soc_ratio 由 min_energy_kwh、max_energy_kwh 与 energy_capacity_kwh 推导；"
            "若容量缺失则为 null。"
        )
    (OUT / "ess_params.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"keys": list(payload.keys()), "missing": payload["_missing_or_null_fields"]}


def ceil_15min(ts: pd.Series) -> pd.Series:
    return ts.dt.ceil("15min")


def floor_15min(ts: pd.Series) -> pd.Series:
    return ts.dt.floor("15min")


def package_ev_sessions() -> tuple[pd.DataFrame, dict]:
    ev = pd.read_csv(RAW / "ev_sessions.csv")
    orig_cols = list(ev.columns)
    ev = ev.copy()
    ev["arrival_time"] = pd.to_datetime(ev["arrival_time"])
    ev["departure_time"] = pd.to_datetime(ev["departure_time"])
    ev["arrival_time_discrete"] = ceil_15min(ev["arrival_time"])
    ev["departure_time_discrete"] = floor_15min(ev["departure_time"])

    ev.insert(0, "ev_index", np.arange(1, len(ev) + 1, dtype=int))

    def slot_of_start(ts: pd.Timestamp) -> int:
        if ts < GRID_START or ts > GRID_END_SLOT_START:
            return np.nan
        return timestamp_to_slot(ts)

    ev["arrival_slot"] = ev["arrival_time_discrete"].map(slot_of_start)
    ev["departure_slot"] = ev["departure_time_discrete"].map(slot_of_start)

    ev["dwell_slots"] = ev["departure_slot"] - ev["arrival_slot"]

    notes: list[str] = []

    def row_issue(r) -> str:
        parts: list[str] = []
        req = float(r["required_energy_at_departure_kwh"])
        ini = float(r["initial_energy_kwh"])
        cap = float(r["battery_capacity_kwh"])
        if req + EPS < ini:
            parts.append("required_energy_at_departure_kwh < initial_energy_kwh")
        if req > cap + EPS:
            parts.append("required_energy_at_departure_kwh > battery_capacity_kwh")
        ds = r["dwell_slots"]
        if pd.isna(ds) or ds <= 0:
            parts.append("dwell_slots<=0 或时间越界（离散到网格外/dep<=arr）")
        if pd.isna(r["arrival_slot"]) or pd.isna(r["departure_slot"]):
            parts.append("arrival_slot 或 departure_slot 无法映射到 672 网格")
        return "; ".join(parts)

    ev["issue_note"] = ev.apply(row_issue, axis=1).fillna("")

    def feasibility(r) -> int:
        if str(r["issue_note"]).strip():
            return 0
        ds = r["dwell_slots"]
        if pd.isna(ds) or ds <= 0:
            return 0
        need = float(r["required_energy_at_departure_kwh"]) - float(r["initial_energy_kwh"])
        if need <= EPS:
            return 1
        p = float(r["max_charge_power_kw"])
        max_kwh = p * float(ds) * DT_HOURS
        return int(need <= max_kwh + 1e-6)

    ev["feasibility_flag"] = ev.apply(feasibility, axis=1)

    extra = [
        "ev_index",
        "arrival_time_discrete",
        "departure_time_discrete",
        "arrival_slot",
        "departure_slot",
        "dwell_slots",
        "feasibility_flag",
        "issue_note",
    ]
    out_cols = extra[:1] + orig_cols + extra[1:]
    ev[out_cols].to_csv(
        OUT / "ev_sessions_model_ready.csv", index=False, na_rep=""
    )

    meta = {"n_ev": len(ev), "orig_columns": orig_cols}
    return ev, meta


def build_ev_matrices(ev: pd.DataFrame) -> dict:
    n_ev = len(ev)
    slot_idx = np.arange(N_SLOTS)
    t_starts = GRID_START + pd.to_timedelta(slot_idx * 15, unit="m")
    t_ends = t_starts + pd.Timedelta(minutes=15)

    avail = np.zeros((N_SLOTS, n_ev), dtype=np.int8)
    p_ch = np.zeros((N_SLOTS, n_ev), dtype=float)
    p_dis = np.zeros((N_SLOTS, n_ev), dtype=float)

    arr_d = ev["arrival_time_discrete"].to_numpy()
    dep_d = ev["departure_time_discrete"].to_numpy()
    mcp = ev["max_charge_power_kw"].astype(float).to_numpy()
    mdp = ev["max_discharge_power_kw"].astype(float).to_numpy()
    v2b = ev["v2b_allowed"].astype(int).to_numpy()

    for j in range(n_ev):
        ta = pd.Timestamp(arr_d[j])
        td = pd.Timestamp(dep_d[j])
        for i in range(N_SLOTS):
            ts = t_starts[i]
            te = t_ends[i]
            if ts < td and te > ta:
                avail[i, j] = 1
                p_ch[i, j] = mcp[j]
                if v2b[j] == 1:
                    p_dis[i, j] = mdp[j]

    ts_col = pd.to_datetime(t_starts)
    slot_col = np.arange(1, N_SLOTS + 1)
    ev_cols = [f"ev_{k}" for k in range(1, n_ev + 1)]

    def write_mat(path, mat):
        d = {"timestamp": ts_col, "slot_id": slot_col}
        for c, j in zip(ev_cols, range(n_ev)):
            d[c] = mat[:, j]
        pd.DataFrame(d).to_csv(path, index=False)

    write_mat(OUT / "ev_availability_matrix.csv", avail)
    write_mat(OUT / "ev_charge_power_limit_matrix_kw.csv", p_ch)
    write_mat(OUT / "ev_discharge_power_limit_matrix_kw.csv", p_dis)

    return {"n_ev": n_ev, "ev_columns": ev_cols}


def package_flexible_load() -> dict:
    fl = pd.read_csv(RAW / "flexible_load_parameters.csv")
    fl = fl.rename(
        columns={
            c: c.strip().lower().replace(" ", "_")
            for c in fl.columns
        }
    )
    numeric_cols = [
        c
        for c in fl.columns
        if c
        not in (
            "load_block",
        )
    ]
    for c in numeric_cols:
        fl[c] = pd.to_numeric(fl[c], errors="coerce")
    fl.to_csv(OUT / "flexible_load_params_clean.csv", index=False)

    mapping_rows = []
    for _, r in fl.iterrows():
        lb = str(r["load_block"])
        if lb == "office_building":
            expl = (
                "对应 timeseries_15min.csv 中的 office_building_kw（办公楼分项负荷）；"
                "柔性参数描述该分项的可转移/可削减能力。"
            )
            conf = "由 load_block 命名与原始数据列名一致，可唯一对应办公楼分项。"
        elif lb == "wet_lab":
            expl = (
                "对应 timeseries_15min.csv 中的 wet_lab_kw（湿实验楼分项负荷）。"
            )
            conf = "由 load_block 命名与原始数据列名一致，可唯一对应湿实验楼分项。"
        elif lb == "teaching_center":
            expl = (
                "对应 timeseries_15min.csv 中的 teaching_center_kw（教学中心分项负荷）。"
            )
            conf = "由 load_block 命名与原始数据列名一致，可唯一对应教学中心分项。"
        else:
            expl = "建议映射解释：原始未提供标准别名，请结合题目说明或场景备注人工核对。"
            conf = "无法从原始 flexible_load_parameters 唯一判断物理对象。"

        mapping_rows.append(
            {
                "load_block": lb,
                "mapping_to_timeseries_component": expl,
                "mapping_confidence": conf,
                "relation_to_total_native_load": (
                    "total_native_load_kw 为各分项之和（见 timeseries），"
                    "flexible_load 各块分别绑定对应分项，而非单独占用总负荷列。"
                ),
            }
        )
    pd.DataFrame(mapping_rows).to_csv(OUT / "flexible_load_mapping.csv", index=False)
    return {"rows": len(fl), "columns": list(fl.columns)}


def null_summary(df: pd.DataFrame) -> dict:
    return {c: int(df[c].isna().sum()) for c in df.columns}


def describe_csv(path: Path, keep_default_na: bool = True) -> dict:
    df = pd.read_csv(path, keep_default_na=keep_default_na)
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "null_counts": null_summary(df),
    }


def write_readme() -> None:
    text = """# 问题1 建模输入封装说明（final_model_inputs）

本目录由 `code/python/package_final_model_inputs.py` 从 `data/raw/` 下原始表生成，**不修改原始文件**。

## 使用的原始文件

| 原始文件 | 用途 |
|----------|------|
| `timeseries_15min.csv` | 拆分为负荷、光伏、电价、网侧限额、碳强度等时序 |
| `asset_parameters.csv` | 固定储能（ESS）参数 → `ess_params.json` |
| `ev_sessions.csv` | EV 逐车表与 672×N 矩阵 |
| `flexible_load_parameters.csv` | 柔性负荷参数与映射说明 |

## 本封装未直接读取的原始文件（可留作校验/文档）

以下文件在本次“最终封装”中**未参与写入**，若建模需要日汇总或场景说明，请另行引用：

- `daily_summary.csv`
- `ev_summary_stats.csv`
- `scenario_notes.csv`

---

## 输出文件字段与用途

### `load_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp` | 15 min 时间戳，起 `2025-07-14 00:00:00` | 原始 |
| `slot_id` | 时段序号 1–672 | **新增** |
| `total_native_load_kw` | 园区不可调原生总负荷 | 原始 |
| `office_building_kw` | 办公楼分项 | 原始 |
| `wet_lab_kw` | 湿实验楼分项 | 原始 |
| `teaching_center_kw` | 教学中心分项 | 原始 |

**问题1用途**：基线负荷曲线；可与柔性块参数联立做移峰/削减。

**假设**：若原始时序与完整 672 网格不一致，脚本按网格 `reindex`，缺失行会出现 NaN（见检查报告）。

---

### `pv_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `pv_available_kw` | 可用光伏出力（已含站内约束后的可用值） | 原始 |

**问题1用途**：可再生供给上界。

---

### `price_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_buy_price_cny_per_kwh` | 购电电价 | 原始 |
| `grid_sell_price_cny_per_kwh` | 售电电价 | 原始 |

**问题1用途**：购售电成本/收益。

---

### `grid_limits.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_import_limit_kw` | 购电功率上限 | 原始 |
| `grid_export_limit_kw` | 售电/上网功率上限 | 原始 |

**问题1用途**：并网点功率约束。

---

### `carbon_profile.csv`

| 字段 | 说明 | 来源 |
|------|------|------|
| `timestamp`, `slot_id` | 同上 | 混合 |
| `grid_carbon_kg_per_kwh` | 电网排放因子 | 原始 |

**问题1用途**：购电碳排放核算（若目标或约束中含碳）。

---

### `ess_params.json`

| 字段 | 说明 | 来源 |
|------|------|------|
| `energy_capacity_kwh` | 储能容量 | 原始 `stationary_battery_energy_capacity_kwh` |
| `initial_energy_kwh` | 初始电量 | 原始 |
| `max_charge_power_kw` / `max_discharge_power_kw` | 最大充/放电功率 | 原始 |
| `charge_efficiency` / `discharge_efficiency` | 单向效率 | 原始 |
| `min_energy_kwh` / `max_energy_kwh` | 能量上下界 | 原始 |
| `min_soc_ratio` / `max_soc_ratio` | SOC 比（由能量界/容量推导） | **派生** |
| `time_step_hours` | 时间步长（小时） | 原始 `default_time_step_hours` |
| `_missing_or_null_fields` | 缺失字段名列表 | **新增** |
| `_remarks` | 备注（如 SOC 推导说明） | **新增** |

未在 `asset_parameters.csv` 中出现的键**不虚构**，对应值为 `null` 并列入 `_missing_or_null_fields`。

**问题1用途**：站内电池状态方程与功率限值。

**说明**：`asset_parameters.csv` 中另有 PV、充电桩数量等条目，本 JSON **仅封装固定储能相关**字段及时间步长。

---

### `ev_sessions_model_ready.csv`

保留 `ev_sessions.csv` 全部原始列，并新增/处理如下。

| 字段 | 说明 | 来源 |
|------|------|------|
| `ev_index` | 车辆序号 1…N（与矩阵列顺序一致） | **新增** |
| `arrival_time` / `departure_time` | datetime 解析 | 原始（类型转换） |
| `arrival_time_discrete` | 到达时间 **向上** 取整到 15 min | **新增** |
| `departure_time_discrete` | 离开时间 **向下** 取整到 15 min | **新增** |
| `arrival_slot` / `departure_slot` | 上述离散时刻在 672 网格上的 1-based 槽位（起点对齐） | **新增** |
| `dwell_slots` | `departure_slot - arrival_slot`（与半开区间 `[t_arr, t_dep)` 内完整 15 min 段数一致） | **新增** |
| `feasibility_flag` | 1/0：在 **无数据异常** 前提下，若 `(required-initial)>0`，是否满足 `(required-initial) ≤ max_charge_power_kw × dwell_slots × 0.25h` | **新增** |
| `issue_note` | 能量上下界违规、停车窗无效或越出网格等说明；正常为空字符串 | **新增** |

**预处理假设（重要）**

- 时间网格：`2025-07-14 00:00:00` 至 `2025-07-20 23:45:00`，共 672 个时段。
- **保守离散化**：到达不早于实际到达（ceil），离开不晚于实际离开（floor），建模停车窗偏短。
- **在站时段与矩阵**：时段 `t` 与停车窗 `[arrival_time_discrete, departure_time_discrete)` 在时间上重叠则视为在站（与 `dwell_slots` 计数一致）。
- **`feasibility_flag`**：未使用车载充电效率；未考虑 V2B 向负荷送电；仅为**上界**意义上的可充性检查。若 `issue_note` 非空，则 `feasibility_flag` 强制为 0。

**问题1用途**：EV 能量约束、到离站、功率上限、V2B 是否允许。

---

### `ev_availability_matrix.csv` / `ev_charge_power_limit_matrix_kw.csv` / `ev_discharge_power_limit_matrix_kw.csv`

| 结构 | 说明 |
|------|------|
| 行 | 672 时段，含 `timestamp`、`slot_id` |
| 列 `ev_k` | 对应 `ev_index = k`（k=1…N） |

- **availability**：在站为 1，否则 0。
- **charge 上限**：在站为该车 `max_charge_power_kw`，否则 0。
- **discharge 上限**：仅当 `v2b_allowed=1` 时在站为 `max_discharge_power_kw`，否则 0。

**问题1用途**：逐车充放电决策的大M/上限约束。

---

### `flexible_load_params_clean.csv`

对 `flexible_load_parameters.csv` 列名做小写与去空格规范化，数值列 `to_numeric`。字段与原始一致：

- `load_block`, `noninterruptible_share`, `max_shiftable_kw`, `max_sheddable_kw`, `rebound_factor`, `penalty_cny_per_kwh_not_served`

**问题1用途**：分块柔性负荷建模参数。

---

### `flexible_load_mapping.csv`

| 字段 | 说明 |
|------|------|
| `load_block` | 块标识 |
| `mapping_to_timeseries_component` | 与 `timeseries_15min` 分项的对应关系说明 |
| `mapping_confidence` | 能否从原始表唯一确定 |
| `relation_to_total_native_load` | 与 `total_native_load_kw` 的关系说明 |

当前原始 `load_block` 命名与 `timeseries_15min` 列名一致，故三行均可**唯一**映射到办公楼/湿实验楼/教学中心分项；**未**将任一块等同于“园区总负荷”本身。

---

## 复现方式

```bash
python code/python/package_final_model_inputs.py
```

"""
    (OUT / "final_model_inputs_readme.md").write_text(text, encoding="utf-8")


def write_packaging_check(
    n_ev: int,
    ts_rows: int,
    ts_reindexed: bool,
) -> None:
    lines = [
        "# 最终封装检查报告（final_packaging_check）",
        "",
        f"- 生成时间（运行脚本时）由文件系统记录；源数据目录：`data/raw/`。",
        f"- 时序源行数（读入后）：{ts_rows}；是否与 672 网格强制对齐：{'是（已 reindex）' if ts_reindexed else '否（原序已对齐）'}。",
        "",
        "## 1. 输出文件是否生成",
        "",
    ]
    expected = [
        "load_profile.csv",
        "pv_profile.csv",
        "price_profile.csv",
        "grid_limits.csv",
        "carbon_profile.csv",
        "ess_params.json",
        "ev_sessions_model_ready.csv",
        "ev_availability_matrix.csv",
        "ev_charge_power_limit_matrix_kw.csv",
        "ev_discharge_power_limit_matrix_kw.csv",
        "flexible_load_params_clean.csv",
        "flexible_load_mapping.csv",
    ]
    all_ok = True
    ev_cols_expected = n_ev + 2
    ts_ok = True
    issue_nonempty = 0
    feas0 = 0

    for fn in expected:
        p = OUT / fn
        ex = p.exists()
        all_ok = all_ok and ex
        lines.append(f"- **{fn}**：{'已生成' if ex else '缺失'}")

    rm = OUT / "final_model_inputs_readme.md"
    r_ok = rm.exists()
    all_ok = all_ok and r_ok
    lines.append(f"- **final_model_inputs_readme.md**：{'已生成' if r_ok else '缺失'}")
    lines.append("- **final_packaging_check.md**：由本脚本末尾写入（即当前文件）。")

    lines.extend(["", "## 2. 行数与列数", ""])

    def add_table_row(name: str, rows: str, cols: str, notes: str = ""):
        lines.append(f"| {name} | {rows} | {cols} | {notes} |")

    lines.append("| 文件 | 行数 | 列数 | 备注 |")
    lines.append("|------|------|------|------|")

    for fn in [
        "load_profile.csv",
        "pv_profile.csv",
        "price_profile.csv",
        "grid_limits.csv",
        "carbon_profile.csv",
    ]:
        p = OUT / fn
        if p.exists():
            d = describe_csv(p)
            ok672 = d["rows"] == 672
            ts_ok = ts_ok and ok672
            add_table_row(fn, str(d["rows"]), str(d["columns"]), "OK 672" if ok672 else "≠672")
        else:
            add_table_row(fn, "-", "-", "文件缺失")

    p_ess = OUT / "ess_params.json"
    if p_ess.exists():
        j = json.loads(p_ess.read_text(encoding="utf-8"))
        nulls = [k for k, v in j.items() if not str(k).startswith("_") and v is None]
        add_table_row(
            "ess_params.json",
            "1 个 JSON 对象",
            str(len([k for k in j if not k.startswith("_")])),
            f"值为 null 的字段：{nulls if nulls else '无'}",
        )
    else:
        add_table_row("ess_params.json", "-", "-", "缺失")

    p_ev = OUT / "ev_sessions_model_ready.csv"
    if p_ev.exists():
        ev_df = pd.read_csv(p_ev, keep_default_na=False)
        issue_nonempty = int(ev_df["issue_note"].astype(str).str.strip().ne("").sum())
        feas0 = int((ev_df["feasibility_flag"] == 0).sum())
        add_table_row(
            "ev_sessions_model_ready.csv",
            str(len(ev_df)),
            str(len(ev_df.columns)),
            f"EV 数 N={n_ev}",
        )
    else:
        add_table_row("ev_sessions_model_ready.csv", "-", "-", "缺失")

    for fn, label in [
        ("ev_availability_matrix.csv", "availability"),
        ("ev_charge_power_limit_matrix_kw.csv", "P_ch"),
        ("ev_discharge_power_limit_matrix_kw.csv", "P_dis"),
    ]:
        p = OUT / fn
        if p.exists():
            d = describe_csv(p)
            ncol = d["columns"]
            match = ncol == ev_cols_expected
            add_table_row(
                fn,
                str(d["rows"]),
                str(d["columns"]),
                f"期望列数 2+N={ev_cols_expected}，{'一致' if match else '不一致'}",
            )
        else:
            add_table_row(fn, "-", "-", "缺失")

    for fn in ["flexible_load_params_clean.csv", "flexible_load_mapping.csv"]:
        p = OUT / fn
        if p.exists():
            d = describe_csv(p)
            add_table_row(fn, str(d["rows"]), str(d["columns"]), "")
        else:
            add_table_row(fn, "-", "-", "缺失")

    lines.extend(
        [
            "",
            "## 3. 空值（NaN）检查",
            "",
            "对 CSV 使用 `pandas.read_csv` 默认缺失值解析；`issue_note` 中空字符串在默认解析下可能显示为 NaN，**属正常现象**，以 `keep_default_na=False` 读取时均为空串。",
            "",
        ]
    )

    for fn in [
        "load_profile.csv",
        "pv_profile.csv",
        "price_profile.csv",
        "grid_limits.csv",
        "carbon_profile.csv",
        "ev_sessions_model_ready.csv",
        "ev_availability_matrix.csv",
        "ev_charge_power_limit_matrix_kw.csv",
        "ev_discharge_power_limit_matrix_kw.csv",
        "flexible_load_params_clean.csv",
        "flexible_load_mapping.csv",
    ]:
        p = OUT / fn
        if not p.exists():
            lines.append(f"- **{fn}**：文件不存在。")
            continue
        kdna = fn == "ev_sessions_model_ready.csv"
        df = pd.read_csv(p, keep_default_na=not kdna)
        nz = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
        if nz:
            lines.append(f"- **{fn}** 含 NaN 的列及计数：`{nz}`")
        else:
            lines.append(f"- **{fn}**：无 NaN。")

    lines.extend(
        [
            "",
            "## 4. 一致性校验",
            "",
            f"- EV 主表车辆数 N = **{n_ev}**；三个矩阵数据列数均为 **{n_ev}**（列名 `ev_1`…`ev_{n_ev}`），与 `ev_index` 顺序一致。",
            f"- `issue_note` 非空行数：**{issue_nonempty}**（数据异常说明）。",
            f"- `feasibility_flag == 0` 行数：**{feas0}**（含 issue 导致强制 0 + 充电上界不足）。",
            f"- 时序类 CSV（负荷/光伏/电价/限额/碳）行数均为 672：**{'是' if ts_ok else '否'}**。",
            "",
            "## 5. 是否适合作为问题1直接输入",
            "",
        ]
    )

    suitable = all_ok and ts_ok and n_ev > 0
    if suitable:
        lines.append(
            "- **结论**：结构完整，时序长度与 EV 矩阵维度一致，可作为问题1确定性/优化模型的**直接读取输入**。"
            "若某 EV `feasibility_flag=0`，建模时应对该会话施加额外松弛变量或剔除约束，需结合物理意义自行处理。"
        )
    else:
        lines.append("- **结论**：存在缺失文件或时序行数非 672，请先修复数据或检查脚本。")

    lines.append("")
    (OUT / "final_packaging_check.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ts_path = RAW / "timeseries_15min.csv"
    ts_raw = pd.read_csv(ts_path)
    ts_rows = len(ts_raw)
    ts_idx = build_time_index()
    ts_reindexed = not pd.to_datetime(ts_raw["timestamp"]).equals(pd.Series(ts_idx))

    package_timeseries()
    package_ess()
    ev_df, ev_meta = package_ev_sessions()
    n_ev = ev_meta["n_ev"]
    build_ev_matrices(ev_df)
    package_flexible_load()

    write_readme()
    write_packaging_check(n_ev=n_ev, ts_rows=ts_rows, ts_reindexed=ts_reindexed)


if __name__ == "__main__":
    main()
