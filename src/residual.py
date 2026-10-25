# -*- coding: utf-8 -*-
"""residual.py — 残差补偿层（迭代精修）
   原理：当前图层栈重建出的画面与参考图逐像素相减，取误差大的像素，
        对这些像素重新聚类成若干颜色，再把它们的轮廓作为**顶层**补上。
   好处：
     - 自动找回 K-means 因为「面积太小」而丢掉的细节（嘴巴、眼睛高光、
       蕾丝孔洞、金色蝴蝶结的高光…），不需要人工干预。
     - 每一轮只补「真正错的地方」，层数增长受控。
     - 直接最小化 MAE，所以还原度与观感同时改善。
"""
from PIL import Image, ImageDraw
import numpy as np
import json, pathlib, os, sys
from scipy import ndimage
from skimage import measure
from sklearn.cluster import MiniBatchKMeans

# 数据目录：脚本同级目录。可用环境变量 CWG_DATA 覆盖。
BASE = pathlib.Path(os.environ.get("CWG_DATA", pathlib.Path(__file__).resolve().parent.parent / "data"))
REF  = BASE / "ai-ref-1k.png"

K2      = int(os.environ.get("K2", 18))       # 残差聚类色数
THRESH  = float(os.environ.get("THRESH", 34))  # 触发残差的像素误差阈值
MINPIX  = int(os.environ.get("MINPIX", 26))   # 残差连通块最小像素
ROUNDS  = int(os.environ.get("ROUNDS", 2))
SIGMA   = float(os.environ.get("SIGMA", 0.9))
DENS    = float(os.environ.get("DENS", 1.25))
MINAREA = float(os.environ.get("MINAREA", 4.0))
GROW    = float(os.environ.get("GROW", 0.32))

def hexs(v):
    return "#%02x%02x%02x" % tuple(int(round(min(255, max(0, c)))) for c in v)

def signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5*float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

def point_in(pt, poly):
    x, y = pt; inside = False; n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2-x1)*(y-y1)/(y2-y1+1e-12)+x1):
            inside = not inside
    return inside

def offset_ring(q, off):
    if abs(off) < 1e-9 or len(q) < 3: return q
    n = len(q)
    t = np.roll(q, -1, axis=0) - np.roll(q, 1, axis=0)
    ln = np.linalg.norm(t, axis=1); ln[ln < 1e-9] = 1e-9
    t /= ln[:, None]
    nrm = np.stack([t[:, 1], -t[:, 0]], 1)
    if signed_area(q) < 0: nrm = -nrm
    return q + nrm*off

def smooth_ring(pts, sigma, dens):
    p = np.asarray(pts, float)
    d = np.linalg.norm(np.diff(np.vstack([p, p[0]]), axis=0), axis=1)
    per = d.sum()
    if per < 4: return None
    n = max(12, int(per*dens))
    s = np.concatenate([[0], np.cumsum(d)]); s /= s[-1]
    su = np.linspace(0, 1, n, endpoint=False)
    xs = np.interp(su, s, np.concatenate([p[:, 0], p[:1, 0]]))
    ys = np.interp(su, s, np.concatenate([p[:, 1], p[:1, 1]]))
    xs = ndimage.gaussian_filter1d(xs, sigma, mode="wrap")
    ys = ndimage.gaussian_filter1d(ys, sigma, mode="wrap")
    q = np.stack([xs, ys], 1)
    keep = [0]
    for i in range(1, n):
        if np.linalg.norm(q[i]-q[keep[-1]]) >= 0.45:
            keep.append(i)
    if len(keep) < 3: return None
    if len(q[keep[-1]]-q[keep[0]]) < 0.45 and len(keep) > 3:
        keep = keep[:-1]
    return q[keep]

def rasterize(rings, W, H):
    canvas = np.zeros((H, W, 3), np.float32)
    owner = np.full((H, W), -1, np.int32)
    for i, r in enumerate(rings):
        im1 = Image.new("1", (W, H), 0)
        ImageDraw.Draw(im1).polygon([tuple(v) for v in r["p"]], fill=1)
        m = np.array(im1, bool)
        col = r.get("_rgb")
        if col is None:
            col = np.array([int(r["c"][j:j+2], 16) for j in (1, 3, 5)], np.float32)
            r["_rgb"] = col
        canvas[m] = col
        owner[m] = i
    return canvas, owner

