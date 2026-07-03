# Template.pptx（iSlide 商务团队主题）使用指南

> 沉淀自 2026-05-16 模板分析：`template/Template.pptx`（39 slides / 6 layouts / 1 MB / 16:9）
> 风格：iSlide 商务团队主题 / coral 红主调 / 卡通 TEAM 装饰贯穿
> **谁会读这份**：用 `agf-writing-pptx-reports` skill 时被指派"用 Template.pptx 模板"或"出培训 / 团队建设 / 商务宣贯 PPT"。

## 何时用本模板

适合：**培训 / 团队建设 / onboarding / 商务宣贯 / 产品介绍**——iSlide 商务团队主题，coral 主调 + 卡通 TEAM 装饰，受众偏年轻（≤ 40 岁）/ 5 章节量级 / 节奏紧凑。

不适合：制度 / 党政 / 财报评审等严肃场景（卡通装饰风格冲突）+ 30+ 页量级（仅 6 layouts 重复用易乏味）。

经验：**AGF 培训 deck 系列就选 Template.pptx**（coral 与我们 diagram 设计 token 撞色，跨页面视觉一致）。

## 1. 模板基础事实

```
画布   13.333 × 7.5 inches (16:9 标准)
总 slide  39
  ├─ 1   封面（slide 1）
  ├─ 1   目录 CONTENTS（slide 2）
  ├─ 5×(1扉页+4-5内容) = 28  五章节内容
  ├─ 1   末尾 Thanks（slide 32）
  └─ 7   空白备用（slide 33-39）
layouts  6（精简，少而精）
theme    theme1 主 + theme2 + 3 themeOverride
体积     997 KB
```

**关键观察**：仅 6 layouts，64% slide 都用 `layout[3] "仅标题页"`——靠 `add_shape` 自定义内容。

## 2. 6 Layouts 详细拆解

### layout[0] "标题幻灯片" — **封面专用**（用量 1）

| placeholder | type | 用途 |
|---|---|---|
| 0 | CENTER_TITLE | 主标题 |
| 1 | SUBTITLE | 副标题 |
| 10 | BODY | Signature（签名）|
| 11 | BODY | Date（日期）|

**取舍**：4 个 placeholder 给"主标题 + 副标题 + 签名 + 日期"齐全，封面信息全在 placeholder 里。

```python
s = prs.slides.add_slide(prs.slide_layouts[0])
for ph in s.placeholders:
    idx = ph.placeholder_format.idx
    if idx == 0:      # title
        ph.text = "AGF 内部培训"
        T._fix_ph_font(ph, size_pt=44, bold=True, color=CORAL)
    elif idx == 1:    # subtitle
        ph.text = "6 小时 · 4 场景 · 14 同事协作"
        T._fix_ph_font(ph, size_pt=20, color=GRAY_700)
    elif idx == 10:   # signature
        ph.text = "讲师：content-writer 团队"
        T._fix_ph_font(ph, size_pt=14, color=GRAY_500)
    elif idx == 11:   # date
        ph.text = "2026-05-16"
        T._fix_ph_font(ph, size_pt=14, color=GRAY_500)
```

### layout[1] "标题和内容" — **设计了但模板没用**（用量 0）

| placeholder | type | 用途 |
|---|---|---|
| 0 | TITLE | 标题 |
| 13 | OBJECT | body（多级文本）|
| 10/11/12 | DATE/FOOTER/SLIDE_NUMBER | 页脚三件套 |

**陷阱**：模板自己没用这个 layout（所有内容页用 layout[3]）。但你可以用它做"纯文本多级 bullets"页（如目录 / 章节 outline）。

### layout[2] "节标题" — **章节扉页**（用量 5）

| placeholder | type | 用途 |
|---|---|---|
| 0 | TITLE | "Section Header Here" |
| 1 | BODY | 副标题 / 章节描述 |

**关键视觉**：模板自带"左 coral 色条 + /0X 编号 + 中央 'Section Header Here' + 右侧卡通 TEAM 装饰图"已嵌入 layout（不是 placeholder，是 master 级 shape）→ 你只需改 title + body 文字，编号 /01-/05 自动来自 master。

```python
s = prs.slides.add_slide(prs.slide_layouts[2])
for ph in s.placeholders:
    if ph.placeholder_format.idx == 0:
        ph.text = "场景 A · 明信片 Happy Path"
        T._fix_ph_font(ph, size_pt=36, bold=True, color=NAVY)
    elif ph.placeholder_format.idx == 1:
        ph.text = "用旅游明信片串起 14 同事 + 派单 schema + progress 自报"
        T._fix_ph_font(ph, size_pt=16, color=GRAY_700)
```

