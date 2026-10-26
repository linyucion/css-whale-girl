# -*- coding: utf-8 -*-
"""build_site.py — 发布版构建器（响应式 + 百分比坐标）

与 showcase.py 的区别：
  · 角色多边形坐标从 px 转成 **百分比**，于是 `.girl` 盒子可以任意尺寸，
    形状自动等比缩放，不再需要 `transform: scale(写死的数字)`。
  · `#rig` 用 `min(94vw, 94vh*743/1095)` + `aspect-ratio` 定尺寸，
    手机 / 平板 / 16:9 / 戴鱼屏 都不裁切。
  · 百分比串比 px 串更短，文件更小。
"""
import json, os, sys, pathlib, random

# 数据目录：脚本同级目录。可用环境变量 CWG_DATA 覆盖。
BASE = pathlib.Path(os.environ.get("CWG_DATA", pathlib.Path(__file__).resolve().parent.parent / "data"))
BLINK_DUR = 5.4

def build(lj_path, out_html, title="鲸鱼娘", desc="", fit=0.94, seed=7,
          frames_json=None):
    d = json.load(open(lj_path, encoding="utf-8"))
    rings = d["rings"]
    W, H = float(d["w"]), float(d["h"])

    rules, body = [], []
    for i, r in enumerate(rings):
        pts = []
        for x, y in r["p"]:
            pts.append(f"{x*100.0/W:.3f}% {y*100.0/H:.3f}%")
        pp = ",".join(pts)
        op = r.get("op", 1.0)
        opc = f"opacity:{op};" if op < 1.0 else ""
        bg = r["c"]
        if "g" in r:
            ang, c0, c1 = r["g"]
            bg = f"linear-gradient({ang}deg,{c0},{c1})"
        rules.append(f".r{i}{{background:{bg};{opc}clip-path:polygon({pp})}}")
        body.append(f'<b class="r{i}"></b>')

    # ── 眨眼：逐帧动画（7 帧，steps 切帧）─────────────────────────
    # 眼睛图层保持完全静止：它们的绘制顺序散落在 389 个不连续段里，
    # 逐个加 transform 会破坏合成（实测 446 个动画元素直接渲染碎裂）。
    # 改为每帧独立的「眼皮多边形（底边是光滑眼睑曲线）+ 沿该曲线的睫毛线」，
    # 用 steps(1,end) 在自己的时间窗内显示 —— 就是传统动画的一格一格。
    lid_rules, lid_body, lid_kf = [], [], []
    nframes = 0
    if frames_json:
        fj = json.load(open(frames_json, encoding="utf-8"))
        Wc, Hc = fj["canvas"]
        skin = fj["skin"]
        lidbg = fj.get("lid_bg", {})
        if not lidbg:
            lidbg = {"l": skin["l"], "r": skin["r"]}
        nframes = len(fj["frames"]["l"])

        def pct(pts):
            return ",".join(f"{x*100.0/Wc:.3f}% {y*100.0/Hc:.3f}%" for x, y in pts)

        # 时间窗：闭 7 步 → 保持 → 睁 6 步（% of BLINK_DUR）
        # 参考视频实测：完全闭合只持续 2~4 帧（67~133ms），过渡近乎硬切。
        # 所以整体压到 ~230ms，保持 54ms。
        START, STEP, HOLD = 88.90, 0.31, 1.00
        win = {k: [] for k in range(1, nframes + 1)}
        t = START
        for k in range(1, nframes + 1):
            win[k].append((round(t, 3), round(t + STEP, 3)))
            t += STEP
        closed_end = t
        win[nframes].append((round(closed_end, 3), round(closed_end + HOLD, 3)))
        t = closed_end + HOLD
        for k in range(nframes - 1, 0, -1):
            win[k].append((round(t, 3), round(t + STEP, 3)))
            t += STEP

        for k in range(1, nframes + 1):
            stops = ["0%{opacity:0}"]
            for a, b in win[k]:
                stops.append(f"{a}%{{opacity:1}}")
                stops.append(f"{b}%{{opacity:0}}")
            stops.append("100%{opacity:0}")
            lid_kf.append(f"@keyframes bf{k}{{{''.join(stops)}}}")

        # 每帧三块：上眼睑 / 下眼睑 / 眼缝睫毛线。
        # 关键：父元素 <b class="eyeL"> 用**眼球剪影**做 clip-path（无背景），
        # 子元素只画光滑的眼睑曲线带 —— 父级裁剪把外侧边缘修干净，
        # 就不会出现「眼皮贴着锯齿状眼缘」那种撕纸感。
        # 剪影用「眼睛实际可见区域」的每一块连通区（刘海位置天然被排除，
        # 否则画在最上层的眼皮会把压在眼睛上的刘海一起盖掉）。
        def pct_list(pts):
            return ",".join(f"{x*100.0/Wc:.3f}% {y*100.0/Hc:.3f}%" for x, y in pts)

        for eye in ("l", "r"):
            sils = fj["silhouette"][eye]
            kids = []
            for k, fr in enumerate(fj["frames"][eye], start=1):
                for tag, key in (("u", "up"), ("o", "lo"), ("l", "lash")):
                    if not fr.get(key):
                        continue
                    cls = f"{tag}d{eye}{k}"
                    col = "#1b1f28" if key == "lash" else lidbg[eye]
                    lid_rules.append(
                        f".{cls}{{background:{col};"
                        f"animation:bf{k} {BLINK_DUR}s steps(1,end) infinite;"
                        f"clip-path:polygon({pct_list(fr[key])})}}")
                    kids.append(f'<b class="{cls}"></b>')
            kid_html = "".join(kids)
            for si, sil in enumerate(sils):
                pcls = f"eye{eye}{si}"
                lid_rules.append(f".{pcls}{{clip-path:polygon({pct_list(sil)})}}")
                lid_body.append(f'<b class="{pcls}">{kid_html}</b>')

    rng = random.Random(seed)

    bubbles = []
    for k in range(34):
        bx = rng.uniform(1, 99); by = rng.uniform(55, 112)
        rad = rng.choice([3, 3, 4, 4, 5, 6, 7, 9, 11])
        dur = rng.uniform(13, 30); delay = rng.uniform(0, 26)
        drift = rng.uniform(-34, 34); op = rng.uniform(0.30, 0.72)
        bubbles.append(
            f".bb{k}{{width:{rad*2}px;height:{rad*2}px;left:{bx:.2f}%;top:{by:.2f}%;"
            f"--o:{op:.2f};animation:rise {dur:.1f}s linear {delay:.1f}s infinite;"
            f"--dx:{drift:.0f}px}}")
    nb = len(bubbles)

    bokeh = []
    for k in range(9):
        bx = rng.uniform(-4, 104); by = rng.uniform(-6, 106)
        rad = rng.uniform(26, 78); dur = rng.uniform(26, 46)
        delay = rng.uniform(0, 30); op = rng.uniform(0.05, 0.13)
        bokeh.append(f".bk{k}{{width:{rad*2:.0f}px;height:{rad*2:.0f}px;"
                     f"left:{bx:.1f}%;top:{by:.1f}%;opacity:{op:.3f};"
                     f"animation:drift{dur % 3:.0f}s ease-in-out {delay:.1f}s infinite}}")
    nk = len(bokeh)

    dusts = []
    for k in range(44):
        dx = rng.uniform(1, 99); dy = rng.uniform(1, 99)
        sz = rng.choice([1, 1, 1, 2, 2, 3])
        dur = rng.uniform(4.5, 12.0); delay = rng.uniform(0, 12)
        dusts.append(f".d{k}{{width:{sz}px;height:{sz}px;left:{dx:.2f}%;top:{dy:.2f}%;"
                     f"animation:twinkle {dur:.2f}s ease-in-out {delay:.2f}s infinite}}")

    stars = []
    for k in range(7):
        sx = rng.choice([8, 12, 16, 84, 88, 92, 50]) + rng.uniform(-3, 3)
        sy = rng.uniform(12, 86)
        sz = rng.choice([10, 13, 16, 20])
        dur = rng.uniform(2.6, 4.8); delay = rng.uniform(0, 5)
        stars.append(f".st{k}{{width:{sz}px;height:{sz}px;left:{sx:.1f}%;top:{sy:.1f}%;"
                     f"animation:sparkle {dur:.2f}s ease-in-out {delay:.2f}s infinite}}")
    ns = len(stars)

    hearts = []
    for k in range(4):
        hx = rng.choice([18, 26, 74, 82]) + rng.uniform(-4, 4)
        hy = rng.uniform(20, 74)
        sz = rng.choice([9, 11, 14])
        dur = rng.uniform(9, 17); delay = rng.uniform(0, 12)
        hearts.append(f".ht{k}{{width:{sz}px;height:{sz}px;left:{hx:.1f}%;top:{hy:.1f}%;"
                      f"animation:floatHeart {dur:.1f}s ease-in-out {delay:.1f}s infinite}}")
    nh = len(hearts)

    ASPECT = W / H
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="{desc}">
<meta name="theme-color" content="#02060d">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#02060d}}

