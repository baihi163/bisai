"""
问题一 baseline：单时段状态更新与时序递推关系（论文简洁版）。

运行：python baseline_state_timestep_recurrence.py
输出：
  - results/figures/baseline_state_timestep_recurrence.png（300 dpi）
  - results/figures/baseline_state_timestep_recurrence.svg
  - results/figures/baseline_state_timestep_recurrence_caption_zh.txt（推荐图注）
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

EDGE = "#5c6b7a"
C_IN = "#d9e8f0"
C_PROC = "#eef0ec"
C_STEP = "#f7f8f6"
C_OUT = "#f0e8dc"
C_TXT = "#243038"
C_SUB = "#3d4d5c"
C_DASH = "#8a9aa8"

FIGURE_CAPTION_ZH = (
    "图X 问题一 baseline 单时段状态更新与时序递推关系。"
    "左栏为时段 t 的外生量与状态量；中栏为按固定次序执行的 baseline 单步调度；"
    "右栏为时段末储能能量与各停留车辆电量。"
    "虚线表示将时段末状态作为下一时段初始状态，形成时序递推。"
)


def _frame(ax, xy, w, h, *, fc):
    x, y = xy
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=1.0,
            edgecolor=EDGE,
            facecolor=fc,
            zorder=2,
        )
    )


def _txt(ax, x, y, s, *, fs=8.0, bold=False, color=None):
    ax.text(
        x,
        y,
        s,
        ha="center",
        va="center",
        fontsize=fs,
        fontweight="bold" if bold else "normal",
        color=color or C_TXT,
        linespacing=1.15,
        zorder=3,
    )


def _arrow(ax, p0, p1, *, dashed=False, rad=0.0):
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=9,
        linewidth=1.0,
        color=C_DASH if dashed else EDGE,
        linestyle="--" if dashed else "-",
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=2,
        shrinkB=2,
        zorder=1,
    )
    ax.add_patch(arr)


def _step_box(ax, cx, cy, w, h, text):
    x, y = cx - w / 2, cy - h / 2
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.012,rounding_size=0.05",
            linewidth=0.85,
            edgecolor=EDGE,
            facecolor=C_STEP,
            zorder=3,
        )
    )
    ax.text(cx, cy, text, ha="center", va="center", fontsize=6.7, color=C_SUB, linespacing=1.08, zorder=4)


def _harrow(ax, x0, x1, y):
    _arrow(ax, (x0, y), (x1, y))


def draw(ax):
    ax.set_xlim(0, 12.6)
    ax.set_ylim(-0.45, 4.35)
    ax.axis("off")
    ax.set_facecolor("#fafbfc")

    y0, h = 0.62, 2.95
    w1, w2, w3 = 2.95, 5.45, 2.95
    gap = 0.32
    x1 = 0.45
    x2 = x1 + w1 + gap
    x3 = x2 + w2 + gap

    # —— 左：外生量 / 状态量 ——
    _frame(ax, (x1, y0), w1, h, fc=C_IN)
    _txt(ax, x1 + w1 / 2, y0 + h - 0.32, "时段 t · 输入", fs=9.0, bold=True)
    _txt(
        ax,
        x1 + w1 / 2,
        y0 + h - 0.78,
        "外生量\n电价 · 限额 · 负荷 · 光伏上限 …",
        fs=7.2,
        color=C_SUB,
    )
    _txt(
        ax,
        x1 + w1 / 2,
        y0 + h - 1.55,
        "状态量\n" + r"$E_{\mathrm{ESS}}(t)$" + "，" + r"$E_{\mathrm{EV}}^k(t)$",
        fs=7.2,
        color=C_SUB,
    )

    # —— 中：单步调度链 ——
    _frame(ax, (x2, y0), w2, h, fc=C_PROC)
    _txt(ax, x2 + w2 / 2, y0 + h - 0.32, "baseline 单步调度", fs=9.0, bold=True)

    bw, bh = 1.38, 0.42
    y_row1 = y0 + h - 1.15
    y_row2 = y0 + h - 2.05
    xs1 = [x2 + 0.55 + i * (bw + 0.28) for i in range(3)]
    xs2 = [x2 + 0.55 + i * (bw + 0.28) for i in range(3)]

    labels_r1 = ["EV规则充电", "总需求形成", "光伏优先消纳"]
    labels_r2 = ["储能条件响应", "电网补足缺口", "余电顺序分配"]
    for cx, lab in zip(xs1, labels_r1):
        _step_box(ax, cx, y_row1, bw, bh, lab)
    for cx, lab in zip(xs2, labels_r2):
        _step_box(ax, cx, y_row2, bw, bh, lab)

    for i in range(2):
        _harrow(ax, xs1[i] + bw / 2 + 0.04, xs1[i + 1] - bw / 2 - 0.04, y_row1)
    for i in range(2):
        _harrow(ax, xs2[i] + bw / 2 + 0.04, xs2[i + 1] - bw / 2 - 0.04, y_row2)

    # 上行末 → 下行首
    _arrow(ax, (xs1[2], y_row1 - bh / 2 - 0.02), (xs2[0], y_row2 + bh / 2 + 0.02))

    # —— 右：时段末状态 ——
    _frame(ax, (x3, y0), w3, h, fc=C_OUT)
    _txt(ax, x3 + w3 / 2, y0 + h - 0.32, r"时段末状态 $(t+\Delta t)$", fs=9.0, bold=True)
    _txt(ax, x3 + w3 / 2, y0 + h - 1.05, r"$E_{\mathrm{ESS}}(t+\Delta t)$", fs=8.2, color=C_SUB)
    _txt(ax, x3 + w3 / 2, y0 + h - 1.75, r"$E_{\mathrm{EV}}^k(t+\Delta t)$", fs=8.2, color=C_SUB)

    mid_y = y0 + h / 2
    _arrow(ax, (x1 + w1, mid_y), (x2 - 0.02, mid_y))
    _arrow(ax, (x2 + w2, mid_y), (x3 - 0.02, mid_y))

    # 底部虚线回传（单箭示意：右下 → 左下）
    yb = y0 + 0.08
    xc_r = x3 + w3 / 2
    xc_l = x1 + w1 / 2
    y_arc = y0 - 0.22
    _arrow(ax, (xc_r, y0), (xc_r, y_arc), dashed=True)
    _arrow(ax, (xc_r, y_arc), (xc_l, y_arc), dashed=True)
    _arrow(ax, (xc_l, y_arc), (xc_l, y0), dashed=True)
    _txt(ax, (xc_l + xc_r) / 2, y_arc - 0.12, "作为下一时段初始状态", fs=7.1, color=C_SUB, bold=False)


def write_caption(path: Path) -> None:
    path.write_text(FIGURE_CAPTION_ZH + "\n", encoding="utf-8")


def main() -> tuple[Path, Path, Path]:
    fig, ax = plt.subplots(figsize=(12.4, 3.45))
    fig.patch.set_facecolor("#fafbfc")

    fig.suptitle(
        "问题一 baseline：单时段状态更新与时序递推关系",
        fontsize=11.8,
        fontweight="bold",
        color=C_TXT,
        y=0.97,
    )

    draw(ax)
    plt.subplots_adjust(left=0.03, right=0.97, top=0.88, bottom=0.12)

    root = Path(__file__).resolve().parents[3]
    out_dir = root / "results" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / "baseline_state_timestep_recurrence"
    cap = out_dir / "baseline_state_timestep_recurrence_caption_zh.txt"

    png = base.with_suffix(".png")
    svg = base.with_suffix(".svg")
    fc = "#fafbfc"
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor=fc, edgecolor="none")
    fig.savefig(svg, bbox_inches="tight", facecolor=fc, edgecolor="none")
    plt.close(fig)

    write_caption(cap)
    return png, svg, cap


if __name__ == "__main__":
    p1, p2, p3 = main()
    print(f"已保存: {p1}\n已保存: {p2}\n图注: {p3}")
