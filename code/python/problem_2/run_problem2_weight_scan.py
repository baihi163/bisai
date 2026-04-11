#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量权重实验：调用问题2生命周期主脚本的对角线权重扫描（--scan-weights）。

用法:
  python run_problem2_weight_scan.py
  python run_problem2_weight_scan.py 0 0.25 0.5 1 2 4
  python run_problem2_weight_scan.py 0 0.5 1 -- --carbon-price 0.05 --run-tag myexp

在 `--` 之后的主脚本参数会原样转发。若未传 `--run-tag`，包装脚本会自动加 `--run-tag auto_weight_scan`。

全周期 5 点扫描可能较久，可加 `-- --max-periods 672 --time-limit 600` 等控制。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        extra = argv[i + 1 :]
        argv = argv[:i]

    weights = argv if argv else ["0", "0.5", "1.0", "2.0"]

    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    main_script = here / "p_2_lifecycle_coordinated.py.code.py"
    if not main_script.is_file():
        print(f"未找到主脚本: {main_script}", file=sys.stderr)
        return 1

    cmd: list[str] = [sys.executable, str(main_script), "--scan-weights", *[str(w) for w in weights]]
    # 避免与用户在 `--` 后传入的 `--run-tag` 重复；仅未指定时使用默认标签
    if not any(a == "--run-tag" for a in extra):
        cmd.extend(["--run-tag", "auto_weight_scan"])
    cmd.extend(extra)
    print("执行:", " ".join(cmd), flush=True)
    return int(subprocess.call(cmd, cwd=str(repo)))


if __name__ == "__main__":
    raise SystemExit(main())