**陷阱**：5 个章节扉页编号 /01-/05 在 master shape 里硬编码——如果你的 deck 不是 5 章节（如 8 章），需要：
- (a) 重复用同 5 个编号（混乱）
- (b) 自己 `add_shape` 加新编号 box 覆盖
- (c) unpack pptx → 编辑 master XML → 加 layout（推荐 deck 章节数固定时）

### layout[3] "仅标题页" ⭐ **主力**（用量 25 = 64%）

| placeholder | type | 用途 |
|---|---|---|
| 0 | TITLE | 顶部标题 |
| 10/11/12 | DATE/FOOTER/SLIDE_NUMBER | 页脚三件套 |

**用法**：内容区（title 之下、footer 之上）是空白画布，自己 `add_shape` 加 6 类版面之一（见 §3）。

```python
s = prs.slides.add_slide(prs.slide_layouts[3])
for ph in s.placeholders:
    if ph.placeholder_format.idx == 0:
        ph.text = "三步流水线架构图"
        T._fix_ph_font(ph, size_pt=28, bold=True, color=NAVY)
# 然后自由用 (0.55, 1.4) 到 (12.78, 6.7) 区间加 shape
T.card(s, Inches(0.55), Inches(1.6), Inches(5.5), Inches(2.0), ...)
```

### layout[4] "空白" — **完全自由**（用量 8）

无 placeholder。模板里 8 张：1 张是目录 CONTENTS（slide 2），7 张是末尾备用（slide 33-39）。

**何时用**：
- 全屏插图（如 Vision → LLM → 文生图 三步流水线图）
- 跨章过渡 slide（黑屏 + 章节倒计时）
- 自定义封面（不想用 layout[0] 的 placeholder 约束时）

### layout[5] "末尾幻灯片" — **Thanks 页**（用量 1）

| placeholder | type | 用途 |
|---|---|---|
| 0 | CENTER_TITLE | "Conclusion" / "Thanks" |
| 18 | BODY | Data（数据 / 说明）|
| 10 | BODY | Signature（讲师签名）|

模板原文 "Thanks And Your Slogan Here / Speaker name and title / Designed by iSlide" → 改成你的口号即可。

```python
s = prs.slides.add_slide(prs.slide_layouts[5])
for ph in s.placeholders:
    if ph.placeholder_format.idx == 0:
        ph.text = "Thanks\n反馈渠道：github.com/.../issues"
        T._fix_ph_font(ph, size_pt=40, bold=True, color=NAVY)
    elif ph.placeholder_format.idx == 10:
        ph.text = "讲师：content-writer + product-lead"
        T._fix_ph_font(ph, size_pt=16, color=GRAY_700)
```

## 3. 内容页 6 类版面模式（按出现频次排序）

### 模式 A — N 卡片网格（典型 slide 4, 5, 25, 27）

3-5 张圆形 icon + 标题 + 短描述，2 行 × 2-3 列 grid。

```python
# 4 卡片 2×2
ICONS = [("📊", "Vision 识别"), ("✏️", "LLM 文案"), ("🎨", "文生图"), ("📮", "明信片输出")]
for i, (icon, label) in enumerate(ICONS):
    row, col = i // 2, i % 2
    x = Inches(1.0 + col * 6.0)
    y = Inches(2.0 + row * 2.2)
    T.card_icon(s, x, y, Inches(5.5), Inches(2.0), icon, label, accent=CORAL)
```

适合：步骤拆解 / 模块概览 / 角色列表

### 模式 B — 圆环 / radial chart（典型 slide 9-12, 21-22, 28）

中心一个大图（圆形 / 多边形）+ 4-6 条放射文字。

```python
# 中心圆 + 4 放射卡片
T.circle(s, Inches(5.6), Inches(3.0), Inches(2.0), fill=NAVY, text="AGF 心法")
positions = [(0.5, 1.5), (10.5, 1.5), (0.5, 5.0), (10.5, 5.0)]  # 4 角
for (x, y), label in zip(positions, ["Agile", "Scrum", "TDD", "Hook 强制"]):
    T.textbox(s, Inches(x), Inches(y), ..., label, ...)
```

适合：核心 + 多维度展开（"以 X 为中心，N 个支撑"叙事）

