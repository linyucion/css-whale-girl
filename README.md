# css-whale-girl

**An illustration drawn with 7,348 `clip-path` polygons. Zero images, zero SVG, zero Canvas, zero JavaScript.**

[Live](https://whale.chu-2.moe) · [Build log (14,000 characters, Chinese)](https://chronicle.linyucion.com/works/001-css-whale-girl/making-of/) · [Why](https://chronicle.linyucion.com/works/001-css-whale-girl/)

> English below · [中文在下面](#中文)

```
File size        4.04 MB
Drawing nodes    7,348  <b> elements
clip-path        7,351  declarations
@keyframes       12     groups
Images / SVG /
Canvas / JS      0      of each
```

> **On the per-pixel error figure.** The article mentions `9.69`. After
> rewriting the measurement script I **could not reproduce it** — the same
> artifact measures 56.55.
>
> So that number is not stated here. The repo ships a reproducible
> measurement script; measure it yourself. Details in
> [`docs/failures.md`](docs/failures.md) §9.
>
> A repo that claims "error is X" when others measure something else is
> worse than one that says nothing.

---

## What this is

A pipeline that traces a bitmap into **pure HTML + CSS**. Give it an
illustration, get a single self-contained HTML file — open it and the
picture is there, with no external dependencies at all.

Compared to similar community projects
([image-to-css-art](https://github.com/AvroraCL/image-to-css-art),
[img2css](https://github.com/javierbyte/img2css)), this route makes three
different choices:

| Choice | What we do | Why |
|---|---|---|
| **No local gradients** | one flat colour per polygon | measured: adding gradients made error go **up**, 11.03 → 18.65 |
| **No bridges for holes** | depth ordering, deeper layers cover shallower | no bridge generation; the cost is more layers |
| **Residual compensation pass** | re-cluster the worst-error pixels, append a deeper layer | mouth, eye highlights, lace holes all come back this way |

Full comparison in [`docs/alternatives.md`](docs/alternatives.md).

---

## Pipeline

```
reference image
  → K-means colour quantization (K≈72)
  → marching squares per colour region (sub-pixel contours)
  → arc-length resample + periodic Gaussian smoothing
  → Douglas-Peucker simplification
  → depth ordering (painter's algorithm)
  → [optional] stroke layer: extract lineart separately
  → [optional] residual layer: re-cluster worst-error pixels
  → emit <b class="rN"></b> + clip-path: polygon(...)
```

All coordinates are percentages, so it scales to any size.

Parameters and **why they were chosen** are in
[`docs/pipeline.md`](docs/pipeline.md).

---

## Usage

```bash
# Generation: Python 3.10+, needs numpy / scipy / scikit-learn / scikit-image / Pillow
pip install -r requirements.txt

# 1. quantize + trace contours
python src/trace.py reference.png

# 2. (optional) stroke layer
python src/inkfix.py

# 3. (optional) residual compensation
python src/residual.py

# 4. build the HTML
python src/build_site.py data/layers_res3.json art/output.html

# 5. verify the error (this step matters — see below)
python measure/remeasure_mae.py --ref reference.png
```

The data directory defaults to `data/` in the repo; override with `CWG_DATA`.

**Viewing needs nothing at all** — the generated HTML opens by double-click.

---

## Why there is a separate measurement script

Two days of this project were spent on **the measurement script itself being wrong**:

1. `Image.transform` parameters swapped → error inflated to 105
2. Reference on white, render on dark → inflated to 147
3. Render at 100% width then downscaled → resampling blur counted as drawing error

Once fixed, the method became:

```
Set the page to the reference's native size (743×1095),
render the character 1:1 with no scaling, screenshot, compare per pixel.
```

`measure/remeasure_mae.py` is the reproducible version. **If you change the
pipeline, run it first for a baseline, then again after.** Don't judge by eye —
we tried: twelve thumbnails that look identical were reported by the broken
ruler as differing by 2.8×.

Full post-mortem in [`docs/failures.md`](docs/failures.md).

---

## Where the reference image comes from

The pipeline needs a reference image to run. It is not in this repo (size +
licensing), but its provenance is documented:

| Step | What |
|---|---|
| 1. Original | a **143×198** pixel sprite circulating in the community. Too low-res — upscaling only gives mush |
| 2. AI redraw | image-to-image into an **864×1152** line art. This is **redrawing**, not interpolating — lace scallops, whale embroidery, the gold bow, individual hair strands are recovered in this step |
| 3. Tool | [Agnes AI](https://apihub.agnes-ai.com) image endpoint (`agnes-image-2.1-flash` / `2.5-flash` / `2.0-flash`), called through DeepSeek Harness's `agnes-image` skill |
| 4. Crop | 864×1152 trimmed of whitespace → **743×1095**, the size all measurements use |

**Why step 2 is essential**: automatic contour tracing can only trace what is
already in the image. There are no lace scallops in a 143×198 sprite — you'd
trace a blob. Let the AI recover the structure first, then trace.

---

## Layout

```
src/          pipeline (Python, generation time only)
measure/      reproducible per-pixel measurement
art/          the finished HTML (CC BY-NC-SA, see below)
docs/
  pipeline.md     every parameter and the trade-off behind it
  failures.md     the wrong turns (the most valuable file here)
  alternatives.md technical comparison with similar projects
```

---

## Licence

- **Code** (`src/`, `measure/`): [MIT](LICENSE)
- **Artwork** (`art/`): [CC BY-NC-SA 4.0](LICENSE-ART)
- **The reference image is not included**

The character "Whale Girl" is a **community-created derivative**, not an
official DeepSeek character:

1. The deepest layer is the **orca** in DeepSeek's official logo
2. The middle layer is the anthropomorphic design built by the community and
   several Bilibili creators
3. The outermost layer is what this repo does — redrawing it once more, a
   different way

Hence CC BY-NC-SA for the artwork: open, non-commercial, share-alike.

---

## Not included

- the video pipeline (69 s short, subtitles, music)
- the article-to-WeChat layout converter
- deployment scripts

None of that has anything to do with "drawing this picture"; including it
would just make the repo heavier.

---

# 中文

**用 7,348 个 `clip-path` 多边形画一张插画。零图片、零 SVG、零 Canvas、零 JavaScript。**

```
文件大小        4.04 MB
绘图节点        7,348 个 <b>
clip-path       7,351 处
@keyframes      12 组
图片 / SVG /
Canvas / JS     全部 0
```

> **关于逐像素误差**：文章里出现过 `9.69`，但我重写测量脚本之后
> **复现不出来**（同一份产物测到 56.55）。所以这个数字不写在这里。
>
> 仓库带了一个可复现的测量脚本，你可以自己测 —— 具体经过见
> [`docs/failures.md`](docs/failures.md) 第九条。
>
> 一个仓库说「误差是 X」而别人测出来不是 X，比不说更糟。

---

## 这是什么

一条把位图描摹成**纯 HTML + CSS** 的管线。输入一张插画，输出一个单文件
HTML —— 打开就长成那张画，没有任何外部依赖。

和社区的同类项目（[image-to-css-art](https://github.com/AvroraCL/image-to-css-art)、
[img2css](https://github.com/javierbyte/img2css)）相比，这条路线的三个不同选择：

| 选择 | 我们的做法 | 为什么 |
|---|---|---|
| **不用局部渐变** | 每个多边形一个纯色 | 测过：套渐变之后误差反而**变大**，11.03 → 18.65 |
| **孔洞不用桥接** | 按深度排序，让更深的层盖住 | 不算桥，代价是层数变多 |
| **加残差补偿层** | 误差最大的那批像素再聚类一次 | 嘴巴、眼高光、蕾丝孔洞全靠它捞回来 |

详细对比见 [`docs/alternatives.md`](docs/alternatives.md)。

---

## 管线

```
参考图
  → K-means 颜色量化（K≈72）
  → 每个颜色区域用 marching squares 提亚像素轮廓
  → 弧长重采样 + 周期高斯平滑
  → Douglas-Peucker 简化
  → 深度排序（painter's algorithm）
  → [可选] 描边层：把 lineart 单独提一层
  → [可选] 残差层：误差最大的像素再聚类
  → 输出 <b class="rN"></b> + clip-path: polygon(...)
```

坐标全部用百分比，所以能任意缩放。

每一步的参数取舍、以及**为什么这么选**，见 [`docs/pipeline.md`](docs/pipeline.md)。

---

## 用法

```bash
pip install -r requirements.txt

python src/trace.py 参考图.png       # 量化 + 描轮廓
python src/inkfix.py                 # （可选）描边层
python src/residual.py               # （可选）残差补偿
python src/build_site.py data/layers_res3.json art/output.html
python measure/remeasure_mae.py --ref 参考图.png
```

数据目录默认 `data/`，可用环境变量 `CWG_DATA` 覆盖。
**查看阶段什么都不需要** —— 生成的 HTML 双击就能开。

---

## 为什么单独有个测量脚本

这个项目的两天时间浪费在**测量脚本本身是错的**：

1. `Image.transform` 参数写反 → 误差虚高到 105
2. 参考图白底、渲染图深底 → 虚高到 147
3. 页面 100% 宽再缩回目标尺寸 → 缩放模糊被算进「绘制误差」

修完之后口径才固定：

```
页面设成参考图的原生尺寸（743×1095），角色 1:1 铺满、不做任何缩放，
截完图直接逐像素比。
```

**改管线之前先跑它拿到基线，改完再跑一次。** 不要凭肉眼判断 ——
我们试过，肉眼几乎看不出差别的十二张图，当时的坏尺子说它们差了 2.8 倍。

完整翻车记录见 [`docs/failures.md`](docs/failures.md)。

---

## 参考图从哪来

管线需要一张参考图才能跑。它不在本仓库里（体积 + 授权），但来源是清楚的：

| 步骤 | 内容 |
|---|---|
| 1. 原始素材 | 社区流传的一张 **143×198** 像素精灵图。分辨率太低，放大只会得到糊色块 |
| 2. AI 重绘 | 用**图生图**把它重绘成 **864×1152** 的线稿 —— 这是「重新画了一遍」，不是插值放大。蕾丝扇贝、鲸鱼绣样、金色蝴蝶结、发丝分缕是这一步补出来的 |
| 3. 生成工具 | [Agnes AI](https://apihub.agnes-ai.com) 的图片接口（`agnes-image-2.1-flash` / `2.5-flash` / `2.0-flash`），通过 DeepSeek Harness 的 `agnes-image` skill 调用 |
| 4. 裁剪 | 864×1152 裁掉留白 → **743×1095**，也就是所有测量用的尺寸 |

**为什么第 2 步不能省**：自动轮廓追踪只能描出图里已有的东西。
143×198 里根本没有蕾丝扇贝的细节，描出来只会是一团色块。

---

## 目录

```
src/          管线（Python，只在生成时用）
measure/      可复现的逐像素测量
art/          成品 HTML（CC BY-NC-SA，见下）
docs/
  pipeline.md     每一步的参数与取舍
  failures.md     走错的路（这个仓库最重要的文件）
  alternatives.md 和社区同类项目的技术对比
```

---

## 许可证

- **代码**（`src/`、`measure/`）：[MIT](LICENSE)
- **插画成品**（`art/`）：[CC BY-NC-SA 4.0](LICENSE-ART)
- **输入参考图不包含在本仓库内**

角色「鲸鱼娘」是**社区共同创作的二创形象**，不是 DeepSeek 官方角色：

1. 最深一层是 DeepSeek 官方标志里那条**虎鲸**
2. 中间一层是社区和 B 站几位 UP 主建立的拟人形象
3. 最外一层才是这个仓库做的事情 —— 用一种新的方式把它重新画了一遍

所以插画资产用 CC BY-NC-SA：开放、非商用、相同方式共享。

---

## 这个仓库不包含

- 视频管线（69 秒短片、字幕、配乐）
- 文章排版转换器
- 部署脚本

那些和「画这张图」无关，放进来只会让这个仓库变重。
