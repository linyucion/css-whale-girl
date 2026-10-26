# -*- coding: utf-8 -*-
"""inkfix.py — 分层提取 v8：分离「描边」并作为独立图层绘制
   问题诊断：AI 参考图有深色 lineart 描边，K-means 把细描边并进邻近色块 →
            渲染缺线，边缘差异大。
   方案：
     1. 用亮度自适应阈值提取「描边 mask」（比周围暗很多的细结构）
     2. 主体色层量化时**排除描边像素**（用 inpaint 后的颜色聚类）
     3. 描边作为最顶层若干图层输出（按连通块）
"""
from PIL import Image, ImageDraw
import numpy as np
import json, pathlib, os
from scipy import ndimage
from sklearn.cluster import MiniBatchKMeans
from skimage import measure

# 数据目录：脚本同级目录。可用环境变量 CWG_DATA 覆盖。
BASE = pathlib.Path(os.environ.get("CWG_DATA", pathlib.Path(__file__).resolve().parent.parent / "data"))
# 参考图：优先读 REF 环境变量（trace.py 就是这么做的），
# 否则用随仓库附带的 docs/reference.png。
REF  = pathlib.Path(os.environ.get("REF", pathlib.Path(__file__).resolve()
                                          .parent.parent / "docs" / "reference.png"))

K       = int(os.environ.get("K", 64))
SIGMA   = float(os.environ.get("SIGMA", 1.8))
DENS    = float(os.environ.get("DENS", 0.9))
MINAREA = float(os.environ.get("MINAREA", 14.0))
MINCOMP = int(os.environ.get("MINCOMP", 26))
MEDIAN  = int(os.environ.get("MEDIAN", 1))
DILATE  = float(os.environ.get("DILATE", 0.55))
TAG     = os.environ.get("TAG", "ink1")
INKMUL  = float(os.environ.get("INKMUL", 0.72))   # 描边阈值：亮度的百分比
INKADD  = float(os.environ.get("INKADD", 12.0))   # 或绝对差阈值
INKSAT  = float(os.environ.get("INKSAT", 0.38))   # 描边饱和度上限（描边近中性）

# ── 抠白底 ────────────────────────────────────────────────
a = np.array(Image.open(REF).convert("RGB")).astype(np.float32)
mx = a.max(axis=2); mn = a.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1e-6)
whiteish = (mx > 242) & (sat < 0.06)
H0, W0 = a.shape[:2]
bg = np.zeros((H0, W0), bool)
from collections import deque
q = deque()
for x in range(W0):
    for y in (0, H0-1):
        if whiteish[y, x] and not bg[y, x]: bg[y, x] = True; q.append((y, x))
for y in range(H0):
    for x in (0, W0-1):
        if whiteish[y, x] and not bg[y, x]: bg[y, x] = True; q.append((y, x))
while q:
    y, x = q.popleft()
    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny, nx = y+dy, x+dx
        if 0 <= ny < H0 and 0 <= nx < W0 and not bg[ny, nx] and whiteish[ny, nx]:
            bg[ny, nx] = True; q.append((ny, nx))
fg = ~bg
fg = ndimage.binary_opening(fg, iterations=1)
fg = ndimage.binary_closing(fg, iterations=2)
cc, n = ndimage.label(fg)
if n > 1:
    sizes = ndimage.sum(fg, cc, range(1, n+1))
    keep = int(np.argmax(sizes)) + 1
    core = (cc == keep)
    keepmask = core.copy()
    for ci, sz in enumerate(sizes, start=1):
        if ci == keep or sz < 400: continue
        comp = (cc == ci)
        if (ndimage.binary_dilation(core, iterations=14) & comp).sum() > comp.sum()*0.5:
            keepmask |= comp
    fg = keepmask

ys, xs = np.nonzero(fg)
pad = 3
x0 = max(0, xs.min()-pad); y0 = max(0, ys.min()-pad)
x1 = min(W0, xs.max()+pad+1); y1 = min(H0, ys.max()+pad+1)
img = a[y0:y1, x0:x1]
fgc = fg[y0:y1, x0:x1]
H, W = img.shape[:2]

# ── 提取描边（局部暗线）──────────────────────────────────────
lum = img.mean(axis=2)
# 局部背景亮度：大核中值滤波（近似「周围颜色」）
local = ndimage.median_filter(lum, size=7)
# 描边必须是「深且低饱和」的线：肤色上的红色阴影/腮红不能算描边
mu = img.mean(axis=2, keepdims=True)
sat_img = ((img.max(axis=2) - img.min(axis=2)) /
           np.maximum(img.max(axis=2), 1e-6))