### 模式 C — 时间轴 / 阶梯（典型 slide 7, 13, 17, 24）

横向递进，节点 + 编号 + 文字。

```python
STEPS = ["01 PRD", "02 派单", "03 实现", "04 Review", "05 E2E", "06 UAT"]
for i, label in enumerate(STEPS):
    x = Inches(0.55 + i * 2.1)
    T.circle(s, x, Inches(3.5), Inches(0.5), fill=CORAL, text=str(i+1))
    T.textbox(s, x - Inches(0.4), Inches(4.2), Inches(1.8), Inches(0.5), label, ...)
    if i < len(STEPS) - 1:
        T.arrow(s, x + Inches(0.5), Inches(3.55), x + Inches(2.0), Inches(3.55))
```

适合：流程 / 阶段门 / 项目 timeline

### 模式 D — 业务对话 / 钩链（典型 slide 14, 16, 19）

多角色 icon + 关系连线（A → B → C 或 A ↔ B）。

适合：协作流程 / 派单链路 / SendMessage 示意

### 模式 E — 卡通插图主视觉（典型 slide 5, 6, 15, 18, 31）

大插图占左半 + 右半放数据/描述。

⚠️ **模板自带 TEAM 卡通图风格强**——如果你的内容是技术架构（如 Hook / Skill 系统），卡通插图会**风格冲突**。建议：
- (a) 删除模板装饰图，仅用版面框架
- (b) 替换为你的架构图（draw.io 出 PNG，见 [`diagram-generation-guide.md`](./diagram-generation-guide.md)）
- (c) 保留模板插图但只在"温度类内容"用（如团队介绍 / 退场感谢页）

### 模式 F — 数据 / icon 装饰大数（典型 slide 30）

齿轮 / 大脑 / 心形等装饰大图 + 关键数据点（如 "1559K / 1176K"）+ 解释。

```python
# 装饰大图（emoji 或导入 png）+ 数据
T.textbox(s, Inches(5.0), Inches(2.0), Inches(3.3), Inches(2.5), "🧠", font_size=180, ...)
T.textbox(s, Inches(0.8), Inches(5.0), Inches(5.0), Inches(0.8), "85%", font_size=80, bold=True, color=CORAL)
T.textbox(s, Inches(0.8), Inches(5.8), Inches(5.0), Inches(0.5), "Vision 准确率（5 道盲测）", font_size=14, color=GRAY_700)
```

适合：单点数据强调 / KPI 展示

## 4. 配色 + 字体 token

```python
# 与 Template.pptx 一致 + 与 diagram 设计 token 对齐
CORAL        = RGBColor(0xF0, 0x69, 0x66)   # 主色（封面 / 节标题色条 / 强调）
CORAL_LIGHT  = RGBColor(0xFF, 0xE5, 0xE5)   # 浅色底（卡片背景）
NAVY         = RGBColor(0x0E, 0x35, 0x69)   # 标题 / 深色块 / 文本
BLUE_ACCENT  = RGBColor(0x3B, 0x82, 0xF6)   # icon 边框 / 链接
GOLD         = RGBColor(0xFF, 0xBF, 0x00)   # 输入 / 第三色
GREEN        = RGBColor(0x2E, 0x8B, 0x57)   # success / pass
GRAY_900     = RGBColor(0x1A, 0x1A, 0x1A)
GRAY_700     = RGBColor(0x4A, 0x4A, 0x4A)
GRAY_500     = RGBColor(0x8C, 0x8C, 0x8C)
GRAY_300     = RGBColor(0xD9, 0xD9, 0xD9)
GRAY_50      = RGBColor(0xFA, 0xFA, 0xFA)
WHITE        = RGBColor(0xFF, 0xFF, 0xFF)
```

**字体一律 PingFang SC**：模板原字体是 Arial / 微软雅黑（macOS 没装 → fallback 丑字）。强制走 `_fix_ph_font(ph, name="PingFang SC")`。

## 5. 装饰元素策略（TEAM 卡通图怎么处理）

模板每个章节扉页 + 封面 + 末尾都有"卡通团队 + TEAM 大字"装饰，**强商务 + 团队主题感**。对 AGF 培训 deck 的取舍：

| 场景 | 处理 |
|---|---|
| 封面 + 末尾 | **保留**（呼应"团队"主题，AGF 14 同事正契合）|
| 章节扉页（场景 A/B/C/D 故事） | **保留**（剧本感强）|
| 技术架构内容页（Hook / TDD / 6 阶段门） | **删除装饰，替换为 draw.io 架构图** |
| 数据 / 矩阵 / 评测 | **删除装饰，替换为 F 类数据图** |

