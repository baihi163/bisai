# -*- coding: utf-8 -*-
"""
从 ``problem1_baseline_dispatch_timeseries_long.csv`` 导出论文散点图用 CSV
（不改模型、不依赖 matplotlib）。

输出（results/tables/）：
- paper_scatter_fig01_price_buy_vs_grid_import.csv
- paper_scatter_fig02_native_load_vs_net_grid.csv
- paper_scatter_fig03_native_load_vs_flex_support.csv
- paper_scatter_fig04_pv_available_vs_ess_charge.csv
- paper_scatter_fig05_price_buy_vs_ess_net.csv
- paper_scatter_plot_guide.md（正文/附录建议 + 逐图解读句）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]

LONG_CSV = "problem1_baseline_dispatch_timeseries_long.csv"

GUIDE_MD = """# 问题一 vs 基线：散点图数据说明与论文使用建议

## 正文 / 附录建议

| 图 | 建议位置 | 理由 |
|----|----------|------|
| 图1 电价–购电 | **正文** | 直接对应「价格信号→购电响应」，两模型云团分离最易读。 |
| 图2 负荷–净购电 | **正文或附录** | 展示「同等负荷下净购电是否被压低」；若正文篇幅紧可放附录。 |
| 图3 负荷–柔性支撑 | **正文** | 突出协同模型独有建筑移位 + V2G/储能放电，基线几乎贴零，机制对比强。 |
| 图4 光伏–储能充电 | **附录** | 解释「剩余光伏能否进储能」；本数据基线充电点极少，正文易占篇幅却需脚注。 |
| 图5 电价–储能净出力 | **附录** | 与图1互补看储能方向；对非专业读者略抽象，适合附录支撑。 |

## 作图通用建议

- 散点 **alpha≈0.25–0.4**，**按模型分色**；**高价时段**（`is_price_peak_slot=1`）可用**深色描边**或**单独叠加一层**小点突出。
- **趋势线**：对每个 `model_name` 做一元线性拟合（注意极端杠杆点可稳健回归或仅作视觉参考）。
- 轴标签建议英文刊：`Retail purchase price (CNY/kWh)`，`Grid import (kW)` 等；中文稿保留中文轴名。

## 逐图一句话解读（论文风格）

1. **电价–购电**：在相同电价水平下，协调优化将购电功率云团整体下移并收窄高价区尾部，体现对价格与功率的联合响应；基线云团更贴近「负荷驱动」的高购电走廊。
2. **负荷–净购电**：同等原生负荷区间内，协调模型净购电分布更靠下，表明柔性资源与储能/EV 协同削弱了网侧净取电峰值。
3. **负荷–柔性支撑**：高负荷区协调模型出现显著的「储能+EV 放电+建筑移位」支撑功率，而基线几乎无该维度，定量刻画非协同策略的调节缺失。
4. **光伏–储能充电**：协调模型在光伏可用功率升高时储能充电点云明显上扬，反映主动吸纳；基线充电点稀疏，与「仅剩余光伏充电」规则一致。
5. **电价–储能净出力**：协调模型在峰价附近净出力（放减充）为正的概率与幅度更高，呈现「峰时放电、谷时充电」的斜向结构；基线则集中在零附近短窗放电。

数据文件见同目录 `paper_scatter_fig*.csv`；作图脚本：`code/python/analysis/plot_paper_dispatch_scatters.py`。
"""


def _load_long(repo: Path) -> pd.DataFrame:
    p = repo / "results" / "tables" / LONG_CSV
    if not p.is_file():
        raise FileNotFoundError(
            f"缺少 {p}，请先运行 build_dispatch_timeseries_tables.py 生成长表。"
        )
    return pd.read_csv(p, encoding="utf-8-sig")


def main() -> int:
    ap = argparse.ArgumentParser(description="导出散点图用 CSV")
    ap.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    out = repo / "results" / "tables"
    out.mkdir(parents=True, exist_ok=True)

    try:
        df = _load_long(repo)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    need = [
        "model",
        "timestamp",
        "slot_id",
        "price_buy_yuan_per_kwh",
        "native_load_kw",
        "grid_import_kw",
        "grid_export_kw",
        "ess_charge_kw",
        "ess_discharge_kw",
        "ev_discharge_kw",
        "building_shift_kw",
        "pv_available_kw",
        "is_price_peak_slot",
    ]
    miss = [c for c in need if c not in df.columns]
    if miss:
        print(f"长表缺列: {miss}", file=sys.stderr)
        return 2

    df = df.copy()
    df["model_name"] = df["model"].astype(str)
    df["net_grid_kw"] = (
        pd.to_numeric(df["grid_import_kw"], errors="coerce").fillna(0.0)
        - pd.to_numeric(df["grid_export_kw"], errors="coerce").fillna(0.0)
    )
    df["flex_support_kw"] = (
        pd.to_numeric(df["ess_discharge_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["ev_discharge_kw"], errors="coerce").fillna(0.0)
        + pd.to_numeric(df["building_shift_kw"], errors="coerce").fillna(0.0)
    )
    df["ess_net_kw"] = (
        pd.to_numeric(df["ess_discharge_kw"], errors="coerce").fillna(0.0)
        - pd.to_numeric(df["ess_charge_kw"], errors="coerce").fillna(0.0)
    )

    base_cols = ["model_name", "slot_id", "timestamp", "is_price_peak_slot"]

    def save(name: str, cols: list[str]) -> None:
        path = out / name
        df[cols].to_csv(path, index=False, encoding="utf-8-sig")
        print(path)

    save(
        "paper_scatter_fig01_price_buy_vs_grid_import.csv",
        base_cols + ["price_buy_yuan_per_kwh", "grid_import_kw"],
    )
    save(
        "paper_scatter_fig02_native_load_vs_net_grid.csv",
        base_cols + ["native_load_kw", "net_grid_kw"],
    )
    save(
        "paper_scatter_fig03_native_load_vs_flex_support.csv",
        base_cols + ["native_load_kw", "flex_support_kw"],
    )
    save(
        "paper_scatter_fig04_pv_available_vs_ess_charge.csv",
        base_cols + ["pv_available_kw", "ess_charge_kw"],
    )
    save(
        "paper_scatter_fig05_price_buy_vs_ess_net.csv",
        base_cols + ["price_buy_yuan_per_kwh", "ess_net_kw"],
    )

    (out / "paper_scatter_plot_guide.md").write_text(GUIDE_MD, encoding="utf-8")
    print(out / "paper_scatter_plot_guide.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