/* ═══ L0 深海背景 ═══════════════════════════════════════ */
#sea{{position:fixed;inset:0;overflow:hidden;
  background:
   radial-gradient(ellipse 76% 62% at 50% 26%,#1d6ba6 0%,#14507f 17%,
                   #0d3459 38%,#07203a 62%,#03101d 84%,#01060c 100%);}}
/* 水面光柱 */
#sea::before{{content:"";position:absolute;inset:-20% -10%;
  background:
   conic-gradient(from 198deg at 36% -12%,transparent 0deg,
     rgba(150,225,255,.155) 6deg,transparent 13deg,
     rgba(120,205,250,.105) 20deg,transparent 28deg,
     rgba(165,232,255,.14) 35deg,transparent 44deg,
     rgba(110,190,245,.08) 52deg,transparent 62deg,
     rgba(140,220,255,.11) 70deg,transparent 82deg,transparent 360deg);
  filter:blur(14px);mix-blend-mode:screen;
  animation:shafts 17s ease-in-out infinite alternate;}}
/* 焦散水波：多个不同位置/大小的柔光散斑，不用 repeating（会变格子布） */
#sea::after{{content:"";position:absolute;inset:-30%;
  background:
   radial-gradient(ellipse 30% 22% at 22% 12%,rgba(150,230,255,.13) 0%,transparent 68%),
   radial-gradient(ellipse 26% 18% at 68% 22%,rgba(125,212,255,.11) 0%,transparent 70%),
   radial-gradient(ellipse 34% 20% at 44% 44%,rgba(105,195,250,.085) 0%,transparent 72%),
   radial-gradient(ellipse 24% 16% at 82% 62%,rgba(135,222,255,.09) 0%,transparent 70%),
   radial-gradient(ellipse 30% 18% at 14% 74%,rgba(100,188,245,.08) 0%,transparent 72%),
   radial-gradient(ellipse 38% 24% at 58% 88%,rgba(120,205,250,.075) 0%,transparent 74%);
  filter:blur(26px);mix-blend-mode:screen;
  animation:caustics 23s ease-in-out infinite alternate;}}

