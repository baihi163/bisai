"""
问题一 baseline：非协同调度逻辑示意图（论文用，无程序循环细节）。

生成简洁版与详细版，各输出 PNG（300 dpi）与 SVG。

运行：python baseline_dispatch_logic_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 120,
    }
)

# 背景 = 蓝；流程矩形（四周步骤框）= 米白；判断菱形 = 橄榄绿
COLOR_BG = "#2472A3C2"
COLOR_PROCESS = "#F4F3EEC2"
COLOR_DECISION = "#A5B55DC2"


def _hex8_rgba(s: str) -> tuple[float, float, float, float]:
    s = s.strip().lstrip("#")
    r, g, b, a = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4, 6))
    return (r, g, b, a)


def _flatten_on_white(rgba: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    return ((1.0 - a) + a * r, (1.0 - a) + a * g, (1.0 - a) + a * b, 1.0)


def _darken(rgba: tuple[float, float, float, float], factor: float = 0.55) -> tuple[float, float, float, float]:
    r, g, b, _ = rgba
    return (r * factor, g * factor, b * factor, 1.0)


def _box(
    ax,
    cx,
    cy,
    w,
    h,
    line1: str,
    line2: str | None,
    fs1: float,
    fs2: float,
    fc2: str,
    *,
    face: tuple[float, float, float, float],
    edge: tuple[float, float, float, float],
):
    x, y = cx - w / 2, cy - h / 2
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.015,rounding_size=0.07",
        linewidth=1.05,
        edgecolor=edge,
        facecolor=face,
        zorder=2,
    )
    ax.add_patch(p)
    if line2:
        ax.text(cx, cy + 0.06, line1, ha="center", va="center", fontsize=fs1, color="#0c1f2e", zorder=3)
        ax.text(cx, cy - 0.14, line2, ha="center", va="center", fontsize=fs2, color=fc2, linespacing=1.2, zorder=3)
    else:
        ax.text(
            cx,
            cy,
            line1,
            ha="center",
            va="center",
            fontsize=fs1,
            color="#0c1f2e",
            linespacing=1.15,
            zorder=3,
        )


def _diamond(
    ax,
    cx,
    cy,
    w,
    h,
    text: str,
    fs: float,
    *,
    face: tuple[float, float, float, float],
    edge: tuple[float, float, float, float],
):
    pts = np.array(
        [
            [cx, cy + h / 2],
            [cx + w / 2, cy],
            [cx, cy - h / 2],
            [cx - w / 2, cy],
        ]
    )
    p = Polygon(pts, closed=True, linewidth=1.1, edgecolor=edge, facecolor=face, zorder=2)
    ax.add_patch(p)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color="#1e2410", linespacing=1.1, zorder=3)


def _arrow(ax, p0, p1, rad=0.0, *, color: tuple[float, float, float, float] | str):
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=9,
        linewidth=1.05,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
        zorder=2,
    )
    ax.add_patch(arr)


def _merge_dot(ax, xy, r=0.06, *, color: tuple[float, float, float, float]):
    ax.add_patch(Circle(xy, r, facecolor=color, edgecolor=color, zorder=3))


def draw_one(
    ax,
    *,
    detailed: bool,
    title: str = "问题一 baseline 非协同调度逻辑示意图",
) -> tuple[float, float, float, float]:
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 4.05)
    ax.axis("off")

    bg = _flatten_on_white(_hex8_rgba(COLOR_BG))
    proc = _flatten_on_white(_hex8_rgba(COLOR_PROCESS))
    dec = _flatten_on_white(_hex8_rgba(COLOR_DECISION))
    edge_p = _darken(proc, 0.52)
    edge_d = _darken(dec, 0.52)
    # 蓝底上箭头、汇合点用浅色
    arr_c = (0.86, 0.92, 0.98, 0.9)
    merge_col = (0.78, 0.88, 0.96, 1.0)
    ax.set_facecolor(bg)

    ax.text(6.6, 3.78, title, ha="center", va="center", fontsize=13.5, fontweight="bold", color="#f7f8fa", zorder=3)
    sub = (
        "单时间步内固定次序执行（规则驱动，非最优化求解）"
        if not detailed
        else "示意单时间步内的信息更新顺序；多时段运行即重复应用本逻辑链"
    )
    ax.text(
        6.6,
        3.48,
        sub,
        ha="center",
        va="center",
        fontsize=8.1,
        color="#d6e8f2",
        style="italic" if not detailed else "normal",
        zorder=3,
    )

    y1 = 2.72 if detailed else 2.78
    h1 = 0.62 if detailed else 0.5
    fs1 = 8.4 if detailed else 8.9
    fs2 = 6.9
    fc2 = "#2c3d4d"

    # 上排：主线（横向）
    specs_row1 = [
        ("读取输入与状态", "外生序列与上步末状态" if detailed else None, 1.38),
        ("EV 规则充电", "到站即充；无 V2B" if detailed else None, 1.22),
        ("形成总需求", "原生负荷 + EV 充电" if detailed else None, 1.22),
        ("光伏优先就地消纳", "供建筑与 EV；得净需求" if detailed else None, 1.52),
        ("净需求（储能前）", None, 1.15),
    ]
    x0 = 0.72
    gap = 0.26
    cx = x0
    centers_r1 = []
    for line1, line2, w in specs_row1:
        centers_r1.append(cx + w / 2)
        cx += w + gap
    # 重算使整行居中略偏：已从左开始排布
    for i, (line1, line2, w) in enumerate(specs_row1):
        cxi = centers_r1[i]
        _box(ax, cxi, y1, w, h1, line1, line2, fs1, fs2, fc2, face=proc, edge=edge_p)
    for i in range(len(centers_r1) - 1):
        w_i = specs_row1[i][2]
        w_next = specs_row1[i + 1][2]
        x0a = centers_r1[i] + w_i / 2 + 0.02
        x1a = centers_r1[i + 1] - w_next / 2 - 0.02
        _arrow(ax, (x0a, y1), (x1a, y1), color=arr_c)

    last_c = centers_r1[-1]

    # 菱形判断
    y_d = 1.72 if detailed else 1.78
    d_w, d_h = (1.35, 0.78) if detailed else (1.2, 0.68)
    d_cx = last_c
    _arrow(ax, (last_c, y1 - h1 / 2 - 0.03), (d_cx, y_d + d_h / 2 + 0.02), color=arr_c)

    d_txt = "购电高价区间？\n且净需求>0？" if detailed else "高价且\n净需求>0？"
    d_fs = 7.8 if detailed else 8.2
    _diamond(ax, d_cx, y_d, d_w, d_h, d_txt, d_fs, face=dec, edge=edge_d)

    # 左侧：储能放电；下方汇合
    ess_w = 1.25 if detailed else 1.12
    ess_h = 0.52 if detailed else 0.44
    ess_cx = d_cx - 1.55
    ess_cy = y_d
    ess_l1 = "储能放电削峰"
    ess_l2 = "功率与 SOC 约束内" if detailed else None
    _box(ax, ess_cx, ess_cy, ess_w, ess_h, ess_l1, ess_l2, fs1 - 0.3, fs2, fc2, face=proc, edge=edge_p)

    m_x, m_y = d_cx, y_d - d_h / 2 - 0.38
    _merge_dot(ax, (m_x, m_y), color=merge_col)

    _arrow(ax, (d_cx - d_w / 2 - 0.02, y_d), (ess_cx + ess_w / 2 + 0.02, ess_cy), rad=0, color=arr_c)
    ax.text(d_cx - d_w / 2 - 0.35, y_d + 0.08, "是", fontsize=7.5, color="#f0f7fc", zorder=3)

    _arrow(ax, (d_cx, y_d - d_h / 2 - 0.02), (m_x, m_y + 0.07), rad=0, color=arr_c)
    ax.text(d_cx + 0.32, y_d - d_h / 2 - 0.2, "否", fontsize=7.5, color="#f0f7fc", zorder=3)

    _arrow(ax, (ess_cx, ess_cy - ess_h / 2 - 0.02), (m_x, m_y + 0.08), rad=0.08, color=arr_c)

    # 下排：购电—未满足—余光伏—更新
    y2 = 0.78
    h2 = 0.58 if detailed else 0.48
    if detailed:
        row2 = [
            ("电网补足缺口", "受进口功率上限", 1.28),
            ("仍不足则记录未满足", "功率/电量缺口", 1.45),
            ("剩余光伏分配", "储能充电→上网→弃光", 1.42),
            ("更新状态", "储能、EV 能量等", 1.12),
        ]
    else:
        row2 = [
            ("电网补足缺口", None, 1.22),
            ("仍不足则记录未满足", None, 1.32),
            ("剩余光伏分配", "充储能→上网→弃光", 1.32),
            ("更新状态", None, 1.08),
        ]

    gap2 = 0.24
    total_w = sum(w for _, _, w in row2) + gap2 * (len(row2) - 1)
    left = m_x - total_w / 2
    centers_r2 = []
    x_edge = left
    for _, _, w in row2:
        centers_r2.append(x_edge + w / 2)
        x_edge += w + gap2

    _arrow(ax, (m_x, m_y - 0.08), (centers_r2[0], y2 + h2 / 2 + 0.02), rad=0, color=arr_c)

    for i, (line1, line2, w) in enumerate(row2):
        _box(ax, centers_r2[i], y2, w, h2, line1, line2, fs1 - 0.2, fs2, fc2, face=proc, edge=edge_p)
    for i in range(len(centers_r2) - 1):
        w_i = row2[i][2]
        w_n = row2[i + 1][2]
        _arrow(
            ax,
            (centers_r2[i] + w_i / 2 + 0.02, y2),
            (centers_r2[i + 1] - w_n / 2 - 0.02, y2),
            color=arr_c,
        )

    return bg


def save_all(out_dir: Path | None = None) -> dict[str, Path]:
    if out_dir is None:
        root = Path(__file__).resolve().parents[3]
        out_dir = root / "results" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    for name, detailed in [("compact", False), ("detailed", True)]:
        fig, ax = plt.subplots(figsize=(13.0, 3.95 if detailed else 3.65))
        bg = draw_one(ax, detailed=detailed)
        fig.patch.set_facecolor(bg)
        plt.tight_layout(rect=(0, 0, 1, 0.97))

        base = out_dir / f"baseline_dispatch_logic_{name}"
        for ext, kw in [("png", {"dpi": 300}), ("svg", {})]:
            p = base.with_suffix(f".{ext}")
            fig.savefig(p, bbox_inches="tight", facecolor=bg, edgecolor="none", **kw)
            paths[f"{name}_{ext}"] = p
        plt.close(fig)

    return paths


if __name__ == "__main__":
    saved = save_all()
    for k, v in saved.items():
        print(f"{k}: {v}")
