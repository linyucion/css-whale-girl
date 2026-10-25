import numpy as np, math
from PIL import Image

SRC = r"C:\Users\linyu\Desktop\Linyucion\dsh\.ref-whale\tight.png"
im = Image.open(SRC).convert("RGBA")
W, H = im.size
print("src", W, H)

# 放大 3 倍再量化，轮廓更平滑
Z = 3
big = im.resize((W*Z, H*Z), Image.LANCZOS)

# 转 RGB（透明区填成背景深色，便于统一处理）
bg = Image.new("RGBA", big.size, (8, 14, 26, 255))
flat = Image.alpha_composite(bg, big).convert("RGB")

q = flat.quantize(colors=16, method=Image.MEDIANCUT, dither=Image.NONE)
pal = q.getpalette()
arr = np.array(q)          # palette index per pixel
cnt = np.bincount(arr.ravel(), minlength=16)

print("\nidx   count     hex       rgb")
order = np.argsort(-cnt)
for i in order:
    if cnt[i] == 0:
        continue
    R, G, B = pal[i*3], pal[i*3+1], pal[i*3+2]
    print(f"{i:3d} {cnt[i]:8d}  #{R:02x}{G:02x}{B:02x}  ({R},{G},{B})")
