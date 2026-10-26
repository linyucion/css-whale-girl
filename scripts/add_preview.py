# -*- coding: utf-8 -*-
"""add_preview.py —— 给 README 加预览图，修 reference.png 的说明

## 修的是什么

用户指出两个问题：

1. **仓库里一张图都没有** —— 一个讲「画插画」的仓库，README 里看不到那张画
2. **命令里写着 `python src/trace.py reference.png`**，
   但仓库里没有 `reference.png` 这个文件，读者会以为漏了

## 为什么把参考图也放进来

之前 README 说「参考图不在仓库里（体积 + 授权）」。
但换个角度：参考图是整条管线的起点，画出来的是它的衍生物，
而衍生物已经以 CC BY-NC-SA 放着了 —— 起点放在一起反而更清楚。

体积 748 KB，可以接受。
"""
import pathlib

d = pathlib.Path(r"C:\Users\linyu\Desktop\Linyucion\css-whale-girl")

EN_OLD = "**An illustration drawn with 7,348 `clip-path` polygons. Zero images, zero SVG, zero Canvas, zero JavaScript.**"
EN_NEW = EN_OLD + '\n\n<img src="docs/preview.png" alt="Whale Girl, drawn with 7,348 clip-path polygons" width="360">'

ZH_OLD = "**用 7,348 个 `clip-path` 多边形画一张插画。零图片、零 SVG、零 Canvas、零 JavaScript。**"
ZH_NEW = ZH_OLD + '\n\n<img src="docs/preview.png" alt="鲸鱼娘，7348 个 clip-path 多边形" width="360">'

# (文件名, 旧, 新, 说明)
EDITS = [
    ("README.md", EN_OLD, EN_NEW, "英文版加预览图"),
    ("README.zh-CN.md", ZH_OLD, ZH_NEW, "中文版加预览图"),

    ("README.md",
     "# 1. quantize + trace contours\npython src/trace.py reference.png",
     "# NOTE: the reference image ships as docs/reference.png. Copy it to\n"
     "# whatever path you pass in, or point --ref at it directly.\n\n"
     "# 1. quantize + trace contours\npython src/trace.py reference.png",
     "英文版命令加说明"),

    ("README.md",
     "The pipeline needs a reference image to run. It is not in this repo (size +\nlicensing), but its provenance is documented:",
     "The pipeline needs a reference image to run. **A copy ships at\n"
     "[`docs/reference.png`](docs/reference.png)**; its provenance:",
     "英文版参考图段落"),

    ("README.md",
     "- **The reference image is not included**",
     "- **The reference image** (`docs/reference.png`) ships for reference only",
     "英文版许可段"),

    ("README.zh-CN.md",
     "管线需要一张参考图才能跑。它不在本仓库里（体积 + 授权），但来源是清楚的：",
     "管线需要一张参考图才能跑。**仓库里带了一份：[`docs/reference.png`](docs/reference.png)**，来源如下：",
     "中文版参考图段落"),

    ("README.zh-CN.md",
     "- **输入参考图不包含在本仓库内**",
     "- **参考图**（`docs/reference.png`）随仓库提供，仅供对照",
     "中文版许可段"),
]


def main():
    ok = bad = 0
    for name, old, new, why in EDITS:
        p = d / name
        t = p.read_text(encoding="utf-8")
        if old in t:
            p.write_text(t.replace(old, new, 1), encoding="utf-8", newline="\n")
            print(f"  ✓ {why}")
            ok += 1
        else:
            print(f"  ✗ 未匹配：{why}")
            bad += 1
    print(f"\n  {ok} 条应用 / {bad} 条未匹配")


if __name__ == "__main__":
    main()
