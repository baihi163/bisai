"""
问题一 baseline：非协同调度单时间步流程图（论文插图）。

运行：python baseline_dispatch_flowchart.py
输出：results/figures/baseline_dispatch_flowchart.png（300 dpi）
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 120,
    }
)

BW, BH = 3.5, 0.44
XC = 4.0


def _proc_box(ax, cx, cy, w, h, text, fontsize=9):
    x, y = cx - w / 2, cy - h / 2
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        linewidth=1.0,
        edgecolor="#222222",
        facecolor="#f4f4f4",
    )
    ax.add_patch(p)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize, color="#111")


def _diamond(ax, cx, cy, w, h, text, fontsize=8.5):
    pts = np.array(
        [
            [cx, cy + h / 2],
            [cx + w / 2, cy],
            [cx, cy - h / 2],
            [cx - w / 2, cy],
        ]
    )
    p = Polygon(pts, closed=True, linewidth=1.0, edgecolor="#222222", facecolor="#fff8e7")
    ax.add_patch(p)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize, color="#111", linespacing=1.12)


def _arrow(ax, p0, p1, style="arc3,rad=0", color="#333", lw=1.0):
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=lw,
        color=color,
        connectionstyle=style,
        shrinkA=3,
        shrinkB=3,
    )
    ax.add_patch(arr)


def draw(save_path: Path | None = None) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 10.8))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 11.3)
    ax.axis("off")

    ax.text(
        4,
        10.9,
        "非协同调度流程（单时间步）",
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color="#111",
    )
    ax.text(
        4,
        10.52,
        "规则驱动 · 固定执行次序 · 非目标函数优化求解",
        ha="center",
        va="center",
        fontsize=9,
        color="#555",
        style="italic",
    )

    gap = 0.76
    # 自上而下各框中心 y（显式，便于核对箭头）
    y0 = 9.82  # 开始
    y_read = y0 - gap
    y_ev = y_read - gap
    y_tot = y_ev - gap
    y_pv = y_tot - gap
    y_d_hi = y_pv - gap * 0.95  # 高价判断菱形
    y_merge = y_d_hi - gap * 1.05
    y_grid = y_merge - gap
    y_unmet = y_grid - gap
    y_pv_rem = y_unmet - gap
    y_upd = y_pv_rem - gap
    y_more = y_upd - gap * 0.95
    y_end = y_more - gap * 0.85

    _proc_box(ax, XC, y0, BW, BH, "开始：当前时间步索引 t", 9.5)
    _proc_box(
        ax,
        XC,
        y_read,
        BW,
        BH,
        "读取外生序列与上时段末状态\n（负荷、光伏上限、电价、限额、储能 SOC、各车电量等）",
        8.5,
    )
    _proc_box(
        ax,
        XC,
        y_ev,
        BW,
        BH,
        "按规则计算电动汽车交流充电功率\n（到站即充，无车网反向送电，不响应电价/光伏）",
        8.5,
    )
    _proc_box(ax, XC, y_tot, BW, BH, "形成总需求：原生负荷 + EV 充电功率", 9)
    _proc_box(
        ax,
        XC,
        y_pv,
        BW,
        BH,
        "光伏优先就地消纳（供负荷与 EV）\n得到储能动作前的净需求",
        8.5,
    )

    _diamond(ax, XC, y_d_hi, 2.05, 0.92, "购电价是否处于\n全周高价区间？\n且净需求 > 0？", 8)

    _proc_box(
        ax,
        XC,
        y_merge,
        BW,
        BH,
        "汇合：得到购电前净需求\n（左支已放电削峰 / 右支未放电）",
        8.5,
    )

    ess_cx, ess_cy = 1.32, y_d_hi
    _proc_box(
        ax,
        ess_cx,
        ess_cy,
        2.12,
        0.5,
        "是：储能在功率/SOC\n约束下放电削峰",
        8,
    )

    _proc_box(ax, XC, y_grid, BW, BH, "电网购电补足剩余缺口\n（功率 ≤ 时段进口上限）", 9)
    _proc_box(
        ax,
        XC,
        y_unmet,
        BW,
        BH,
        "若购电达上限仍不足：\n记录本步 unmet_load_kw",
        8.5,
    )
    _proc_box(
        ax,
        XC,
        y_pv_rem,
        BW,
        BH,
        "按规则分配剩余光伏\n（充储能 → 上网受出口上限 → 弃光）",
        8.5,
    )
    _proc_box(ax, XC, y_upd, BW, BH, "更新状态：储能能量、各 EV 电量等\n（递推至时段末）", 8.5)

    _diamond(ax, XC, y_more, 1.82, 0.76, "是否还有\n下一时间步？", 9)
    _proc_box(ax, XC, y_end, 2.15, 0.38, "否：仿真结束", 9)

    # 竖直主链箭头
    chain = [y0, y_read, y_ev, y_tot, y_pv]
    for i in range(len(chain) - 1):
        _arrow(ax, (XC, chain[i] - BH / 2 - 0.02), (XC, chain[i + 1] + BH / 2 + 0.02))
    _arrow(ax, (XC, y_pv - BH / 2 - 0.02), (XC, y_d_hi + 0.92 / 2 + 0.02))

    # 菱形 → 左（是）→ 储能
    _arrow(ax, (XC - 1.02, y_d_hi), (ess_cx + 2.12 / 2 + 0.02, ess_cy))
    ax.text(XC - 1.28, y_d_hi + 0.1, "是", fontsize=8, color="#333")
    # 菱形 → 下（否）→ 汇合框
    _arrow(ax, (XC, y_d_hi - 0.92 / 2 - 0.02), (XC, y_merge + BH / 2 + 0.02))
    ax.text(XC + 0.38, y_d_hi - 0.58, "否", fontsize=8, color="#333")
    # 储能 → 汇合框
    _arrow(ax, (ess_cx + 2.12 / 2 + 0.02, ess_cy), (XC - BW / 2 + 0.2, y_merge), style="arc3,rad=-0.06")
    ax.text(2.5, y_merge + 0.16, "汇合", fontsize=7.5, color="#666")

    _arrow(ax, (XC, y_merge - BH / 2 - 0.02), (XC, y_grid + BH / 2 + 0.02))
    _arrow(ax, (XC, y_grid - BH / 2 - 0.02), (XC, y_unmet + BH / 2 + 0.02))
    _arrow(ax, (XC, y_unmet - BH / 2 - 0.02), (XC, y_pv_rem + BH / 2 + 0.02))
    _arrow(ax, (XC, y_pv_rem - BH / 2 - 0.02), (XC, y_upd + BH / 2 + 0.02))
    _arrow(ax, (XC, y_upd - BH / 2 - 0.02), (XC, y_more + 0.76 / 2 + 0.02))

    # 是否还有下一时段
    _arrow(ax, (XC, y_more - 0.76 / 2 - 0.02), (XC, y_end + 0.38 / 2 + 0.02))
    ax.text(XC + 0.42, y_more - 0.5, "否", fontsize=8, color="#333")

    xr = 7.2
    _arrow(ax, (XC + 0.92, y_more), (xr, y_more))
    ax.text(5.85, y_more + 0.2, "是", fontsize=8, color="#333")
    _arrow(ax, (xr, y_more), (xr, y_read))
    _arrow(ax, (xr, y_read), (XC + BW / 2 + 0.02, y_read))
    ax.text(
        xr + 0.12,
        (y_more + y_read) / 2,
        "t ← t+1\n返回读取",
        ha="left",
        va="center",
        fontsize=8,
        color="#1a5276",
    )

    plt.tight_layout()

    if save_path is None:
        root = Path(__file__).resolve().parents[3]
        save_path = root / "results" / "figures" / "baseline_dispatch_flowchart.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    return save_path


if __name__ == "__main__":
    out = draw()
    print(f"已保存: {out}")
