# -*- coding: utf-8 -*-
"""remeasure_mae.py —— 可复现的逐像素误差测量

## 为什么这个脚本单独存在

这个项目有两天浪费在**测量脚本本身是错的**：

1. `Image.transform` 参数写反  -> MAE 虚高到 105
2. 参考图白底、渲染图深底      -> 虚高到 147
3. 页面 100% 宽再缩回目标尺寸  -> 缩放模糊被算进「绘制误差」

修完之后口径才固定下来，也就是这个脚本做的事：

    页面设成参考图的原生尺寸（743×1095），角色 1:1 铺满、不做任何缩放，
    截完图直接逐像素比。

**改管线之前先跑它拿到基线，改完再跑一次。**
不要凭肉眼判断好坏 —— 肉眼几乎看不出差别的十二张图，
当时的坏尺子说它们差了 2.8 倍。

## 用法

    python measure/remeasure_mae.py --ref 参考图.png
    python measure/remeasure_mae.py --ref 参考图.png --art art/css-whale-girl.html
    python measure/remeasure_mae.py --ref 参考图.png --json out.json   # CI 用

参考图不在本仓库内（版权原因）。如果你要复现，需要自己准备一张
743×1095 的参考图，或者用 `--crop` 从更大的图里裁。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
MW, MH = 743, 1095


def find_chrome() -> str | None:
    """找一个可用的 Chrome / Chromium。"""
    env = os.environ.get("CHROME")
    if env and pathlib.Path(env).exists():
        return env
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if pathlib.Path(c).exists():
            return c
    return shutil.which("google-chrome") or shutil.which("chromium")


def prepare_reference(src: pathlib.Path, out: pathlib.Path) -> Image.Image:
    """裁掉参考图四周的留白，凑成 743×1095。"""
    im = Image.open(src).convert("RGB")
    a = np.asarray(im)
    mask = ~((a[:, :, 0] > 245) & (a[:, :, 1] > 245) & (a[:, :, 2] > 245))
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise SystemExit("参考图看起来是全白的 —— 检查一下是不是传错了")

    x0 = max(0, int(xs.min()) - 3)
    y0 = max(0, int(ys.min()) - 2)
    x0 = min(x0, max(0, im.width - MW))
    y0 = min(y0, max(0, im.height - MH))
    ref = im.crop((x0, y0, x0 + MW, y0 + MH))
    ref.save(out / "ref-743x1095.png")
    print(f"  参考图  裁 ({x0},{y0}) -> {MW}×{MH}")
    return ref


def render_character(art: pathlib.Path, out: pathlib.Path, chrome: str) -> Image.Image:
    """渲染角色本体：隐藏氛围层、停动画、视口 743×1095。"""
    html = art.read_text(encoding="utf-8", errors="ignore")
    inject = f"""
