"""
问题一 baseline：单时段能量分配逻辑（论文简洁版插图）。

运行：python single_period_energy_allocation.py
输出：
  - results/figures/single_period_energy_allocation_paper.png（300 dpi）
  - results/figures/single_period_energy_allocation_paper.svg
  - results/figures/single_period_energy_allocation_caption_zh.txt（推荐图注）

图题（正文）：问题一 baseline 单时段能量分配逻辑
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.dpi": 120,
    }
)

# 七色配色（背景 #2472A3C2 与白底 alpha 合成；其余 6 色为不透明填充）
# 映射：C1 光伏可用 | C2 剩余光伏/充储能/储能放电 | C3 弃光、高价判断
#      C4 总需求 | C5 上网、电网购电 | C6 净需求、未满足负荷
C_BG_HEX = "#2472A3C2"
C_1 = "#9DD3AF"
C_2 = "#C0E2CA"
C_3 = "#D1B494"
C_4 = "#D9EEDF"
C_5 = "#E0C79F"
C_6 = "#F1DEBD"

C_TXT = "#243038"
EDGE = "#5d7a8c"
C_TITLE = "#f4f8fb"
C_LBL = "#dfeaf3"
C_ARROW = (0.90, 0.94, 0.99, 0.88)


def _hex_rgba(s: str) -> tuple[float, float, float, float]:
    s = s.strip().lstrip("#")
    if len(s) == 8:
        r, g, b, a = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4, 6))
        return (r, g, b, a)
    r, g, b = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, 1.0)


def _flatten_on_white(rgba: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    r, g, b, a = rgba
    return ((1.0 - a) + a * r, (1.0 - a) + a * g, (1.0 - a) + a * b, 1.0)


def _fc(s: str) -> tuple[float, float, float, float]:
    s = s.strip().lstrip("#")
    if len(s) == 6:
        r, g, b = (int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        return (r, g, b, 1.0)
    return _flatten_on_white(_hex_rgba("#" + s))


BG = _flatten_on_white(_hex_rgba(C_BG_HEX))

# 推荐图注（写入 txt，便于粘贴至论文）
FIGURE_CAPTION_ZH = (
    "图X 问题一 baseline 单时段能量分配逻辑。"
    "左栏为光伏充足情形：光伏优先就地满足总需求（建筑与EV）；"
    "剩余电力按固定次序用于储能充电（仅以光伏余电）、受出口上限约束的上网及弃光；"
    "本情形下储能不因缺电放电，一般无需购电。"
    "右栏为光伏不足情形：就地消纳后形成净需求（储能动作前）；"
    "若处于购电高价时段且净需求大于零，储能在功率与SOC约束内放电削峰；"
    "再以电网购电补足（受进口上限）；若仍不足则记为未满足负荷。"
    "若时段内仍存在就地消纳后的光伏余量，其余电分配次序与左栏一致。"
    "图示为规则驱动次序，非最优化求解。"
)


def _box(ax, cx, cy, w, h, text, *, fc, fs=8.2, bold=False):
    x, y = cx - w / 2, cy - h / 2
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.018,rounding_size=0.07",
            linewidth=1.0,
            edgecolor=EDGE,
            facecolor=fc,
            zorder=2,
        )
    )
    ax.text(
        cx,
        cy,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        fontweight="bold" if bold else "normal",
        color=C_TXT,
        linespacing=1.15,
        zorder=3,
    )


def _arrow(ax, p0, p1, label=None, off=(0, 0), *, rad=0.0):
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.0,
        color=C_ARROW,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
        zorder=1,
    )
    ax.add_patch(arr)
    if label:
        mx = (p0[0] + p1[0]) / 2 + off[0]
        my = (p0[1] + p1[1]) / 2 + off[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=7.0, color=C_LBL, fontweight="bold", zorder=3)


def _panel_frame(ax, subtitle: str):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9.2)
    ax.axis("off")
    ax.set_facecolor(BG)
    ax.text(5.0, 8.85, subtitle, ha="center", va="top", fontsize=10.5, fontweight="bold", color=C_TITLE)


def draw_sufficient(ax):
    """情形一：对称顶行 + 中轴剩余 + 底行三格。"""
    _panel_frame(ax, "情形一：光伏充足")

    y_top = 7.55
    _box(ax, 2.55, y_top, 2.15, 0.72, "光伏可用", fc=_fc(C_1), bold=True)
    _box(ax, 7.45, y_top, 2.15, 0.72, "总需求\n建筑与EV", fc=_fc(C_4))

    _arrow(ax, (3.65, y_top), (6.35, y_top), "① 就地", off=(0, 0.32))

    y_mid = 5.55
    _box(ax, 5.0, y_mid, 2.5, 0.68, "剩余光伏", fc=_fc(C_2))
    _arrow(ax, (5.0, 7.19), (5.0, y_mid + 0.34), None)

    y_bot = 3.35
    w3 = 1.38
    x1, x2, x3 = 2.55, 5.0, 7.45
    _box(ax, x1, y_bot, w3, 0.68, "② 充储能\n光伏余电", fc=_fc(C_2))
    _box(ax, x2, y_bot, w3, 0.68, "③ 上网\n≤出口上限", fc=_fc(C_5))
    _box(ax, x3, y_bot, w3, 0.68, "④ 弃光", fc=_fc(C_3))

    y_sp = 4.42
    _arrow(ax, (5.0, y_mid - 0.34), (5.0, y_sp), None)
    for x in (x1, x2, x3):
        _arrow(ax, (5.0, y_sp), (x, y_sp), None)
        _arrow(ax, (x, y_sp), (x, y_bot + 0.34), None)


def draw_insufficient(ax):
    """情形二：同顶行 + 净需求中轴 + 分支与购电、未满足负荷。"""
    _panel_frame(ax, "情形二：光伏不足")

    y_top = 7.55
    _box(ax, 2.55, y_top, 2.15, 0.72, "光伏可用", fc=_fc(C_1), bold=True)
    _box(ax, 7.45, y_top, 2.15, 0.72, "总需求\n建筑与EV", fc=_fc(C_4))

    _arrow(ax, (3.65, y_top), (6.35, y_top), "① 就地", off=(0, 0.32))

    y_mid = 5.55
    _box(ax, 5.0, y_mid, 2.55, 0.68, "净需求\n（储能前）", fc=_fc(C_6))
    _arrow(ax, (5.0, 7.19), (5.0, y_mid + 0.34), None)

    y_j = 4.35
    _box(ax, 2.55, y_j, 2.05, 0.66, "② 高价？\n净需求>0", fc=_fc(C_3))
    # 净需求 → 判断
    _arrow(ax, (5.0, y_mid - 0.34), (5.0, 4.92), None)
    _arrow(ax, (5.0, 4.92), (3.58, 4.68), None, rad=-0.06)

    y_e = 3.25
    _box(ax, 2.55, y_e, 2.05, 0.58, "储能放电", fc=_fc(C_2))
    _arrow(ax, (2.55, y_j - 0.33), (2.55, y_e + 0.29), "是", off=(-0.38, 0))
    _arrow(ax, (3.58, y_j), (5.0, y_j), "否", off=(0, 0.28))

    y_g = 2.35
    _box(ax, 5.0, y_g, 2.5, 0.66, "③ 电网购电\n≤进口上限", fc=_fc(C_5))
    # 否：自 (5, y_j) 下至购电；是：储能放电后汇入购电上沿
    _arrow(ax, (5.0, y_j - 0.08), (5.0, y_g + 0.33), None)
    _arrow(ax, (2.55, y_e - 0.29), (5.0, y_g + 0.33), None, rad=0.12)

    y_u = 1.2
    _box(ax, 5.0, y_u, 2.5, 0.58, "④ 未满足负荷", fc=_fc(C_6))
    _arrow(ax, (5.0, y_g - 0.33), (5.0, y_u + 0.29), None)


def write_caption(path: Path) -> None:
    path.write_text(FIGURE_CAPTION_ZH + "\n", encoding="utf-8")


def draw_paper(out_dir: Path | None = None) -> tuple[Path, Path, Path]:
    if out_dir is None:
        root = Path(__file__).resolve().parents[3]
        out_dir = root / "results" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    base = out_dir / "single_period_energy_allocation_paper"
    cap_path = out_dir / "single_period_energy_allocation_caption_zh.txt"

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.85))
    fig.patch.set_facecolor(BG)

    fig.suptitle(
        "问题一 baseline 单时段能量分配逻辑",
        fontsize=12.5,
        fontweight="bold",
        color=C_TITLE,
        y=0.97,
    )

    draw_sufficient(ax1)
    draw_insufficient(ax2)

    plt.subplots_adjust(left=0.04, right=0.96, top=0.86, bottom=0.06, wspace=0.16)

    png = base.with_suffix(".png")
    svg = base.with_suffix(".svg")
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor=BG, edgecolor="none")
    fig.savefig(svg, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)

    write_caption(cap_path)
    return png, svg, cap_path


if __name__ == "__main__":
    p1, p2, p3 = draw_paper()
    print(f"已保存: {p1}\n已保存: {p2}\n图注: {p3}")
