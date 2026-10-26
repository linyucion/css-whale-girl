# css-whale-girl

**English** · [中文](README.zh-CN.md)

**An illustration drawn with 7,348 `clip-path` polygons. Zero images, zero SVG, zero Canvas, zero JavaScript.**

[Live](https://whale.chu-2.moe) · [Build log (14,000 characters, Chinese)](https://chronicle.linyucion.com/works/001-css-whale-girl/making-of/) · [Why](https://chronicle.linyucion.com/works/001-css-whale-girl/)

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