<style id="meas">
  html,body{{width:{MW}px!important;height:{MH}px!important;
            margin:0!important;overflow:hidden!important;background:#fff!important}}
  #sea{{display:none!important}}
  i{{display:none!important}}
  #stage{{perspective:none!important}}
  #rig{{transform:none!important}}
  #girl{{animation:none!important;filter:none!important;inset:0!important}}
  *{{animation:none!important;transition:none!important}}
</style>
</head>"""
    html = html.replace("</head>", inject, 1) if "</head>" in html else inject.replace("</head>", "") + html

    mh = out / "meas.html"
    mh.write_text(html, encoding="utf-8", newline="\n")

    shot = out / "render-743x1095.png"
    if shot.exists():
        shot.unlink()
    # 每次用全新的临时 user-data-dir。
    # 固定目录在第二次运行时会因为残留锁而让 Chrome 静默退出
    # （returncode 0 但不产出截图）—— 这个坑踩过一次。
    profile = pathlib.Path(tempfile.mkdtemp(prefix="cwg-chrome-"))
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={profile}",
             f"--window-size={MW},{MH}", "--virtual-time-budget=6000",
             f"--screenshot={shot}", mh.as_uri()],
            # 不用 capture_output：某些沙箱环境禁止子进程用管道捕获输出
            # （会以 EPERM 静默失败，截图文件根本不生成）。
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=180)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not shot.exists():
        raise SystemExit(f"渲染失败 —— Chrome 没产出截图。用的命令是:\n  {chrome}")

    im = Image.open(shot).convert("RGB")
    if im.size != (MW, MH):
        im = im.crop((0, 0, MW, MH))
    im.save(shot)
    print(f"  渲染图  {im.size[0]}×{im.size[1]}")
    return im


def edge_band(mask: np.ndarray, r: int) -> np.ndarray:
    """前景蒙版膨胀 r 像素后减去原蒙版 = 边缘带（可分离膨胀）。"""
    m = mask.astype(np.uint8)
    for _ in range(r):
        m2 = m.copy()
        m2[1:, :] |= m[:-1, :]
        m2[:-1, :] |= m[1:, :]
        m2[:, 1:] |= m[:, :-1]
        m2[:, :-1] |= m[:, 1:]
        m = m2
    return m.astype(bool) & (~mask)


def main() -> int:
    ap = argparse.ArgumentParser(description="逐像素误差测量")
    ap.add_argument("--ref", required=True, help="参考图路径")
    ap.add_argument("--art", default=str(ROOT / "art" / "css-whale-girl.html"))
    ap.add_argument("--out", default=str(ROOT / ".work" / "measure"))
    ap.add_argument("--json", help="把结果写成 JSON（CI 用）")
    ap.add_argument("--render", help="已渲染好的截图路径。给了就跳过 Chrome")
    ap.add_argument("--max-mae", type=float, default=10.5,
                    help="前景 MAE 上限，超过就返回非零（默认 10.5，实测 9.69）")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("=== 重建测量管线 ===")
    ref = np.asarray(prepare_reference(pathlib.Path(args.ref), out)).astype(np.float64)

    if args.render:
        # 渲染交给外部（CI 里用 headless Chrome 直接跑，更可控）。
        # 有些沙箱环境禁止 Python 子进程启动的 Chrome 写文件 ——
        # 那种情况下这个开关是唯一能用的路径。
        ren_im = Image.open(args.render).convert("RGB")
        if ren_im.size != (MW, MH):
            ren_im = ren_im.crop((0, 0, MW, MH))
        print(f"  渲染图  (外部) {ren_im.size[0]}×{ren_im.size[1]}")
        ren = np.asarray(ren_im).astype(np.float64)
    else:
        chrome = find_chrome()
        if not chrome:
            print("  !! 找不到 Chrome。设置 CHROME 环境变量，或改用 --render。", file=sys.stderr)
            return 2
        ren = np.asarray(render_character(pathlib.Path(args.art), out, chrome)).astype(np.float64)

    fg = ~((ref[:, :, 0] > 245) & (ref[:, :, 1] > 245) & (ref[:, :, 2] > 245))
    print(f"  前景像素 {fg.sum():,} / {fg.size:,}  ({fg.sum()/fg.size*100:.1f}%)")

    err = np.abs(ref - ren).mean(axis=2)

    print()
    print(f"{'边缘带宽':>8} {'边缘像素%':>10} {'内部MAE':>9} {'边缘MAE':>9} "
          f"{'前景MAE':>9} {'边缘误差占比':>13}")
    print("-" * 66)

    result = {}
    for r in (1, 2, 3):
        band = edge_band(fg, r)
        inner = fg & (~band)
        if band.sum() == 0 or inner.sum() == 0:
            continue
        mae_in = float(err[inner].mean())
        mae_band = float(err[band].mean())
        mae_fg = float(err[fg].mean())
        share = float(err[band].sum() / err[fg].sum())
        result[f"band{r}"] = {
            "band_px_pct": round(float(band.sum() / fg.size * 100), 2),
            "inner_mae": round(mae_in, 2),
            "band_mae": round(mae_band, 2),
            "fg_mae": round(mae_fg, 2),
            "band_err_share": round(share * 100, 1),
        }
        print(f"{r:>8} {band.sum()/fg.size*100:>9.1f}% {mae_in:>9.2f} "
              f"{mae_band:>9.2f} {mae_fg:>9.2f} {share*100:>12.1f}%")

    heat = np.clip(err * 6, 0, 255).astype(np.uint8)
    Image.fromarray(heat, mode="L").save(out / "error-heat.png")
    print(f"\n  误差热力图 -> {out / 'error-heat.png'}")

    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  JSON -> {args.json}")

    # 回归门槛
    fg_mae = result["band2"]["fg_mae"] if "band2" in result else None
    if fg_mae is not None:
        print(f"\n  前景 MAE = {fg_mae}  (门槛 {args.max_mae})")
        if fg_mae > args.max_mae:
            print(f"  ✗ 超过门槛 —— 管线改动让误差变大了", file=sys.stderr)
            return 1
        print("  ✓ 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
