---
name: agf-writing-pptx-reports
description: 用 python-pptx 写"现代化中文制度 / 党政 / 企业宣贯 PPT"（含决议书提报、评审报告、管理办法、培训宣贯等 23 页量级 deck）。当用户要求程序化生成 PPT 且抱怨"老土 / 字体丑 / 表格乱 / 文字溢出 / 中文字体 fallback / 缺架构图"时启用——`python-pptx` 默认 API 一堆坑必须主动避开。提供：路径决策 / 设计 token / 12 个 helper 全套 / 7 个致丑反模式 / 12 个关键技巧 / LibreOffice 渲染验证闭环 / 跨平台中文字体生效 lxml 写法 / 配套 draw.io 画架构图选型（中文字体、配色、8 大坑、嵌入 PPT 链路）。
---

# 写 pptx 报告 — 高密度实战手册

> 沉淀自《AI 4A 架构评审管理办法》v1.0 PPT 实战（23 页，GAC 红主调，含双视图嵌入流程图）
> 全部踩过 + 验证过的坑与方法，不含理论水文

## 何时用本 skill

| 信号 | 用本 skill |
|---|:--:|
| 需要程序化生成 PPT（数据驱动 / 模板批量 / 内容版本化） | ✅ |
| 中文制度 / 党政 / 企业内部宣贯 deck | ✅ |
| 用户反馈"老土 / 字体丑 / 表格乱 / 文字溢出 / 中文字体 fallback" | ✅ |
| 内容会反复迭代，PPT 必须从源码可重生成 | ✅ |
| 需要 mermaid 流程图嵌入 + 双视图卡片化 | ✅ |
| 高度自由排版 / 视觉冲击型营销 deck | ❌ 直接 Keynote / Figma |
| 复杂动画 / 视频嵌入 | ❌ python-pptx 弱项 |
| 一次性单页海报 | ❌ 直接画 |
| 要 docx / xlsx | ❌ 转 writing-docx-reports / xlsx skill |

## 路径决策（4 选 1）

| 路径 | 何时选 | 代价 |
|---|---|---|
| **手动复制 .pptx 模板编辑** | 一次性 deck / 设计师介入 / 不需重生成 | 几分钟；后续维护成本高 |
| **`pptx` skill 局部改** | 已有 .pptx 做小幅修改（≤ 5 张 slide / 仅换文字）| 中等；不适合从零生成 |
| **基于模板 + `python-pptx` 混合** ⭐ | 仓库已有 .pptx 模板 / 视觉风格已定 / 需版本化 + 重生成 | 一次 ~500 行；保留模板视觉投入 + 代码可重跑 |
| **`python-pptx` 全定制** | 没现成模板 / 视觉自己定义 / 跨平台中文 / 23+ 页量级 | 一次 ~800 行 Python，复用率 90% |

判定经验：
- **本仓库 `template/` 已有 1 个 .pptx 模板**（`Template.pptx`，coral 团队风）→ 默认走"基于模板 + python-pptx 混合"，不要重造视觉
- **用户说"老土 / 中文字体不对 / 表格乱"** 基本意味着要"模板混合"或"全定制"——只有"手动复制"路径根治不了
- **用户给了具体模板路径**（如 "用 Template.pptx"）→ 必走"模板混合"路径，并先读对应的 `template-*-guide.md`

## ★ 基于已有 .pptx 模板生成（推荐路径详解）

适用：仓库 `template/` 下已有 `.pptx` 设计模板，用户希望保留模板视觉 + 程序化生成内容。

**前置必看**：每个已落地的模板都有一份 `template-*-guide.md`（在本 skill 目录下），例如 `template-team-guide.md`。**先读 guide 再动手**——guide 会告诉你这个模板的可渲染 slide 范围、配色、字体覆盖坑、6 类页面用法、踩坑清单。

### Step 1 — 模板分析三件套（先看再动）

依赖 `.claude/skills/pptx/`（Anthropic 提供的低层 .pptx 工具 skill）。

