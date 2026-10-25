# css-whale-girl

**用 7,348 个 `clip-path` 多边形画一张插画。零图片、零 SVG、零 Canvas、零 JavaScript。**

[在线看](https://whale.chu-2.moe) · [制作记录（一万四千字）](https://chronicle.linyucion.com/works/001-css-whale-girl/making-of/) · [为什么这么做](https://chronicle.linyucion.com/works/001-css-whale-girl/)

```
文件大小        4.04 MB
绘图节点        7,348 个 <b>
clip-path       7,351 处
@keyframes      12 组
图片 / SVG /
Canvas / JS     全部 0
逐像素 MAE      9.69 / 255
```

---

## 这是什么

一条把位图描摹成**纯 HTML + CSS** 的管线。输入一张插画，输出一个单文件
HTML —— 打开就长成那张画，没有任何外部依赖。

和社区的同类项目（[image-to-css-art](https://github.com/AvroraCL/image-to-css-art)、
[img2css](https://github.com/javierbyte/img2css)）相比，这条路线的三个不同选择：

| 选择 | 我们的做法 | 为什么 |
|---|---|---|
| **不用局部渐变** | 每个多边形一个纯色 | 测过：套渐变后 MAE 从 11.03 **涨到** 18.65 |
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
# 生成阶段：Python 3.10+，需要 numpy / scipy / scikit-learn / scikit-image / Pillow
pip install -r requirements.txt

# 1. 量化 + 描轮廓
python src/trace.py 参考图.png

# 2.（可选）描边层
python src/inkfix.py

# 3.（可选）残差补偿
python src/residual.py

# 4. 生成 HTML
python src/build_site.py data/layers_res3.json art/output.html

# 5. 验证误差（这一步很重要，见下面）
python measure/remeasure_mae.py
```

数据目录默认是仓库里的 `data/`，可以用环境变量 `CWG_DATA` 覆盖。

**查看阶段什么都不需要** —— 生成的 HTML 双击就能开。

---

## 为什么单独有个测量脚本

这个项目的两天时间浪费在**测量脚本本身是错的**：

1. `Image.transform` 参数写反 → MAE 虚高到 105
2. 参考图是白底、渲染图是深底 → 虚高到 147

修完之后，测法才变成现在的口径：

```
页面设成参考图的原生尺寸（743×1095），角色 1:1 铺满、不做任何缩放，
截完图直接逐像素比。
```

`measure/remeasure_mae.py` 是可复现的版本。**如果你要改管线，
先跑它拿到基线，改完再跑一次。** 不要凭肉眼判断好坏 —— 我们试过，
肉眼几乎看不出差别的十二张图，当时的数字说它们差了 2.8 倍。

完整的翻车记录见 [`docs/failures.md`](docs/failures.md)。

---

## 目录

```
src/          管线（Python，只在生成时用）
measure/      可复现的 MAE 测量
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

所以插画资产用 CC BY-NC-SA：**开放、非商用、相同方式共享**，
和社区二创的性质一致。

---

## 这个仓库不包含

- 视频管线（69 秒短片、字幕、配乐）
- 文章排版转换器
- 部署脚本

那些和「画这张图」无关，放进来只会让这个仓库变重。
