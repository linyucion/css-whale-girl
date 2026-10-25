# -*- coding: utf-8 -*-
"""从 AI 高清参考图追踪分层 clip-path 几何
   trace.py  (env: K, SIGMA, DENS, MINAREA, MINCOMP, MEDIAN, REF, TAG)
"""
from PIL import Image, ImageDraw
import numpy as np
import json, pathlib, os
from scipy import ndimage
from skimage import measure

# 数据目录：脚本同级目录。可用环境变量 CWG_DATA 覆盖。
BASE = pathlib.Path(os.environ.get("CWG_DATA", pathlib.Path(__file__).resolve().parent.parent / "data"))
OUT  = BASE
REF  = os.environ.get("REF", str(OUT / "ai-ref-1k.png"))

K       = int(os.environ.get("K", 40))
SIGMA   = float(os.environ.get("SIGMA", 2.2))
DENS    = float(os.environ.get("DENS", 0.9))
MINAREA = float(os.environ.get("MINAREA", 60.0))
MINCOMP = int(os.environ.get("MINCOMP", 120))
MEDIAN  = int(os.environ.get("MEDIAN", 2))
TAG     = os.environ.get("TAG", "ai1")
DILATE  = float(os.environ.get("DILATE", 0.0))   # 每层向外扩（像素）

# ── 读入 & 抠白底 ──────────────────────────────────────────
im = Image.open(REF).convert("RGB")
W0, H0 = im.size
a = np.array(im).astype(np.float32)

# 白底 → alpha：亮度接近白且饱和度低算背景
mx = a.max(axis=2); mn = a.min(axis=2)
sat = (mx - mn) / np.maximum(mx, 1e-6)
# 从四角泛洪判断背景（避免吃掉角色身上的白色蕾丝/围裙）
from collections import deque
H, W = a.shape[:2]
bgmask = np.zeros((H, W), bool)
# 自适应阈值：接近纯白
seed_val = 246.0
whiteish = (mx > seed_val - 4) & (sat < 0.06)
q = deque()
for x in range(W):
    for y in (0, H - 1):
        if whiteish[y, x] and not bgmask[y, x]:
            bgmask[y, x] = True; q.append((y, x))
for y in range(H):
    for x in (0, W - 1):
        if whiteish[y, x] and not bgmask[y, x]:
            bgmask[y, x] = True; q.append((y, x))
while q:
    y, x = q.popleft()
    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny, nx = y+dy, x+dx
        if 0 <= ny < H and 0 <= nx < W and not bgmask[ny, nx] and whiteish[ny, nx]:
            bgmask[ny, nx] = True; q.append((ny, nx))

fg = ~bgmask
# 收紧：只在真正角色处
fg = ndimage.binary_opening(fg, iterations=1)
fg = ndimage.binary_closing(fg, iterations=2)
# 只保留最大连通块
cc, n = ndimage.label(fg)
if n > 1:
    sizes = ndimage.sum(fg, cc, range(1, n+1))
    keep = int(np.argmax(sizes)) + 1
    fg = (cc == keep)
    # 但把靠得很近的小块（呆毛、尾巴尖）也补回来
    for ci, sz in enumerate(sizes, start=1):
        if ci == keep: continue
        if sz < 400: continue
        comp = (cc == ci)
        d = ndimage.binary_dilation(fg, iterations=12) & comp
        if d.sum() > comp.sum() * 0.5:
            fg |= comp
print(f"fg bbox: x {np.nonzero(fg)[1].min()}..{np.nonzero(fg)[1].max()} "
      f"y {np.nonzero(fg)[0].min()}..{np.nonzero(fg)[0].max()}  px={fg.sum()}")

# 裁到 fg 的 bbox，加边距
ys, xs = np.nonzero(fg)
pad = 3
x0, x1 = xs.min()-pad, xs.max()+pad+1
y0, y1 = ys.min()-pad, ys.max()+pad+1
x0, y0 = max(0, x0), max(0, y0)
x1, y1 = min(W, x1), min(H, y1)
img = a[y0:y1, x0:x1]
fgc = fg[y0:y1, x0:x1]
H, W = img.shape[:2]
print(f"cropped to {W}x{H}")

# ── 量化（在 fg 上）────────────────────────────────────────
from sklearn.cluster import MiniBatchKMeans
px = img[fgc]
km = MiniBatchKMeans(n_clusters=K, random_state=0, n_init=10,
                     batch_size=8192, max_iter=600)
lab = km.fit_predict(px)
centers = np.clip(km.cluster_centers_, 0, 255)

BG = -1
label = np.full((H, W), BG, np.int32)
label[fgc] = lab

# 中值滤波去锯齿
for _ in range(MEDIAN):
    sm = ndimage.median_filter(np.where(fgc, label, 0), size=3)
    label = np.where(fgc, sm, BG)

def clean_small(lab_arr, min_px, fgm):
    cnt_changed = 0
    for k in range(K):
        m = (lab_arr == k)
        if not m.any(): continue
        cc, nc = ndimage.label(m)
        if nc == 0: continue
        for ci, sz in enumerate(ndimage.sum(m, cc, range(1, nc+1)), start=1):
            if sz >= min_px: continue
            comp = (cc == ci)
            ring = ndimage.binary_dilation(comp, iterations=1) & ~comp
            nb = lab_arr[ring]
            nb = nb[(nb != k) & (nb >= 0)]
            if nb.size == 0: continue
            v, c = np.unique(nb, return_counts=True)
            lab_arr[comp] = v[np.argmax(c)]
            cnt_changed += 1
    return lab_arr, cnt_changed