**怎么删 master 级装饰图**：
- 方案 A：unpack pptx → 编辑 slideMaster1.xml 删 sp 元素 → repack
- 方案 B：在 slide 上 `add_shape` 加白色矩形遮盖装饰图（不推荐 / 渲染时仍占体积）
- 方案 C：内容页全部用 `layout[3] "仅标题页"`（装饰图在 layout[2] 节标题里，不影响内容页）← **推荐**

## 6. 上手 7 步（标准 build_main.py 骨架）

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
import template as T

# 1. 加载 + 清空 39 张样例
prs = Presentation("template/Template.pptx")
T.clear_template_slides(prs)

# 2. 封面（layout[0]）
s = prs.slides.add_slide(prs.slide_layouts[0])
fill_cover(s)

# 3. 目录（layout[4] 空白）
s = prs.slides.add_slide(prs.slide_layouts[4])
fill_toc(s)

# 4. 5 个章节
for chapter_num, (title, subtitle, content_slides) in enumerate(CHAPTERS, 1):
    # 4a. 节标题（layout[2]）
    s = prs.slides.add_slide(prs.slide_layouts[2])
    fill_section_header(s, chapter_num, title, subtitle)
    # 4b. 内容页（layout[3]，每页选模式 A-F 之一）
    for content in content_slides:
        s = prs.slides.add_slide(prs.slide_layouts[3])
        fill_content(s, content)

# 5. 末尾（layout[5]）
s = prs.slides.add_slide(prs.slide_layouts[5])
fill_thanks(s)

# 6. 保存
prs.save("docs/training/agf-overview.pptx")

# 7. 渲染验证（soffice + pdftocairo → Read PNG，见 SKILL.md §★ 迭代验证）
```

## 7. 6 个踩坑预判（节省你 2-3h）

| # | 坑 | 现象 | 解 |
|---|---|---|---|
| 1 | 不 `clear_template_slides` | 输出含 39 张原样例 | 加载后立即清 |
| 2 | placeholder 字体没改 | 中文 fallback 到丑字 | 每 placeholder 走 `_fix_ph_font(ph, name="PingFang SC")` |
| 3 | layout[2] 节标题编号硬编码 /01-/05 | 你想要 8 章则编号撞车 | 章节数 ≤ 5 用模板；> 5 章自己 add_shape 覆盖编号 |
| 4 | TEAM 卡通装饰图与技术内容风格冲突 | 培训技术 deck 看起来"幼稚" | 内容页用 layout[3] 不带装饰，仅封面/章节/末尾保留 |
| 5 | layout[1] "标题和内容" 模板没用过 | 你以为可以放 bullet 列表 | 实测可用，但需自己测 placeholder 字体行为 |
| 6 | 空白 slide 33-39 备用页 LibreOffice 不渲染 | PDF 页数 < `len(prs.slides)` | 同 SKILL.md §Step 6；`clear_template_slides` 自动清掉 |

## 8. 完整 build script 路径（建议）

```
docs/training/
├── agf-overview.pptx       # 产出
├── agf-overview.pdf        # LibreOffice 渲染验证
├── build_main.py           # 主入口（import 章节 module + 串联）
├── build_sec_M1.py         # 第 1 章构建（如 §0 垫层）
├── build_sec_M2.py         # 第 2 章
├── ...                     # 章节并行可写（worktree）
├── diagrams/png/*.png      # 41 张 draw.io 出图（commit 0bd917a）
└── specs/2026-05-16-agf-training-deck-design.md  # spec v2.2
```

3+ 章节并行时按 [`.claude/standards/workflow.md`](../../standards/workflow.md) "Parallel Dispatch" 走 worktree（防 build_main.py 合并冲突）。

## 9. 沉淀来源

2026-05-16 模板分析：
- 输入：`template/Template.pptx`（1 MB / 39 slides）
- 工具：`.claude/skills/pptx/scripts/thumbnail.py` + `unpack.py` + python-pptx dump 脚本
- 时长：~30min（含 2 张 thumbnail.jpg 视觉评估 + layout dump + slide-layout 映射统计）
- 上下游：
  - 配套画图 [`diagram-generation-guide.md`](./diagram-generation-guide.md)（41 张 draw.io 图）
  - 主 skill [`SKILL.md`](./SKILL.md) §★ 基于已有 .pptx 模板生成
