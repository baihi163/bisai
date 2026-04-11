"""
园区综合能源系统结构及能量流示意图（问题一 baseline，论文插图用）。

运行：python campus_baseline_energy_flow.py
输出：results/figures/campus_baseline_energy_flow.png（300 dpi）
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

# 论文字号与中文
plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 120,
    }
)


def _box(ax, xy, w, h, text, fontsize=10):
    """圆角节点框，返回中心坐标。"""
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.0,
        edgecolor="#222222",
        facecolor="#f7f7f7",
    )
    ax.add_patch(patch)
    cx, cy = x + w / 2, y + h / 2
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize, color="#111111")
    return cx, cy, w, h


def _arrow(ax, p0, p1, text=None, text_offset=(0, 0), color="#333333", lw=1.2, style="arc3,rad=0"):
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=lw,
        color=color,
        connectionstyle=style,
        shrinkA=2,
        shrinkB=2,
    )
    ax.add_patch(arr)
    if text:
        mx, my = (p0[0] + p1[0]) / 2 + text_offset[0], (p0[1] + p1[1]) / 2 + text_offset[1]
        ax.text(mx, my, text, ha="center", va="center", fontsize=8, color="#222222")


def draw(save_path: Path | None = None) -> Path:
    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.6)
    ax.axis("off")

    # —— 节点布局（左：电网/储能，中：母线，右上：负荷，右下：EV，上：光伏）——
    bus_w, bus_h = 2.4, 0.65
    bus_x, bus_y = (10 - bus_w) / 2, 3.15
    _box(ax, (bus_x, bus_y), bus_w, bus_h, "园区交流母线", fontsize=11)
    bus_cx, bus_cy = bus_x + bus_w / 2, bus_y + bus_h / 2

    pv_cx, pv_cy, _, _ = _box(ax, (4.0, 5.85), 2.0, 0.55, "光伏（PV）", 10)
    grid_cx, grid_cy, _, _ = _box(ax, (0.45, 3.05), 1.35, 0.75, "大电网", 10)
    ess_cx, ess_cy, _, _ = _box(ax, (0.45, 1.05), 1.35, 0.75, "固定储能", 10)
    load_cx, load_cy, _, _ = _box(ax, (7.85, 4.35), 1.7, 0.65, "建筑原生负荷", 9)
    ev_cx, ev_cy, _, _ = _box(ax, (7.85, 1.85), 1.7, 0.65, "电动汽车\n（EV）", 9)

    # 母线矩形边界（用于箭头端点）
    bus_left, bus_right = bus_x, bus_x + bus_w
    bus_bot, bus_top = bus_y, bus_y + bus_h

    # 光伏 → 母线（优先本地消纳）
    _arrow(
        ax,
        (pv_cx, 5.85),
        (bus_cx, bus_top + 0.02),
        "优先本地消纳",
        text_offset=(0.55, 0.25),
        color="#2d6a4f",
    )

    # 大电网 ↔ 母线
    _arrow(ax, (grid_cx + 0.7, grid_cy), (bus_left - 0.02, bus_cy), "购电", text_offset=(0, 0.22))
    _arrow(ax, (bus_left - 0.02, bus_cy + 0.18), (grid_cx + 0.7, grid_cy + 0.18), "上网", text_offset=(0, 0.22))

    # 储能 → 母线（放电）
    _arrow(
        ax,
        (ess_cx + 0.68, ess_cy + 0.2),
        (bus_left + 0.15, bus_bot - 0.02),
        "放电（高价缺电）",
        text_offset=(-0.35, -0.35),
        style="arc3,rad=-0.12",
    )

    # 母线 → 储能（仅剩余光伏充电，不从电网）
    _arrow(
        ax,
        (bus_left + 0.35, bus_bot - 0.02),
        (ess_cx + 0.68, ess_cy - 0.05),
        "充电：仅光伏余电\n（不从电网充电）",
        text_offset=(-0.42, 0.15),
        style="arc3,rad=0.15",
        color="#6c757d",
    )

    # 母线 → 负荷
    _arrow(
        ax,
        (bus_right + 0.02, bus_cy + 0.12),
        (load_cx - 0.86, load_cy),
        None,
        lw=1.0,
    )
    ax.text((bus_right + load_cx - 0.86) / 2 + 0.1, bus_cy + 0.42, "供电", ha="center", fontsize=8)

    # 母线 → EV（仅充电）
    _arrow(
        ax,
        (bus_right + 0.02, bus_cy - 0.12),
        (ev_cx - 0.86, ev_cy),
        "仅充电（无放电）",
        text_offset=(0.15, -0.35),
        color="#1d3557",
    )

    # 标题
    ax.text(
        5,
        7.25,
        "园区综合能源系统结构及能量流（问题一 baseline）",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        color="#111111",
    )

    # baseline 假设汇总
    note = (
        "baseline 要点：① EV 仅从母线取电充电，不向母线放电（无 V2B）；"
        "② 储能能量仅来自光伏盈余充电，不以购电充电；"
        "③ 光伏优先满足建筑与 EV，再考虑储能、上网与弃光。"
    )
    ax.text(
        5,
        0.22,
        note,
        ha="center",
        va="top",
        fontsize=7.8,
        color="#444444",
        linespacing=1.35,
    )

    plt.tight_layout()

    if save_path is None:
        root = Path(__file__).resolve().parents[3]
        save_path = root / "results" / "figures" / "campus_baseline_energy_flow.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    return save_path


if __name__ == "__main__":
    out = draw()
    print(f"已保存: {out}")