dark = (lum < local * INKMUL) & (local - lum > INKADD)
low_sat = sat_img < INKSAT                 # 描边是近中性深色
ink = dark & low_sat & fgc
# 注意：不要排除「暖色」——嘴巴的深红描边也是描边，排掉会导致嘴巴消失。
# 腮红是亮色（dark 判定为假），本来就不会进 ink。
ink = ndimage.binary_opening(ink, iterations=1)
# 只要细结构：去掉太粗的块；同时去掉碎点（INKSAT 关掉后靠这一步清脸）
cc_i, n_i = ndimage.label(ink)
INKMAX = float(os.environ.get("INKMAX", 2600))
INKMIN = float(os.environ.get("INKMIN", 22))
if n_i:
    for ci, sz in enumerate(ndimage.sum(ink, cc_i, range(1, n_i+1)), start=1):
        comp = (cc_i == ci)
        if sz == 0: continue
        if sz > INKMAX or sz < INKMIN:
            ink[comp] = False
print(f"ink px = {int(ink.sum())} ({100*ink.sum()/fgc.sum():.1f}% of fg)")

# 描边颜色：取描边像素的中位色
if ink.sum() > 50:
    ink_rgb = np.median(img[ink], axis=0)
else:
    ink_rgb = np.array([30, 34, 44], np.float32)
ink_hex = "#%02x%02x%02x" % tuple(int(round(v)) for v in np.clip(ink_rgb, 0, 255))
print("ink color", ink_hex)

# ── 主体：先用 inpaint 掉描边，再量化（避免描边把色层拉脏）────────
from scipy import interpolate
body = img.copy()
if ink.sum() > 50:
    # 简单的邻域扩散 inpaint：迭代用非描边邻居均值填充
    mask = ink.copy()
    for _ in range(6):
        if not mask.any(): break
        nb = np.zeros((H, W, 3), np.float32)
        cnt = np.zeros((H, W), np.float32)
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            sy = np.clip(np.arange(H)+dy, 0, H-1)
            sx = np.clip(np.arange(W)+dx, 0, W-1)
            sh = body[sy][:, sx]
            valid = (~mask)[sy][:, sx]
            nb += sh * valid[..., None]
            cnt += valid
        fill = cnt > 0
        upd = mask & fill
        body[upd] = (nb[upd] / cnt[upd][:, None])
        mask = mask & ~upd

px = body[fgc]
km = MiniBatchKMeans(n_clusters=K, random_state=0, n_init=10, batch_size=8192, max_iter=600)
lab = km.fit_predict(px)
centers = np.clip(km.cluster_centers_, 0, 255)

BG = -1
label = np.full((H, W), BG, np.int32)
label[fgc] = lab
for _ in range(MEDIAN):
    sm = ndimage.median_filter(np.where(fgc, label, 0), size=3)
    label = np.where(fgc, sm, BG)

def clean_small(lab_arr, min_px):
    n = 0
    for k in range(K):
        m = (lab_arr == k)
        if not m.any(): continue
        cc, nc = ndimage.label(m)
        if nc == 0: continue
        for ci, sz in enumerate(ndimage.sum(m, cc, range(1, nc+1)), start=1):
            if sz >= min_px: continue
            comp = (cc == ci)
            ring = ndimage.binary_dilation(comp, iterations=1) & ~comp
            nb = lab_arr[ring]; nb = nb[(nb != k) & (nb >= 0)]
            if nb.size == 0: continue
            v, c = np.unique(nb, return_counts=True)
            lab_arr[comp] = v[np.argmax(c)]
            n += 1
    return lab_arr, n

label, nchg = clean_small(label.copy(), MINCOMP)

def signed_area(p):
    x = p[:,0]; y = p[:,1]
    return 0.5*float(np.dot(x, np.roll(y,-1)) - np.dot(y, np.roll(x,-1)))

def point_in(pt, poly):
    x, y = pt; inside=False; n=len(poly)
    for i in range(n):
        x1,y1 = poly[i]; x2,y2 = poly[(i+1)%n]
        if ((y1>y)!=(y2>y)) and (x < (x2-x1)*(y-y1)/(y2-y1+1e-12)+x1):
            inside = not inside
    return inside

def smooth_ring(pts, sigma, dens):
    p = np.asarray(pts, float)
    d = np.linalg.norm(np.diff(np.vstack([p, p[0]]), axis=0), axis=1)
    per = d.sum()
    if per < 6: return None
    n = max(16, int(per*dens))
    s = np.concatenate([[0], np.cumsum(d)]); s /= s[-1]
    su = np.linspace(0, 1, n, endpoint=False)
    xs_ = np.interp(su, s, np.concatenate([p[:,0], p[:1,0]]))
    ys_ = np.interp(su, s, np.concatenate([p[:,1], p[:1,1]]))
    xs_ = ndimage.gaussian_filter1d(xs_, sigma, mode="wrap")
    ys_ = ndimage.gaussian_filter1d(ys_, sigma, mode="wrap")
    q = np.stack([xs_, ys_], 1)
    keep = [0]
    for i in range(1, n):
        if np.linalg.norm(q[i]-q[keep[-1]]) >= 0.55:
            keep.append(i)
    if len(keep) < 3: return None
    if np.linalg.norm(q[keep[-1]]-q[keep[0]]) < 0.55 and len(keep) > 3:
        keep = keep[:-1]
    return q[keep]

