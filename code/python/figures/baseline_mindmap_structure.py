"""
问题一 baseline：思维导图式模型结构与规则逻辑（论文横版插图）。

运行：python baseline_mindmap_structure.py
输出：results/figures/baseline_mindmap_structure.png（300 dpi）与同基名 .svg

配色：背景 / 中心 / 四周各一色（平涂无渐变）；#RRGGBBAA 末两位为透明度，导出时与白底合成不透明色。
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 120,
    }
)

# 背景、中心、四周
COLOR_BACKGROUND = "#2472A3C2"
COLOR_CENTER = "#A5B55DC2"
COLOR_PERIPHERY = "#F4F3EEC2"


def _hex8_rgba(s: str) -> tuple[float, float, float, float]:
    s = s.strip().lstrip("#")
    r, g, b, a = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4, 6))
    return (r, g, b, a)


def _flatten_on_white(rgba: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """半透明色与白底 alpha 合成，得到不透明平涂 RGB。"""
    r, g, b, a = rgba
    rw = (1.0 - a) + a * r
    gw = (1.0 - a) + a * g
    bw = (1.0 - a) + a * b
    return (rw, gw, bw, 1.0)


def _darken_edge(rgba: tuple[float, float, float, float], factor: float = 0.62) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    return (r * factor, g * factor, b * factor, 1.0)


def _rounded_rect(ax, cx, cy, w, h, **kwargs):
    x, y = cx - w / 2, cy - h / 2
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.015,rounding_size=0.12",
        **kwargs,
    )
    ax.add_patch(p)


def _branch_box(
    ax,
    cx,
    cy,
    w,
    h,
    title: str,
    body: str,
    *,
    face_rgba: tuple[float, float, float, float],
    title_fs=9.8,
    body_fs=7.6,
):
    edge = _darken_edge(face_rgba)
    _rounded_rect(ax, cx, cy, w, h, linewidth=1.15, edgecolor=edge, facecolor=face_rgba, zorder=3)
    top = cy + h / 2 - 0.08
    ax.text(
        cx,
        top,
        title,
        ha="center",
        va="top",
        fontsize=title_fs,
        fontweight="bold",
        color="#1e1a2e",
        zorder=4,
    )
    ax.text(
        cx,
        top - 0.26,
        body,
        ha="center",
        va="top",
        fontsize=body_fs,
        color="#2d2840",
        linespacing=1.32,
        zorder=4,
    )


def _connect(ax, p0, p1, color, lw=1.45):
    ax.plot(
        [p0[0], p1[0]],
        [p0[1], p1[1]],
        color=color,
        linewidth=lw,
        solid_capstyle="round",
        zorder=2,
    )


def draw(save_base: Path | None = None) -> tuple[Path, Path]:
    fig_w, fig_h = 12.0, 6.85
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    xmin, xmax, ymin, ymax = 0.0, 12.0, 0.0, 6.85
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.axis("off")

    bg = _flatten_on_white(_hex8_rgba(COLOR_BACKGROUND))
    center_fill = _flatten_on_white(_hex8_rgba(COLOR_CENTER))
    periph_fill = _flatten_on_white(_hex8_rgba(COLOR_PERIPHERY))

    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    line_rgb = (
        0.35 * bg[0] + 0.35 * center_fill[0] + 0.30 * periph_fill[0],
        0.35 * bg[1] + 0.35 * center_fill[1] + 0.30 * periph_fill[1],
        0.35 * bg[2] + 0.35 * center_fill[2] + 0.30 * periph_fill[2],
    )
    line_color = (*line_rgb, 0.88)

    ax.text(
        6,
        6.52,
        "问题一 baseline 模型结构与规则逻辑示意图",
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
        color="#1a1528",
        zorder=4,
    )

    cx, cy = 6.0, 3.05
    cw, ch = 2.85, 0.92
    _rounded_rect(
        ax,
        cx,
        cy,
        cw,
        ch,
        linewidth=1.85,
        edgecolor=_darken_edge(center_fill, 0.55),
        facecolor=center_fill,
        zorder=3,
    )
    ax.text(
        cx,
        cy,
        "问题一 baseline\n非协同调度模型",
        ha="center",
        va="center",
        fontsize=10.5,
        fontweight="bold",
        color="#141022",
        linespacing=1.2,
        zorder=4,
    )

    def center_anchor(angle_deg: float, pad: float = 0.02):
        phi = math.radians(angle_deg)
        ex = (cw / 2 - pad) * math.cos(phi)
        ey = (ch / 2 - pad) * math.sin(phi)
        return cx + ex, cy + ey

    branches = [
        {
            "title": "建筑负荷",
            "body": "原生负荷给定\n不参与柔性调节\n优先保障",
            "pos": (6.0, 5.05),
            "w": 2.55,
            "h": 1.05,
            "angle": 90,
            "anchor_inner": center_anchor(90),
        },
        {
            "title": "电动汽车",
            "body": "到站即充，仅充电不放电\n仅在停留时段可调\n离站须满足目标电量",
            "pos": (9.35, 4.05),
            "w": 2.58,
            "h": 1.22,
            "angle": 28,
            "anchor_inner": center_anchor(28),
        },
        {
            "title": "光伏发电",
            "body": "受可用出力上限约束\n优先本地消纳\n先供建筑与 EV\n剩余：储能 / 上网 / 弃光",
            "pos": (9.05, 1.35),
            "w": 2.72,
            "h": 1.28,
            "angle": -42,
            "anchor_inner": center_anchor(-42),
        },
        {
            "title": "固定储能",
            "body": "不从电网充电\n仅吸收光伏余电充电\n高价且缺电时放电\n受 SOC 与功率约束",
            "pos": (2.95, 1.35),
            "w": 2.72,
            "h": 1.22,
            "angle": -138,
            "anchor_inner": center_anchor(-138),
        },
        {
            "title": "大电网",
            "body": "补足剩余功率缺口\n购电 / 上网分受上限约束\n受限时可记录未满足负荷",
            "pos": (2.65, 4.05),
            "w": 2.58,
            "h": 1.15,
            "angle": 152,
            "anchor_inner": center_anchor(152),
        },
    ]

    for b in branches:
        bx, by = b["pos"]
        bw, bh = b["w"], b["h"]
        phi = math.radians(b["angle"])
        inset = 0.06
        inner_x = bx - (bw / 2 - inset) * math.cos(phi)
        inner_y = by - (bh / 2 - inset) * math.sin(phi)

        _connect(ax, b["anchor_inner"], (inner_x, inner_y), color=line_color, lw=1.45)
        _branch_box(
            ax,
            bx,
            by,
            bw,
            bh,
            b["title"],
            b["body"],
            face_rgba=periph_fill,
        )

    plt.tight_layout(rect=(0, 0, 1, 0.96))

    if save_base is None:
        root = Path(__file__).resolve().parents[3]
        save_base = root / "results" / "figures" / "baseline_mindmap_structure"

    save_base.parent.mkdir(parents=True, exist_ok=True)
    png = save_base.with_suffix(".png")
    svg = save_base.with_suffix(".svg")

    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor=bg, edgecolor="none")
    fig.savefig(svg, bbox_inches="tight", facecolor=bg, edgecolor="none")
    plt.close(fig)
    return png, svg


if __name__ == "__main__":
    p1, p2 = draw()
    print(f"已保存: {p1}\n已保存: {p2}")