label, nchg = clean_small(label.copy(), MINCOMP, fgc)

# ── 轮廓提取 + 平滑 ────────────────────────────────────────
def smooth_ring(pts, sigma, dens):
    p = np.asarray(pts, float)
    d = np.linalg.norm(np.diff(np.vstack([p, p[0]]), axis=0), axis=1)
    per = d.sum()
    if per < 6: return None
    n = max(16, int(per * dens))
    s = np.concatenate([[0], np.cumsum(d)]); s /= s[-1]
    su = np.linspace(0, 1, n, endpoint=False)
    xs = np.interp(su, s, np.concatenate([p[:,0], p[:1,0]]))
    ys = np.interp(su, s, np.concatenate([p[:,1], p[:1,1]]))
    xs = ndimage.gaussian_filter1d(xs, sigma, mode="wrap")
    ys = ndimage.gaussian_filter1d(ys, sigma, mode="wrap")
    q = np.stack([xs, ys], 1)
    keep = [0]
    for i in range(1, n):
        if np.linalg.norm(q[i]-q[keep[-1]]) >= 0.55:
            keep.append(i)
    if len(keep) < 3: return None
    if np.linalg.norm(q[keep[-1]]-q[keep[0]]) < 0.55 and len(keep) > 3:
        keep = keep[:-1]
    return q[keep]

def offset_ring(q, off):
    """沿外法线把闭合多边形整体外扩 off 像素（用面积符号判方向）"""
    if abs(off) < 1e-9 or len(q) < 3:
        return q
    n = len(q)
    nxt = np.roll(q, -1, axis=0)
    prv = np.roll(q, 1, axis=0)
    t = nxt - prv
    ln = np.linalg.norm(t, axis=1)
    ln[ln < 1e-9] = 1e-9
    t /= ln[:, None]
    # 法线（逆时针时指向外侧）
    nrm = np.stack([t[:, 1], -t[:, 0]], axis=1)
    if signed_area(q) < 0:
        nrm = -nrm
    return q + nrm * off


def signed_area(p):
    x = p[:,0]; y = p[:,1]
    return 0.5*float(np.dot(x, np.roll(y,-1)) - np.dot(y, np.roll(x,-1)))

def point_in(pt, poly):
    x, y = pt; inside = False; n = len(poly)
    for i in range(n):
        x1,y1 = poly[i]; x2,y2 = poly[(i+1)%n]
        if ((y1>y)!=(y2>y)) and (x < (x2-x1)*(y-y1)/(y2-y1+1e-12)+x1):
            inside = not inside
    return inside

allrings = []
for k in range(K):
    m = (label == k)
    if m.sum() < MINAREA: continue
    pad_ = np.zeros((H+2, W+2), np.float32)
    pad_[1:-1, 1:-1] = m.astype(np.float32)
    rings = []
    for c in measure.find_contours(pad_, 0.5):
        pts = np.stack([c[:,1]-1.0, c[:,0]-1.0], 1)
        if len(pts) < 8: continue
        if np.linalg.norm(pts[0]-pts[-1]) < 1e-9: pts = pts[:-1]
        sm = smooth_ring(pts, SIGMA, DENS)
        if sm is None: continue
        if DILATE > 0:
            sm = offset_ring(sm, DILATE)
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
npt = sum(len(r["pts"]) for r in allrings)
print(f"TAG{TAG} K={K} SIGMA={SIGMA} DENS={DENS} MINAREA={MINAREA} MINCOMP={MINCOMP}")
print(f"  rings={len(allrings)} pts={npt} cleaned={nchg} canvas={W}x{H}")

# ── 重建误差 ──────────────────────────────────────────────
canvas = np.zeros((H, W, 3), np.float32)
cover = np.zeros((H, W), bool)
for r in allrings:
    col = tuple(int(r["color"][i:i+2], 16) for i in (1,3,5))
    im1 = Image.new("1", (W, H), 0)
    ImageDraw.Draw(im1).polygon([tuple(v) for v in r["pts"].tolist()], fill=1)
    mm = np.array(im1, bool)
    canvas[mm] = col; cover |= mm

mae = float(np.abs(canvas[fgc] - img[fgc]).mean())
print(f"  recon MAE={mae:.2f} cover={cover[fgc].mean()*100:.2f}%")
Image.fromarray(canvas.astype(np.uint8)).save(OUT / f"recon_{TAG}.png")

json.dump({"w": W, "h": H,
           "rings": [{"c": r["color"], "d": r["depth"], "a": round(r["area"],1),
                      "p": [[round(float(x),2), round(float(y),2)] for x,y in r["pts"].tolist()]}
                     for r in allrings]},
          open(OUT / f"layers_{TAG}.json", "w", encoding="utf-8"), separators=(",", ":"))
print(f"  json {(OUT / f'layers_{TAG}.json').stat().st_size} bytes")