def main():
    src = sys.argv[1]
    dst = sys.argv[2]
    d = json.load(open(src, encoding="utf-8"))
    W, H = int(d["w"]), int(d["h"])
    rings = d["rings"]

    a = np.array(Image.open(REF).convert("RGB")).astype(np.float32)
    mx = a.max(axis=2); mn = a.min(axis=2)
    sat = (mx-mn)/np.maximum(mx, 1e-6)
    fgall = ~((mx > 242) & (sat < 0.06))
    ys, xs = np.nonzero(fgall)
    x0 = max(0, xs.min()-3); y0 = max(0, ys.min()-3)
    ref = a[y0:y0+H, x0:x0+W]
    fg = fgall[y0:y0+H, x0:x0+W]

    for rnd in range(ROUNDS):
        canvas, _ = rasterize(rings, W, H)
        err = np.abs(canvas - ref).mean(axis=2)
        bad = (err > THRESH) & fg
        bad = ndimage.binary_opening(bad, iterations=1)
        # 去掉过小的连通块
        cc, n = ndimage.label(bad)
        if n == 0:
            print(f"round {rnd}: no residual"); break
        sizes = ndimage.sum(bad, cc, range(1, n+1))
        keepmask = np.zeros_like(bad)
        for ci, sz in enumerate(sizes, start=1):
            if sz >= MINPIX:
                keepmask |= (cc == ci)
        bad = keepmask
        npx = int(bad.sum())
        if npx < 200:
            print(f"round {rnd}: residual too small ({npx})"); break
        print(f"round {rnd}: residual px={npx} "
              f"({100*npx/max(1,fg.sum()):.2f}% of fg) meanErr={err[bad].mean():.1f}")

        # 残差像素聚类
        cols = ref[bad]
        k = min(K2, max(2, len(cols)//40))
        km = MiniBatchKMeans(n_clusters=k, random_state=0, n_init=8,
                             batch_size=4096, max_iter=400)
        lab = km.fit_predict(cols)
        centers = np.clip(km.cluster_centers_, 0, 255)

        rlabels = np.full((H, W), -1, np.int32)
        rlabels[bad] = lab
        rlabels = ndimage.median_filter(np.where(bad, rlabels, -1), size=3)
        rlabels = np.where(bad, rlabels, -1)

        new = []
        base_depth = max((r.get("d", 0) for r in rings), default=0) + 1
        for kk in range(k):
            m = (rlabels == kk)
            if m.sum() < MINAREA: continue
            pad = np.zeros((H+2, W+2), np.float32)
            pad[1:-1, 1:-1] = m.astype(np.float32)
            rr = []
            for c in measure.find_contours(pad, 0.5):
                pts = np.stack([c[:, 1]-1.0, c[:, 0]-1.0], 1)
                if len(pts) < 6: continue
                if np.linalg.norm(pts[0]-pts[-1]) < 1e-9: pts = pts[:-1]
                sm = smooth_ring(pts, SIGMA, DENS)
                if sm is None: continue
                if GROW > 0: sm = offset_ring(sm, GROW)
                aa = abs(signed_area(sm))
                if aa < MINAREA*0.6: continue
                rr.append([sm, aa, 0])
            if not rr: continue
            rr.sort(key=lambda t: -t[1])
            for i, t in enumerate(rr):
                probe = t[0][0]
                t[2] = sum(1 for j, o in enumerate(rr)
                           if i != j and o[1] > t[1] and point_in(probe, o[0]))
            col = hexs(centers[kk])
            for pts, aa, dd in rr:
                new.append({"c": col, "d": base_depth + dd, "a": round(float(aa), 1),
                            "p": [[round(float(x), 2), round(float(y), 2)]
                                  for x, y in pts.tolist()]})
        new.sort(key=lambda r: (r["d"], -r["a"]))
        rings.extend(new)
        print(f"  added {len(new)} residual rings (k={k})")

    # 清理内部键
    for r in rings:
        r.pop("_rgb", None)
    json.dump({"w": W, "h": H, "rings": rings},
              open(dst, "w", encoding="utf-8"), separators=(",", ":"))
    sz = pathlib.Path(dst).stat().st_size
    # 最终 numpy 误差
    canvas, _ = rasterize(rings, W, H)
    err = np.abs(canvas - ref).mean(axis=2)
    print(f"DONE rings={len(rings)}  nMAE_fg={err[fg].mean():.2f} "
          f"nP95={np.percentile(err[fg],95):.2f}  {sz/1048576:.2f} MB")

if __name__ == "__main__":
    main()
