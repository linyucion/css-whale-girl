# -*- coding: utf-8 -*-
"""remeasure_mae.py —— 重算误差分布

## 为什么要重算

文章第六节写着：

    色块内部 MAE  = 0.98
    边缘带   MAE  = 45
    边缘占误差比重 = 72%

Grok 指出这三个数互相推不出整图 MAE（11.03）：
若边缘占误差质量 72%，整图 MAE 只有约 3.2；若整图是 11.03，
边缘应占 93%。原始计算脚本已不在仓库里，无法复现 72% 的定义。

## 这次的做法

把测量管线重建一遍，定义写死，谁都能复算：

1. 参考图：`ai-ref-1k.png`（864×1152）裁出 743×1095（去留白）
2. 渲染图：拿 `css-whale-girl.html`，隐藏海面与氛围层、停掉动画，
   视口设成 743×1095 截屏 —— 1:1，不做任何缩放
3. 前景蒙版：参考图非近白像素
4. 边缘带：前景蒙版向内/向外膨胀 R 像素后减去原蒙版的环
5. 指标：
   - 内部 MAE   = 非边缘、非背景像素上的平均绝对误差
   - 边缘 MAE   = 边缘带像素上的平均绝对误差
   - 整图 MAE   = 前景（含边缘）上的平均绝对误差
   - 误差质量占比 = 边缘带误差之和 / 前景误差之和
"""
import pathlib
import subprocess

import numpy as np
from PIL import Image

W = pathlib.Path(r"C:\Users\linyu\Desktop\Linyucion\ai-studio"
                 r"\works\2026\whale-css")
OUT = W / "_media" / "build" / "remeasure"
OUT.mkdir(parents=True, exist_ok=True)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

MW, MH = 743, 1095


def make_reference():
    src = Image.open(W / "_media" / "inputs" / "ai-ref-1k.png").convert("RGB")
    a = np.asarray(src)
    mask = ~((a[:, :, 0] > 245) & (a[:, :, 1] > 245) & (a[:, :, 2] > 245))
    ys, xs = np.where(mask)
    # 包围盒 737×1090，向外各留 3px 凑成 743×1095
    x0 = max(0, xs.min() - 3)
    y0 = max(0, ys.min() - 2)
    x0 = min(x0, src.width - MW)
    y0 = min(y0, src.height - MH)
    ref = src.crop((x0, y0, x0 + MW, y0 + MH))
    ref.save(OUT / "ref-743x1095.png")
    print(f"  参考图  裁 ({x0},{y0}) 743×1095  ->  ref-743x1095.png")
    return ref


def render_character():
    """渲染角色本体：隐藏海面与氛围层，停动画，视口 743×1095。"""
    html = (W / "content" / "illustration" / "css-whale-girl.html").read_text(
        encoding="utf-8", errors="ignore")
    inject = """
<style id="meas">
  html,body{width:743px!important;height:1095px!important;
            margin:0!important;overflow:hidden!important;background:#fff!important}
  #sea{display:none!important}
  i{display:none!important}                 /* L3 氛围：气泡/光尘/散景/闪星/爱心 */
  #stage{perspective:none!important}
  #rig{transform:none!important}
  #girl{animation:none!important;filter:none!important;inset:0!important}
  *{animation:none!important;transition:none!important}
</style>
</head>"""
    if "</head>" in html:
        html = html.replace("</head>", inject, 1)
    else:
        html = inject.replace("</head>", "") + html
    mh = OUT / "meas.html"
    mh.write_text(html, encoding="utf-8", newline="\n")

    shot = OUT / "render-743x1095.png"
    if shot.exists():
        shot.unlink()
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={MW},{MH}", "--virtual-time-budget=6000",
         f"--screenshot={shot}", mh.as_uri()],
        capture_output=True, text=True)
    if not shot.exists():
        print("  !! 渲染失败")
        return None
    im = Image.open(shot).convert("RGB")
    if im.size != (MW, MH):
        im = im.crop((0, 0, MW, MH))
    im.save(shot)
    print(f"  渲染图  {im.size[0]}×{im.size[1]}  ->  render-743x1095.png")
    return im


def edge_band(mask, r):
    """前景蒙版膨胀 r 像素后减去原蒙版 = 边缘带。用简单的可分离膨胀。"""
    m = mask.astype(np.uint8)
    for _ in range(r):
        m2 = m.copy()
        m2[1:, :] |= m[:-1, :]
        m2[:-1, :] |= m[1:, :]
        m2[:, 1:] |= m[:, :-1]
        m2[:, :-1] |= m[:, 1:]
        m = m2
    return (m.astype(bool)) & (~mask)


def main():
    print("=== 重建测量管线 ===")
    ref = np.asarray(make_reference()).astype(np.float64)
    ren = render_character()
    if ren is None:
        return
    ren = np.asarray(ren).astype(np.float64)

    # 前景：参考图非近白
    fg = ~((ref[:, :, 0] > 245) & (ref[:, :, 1] > 245) & (ref[:, :, 2] > 245))
    print(f"  前景像素 {fg.sum():,} / {fg.size:,}  ({fg.sum()/fg.size*100:.1f}%)")

    err = np.abs(ref - ren).mean(axis=2)

    print()
    print(f"{'边缘带宽':>8} {'边缘像素%':>10} {'内部MAE':>9} {'边缘MAE':>9} "
          f"{'前景MAE':>9} {'边缘误差占比':>13}")
    print("-" * 66)
    for r in (1, 2, 3):
        band = edge_band(fg, r)
        inner = fg & (~band)
        if band.sum() == 0 or inner.sum() == 0:
            continue
        mae_in = err[inner].mean()
        mae_band = err[band].mean()
        mae_fg = err[fg].mean()
        share = err[band].sum() / err[fg].sum()
        print(f"{r:>8} {band.sum()/fg.size*100:>9.1f}% {mae_in:>9.2f} "
              f"{mae_band:>9.2f} {mae_fg:>9.2f} {share*100:>12.1f}%")

    # 存一张误差热力图，便于人眼核对
    heat = np.clip(err * 6, 0, 255).astype(np.uint8)
    Image.fromarray(heat, mode="L").save(OUT / "error-heat.png")
    print()
    print(f"  误差热力图 -> {OUT / 'error-heat.png'}")


if __name__ == "__main__":
    main()
