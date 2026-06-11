# 设计 token + 12 个关键技巧 + 品牌色获取流程

> 从 `SKILL.md` 下沉的完整参考。写 helper / 调样式 / 定色板前**必读本文全文**；可直接跑的 helper 集合在 [`../template.py`](../template.py)。

## 设计 token（直接拷贝到脚本头部）

完整 helper + 色板放在 [`template.py`](../template.py)，直接 `python3 template.py` 可跑出一份样例 deck。要点：

- **单一品牌色**：1 主深 + 1 主标准 + 1 主淡 + 1 强调 + 5 灰阶 = 7 个色变量，**不超 12 个**
- **字体**：`PingFang SC`（macOS 原生）+ Windows/Linux fallback `Microsoft YaHei` / `Source Han Sans CN`
- **页面 16:9**：13.333 × 7.5 inches；左右边距 0.55"，顶部标题区 1.4"，底部页脚 0.5"
- **行高**：中文正文 `line_spacing=1.45`，标题 `1.0`

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

完整版见 [`template.py`](../template.py) `set_font()`。

**⚠️ Placeholder 单独需要 `_fix_ph_font()`**：

`set_font(run, ...)` 只能改你自己 `add_textbox` 加的 run。**Placeholder 字体继承自 master 的 `<a:ea>`（通常是微软雅黑，macOS 没装）**——run 级 set_font 够不到 master 那一层。

```python
# ❌ 错的做法（改不动 placeholder 的中文字体）
ph.text = "我的标题"
for run in ph.text_frame.paragraphs[0].runs:
    set_font(run, name="Heiti SC")  # latin 改了，但 ea 仍继承 master 的微软雅黑

# ✅ 正确做法（用 _fix_ph_font 对整个 placeholder 写 <a:ea>）
ph.text = "我的标题"
T._fix_ph_font(ph, name="Heiti SC", size_pt=28, bold=True, color=NAVY)
```

`_fix_ph_font` 完整实现见 [`template.py`](../template.py)；何时用哪个见 [`template-based-generation.md`](./template-based-generation.md) `Step 2 — Placeholder vs Shape 概念区分`。

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

80pt 数字是视觉锚点，让人一眼记住"这是阶段 N"。

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

7 个色变量足够覆盖 90% 场景。别超过 12 个，否则 PPT 失控。

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
