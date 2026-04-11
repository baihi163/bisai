# -*- coding: utf-8 -*-
"""
问题2 权重扫描结果作图

默认输入（按修改时间取最新一份，自上而下搜索）：
  1) results/tables/problem2_weight_scan_*.csv   （与全仓 tables 习惯一致，由主求解脚本同步写入）
  2) results/problem2_lifecycle/tables/weight_scan_summary_*.csv
  3) results/problem2_lifecycle/scans/**/weight_scan_summary.csv

默认输出：
  results/figures/problem2/problem2_weight_pareto.png
  results/figures/problem2/problem2_weight_throughput_stack.png

用法示例：
  python plot_p2_results.py
  python plot_p2_results.py results/tables/problem2_weight_scan_myrun.csv
  python plot_p2_results.py -i results/tables/problem2_weight_scan_myrun.csv -o results/figures/problem2 --tag myrun
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parents[2]


def _iter_candidate_scan_csvs(repo: Path) -> list[Path]:
    """所有可能存放权重汇总表的路径（不含子目录递归外的遗漏）。"""
    out: list[Path] = []
    p1 = repo / "results" / "tables"
    if p1.is_dir():
        out.extend(p1.glob("problem2_weight_scan_*.csv"))
    p2 = repo / "results" / "problem2_lifecycle" / "tables"
    if p2.is_dir():
        out.extend(p2.glob("weight_scan_summary_*.csv"))
    scans = repo / "results" / "problem2_lifecycle" / "scans"
    if scans.is_dir():
        out.extend(scans.glob("**/weight_scan_summary.csv"))
    return out


def pick_latest_scan_csv(repo: Path) -> Path | None:
    files = _iter_candidate_scan_csvs(repo)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def plot_results(
    csv_path: Path,
    *,
    out_dir: Path,
    pareto_name: str,
    stack_name: str,
) -> int:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    if not csv_path.is_file():
        print(f"未找到 CSV: {csv_path}", file=sys.stderr)
        return 1

    print(f"读取: {csv_path}")
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    if "operation_cost" not in df.columns:
        print("CSV 缺少 operation_cost 列。", file=sys.stderr)
        return 1

    df = df.dropna(subset=["operation_cost"]).copy()
    if df.empty:
        print("无有效数据行。", file=sys.stderr)
        return 1

    if "ess_deg_weight" in df.columns:
        df = df.sort_values("ess_deg_weight", kind="mergesort")

    ess_col = "ess_throughput" if "ess_throughput" in df.columns else "ess_throughput_kwh"
    ev_col = "ev_throughput" if "ev_throughput" in df.columns else "ev_throughput_kwh"
    if ess_col not in df.columns or ev_col not in df.columns:
        print(f"缺少吞吐列。列名: {list(df.columns)}", file=sys.stderr)
        return 1

    df["total_throughput"] = df[ess_col].astype(float) + df[ev_col].astype(float)

    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 图1 ----------
    fig1, ax1 = plt.subplots(figsize=(9, 6))
    color1 = "#D62728"
    ax1.set_xlabel(
        "运行成本（元）\n(operation_cost = 购电 − 售电 + 碳 + 弃光惩罚 + 柔性惩罚)",
        fontsize=11,
    )
    ax1.set_ylabel("系统总吞吐量 (kWh)\n(ESS+EV，半周转口径)", color=color1, fontsize=11)
    ax1.plot(
        df["operation_cost"],
        df["total_throughput"],
        marker="o",
        markersize=8,
        color=color1,
        linewidth=2,
        label="总吞吐量",
    )
    ax1.tick_params(axis="y", labelcolor=color1)

    wcol = "ess_deg_weight" if "ess_deg_weight" in df.columns else None
    if wcol:
        for _, row in df.iterrows():
            ax1.annotate(
                f"w={row[wcol]}",
                (float(row["operation_cost"]), float(row["total_throughput"])),
                textcoords="offset points",
                xytext=(8, 4),
                ha="left",
                fontsize=9,
            )

    oc = df["operation_cost"].astype(float)
    if oc.max() - oc.min() < 1e-3 * max(1.0, abs(oc.mean())):
        fig1.text(
            0.5,
            0.02,
            "提示：各权重下运行成本几乎相同，曲线近似竖线；可加长 horizon 或调碳价/权重维度。",
            ha="center",
            fontsize=9,
            style="italic",
            transform=fig1.transFigure,
        )

    ax1.set_title("问题2：运行成本与电池总吞吐量（权重扫描）", fontsize=13)
    ax1.grid(True, linestyle="--", alpha=0.5)
    fig1.tight_layout()
    p1 = out_dir / pareto_name
    fig1.savefig(p1, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig1)
    print(f"写出: {p1}")

    # ---------- 图2 ----------
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    weights = df[wcol].astype(float) if wcol else pd.RangeIndex(len(df))
    x_labels = [f"{w:g}" for w in weights] if wcol else [str(i) for i in range(len(df))]
    x = range(len(df))
    bar_w = 0.55
    essv = df[ess_col].astype(float).to_numpy()
    evv = df[ev_col].astype(float).to_numpy()
    ax2.bar(x, essv, bar_w, label="ESS 吞吐量", color="#1F77B4", alpha=0.85)
    ax2.bar(x, evv, bar_w, bottom=essv, label="EV 吞吐量", color="#FF7F0E", alpha=0.85)
    ax2.set_xticks(list(x), x_labels, rotation=0)
    ax2.set_xlabel("退化成本权重 w（对角扫描：ESS 与 EV 同权）", fontsize=11)
    ax2.set_ylabel("吞吐量 (kWh)", fontsize=11)
    ax2.set_title("问题2：ESS / EV 吞吐量分工", fontsize=13)
    ax2.legend()
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    fig2.tight_layout()
    p2 = out_dir / stack_name
    fig2.savefig(p2, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig2)
    print(f"写出: {p2}")

    return 0


def main(argv: list[str] | None = None) -> int:
    repo = _repo_root()
    default_fig = repo / "results" / "figures" / "problem2"

    parser = argparse.ArgumentParser(
        description="问题2 权重扫描作图（默认读 results/tables 或 lifecycle 下最新汇总表，写到 results/figures/problem2）",
    )
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=None,
        help="权重汇总 CSV 路径（可省略，则自动选最新候选文件）",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=None,
        help="同 positional，显式指定输入（优先于 positional）",
    )
    parser.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="图输出根目录，默认: results/figures/problem2",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="子目录名：存在时图保存到 <out-dir>/<tag>/ 下，避免覆盖其它实验",
    )
    args = parser.parse_args(argv)

    csv_in = args.input if args.input is not None else args.csv
    if csv_in is not None:
        csv_path = csv_in.expanduser().resolve()
        if not csv_path.is_file():
            print(f"文件不存在: {csv_path}", file=sys.stderr)
            return 1
    else:
        csv_path = pick_latest_scan_csv(repo)
        if csv_path is None:
            print(
                "未找到任何权重汇总 CSV。请先运行权重扫描，或手动指定文件，例如:\n"
                f"  python {Path(__file__).name} results/tables/problem2_weight_scan_<run_tag>.csv",
                file=sys.stderr,
            )
            return 1
        print(f"自动选用（最新修改时间）: {csv_path}")

    out_base = (args.out_dir.expanduser().resolve() if args.out_dir else default_fig)
    if args.tag:
        out_dir = out_base / args.tag.strip().replace(" ", "_")
    else:
        out_dir = out_base

    pareto_name = "problem2_weight_pareto.png"
    stack_name = "problem2_weight_throughput_stack.png"

    return plot_results(csv_path, out_dir=out_dir, pareto_name=pareto_name, stack_name=stack_name)


if __name__ == "__main__":
    raise SystemExit(main())