```bash
# 复制模板到临时目录
mkdir -p /tmp/template-analysis && cp template/Template.pptx /tmp/template-analysis/

# 1. 缩略图网格（看每张 slide 视觉概览）
python .claude/skills/pptx/scripts/thumbnail.py /tmp/template-analysis/Template.pptx --cols 4
# 产物：thumbnails-1.jpg, thumbnails-2.jpg ...

# 2. unpack 看 XML 结构（theme / master / layout）
python .claude/skills/pptx/scripts/office/unpack.py /tmp/template-analysis/Template.pptx /tmp/template-analysis/unpacked/
# 产物：unpacked/ppt/{theme,slideMasters,slideLayouts,slides}/*.xml

# 3. 用 python-pptx dump slide → layout 映射 + placeholder 信息（自己写脚本）
```

dump 脚本骨架：

```python
from pptx import Presentation
prs = Presentation("/tmp/template-analysis/Template.pptx")
for i, layout in enumerate(prs.slide_layouts):
    print(f"layout[{i}] '{layout.name}' — {len(layout.placeholders)} placeholders")
    for ph in layout.placeholders:
        idx = ph.placeholder_format.idx
        ptype = ph.placeholder_format.type
        print(f"  ph[{idx}] type={ptype}")
for i, slide in enumerate(prs.slides, 1):
    print(f"slide{i} → '{slide.slide_layout.name}'")
```

**看 dump 结果找规律**：哪些 layout 真被 slide 用过？用得多的是核心 layout，没被用的是"备用 layout"——你也基本不会用到。

### Step 2 — Placeholder vs Shape 概念区分（最关键认知）

| 项 | Placeholder | Shape |
|---|---|---|
| 哪里来 | layout / master 预定义的"位置 + 类型" | 你 `slide.shapes.add_*` 自己加的 |
| 字体 | **继承 master 默认字体**（很可能是微软雅黑）| 你 `set_font(run, ...)` 直接控制 |
| 位置 | 模板定死（一般不动）| 你自己定义 |
| 何时用 | 封面 / 章节扉页 / 标题这种"模板已设计"位置 | 内容区卡片 / icon / 表格 / 装饰元素 |
| 字体修复函数 | `_fix_ph_font(ph, ...)` ⚠️ 不同于 set_font | `set_font(run, ...)` |

**误区**：用 `set_font(run, ...)` 想改 placeholder 字体——**改不动**，因为 placeholder 的 `<a:ea>` 字体节点在 layout / master 那一层，slide 级别 set_font 改不到。

**正解**：placeholder 用 `_fix_ph_font(ph, ...)`（template.py 已提供）；自己 add 的 textbox 用 `set_font(run, ...)`。

### Step 3 — 加载模板 + 清空样例 slide

模板自带的 39 张样例 slide 必须先清空（保留 layout / master / theme）：

```python
from pptx import Presentation
import template as T  # 引用本 skill 的 template.py

prs = Presentation("template/Template.pptx")
T.clear_template_slides(prs)   # template.py 提供
# 现在 prs 是个空壳，但所有 layout / master / theme 都保留
```

### Step 4 — 选 layout + 填 placeholder + 修字体

```python
# 用 layout[0] '标题幻灯片' 做封面
s = prs.slides.add_slide(prs.slide_layouts[0])
for ph in s.placeholders:
    idx = ph.placeholder_format.idx
    if idx == 0:    # title
        ph.text = "我的标题"
        T._fix_ph_font(ph, size_pt=38, bold=True, color=T.NAVY)
    elif idx == 1:  # subtitle
        ph.text = "副标题"
        T._fix_ph_font(ph, size_pt=18, color=T.GRAY_700)
```

### Step 5 — 内容页：在 layout[3] 空白画布上 add_shape

25 个内容页都用 `layout[3] '仅标题页'`（只含 title + footer 三件套，内容区是空白）。视觉元素全靠你 `add_shape`：

```python
s = prs.slides.add_slide(prs.slide_layouts[3])
# 填 title placeholder
for ph in s.placeholders:
    if ph.placeholder_format.idx == 0:
        ph.text = "本页标题"
        T._fix_ph_font(ph, size_pt=28, bold=True, color=T.NAVY)
# 然后在 (0.55, 1.4) 到 (12.78, 6.7) 区间自己加 card / bullets / icon / 表格
T.card(s, Inches(0.55), Inches(1.6), Inches(5.5), Inches(2.0), ...)
```

