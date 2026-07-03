# 基于已有 .pptx 模板生成（推荐路径详解）

> 从 `SKILL.md` 下沉的完整参考。走"基于模板 + python-pptx 混合"路径时**必读本文全文**。

适用：仓库 `template/` 下已有 `.pptx` 设计模板，用户希望保留模板视觉 + 程序化生成内容。

**前置必看**：每个已落地模板在本 skill 目录下都有一份 `template-*-guide.md`，例如 `template-team-guide.md`。**先读 guide 再动手**——它会告诉你该模板的可渲染 slide 范围、配色、字体覆盖坑、6 类页面用法、踩坑清单。

## Step 1 — 模板分析三件套（先看再动）

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

**看 dump 结果找规律**：哪些 layout 真被 slide 用过？用得多的是核心 layout，没被用的是"备用"——你也基本用不到。

## Step 2 — Placeholder vs Shape 概念区分（最关键认知）

| 项 | Placeholder | Shape |
|---|---|---|
| 哪里来 | layout / master 预定义的"位置 + 类型" | 你 `slide.shapes.add_*` 自己加的 |
| 字体 | **继承 master 默认字体**（很可能是微软雅黑）| 你 `set_font(run, ...)` 直接控制 |
| 位置 | 模板定死（一般不动）| 你自己定义 |
| 何时用 | 封面 / 章节扉页 / 标题这种"模板已设计"位置 | 内容区卡片 / icon / 表格 / 装饰元素 |
| 字体修复函数 | `_fix_ph_font(ph, ...)` ⚠️ 不同于 set_font | `set_font(run, ...)` |

**误区**：用 `set_font(run, ...)` 改 placeholder 字体——**改不动**，因为 placeholder 的 `<a:ea>` 字体节点在 layout / master 那一层，slide 级 set_font 够不着。

**正解**：placeholder 用 `_fix_ph_font(ph, ...)`（template.py 已提供）；自己 add 的 textbox 用 `set_font(run, ...)`。

## Step 3 — 加载模板 + 清空样例 slide

模板自带的 39 张样例 slide 必须先清空（保留 layout / master / theme）：

```python
from pptx import Presentation
import template as T  # 引用本 skill 的 template.py

prs = Presentation("template/Template.pptx")
T.clear_template_slides(prs)   # template.py 提供
# 现在 prs 是个空壳，但所有 layout / master / theme 都保留
```

## Step 4 — 选 layout + 填 placeholder + 修字体

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

## Step 5 — 内容页：在 layout[3] 空白画布上 add_shape

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

## Step 6 — LibreOffice 不渲染部分 slide 的兜底

某些 iSlide 模板含"工具说明页"（教用户用 iSlide 插件换图标），**LibreOffice 不识别这类 slide**——渲染时 PDF 页数 < 模板 XML 中 slide 数。

**判断方法**：跑完 `soffice --convert-to pdf` 后 `pdftoppm` 出 PNG，数 PNG 数量。比 `len(prs.slides)` 少时先看 guide（如 `template-team-guide.md` §1 注明哪些 slide 不渲染），别立刻怀疑代码 bug。

**清理方法**：基于模板生成时，加载后 `clear_template_slides()` 清空所有样例 slide——工具说明页一并清除，避免污染输出。

## Step 7 — 渲染验证 5 步循环

同 `SKILL.md` 的「★ 迭代验证流程（生死循环）」节。

## 关键文件指针

| 文件 | 说明 |
|---|---|
| `template/Template.pptx` | 仓库已有 1 个 coral 团队风 .pptx 模板（详 `template-team-guide.md` 拆解）|
| `template-team-guide.md`（skill 根目录）| Template.pptx 完整拆解 + 6 layouts + 6 类内容版面 + 6 个踩坑（coral 团队风，适合培训 / 商务宣贯）|
| `diagram-generation-guide.md`（skill 根目录）| draw.io / Mermaid / matplotlib 画图选型 + 41 张图实战经验 + 8 大坑 + 嵌入 PPT 链路 |
| `.claude/skills/pptx/SKILL.md` | Anthropic 提供的低层 .pptx 读写 skill |
| `.claude/skills/pptx/scripts/{thumbnail,unpack,clean,pack,add_slide}.py` | 模板分析脚本 |
