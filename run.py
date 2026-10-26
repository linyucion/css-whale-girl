#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run.py —— 一条命令跑完整条管线（从仓库根目录）

## 为什么需要这个

原来的跑法是一串环境变量 + 手写路径：

    $env:TAG="ai2"; $env:CWG_DATA="..."; python src/trace.py
    ...

`trace.py` 甚至没有 `__main__` 和命令行参数，靠 `REF` 环境变量指参考图。
别人 clone 下来要么跑不起来，要么得先读懂五个脚本。

## 真实的三步（不是四步）

一开始我以为 trace → inkfix → residual 是串行链。**读代码后发现不是：**

`inkfix.py` 会**自己重新跑一遍描轮廓**（它直接打开参考图，
不读 trace 的产物），只是额外把深色描边单独提成一层。

所以 `trace.py` 和 `inkfix.py` 是**二选一**：

    有描边层   inkfix.py  -> layers_ai3.json    约 145 秒
    不描边层   trace.py   -> layers_ai2.json    约 83 秒

然后都接 `residual.py` -> `layers_res3.json`，再 `build_site.py` -> HTML。

不搞清这一点，串起来跑会白白多花 83 秒，而且中间文件名对不上。

## 用法

    python run.py                     # 完整跑（含描边和残差）
    python run.py --skip-ink          # 不做描边层，快一些
    python run.py --skip-residual     # 不做残差补偿，更快但细节会丢
    python run.py --out art/x.html    # 换输出位置

## 为什么中间文件放 data/

`data/` 在 .gitignore 里 —— 中间产物（几 MB 的 JSON）不该进仓库。
每次跑都会重新生成。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"


def call(script: str, argv: list[str], env: dict, label: str) -> dict:
    """跑一个子脚本，返回 {'ok': bool, 'stdout': str, 'sec': float}。"""
    print(f"  [{label}] {script} …", end="", flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(SRC / script), *argv], env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    sec = time.time() - t0
    if r.returncode != 0:
        print(f" 失败（{sec:.0f}s）")
        if r.stdout:
            print(r.stdout[-1500:])
        if r.stderr:
            print(r.stderr[-2500:])
    else:
        tail = (r.stdout or "").strip().splitlines()
        print(f" {sec:.0f}s  {tail[-1][:60] if tail else 'ok'}")
    return {"ok": r.returncode == 0, "stdout": r.stdout or "", "sec": sec}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从参考图跑出单文件 HTML（零图片 / 零 SVG / 零 JS）")
    ap.add_argument("--ref", default=str(ROOT / "docs" / "reference.png"),
                    help="参考图路径（默认 docs/reference.png）")
    ap.add_argument("--out", default=str(ROOT / "art" / "css-whale-girl.html"),
                    help="输出 HTML 路径")
    ap.add_argument("--workdir", default=str(ROOT / "data"),
                    help="中间文件目录（默认 data/，被 .gitignore 忽略）")
    ap.add_argument("--k", type=int, default=None,
                    help="K-means 色数（默认读环境变量 K，否则 40）")
    ap.add_argument("--skip-ink", action="store_true",
                    help="不做描边层（快约 60 秒，但边缘会糊）")
    ap.add_argument("--skip-residual", action="store_true",
                    help="不做残差补偿（快，但嘴巴/眼高光/蕾丝会丢）")
    ap.add_argument("--noblink", action="store_true",
                    help="关掉眨眼（主站 whale.chu-2.moe 用的就是无眨眼版）")
    args = ap.parse_args()

    ref = pathlib.Path(args.ref).resolve()
    out = pathlib.Path(args.out).resolve()
    wd = pathlib.Path(args.workdir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not ref.exists():
        print(f"  ✗ 参考图不存在：{ref}", file=sys.stderr)
        print("    仓库自带的是 docs/reference.png", file=sys.stderr)
        return 2

    print(f"  参考图   {ref}")
    print(f"  输出     {out}")
    print(f"  中间文件 {wd}")
    print()

    env = {**os.environ, "CWG_DATA": str(wd), "REF": str(ref)}
    if args.k is not None:
        env["K"] = str(args.k)
    t_all = time.time()

    # ── ① 描轮廓（二选一）──────────────────────────────
    if args.skip_ink:
        r = call("trace.py", [], {**env, "TAG": "ai2"}, "1/3 描轮廓")
        if not r["ok"]:
            return 1
        cur = wd / "layers_ai2.json"
    else:
        r = call("inkfix.py", [], {**env, "TAG": "ai3"}, "1/3 描轮廓+描边")
        if not r["ok"]:
            return 1
        cur = wd / "layers_ai3.json"

    if not cur.exists():
        print(f"  ✗ 预期产物不存在：{cur.name}", file=sys.stderr)
        return 1

    # ── ② 残差补偿 ────────────────────────────────────
    if args.skip_residual:
        print("  [2/3 残差层] 跳过")
        final_json = cur
    else:
        nxt = wd / "layers_res3.json"
        r = call("residual.py", [str(cur), str(nxt)], env, "2/3 残差层")
        if not r["ok"]:
            return 1
        final_json = nxt

    # ── ③ 生成 HTML ───────────────────────────────────
    argv = [str(final_json), str(out),
            "鲸鱼娘 · 纯 HTML/CSS 手绘",
            "纯 CSS 绘制的鲸鱼娘插画：7348 个 clip-path 多边形，"
            "零 SVG / img / canvas / script。"]
    if args.noblink:
        argv.append("noblink")
    r = call("build_site.py", argv, env, "3/3 生成")
    if not r["ok"]:
        return 1

    print()
    print(f"  ✅ 完成，总耗时 {time.time()-t_all:.0f}s")
    print(f"     {out}")
    print(f"     {out.stat().st_size/1024/1024:.2f} MB —— 双击就能打开，零外部依赖")
    print()
    print(f"  想验证误差：python measure/remeasure_mae.py --ref {ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