def offset_ring(q, off):
    if abs(off) < 1e-9 or len(q) < 3: return q
    n = len(q)
    nxt = np.roll(q, -1, axis=0); prv = np.roll(q, 1, axis=0)
    t = nxt - prv
    ln = np.linalg.norm(t, axis=1); ln[ln < 1e-9] = 1e-9
    t /= ln[:, None]
    nrm = np.stack([t[:,1], -t[:,0]], 1)
    if signed_area(q) < 0: nrm = -nrm
    return q + nrm*off

# ── 主体色层 ──────────────────────────────────────────────
allrings = []
for k in range(K):
    m = (label == k)
    if m.sum() < MINAREA: continue
    pd = np.zeros((H+2, W+2), np.float32)
    pd[1:-1, 1:-1] = m.astype(np.float32)
    rings = []
    for c in measure.find_contours(pd, 0.5):
        pts = np.stack([c[:,1]-1.0, c[:,0]-1.0], 1)
        if len(pts) < 8: continue
        if np.linalg.norm(pts[0]-pts[-1]) < 1e-9: pts = pts[:-1]
        sm = smooth_ring(pts, SIGMA, DENS)
        if sm is None: continue
        if DILATE > 0: sm = offset_ring(sm, DILATE)
        aa = abs(signed_area(sm))
        if aa < MINAREA*0.5: continue
        rings.append([sm, aa, 0])
    if not rings: continue
    rings.sort(key=lambda r: -r[1])
    for i, r in enumerate(rings):
        probe = r[0][0]
        r[2] = sum(1 for j,o in enumerate(rings)
                   if i!=j and o[1]>r[1] and point_in(probe, o[0]))
    col = "#%02x%02x%02x" % tuple(int(round(v)) for v in centers[k])
    for pts, aa, d in rings:
        allrings.append({"color": col, "pts": pts, "area": aa, "depth": d})

allrings.sort(key=lambda r: (r["depth"], -r["area"]))

# ── 描边层：作为最高 depth 追加，保证盖在最上 ──────────────────
ink_rings = []
if ink.sum() > 50:
    pd = np.zeros((H+2, W+2), np.float32)
    pd[1:-1, 1:-1] = ink.astype(np.float32)
    for c in measure.find_contours(pd, 0.5):
        pts = np.stack([c[:,1]-1.0, c[:,0]-1.0], 1)
        if len(pts) < 8: continue
        if np.linalg.norm(pts[0]-pts[-1]) < 1e-9: pts = pts[:-1]
        sm = smooth_ring(pts, SIGMA*0.75, DENS*1.15)
        if sm is None: continue
        aa = abs(signed_area(sm))
        if aa < 3.0: continue
        ink_rings.append([sm, aa])
    ink_rings.sort(key=lambda r: -r[1])
    for pts, aa in ink_rings:
        allrings.append({"color": ink_hex, "pts": pts, "area": aa, "depth": 99})
else:
    allrings = allrings

npt = sum(len(r["pts"]) for r in allrings)
print(f"TAG{TAG} K={K} SIGMA={SIGMA} DENS={DENS} DILATE={DILATE} INK={ink_hex}")
print(f"  body_rings={len(allrings)-len(ink_rings)} ink_rings={len(ink_rings)} pts={npt}")

# ── 重建误差（numpy，含描边）──
canvas = np.zeros((H, W, 3), np.float32)
for r in allrings:
    col = tuple(int(r["color"][i:i+2],16) for i in (1,3,5))
    im1 = Image.new("1", (W,H), 0)
    ImageDraw.Draw(im1).polygon([tuple(v) for v in r["pts"].tolist()], fill=1)
    canvas[np.array(im1,bool)] = col

mae = float(np.abs(canvas[fgc]-img[fgc]).mean())
print(f"  recon MAE={mae:.2f}")
Image.fromarray(canvas.astype(np.uint8)).save(BASE/f"recon_{TAG}.png")

json.dump({"w": W, "h": H,
           "rings":[{"c":r["color"],"d":r["depth"],"a":round(r["area"],1),
                     "p":[[round(float(x),2), round(float(y),2)] for x,y in r["pts"].tolist()]}
                    for r in allrings]},
          open(BASE/f"layers_{TAG}.json","w",encoding="utf-8"), separators=(",",":"))
print("  json", (BASE/f"layers_{TAG}.json").stat().st_size, "bytes")