/* ═══ 舞台 ═════════════════════════════════════════════ */
#stage{{position:absolute;inset:0;display:grid;place-items:center;
  perspective:1500px;perspective-origin:50% 46%;}}
/* 响应式：宽度取「可用宽」与「按宽高比换算的高」的较小值 —— 任何比例都不裁切 */
#rig{{position:relative;
  width:min(94vw, calc(94vh * {ASPECT:.6f}));
  aspect-ratio:{W:.4f} / {H:.4f};
  transform-style:preserve-3d;
  transition:transform .55s cubic-bezier(.22,.9,.28,1);}}

/* 角色本体：{len(rings)} 层，坐标是百分比，盒子多大都能等比缩放 */
#girl{{position:absolute;inset:0;
  filter:drop-shadow(0 3vmin 6vmin rgba(1,7,18,.78))
         drop-shadow(0 0 3.4vmin rgba(90,200,255,.20));
  animation:hedsway 5.8s ease-in-out infinite;}}
#girl b{{position:absolute;left:0;top:0;width:100%;height:100%;display:block;}}
{chr(10).join(rules)}
{chr(10).join(lid_rules)}
{chr(10).join(lid_kf)}

/* ═══ L2 光照层 ════════════════════════════════════════ */
#sheen{{position:absolute;inset:-6%;pointer-events:none;
  mix-blend-mode:screen;opacity:.5;
  background:linear-gradient(104deg,
    transparent 30%,rgba(190,240,255,.16) 44%,
    rgba(255,255,255,.30) 50%,rgba(190,240,255,.16) 56%,transparent 70%);
  animation:sweep 8.5s cubic-bezier(.4,0,.6,1) infinite;}}