### Step 6 — LibreOffice 不渲染部分 slide 的兜底

某些 iSlide 模板含"工具说明页"（教用户用 iSlide 插件换图标），**LibreOffice 不识别这类 slide**——所以渲染时 PDF 页数 < 模板 XML 中 slide 数。

**判断方法**：跑完 `soffice --convert-to pdf` 后 `pdftoppm` 出 PNG，数 PNG 数量。如果比 `len(prs.slides)` 少，先看 guide 文档（如 `template-team-guide.md` §1 注明哪些 slide 不渲染），不要立刻怀疑代码 bug。

**清理方法**：基于模板生成时，加载后 `clear_template_slides()` 清空所有样例 slide——这些工具说明页也一起被清除，避免污染输出。

### Step 7 — 渲染验证 5 步循环

同后文 [`迭代验证流程`](#-迭代验证流程生死循环)。

### 关键文件指针

| 文件 | 说明 |
|---|---|
| `template/Template.pptx` | 仓库已有 1 个 coral 团队风 .pptx 模板（详 `template-team-guide.md` 拆解）|
| `template-team-guide.md`（本 skill 目录）| Template.pptx 完整拆解 + 6 layouts + 6 类内容版面 + 6 个踩坑（coral 团队风，适合培训 / 商务宣贯）|
| `diagram-generation-guide.md`（本 skill 目录）| draw.io / Mermaid / matplotlib 画图选型 + 41 张图实战经验 + 8 大坑 + 嵌入 PPT 链路 |
| `.claude/skills/pptx/SKILL.md` | Anthropic 提供的低层 .pptx 读写 skill |
| `.claude/skills/pptx/scripts/{thumbnail,unpack,clean,pack,add_slide}.py` | 模板分析脚本 |

---

## 工具链（macOS 实测）

| 用途 | 工具 | 装法 |
|---|---|---|
| **PPT 生成** | `python-pptx ≥ 1.0` | `pip3 install --user --break-system-packages python-pptx` |
| **XML 微调**（EA 字体 / 表格属性 / 阴影） | `lxml` | 通常已装 |
| **PPT → PDF**（实际渲染验证）| `soffice`（LibreOffice）| `brew install --cask libreoffice` |
| **PDF → PNG**（视觉验证）| `pdftocairo`（poppler）| `brew install poppler` |
| **多 PNG → PDF 合并** | `sips`（系统自带）+ `pdfunite` | `brew install poppler` |
| **mermaid 流程图** | `mmdc` | `brew install mermaid-cli` |

⚠ **不要装 PrinceXML**（商业 + 免费版水印）；不要走 `pandoc --pdf-engine=prince` 这条路。

## ★ 图层 — 架构图 / 流程图先于 PPT

deck 里 5+ 张架构 / 流程 / 矩阵 / 决策图 → **图先行 + 单独生成 PNG → PPT 嵌入**。完整方法论独立沉淀在 [`diagram-generation-guide.md`](./diagram-generation-guide.md)（500 行，含 41 张图实战），本节只放选型决策 + 触发指针。

### 工具选型决策（≤ 5min 速判）

| 图类型 | 工具首选 | 替代 | 何时切换 |
|---|---|---|---|
| 简单线性流程（≤ 8 节点）| Mermaid | draw.io | 节点 > 10 或要精确配色 → draw.io |
| 多层架构 / 嵌套 subgraph | **draw.io** | — | 没替代 |
| 矩阵 / 决策树 / 角色边界 | **draw.io** | — | Mermaid 形状有限 |
| 数据驱动可视化（柱 / 雷达） | matplotlib | draw.io 静态 | 数据 > 5 行用 mpl |
| 卡片墙 / icon grid | draw.io | python-pptx 直接画 | 多个 slide 用同款 → draw.io 生成 PNG 复用 |

经验：deck 总图数 ≤ 10 → 全 Mermaid；> 10 张 或 需"视觉一致" → 全 draw.io 沉本到底；**不混搭**（会造成视觉割裂）。

### 触发本节的信号

- 用户：deck 缺图 / 架构看不懂 / 41 页文字墙
- 你（content-writer / pptx skill 用户）：发现某个 slide 描述完后没图可塞
- 派单含"需要 N 张架构图"或"图先行"

### 必读：完整方法论

走 draw.io 前，**先读 `diagram-generation-guide.md` 全文**——里面有：

- 安装 + headless CLI（`brew install --cask drawio` + `--width 3200`）
- mxGraph XML 最小模板 + 10 类 Cell（rect/ellipse/triangle/rhombus/text/edge…）
- AGF 设计 token（navy `#0E3569` / coral `#F06966` / gold `#FFBF00` + 浅色底）
- 字号体系（基准 1600×900：标题 28pt / 节点 20-22pt / 注解 16-18pt）
- **8 大致丑坑**（Heiti SC 老派 / sketch hatch / 长英文换行 / 默认 800px 糊 / `&#xa;` 换行 / XML 转义 / edge 坐标失稳 / emoji LibreOffice fallback）
- 批量工作流（sed 全局字体替换 + for loop 批量渲染）
- 嵌入 PPT 链路（PNG → `add_picture(height=Inches(N))`）

⚠️ **字体一致性**：guide 与 PPT 一律用 **PingFang SC**（PPT 用 `_fix_ph_font(ph, name="PingFang SC")`）；不要图用 Heiti SC、PPT 用 PingFang SC 造成跨页面字体跳变。

## 设计 token（直接拷贝到脚本头部）

完整 helper + 色板放在 [`template.py`](./template.py)，直接 `python3 template.py` 可跑出一份样例 deck。要点：

- **单一品牌色**：1 主深 + 1 主标准 + 1 主淡 + 1 强调 + 5 灰阶 = 7 个色变量，**不超 12 个**
- **字体**：`PingFang SC`（macOS 原生）+ Windows/Linux fallback `Microsoft YaHei` / `Source Han Sans CN`
- **页面 16:9**：13.333 × 7.5 inches；左右边距 0.55"，顶部标题区 1.4"，底部页脚 0.5"
- **行高**：中文正文 `line_spacing=1.45`，标题 `1.0`

## ★ 7 个致丑反模式（必须主动避开）

| # | 反模式 | 为什么丑 | 正确做法 |
|:-:|---|---|---|
| 1 | 顶部厚色带（≥0.5"）每页都重复 | 压死页面空间 + 视觉疲劳 | 6pt 极细线 + 右上 140pt 装饰大数字 |
| 2 | 每页同一 `header(title, page)` 通用模板 | 章节同质化、无层次感 | 章节扉页与内容页分两种 layout |
| 3 | 表格全网格（Excel 风）+ 默认 banding | 老土 + 信息密度低 | 表头深色 + 0 内边框 + 自定义斑马纹 |
| 4 | 一页 5+ 种饱和色（绿/蓝/红/橙/紫） | 眼花、权重失序 | 1 主色 + 1 强调色 + 灰阶 + 白 |
| 5 | 全屏文字墙（一页 >100 字）| 没人会读完 | 卡片化（每个信息单元独立矩形） |
| 6 | 标题用艺术字 / 阴影 / 3D / 渐变铺底 | 党政"信封风" | 简洁字体 + 1pt 横线分隔 |
| 7 | emoji 滥用（🚀 ✅ 🎉 等活泼感）| 制度文件不严肃 | 仅 ⚠ ⛔ 🔒 类警示性图标 |

## ★ 12 个关键技巧（按重要性排序）

### 1. 中文字体跨平台生效（最致命的坑）

**`python-pptx` 默认 `font.name` 只写 `<a:latin>`，中文不生效！** 跨平台时 fallback 到丑字体。

```python
from pptx.oxml.ns import qn
from lxml import etree

def set_font(run, *, name="PingFang SC", size=14, bold=False, color=RGBColor(0,0,0)):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    # 关键：显式写 <a:ea>（东亚文字）+ <a:cs>（复杂脚本）
    rPr = run._r.get_or_add_rPr()
    for tag in ('a:ea', 'a:cs'):
        elem = rPr.find(qn(tag))
        if elem is None:
            elem = etree.SubElement(rPr, qn(tag))
        elem.set('typeface', name)
```

完整版见 [`template.py`](./template.py) `set_font()`。

**⚠️ Placeholder 单独需要 `_fix_ph_font()`**：

`set_font(run, ...)` 只能改你自己 `add_textbox` 加的 run。**Placeholder 字体继承自 master 的 `<a:ea>`（通常是微软雅黑，macOS 没装）**——run 级 set_font 改不到 master 那一层。

```python
# ❌ 错的做法（改不动 placeholder 的中文字体）
ph.text = "我的标题"
for run in ph.text_frame.paragraphs[0].runs:
    set_font(run, name="Heiti SC")  # latin 改了，但 ea 仍继承 master 的微软雅黑

# ✅ 正确做法（用 _fix_ph_font 对整个 placeholder 写 <a:ea>）
ph.text = "我的标题"
T._fix_ph_font(ph, name="Heiti SC", size_pt=28, bold=True, color=NAVY)
```

`_fix_ph_font` 完整实现见 [`template.py`](./template.py)；何时用哪个见上文 `Step 2 — Placeholder vs Shape 概念区分`。

### 2. textbox 必须显式归零默认 margin

```python
box = slide.shapes.add_textbox(x, y, w, h)
tf = box.text_frame
tf.margin_left = tf.margin_right = Emu(0)
tf.margin_top = tf.margin_bottom = Emu(0)
tf.word_wrap = True   # 普通文本要
tf.word_wrap = False  # 大字号装饰文本要（防换行）
```

否则文字神秘偏右/偏下，对齐失败。

### 3. 大字号装饰数字防换行

180pt 大数字默认 `word_wrap=True` 会把 "01" 换成两行（"0\n1"）。修复：

```python
def page_decoration(slide, num, tint_color):
    box = slide.shapes.add_textbox(Inches(8.8), Inches(0.25), Inches(4.4), Inches(2.0))
    tf = box.text_frame
    tf.word_wrap = False  # 关键
    tf.margin_left = tf.margin_right = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    p.line_spacing = 1.0
    r = p.add_run()
    r.text = num
    r.font.name = "Helvetica Neue"
    r.font.size = Pt(140)
    r.font.bold = True
    r.font.color.rgb = tint_color
```

textbox 宽度必须 ≥ `字符数 × 0.6 × 字号pt / 72`，否则触发自动换行。

### 4. 表格行高 + 关闭 banding（防被截断 / 防意外横纹）

```python
def table_modern(slide, x, y, w, h, headers, rows, *, row_height=Inches(0.5)):
    tbl = slide.shapes.add_table(len(rows)+1, len(headers), x, y, w, h).table

    # 显式行高（否则 LibreOffice 渲染时行高失控）
    for row in tbl.rows:
        row.height = row_height

    # 关键：关闭 python-pptx 默认 banding（防奇怪横纹）
    tblPr = tbl._tbl.find(qn('a:tblPr'))
    if tblPr is not None:
        tblPr.set('firstRow', '0')
        tblPr.set('bandRow', '0')
    # 然后手动给奇数行填 GRAY_50 实现斑马纹
```

### 5. shape 真正"无边框"/"无填充"

```python
# ❌ fill=None / line=None 不是"无"，是"默认"（会有边）
shape.fill = None

# ✅ 正确：
shape.fill.background()        # 真无填充（透明）
shape.line.fill.background()   # 真无边框
```

### 6. 卡片化（圆角矩形 + 左 accent 色条）

```python
def card(slide, x, y, w, h, *, fill=WHITE, border=GRAY_300, accent=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = border
    shape.line.width = Pt(0.75)
    shape.adjustments[0] = 0.05  # 圆角调小（默认大圆角丑）
    if accent:  # 左侧 4pt 色条作为视觉锚点
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, Emu(36000), h)
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
    return shape
```

### 7. 现代 bullet（▎ 短竖线代替圆点）

```python
def bullets(slide, x, y, w, h, items, *, size=14, accent_color, body_color):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.margin_left = tf.margin_right = Emu(0)
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.45  # 中文行高至少 1.4 才不挤
        r1 = p.add_run(); r1.text = "▎ "
        set_font(r1, size=size, color=accent_color, bold=True)
        r2 = p.add_run(); r2.text = item
        set_font(r2, size=size, color=body_color)
```

`▎` 比 `•` `‣` 更现代，在制度 / 咨询 PPT 里常见。

### 8. 字号层级（16:9 = 13.333 × 7.5 inches）

| 用途 | 字号 | 加粗 |
|---|---|---|
| 封面主标题 | 44-54pt | bold |
| 章节扉页大标题 | 36-40pt | bold |
| 内容页 H2 | 20-28pt | bold |
| 内容页 H3 / 小节 | 14-18pt | bold |
| 正文 bullet | 11.5-14pt | normal |
| 表格 body | 10.5-12pt | normal |
| 页脚 / caption | 8.5-10pt | normal |
| 装饰大数字 | 120-150pt | bold（淡色） |

行高：中文正文 `1.45`，标题 `1.0`。

### 9. 留白边界（标准 layout）

```python
slide_width  = Inches(13.333)
slide_height = Inches(7.5)
LEFT_MARGIN  = Inches(0.55)
RIGHT_MARGIN = Inches(0.55)
HEADER_BOTTOM = Inches(1.4)   # 标题区域结束
FOOTER_TOP    = Inches(7.0)   # 页脚分隔线

content_w = Inches(13.333) - LEFT_MARGIN - RIGHT_MARGIN  # 12.23
content_h = FOOTER_TOP - HEADER_BOTTOM                    # 5.60
```

### 10. 双视图嵌入（图 + 描述卡片化）

竖长图（如 mermaid sequence/flowchart）适合"左图右文"：

- 左 4-5" 嵌入图（`height=Inches(5)` 等比缩放）
- 右 8" 文字区：序号小字 / 主标题 28pt / 短线 / 4 个左色条卡片说明

```python
# 左：图
slide.shapes.add_picture(str(img_path), Inches(0.55), Inches(1.9), height=Inches(5.0))

# 右：4 卡片
for i, (k, v) in enumerate(points):
    y = Inches(2.95 + i * 0.78)
    card(slide, Inches(4.8), y, Inches(8.0), Inches(0.65),
         fill=GRAY_50, border=GRAY_300, accent=NAVY)
```

### 11. 阶段 / 流程页万能 layout

左 1.7" 大色块（80pt 巨大数字）+ 右 10" 信息区（元信息卡 / 主要活动 / 交付物 / 红色提示框）。

```python
rect(s, Inches(0.55), Inches(1.9), Inches(1.7), Inches(2.0), STAGE_COLOR)
textbox(s, Inches(0.55), Inches(1.9), Inches(1.7), Inches(2.0),
        str(stage_num), size=80, bold=True, color=WHITE, font=FONT_NUM,
        align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
```

数字字号 80pt 是视觉锚点，让人一眼记住"这是阶段 N"。

### 12. 单一品牌色覆盖（≤ 12 个色变量）

```python
PRIMARY_DEEP   = RGBColor(0x8B, 0x1F, 0x24)  # 主调
PRIMARY_DARK   = RGBColor(0x5E, 0x0E, 0x14)  # 大色块
PRIMARY_TINT   = RGBColor(0xFB, 0xE5, 0xE7)  # 装饰底
ACCENT_BRAND   = RGBColor(0xEC, 0x0A, 0x1E)  # 警示 / 一票否决 / 关键字
ACCENT_PALE    = RGBColor(0xFE, 0xE1, 0xE4)
GOLD           = RGBColor(0xC8, 0xA1, 0x4E)  # 少量 — 装饰短线
GRAY_900       = RGBColor(0x1A, 0x1A, 0x1A)
GRAY_700       = RGBColor(0x4A, 0x4A, 0x4A)
GRAY_500       = RGBColor(0x8C, 0x8C, 0x8C)
GRAY_300       = RGBColor(0xD9, 0xD9, 0xD9)
GRAY_50        = RGBColor(0xFA, 0xFA, 0xFA)
WHITE          = RGBColor(0xFF, 0xFF, 0xFF)
```

7 个色变量足够覆盖 90% 场景。不要超过 12 个，否则 PPT 失控。

## ★ 迭代验证流程（生死循环）

**最致命的错误**：只用 `python-pptx` 读回验证文件合法性，不看实际渲染。

字符溢出 / 表格被截 / 文字遮挡 / 行高失控 / 中文字体 fallback —— 这些**只能用 LibreOffice 渲染 PDF + 看 PNG 才能发现**。

### 标准 5 步调试 cycle

```bash
# 1. 生成
python3 build-ppt.py

# 2. 转 PDF（实际渲染）
cd /tmp && rm -rf preview && mkdir preview && cd preview
soffice --headless --convert-to pdf /path/to/output.pptx

# 3. 转 PNG（视觉）
pdftocairo -png -r 100 output.pdf p

# 4. 用 Read tool 看关键页（封面、表格页、嵌入图页、警示页）
# 5. 发现问题 → 改 build-ppt.py → 回到 1
```

**每页 3 步检查**：
- ✓ 文字是否被截断 / 溢出框 / 遮挡？
- ✓ 中文字体是否正确（不是 fallback 到丑字体）？
- ✓ 表格 / 列宽是否合理，斑马纹是否生效？

## 品牌色获取流程

### Step 1 — 找官方色

| 来源 | 适用 |
|---|---|
| 公司官网 → "品牌识别" / "VI 手册" / "Brand Guidelines" | 优先 |
| [BrandColorCode.com](https://www.brandcolorcode.com) | 一般企业 |
| [Brandfetch.com](https://brandfetch.com) | 国际品牌 |
| Pantone 色卡 | 严格设计场景 |

### Step 2 — 衍生色板

从主色（如 GAC 红 `#EC0A1E`）衍生：

```
主色 → 加黑 30% → 主调（PRIMARY_DEEP）
主色 → 加白 80% → 装饰底（PRIMARY_TINT）
主色 → 加黑 50% → 大色块（PRIMARY_DARK）
主色 → 原色 → 强调警示（ACCENT_BRAND）
```

用 [coolors.co](https://coolors.co) 或 [paletton.com](https://paletton.com) 一键生成调和色板。

### Step 3 — 党政红 / 汽车风惯用搭配

- 主色：枣红 `#8B1F24` 或朱砂 `#A82027`（稳重）
- 强调：正红 `#EC0A1E`（警示）
- Accent：金 `#C8A14E`（少量）
- 大量留白 + 黑白灰

## Checklist — 交付前自检

**通用（所有路径都查）**：
- [ ] 跨平台中文字体（用了 lxml 写 `<a:ea>` + `<a:cs>`）
- [ ] 没有文字被截断 / 溢出 / 遮挡（LibreOffice 实测）
- [ ] 没有 emoji 滥用（仅 ⚠ ⛔ 🔒 类警示性）
- [ ] 单一主色 + 1 强调色（不超过 7 个色变量）
- [ ] 表格关了 `firstRow` / `bandRow`（防 banding）
- [ ] 大字号 textbox 设了 `word_wrap=False`
- [ ] 所有 textbox 设了 `margin_left/right = 0`
- [ ] `line_spacing` 显式设置（标题 1.0 / 正文 1.45）
- [ ] 每页有页脚 + 页码 `N / TOTAL`
- [ ] 章节扉页与内容页 layout 不同
- [ ] 图片用 `height=Inches(N)` 等比缩放（不变形）
- [ ] 不依赖 PrinceXML / 商业 PDF 引擎
- [ ] 可用 `python3 build-ppt.py` 一键重生成

**基于模板路径专项（增加 4 项）**：
- [ ] 加载模板后已用 `clear_template_slides(prs)` 清空所有样例 slide
- [ ] 所有 placeholder 都已用 `_fix_ph_font(ph, ...)` 修字体（不是 `set_font(run, ...)`）
- [ ] 已对照 LibreOffice 输出页数 vs `len(prs.slides)` —— 不一致时确认是"模板含工具说明页"而非代码 bug
- [ ] 已读过对应的 `template-*-guide.md`（如 `template-team-guide.md`），知道该模板的可用 layout / 配色 / 字体坑

## Anti-prompt — 让 Claude 不要做的事

把下面这段拷给 Claude 避免它走弯路：

```
- 不要装 PrinceXML / pandoc-with-prince
- 不要用 python-pptx 默认 font.name 设中文字体 — 必须用 lxml 写 <a:ea>
- 不要每页都用同一个 header layout — 章节扉页要有独立 layout
- 不要堆 5 种以上饱和色 — 主色 + 1 强调色 + 灰阶
- 不要只用 python-pptx 读回验证 — 必须 LibreOffice 转 PDF + 看 PNG
- 不要 commit 渲染产物（HTML / PDF / .pyc）— 在 .gitignore 里
# 基于模板路径专项 anti-prompt：
- 不要在 LibreOffice 输出 PNG 数 < 预期时立即报错 — 模板可能含工具说明页（如 iSlide 插件页）不被识别；先读 template-*-guide.md
- 不要假设 placeholder 用的是你 set_font 的字体 — placeholder 继承 master 的 <a:ea>，必须用 _fix_ph_font(ph, ...)
- 不要看到 11 个 layout 就以为全可用 — 多数模板实测只有 4-5 个 layout 真被用过；先 dump slide → layout 映射找规律
- 不要直接用模板自带的 39 张样例 slide — 生成时先 clear_template_slides(prs) 清空，保留 layout / master 即可
```

## 一键 SVG/PNG/PDF 输出 + mermaid 嵌入

```bash
# 在 build-ppt.py 之前先跑：
mmdc -i diagram.mmd -o diagram.svg
mmdc -i diagram.mmd -o diagram.png -w 2400 -H 1800 -b transparent
```

```python
# build-ppt.py 直接引用 .png：
slide.shapes.add_picture("diagram.png", Inches(0.55), Inches(1.9), height=Inches(5.0))
```

合并多 PNG 为单 PDF（视觉对外提报）：

```python
import subprocess, tempfile
with tempfile.TemporaryDirectory() as tmp:
    for i, png in enumerate(png_paths):
        subprocess.run(["sips", "-s", "format", "pdf", png,
                        "--out", f"{tmp}/p{i}.pdf"], check=True)
    subprocess.run(["pdfunite"] +
                   [f"{tmp}/p{i}.pdf" for i in range(len(png_paths))] +
                   ["out.pdf"], check=True)
```

## 资源链接

**本仓库内**（优先看）：
- [`template/Template.pptx`](../../../template/) — 1 个 coral 团队风 .pptx 模板（39 slides / 6 layouts / 1 MB；详 `template-team-guide.md` 内 6 layouts + 6 类版面拆解）
- [`template-team-guide.md`](./template-team-guide.md) — Template.pptx 完整使用指南（39 slides / 6 layouts / 6 类版面 / 6 个踩坑）
- [`template.py`](./template.py) — 本 skill 自带的 helper 集合（含 `_fix_ph_font` / `clear_template_slides` / `card` / `bullets` / `table_modern` 等）
- [`.claude/skills/pptx/SKILL.md`](../pptx/SKILL.md) — Anthropic 提供的低层 .pptx 读写 skill（unpack / thumbnail / clean / pack 脚本）

**外部资源**：
- [python-pptx 官方文档](https://python-pptx.readthedocs.io/)
- [python-pptx Issue #503 — .potx 模板讨论](https://github.com/scanny/python-pptx/issues/503)
- [pptx-ea-font](https://github.com/AndersonBY/pptx-ea-font) — 手写 EA 字段的封装库（不装也行，本 skill 已展示手写法）
- [SlidesCarnival](https://www.slidescarnival.com/tag/minimalist) — 严肃极简风免费模板（视觉参考）
- [BrandColorCode](https://www.brandcolorcode.com) — 企业品牌色查询
- [Mermaid Live Editor](https://mermaid.live) — 在线调试 mermaid 图

## 本 skill 的沉淀来源

2026-05《AI 4A 架构评审管理办法（试行）》v1.0 PPT 实战：
- 23 页，GAC 广汽红主调，党政严肃风
- 嵌入 mermaid flowchart + sequence 双视图 + isolation matrix
- 约 4 小时（含 3 轮迭代：纯代码版 / 装饰修复版 / GAC 红主题版）

> 历史产物（含完整 1500 行生成器、文档源、最终 .pptx）位于 TopConsultant 仓库，迁入 AppGenesisForge 时已剥离项目耦合，仅保留通用方法论。