#rim{{position:absolute;inset:-3%;pointer-events:none;
  mix-blend-mode:screen;
  background:radial-gradient(ellipse 52% 44% at 50% 40%,
    rgba(120,215,255,.13) 0%,rgba(70,170,235,.07) 42%,transparent 72%);
  animation:rimPulse 6.4s ease-in-out infinite;}}

/* ═══ L3 气泡 / 光尘 / 散景 / 闪星 / 爱心 ══════════════ */
.bb{{position:absolute;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle at 32% 28%,
    rgba(255,255,255,.95) 0%,rgba(190,240,255,.55) 26%,
    rgba(120,200,245,.18) 54%,rgba(90,170,230,.05) 78%,transparent 100%);
  box-shadow:inset 0 0 4px rgba(200,245,255,.7),
             0 0 9px rgba(110,200,250,.35);}}
.d{{position:absolute;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle,#dff6ff 0%,rgba(160,225,255,.55) 55%,transparent 100%);
  box-shadow:0 0 5px rgba(150,225,255,.85);}}
.bk{{position:absolute;border-radius:50%;pointer-events:none;
  mix-blend-mode:screen;
  background:radial-gradient(circle at 40% 36%,
    rgba(190,240,255,.55) 0%,rgba(120,205,250,.22) 46%,
    rgba(80,170,235,.06) 74%,transparent 100%);
  filter:blur(3px);}}
/* 四角闪星：clip-path 多边形，和角色同一套技术 */
.st{{position:absolute;pointer-events:none;
  background:radial-gradient(circle,#ffffff 0%,#ccf2ff 42%,rgba(150,225,255,0) 78%);
  clip-path:polygon(50% 0%,58% 42%,100% 50%,58% 58%,50% 100%,42% 58%,0% 50%,42% 42%);
  filter:drop-shadow(0 0 5px rgba(180,240,255,.9));}}
/* 小爱心：两瓣圆 + 45° 旋转的方块，纯 CSS 无图 */
.ht{{position:absolute;pointer-events:none;transform:rotate(45deg);
  background:linear-gradient(135deg,#ff9ec4,#ff6fa5);
  border-radius:0 0 2px 0;
  box-shadow:0 0 10px rgba(255,140,190,.55);}}
.ht::before,.ht::after{{content:"";position:absolute;width:100%;height:100%;
  background:inherit;border-radius:50%;}}
.ht::before{{top:-50%;left:0}}
.ht::after{{top:0;left:-50%}}
{chr(10).join(stars)}
{chr(10).join(hearts)}
{chr(10).join(bokeh)}
{chr(10).join(bubbles)}
{chr(10).join(dusts)}

/* ═══ L4 交互：3D 视差 ═════════════════════════════════ */
#stage:hover #rig{{transform:rotateX(2.2deg) rotateY(-3.4deg) translateZ(14px)}}
#stage:hover #sheen{{opacity:.78}}
#stage:hover #girl{{filter:drop-shadow(0 3.4vmin 7vmin rgba(1,7,18,.8))
                          drop-shadow(0 0 4.6vmin rgba(110,215,255,.30));}}
@media (hover:none){{
  #stage:hover #rig{{transform:none}}}}

/* ═══ 动画 ═════════════════════════════════════════════ */
@keyframes hedsway{{
  0%,100%{{transform:translateY(0) rotate(-.45deg)}}
  50%{{transform:translateY(-.55vmin) rotate(.45deg)}}}}
@keyframes rise{{
  0%{{transform:translate3d(0,0,0) scale(.55);opacity:0}}
  12%{{opacity:var(--o,.35)}}
  88%{{opacity:var(--o,.35)}}
  100%{{transform:translate3d(var(--dx,0),-118vh,0) scale(1.15);opacity:0}}}}
@keyframes twinkle{{
  0%,100%{{opacity:.14;transform:scale(.8)}}
  50%{{opacity:.85;transform:scale(1.35)}}}}
@keyframes caustics{{
  0%{{transform:translate3d(0,0,0) rotate(0deg)}}
  100%{{transform:translate3d(-3%,-4%,0) rotate(3deg)}}}}
@keyframes shafts{{
  0%{{transform:translateX(-2.5%) skewX(0deg);opacity:.72}}
  100%{{transform:translateX(2.5%) skewX(2.4deg);opacity:1}}}}
@keyframes sweep{{
  0%{{transform:translateX(-68%)}}
  55%,100%{{transform:translateX(68%)}}}}
@keyframes rimPulse{{
  0%,100%{{opacity:.55;transform:scale(1)}}
  50%{{opacity:.92;transform:scale(1.035)}}}}
@keyframes drift0{{
  0%,100%{{transform:translate3d(0,0,0)}} 50%{{transform:translate3d(-14px,20px,0)}}}}
@keyframes drift1{{
  0%,100%{{transform:translate3d(0,0,0)}} 50%{{transform:translate3d(18px,-16px,0)}}}}
@keyframes drift2{{
  0%,100%{{transform:translate3d(0,0,0)}} 50%{{transform:translate3d(10px,24px,0)}}}}
@keyframes sparkle{{
  0%,100%{{opacity:0;transform:scale(.25) rotate(0deg)}}
  45%{{opacity:1;transform:scale(1.1) rotate(24deg)}}
  70%{{opacity:.55;transform:scale(.8) rotate(40deg)}}}}
  90.8%,92%{{transform:scaleY(1)}}
  93.8%,100%{{transform:scaleY(0)}}}}
  90.6%,92.2%{{opacity:1}}
  93.4%,100%{{opacity:0}}}}
@keyframes floatHeart{{
  0%{{opacity:0;transform:translateY(0) rotate(45deg) scale(.6)}}
  18%{{opacity:.9}} 80%{{opacity:.55}}
  100%{{opacity:0;transform:translateY(-70px) rotate(45deg) scale(1.05)}}}}
@media (prefers-reduced-motion:reduce){{
  *{{animation:none!important}}}}
</style></head><body>

<div id="sea"></div>

<div id="stage">
  <div id="rig">
    <div id="girl">
{chr(10).join(body)}
{chr(10).join(lid_body)}
    </div>
    <div id="sheen"></div>
    <div id="rim"></div>
  </div>
</div>

{chr(10).join(f'<i class="bk bk{k}"></i>' for k in range(nk))}
{chr(10).join(f'<i class="bb bb{k}"></i>' for k in range(nb))}
{chr(10).join(f'<i class="d d{k}"></i>' for k in range(len(dusts)))}
{chr(10).join(f'<i class="st st{k}"></i>' for k in range(ns))}
{chr(10).join(f'<i class="ht ht{k}"></i>' for k in range(nh))}

</body></html>
"""
    # 明确 LF：Windows 上 write_text 默认会写 CRLF，与仓库 .gitattributes 冲突
    pathlib.Path(out_html).write_text(html, encoding="utf-8", newline="\n")
    low = html.lower()
    bad = [t for t in ["<svg", "<img", "<canvas", "<script", "url("] if t in low]
    assert not bad, bad
    return len(html), len(rings)

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else str(BASE/"layers_res3.json")
    dst = sys.argv[2] if len(sys.argv) > 2 else str(BASE/"site.html")
    title = sys.argv[3] if len(sys.argv) > 3 else "鲸鱼娘 · 纯 HTML/CSS 手绘"
    desc = sys.argv[4] if len(sys.argv) > 4 else ""
    # 第 6 个参数写 noblink 可关掉眨眼（主站 whale.chu-2.moe 用无眨眼版，
    # 眨眼实验放在 blink.chu-2.moe）
    use_blink = not (len(sys.argv) > 5 and sys.argv[5] == "noblink")
    fr = str(BASE/"blink_frames.json")
    fj = fr if (use_blink and pathlib.Path(fr).exists()) else None
    n, nr = build(src, dst, title, desc, frames_json=fj)
    print(f"wrote {dst}  {n} chars  rings={nr}  CLEAN")
