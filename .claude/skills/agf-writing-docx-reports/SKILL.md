---
name: agf-writing-docx-reports
description: 用 docx-js 写"阅读友好的中文 docx 报告"（决议书 / 评审报告 / 调研 / 分析 / 投标书等高密度报告型文档）。当用户要求把 markdown 内容转 docx 且抱怨"格式混乱 / 不专业 / 看不下去"时启用——pandoc 默认转换难以满足。提供：路径决策 / 设计 token / 可复用 helper 全套 / 11 个 pitfall / 生成-预览闭环。
---

# 写 docx 报告 — 高密度实战手册

## 何时用本 skill

| 信号 | 用本 skill |
|---|:--:|
| 用户要把 markdown 报告 → docx | ✅ |
| 报告是中文 / 含大量表格 / 需要视觉强调（决议 / 警示） | ✅ |
| 用户反馈"格式混乱 / 不专业 / 字段被分行 / 段前段后大 / 页边距宽" | ✅ |
| 报告需要封面页 / 自动目录 / 页眉页脚 / 警示框 | ✅ |
| 只是导出几页纯文本 / 没有表格 | ❌ 用 pandoc 默认即可 |
| 要做的是 PPT / Excel | ❌ 转 pptx / xlsx skill |

## 路径决策（3 选 1）

| 路径 | 何时选 | 代价 |
|---|---|---|
| **pandoc 默认** `pandoc x.md -o x.docx` | 内部草稿 / 纯文本为主 / 表格 ≤ 3 个 | 几秒；视觉无控制 |
| **pandoc + reference.docx** | 想统一字体 / 标题色但不要 callout | 中等；要先在 Word 里手工调样式做模板 |
| **docx-js 全定制**（本 skill 核心） | 正式对外报告 / 高密度表格 / 警示框 / 封面页 | 一次写 ~600 行 JS，复用率 90% |

判定经验：**用户说"格式混乱"基本意味着要 docx-js**——pandoc 的列宽 auto + 无样式覆盖就是混乱的根因。

## 设计 token（直接拷贝到脚本头部）

```javascript
const FONT = "PingFang SC";   // 中文渲染。Word 在 macOS/Windows 都识别
const FONT_EN = "Arial";       // 西文 fallback

// 页面：A4 (11906x16838 DXA)。1440 DXA = 1 inch
const MARGIN = { top: 900, right: 720, bottom: 900, left: 720 }; // 上下 0.625" / 左右 0.5"
const CONTENT_WIDTH = 11906 - MARGIN.left - MARGIN.right; // = 10466 DXA

// ⚠️ 不要用默认 1" 边距 — 中文表格分行的元凶
// ⚠️ 不要用 Letter 尺寸 — 国内打印机标准是 A4

const COLOR = {
  TEXT: "1F1F1F", MUTED: "595959",
  PRIMARY: "1F4E79", PRIMARY_LIGHT: "D9E2F3",  // 深蓝 / 浅蓝
  DANGER: "C00000", DANGER_BG: "FCE4E4",        // 红 / 浅红
  WARN: "BF8F00", WARN_BG: "FFF2CC",            // 黄 / 浅黄
  OK: "548235",                                  // 绿
  BORDER: "BFBFBF", ALT_ROW: "F7F7F7",          // 边框灰 / 隔行底
};
```

**配色铁律**：

- 标题用 `PRIMARY`（深蓝），不用默认黑——视觉层次需要颜色对比
- "强制不通过 / 警示 / 一票否决"用 `DANGER` + 浅红 BG callout
- "事实风险 / 即将逾期"用 `WARN` + 浅黄 BG callout
- 表头一律 `PRIMARY_LIGHT` 底，body 用 `ALT_ROW` 隔行底（zebra）
- 普通文本辅助信息（注释 / 路径）用 `MUTED` 灰

## 段落与表格 spacing（v2 收紧版，必背）

```javascript
// 标题
H1: { before: 240, after: 120 }   // 节标题
H2: { before: 160, after: 80 }    // 小节
H3: { before: 120, after: 60 }    // 子小节

// 正文段落（默认）
p:  { before: 40, after: 40, line: 280 }

// 表格周边段落（更紧）
表格上下文段: { before: 30, after: 30 }

// Bullet 项
bullet: { before: 30, after: 30, line: 280 }

// Cell margins（cell 内 padding）
cell: { top: 60, bottom: 60, left: 100, right: 100 }
```

**经验**：v1 用了 default spacing（before 240+ / after 180+），19 页；v2 收紧后 15 页（-21%）。**段前段后是 docx 最容易膨胀的维度**。

## 9 个可复用 helper（粘到脚本头）

```javascript
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber,
} = require('docx');

const border = { style: BorderStyle.SINGLE, size: 4, color: COLOR.BORDER };
const cellBorders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBordersAll = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

// 1. 列宽按比例缩到内容区（避免逐表手算）
const scaleWidths = (widths, target = CONTENT_WIDTH) => {
  const sum = widths.reduce((a, b) => a + b, 0);
  const scaled = widths.map(w => Math.round(w * target / sum));
  scaled[scaled.length - 1] += target - scaled.reduce((a, b) => a + b, 0);
  return scaled;
};

// 2. TextRun 简写（中文必带 font）
const txt = (text, opts = {}) => new TextRun({
  text: String(text), font: FONT,
  size: opts.size || 22, bold: !!opts.bold,
  color: opts.color || COLOR.TEXT,
  italics: !!opts.italics,
});

// 3. 段落
const p = (children, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.LEFT,
  spacing: { before: opts.before ?? 40, after: opts.after ?? 40, line: opts.line ?? 280 },
  children: Array.isArray(children) ? children : [children],
  pageBreakBefore: !!opts.pageBreakBefore,
  numbering: opts.numbering,
});

// 4-6. 标题
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true,
  spacing: { before: 240, after: 120 },
  children: [new TextRun({ text, font: FONT, size: 32, bold: true, color: COLOR.PRIMARY })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2,
  spacing: { before: 160, after: 80 },
  children: [new TextRun({ text, font: FONT, size: 26, bold: true, color: COLOR.PRIMARY })] });
const h3 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_3,
  spacing: { before: 120, after: 60 },
  children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: COLOR.MUTED })] });

// 7. 单元格（支持"字符串"或"[字符串, opts]"两种写法）
const cellOf = (content, opts = {}) => {
  const para = Array.isArray(content) ? content : [content];
  const children = para.map(c => typeof c === 'string'
    ? p(txt(c, { size: opts.size || 20, bold: opts.bold, color: opts.color }),
        { align: opts.align, before: 0, after: 0, line: 260 })
    : c);
  return new TableCell({
    width: { size: opts.width, type: WidthType.DXA },
    borders: opts.borderless ? noBordersAll : cellBorders,
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
    children,
  });
};
const rowOf = (cells, opts = {}) => new TableRow({ tableHeader: !!opts.header, children: cells });

// 8. 表格（headers + rows + 列宽数组）
const tableOf = (headers, rows, widthsBefore, opts = {}) => {
  const widths = scaleWidths(widthsBefore);
  const total = widths.reduce((a, b) => a + b, 0);
  const headerCells = headers.map((h, i) => cellOf(h, {
    width: widths[i], fill: COLOR.PRIMARY_LIGHT, bold: true, size: 20,
    align: opts.headerAlign || AlignmentType.CENTER,
  }));
  const bodyRows = rows.map((row, rIdx) => rowOf(row.map((cell, cIdx) => {
    const cellOpts = {
      width: widths[cIdx], size: 20,
      align: opts.bodyAlign?.[cIdx] || AlignmentType.LEFT,
      fill: opts.zebra && rIdx % 2 === 1 ? COLOR.ALT_ROW : undefined,
    };
    return Array.isArray(cell)
      ? cellOf(cell[0], { ...cellOpts, ...cell[1] })  // [text, override-opts]
      : cellOf(cell, cellOpts);
  })));
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [rowOf(headerCells, { header: true }), ...bodyRows],
  });
};

// 9. callout 框（1×1 表格 + 左厚边框 + 浅色 BG）
const callout = (lines, opts = {}) => {
  const paras = lines.map((line, i) => typeof line === 'string'
    ? p(txt(line, { color: opts.textColor, bold: opts.bold || i === 0, size: opts.size || 22 }),
        { before: i === 0 ? 0 : 30, after: i === lines.length - 1 ? 0 : 30 })
    : line);
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: [CONTENT_WIDTH],
    rows: [rowOf([new TableCell({
      width: { size: CONTENT_WIDTH, type: WidthType.DXA },
      borders: {
        top: { style: BorderStyle.SINGLE, size: 12, color: opts.borderColor || COLOR.PRIMARY },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: opts.borderColor || COLOR.PRIMARY },
        left: { style: BorderStyle.SINGLE, size: 24, color: opts.borderColor || COLOR.PRIMARY },
        right: { style: BorderStyle.SINGLE, size: 4, color: opts.borderColor || COLOR.PRIMARY },
      },
      shading: { fill: opts.fill || COLOR.PRIMARY_LIGHT, type: ShadingType.CLEAR, color: "auto" },
      margins: { top: 120, bottom: 120, left: 200, right: 200 },
      children: paras,
    })])],
  });
};
```

**用法示例**：

```javascript
// 普通表格
tableOf(
  ["字段", "内容"],
  [
    ["评审 ID", "LA-20260511-001"],
    ["决议", ["强制不通过", { color: COLOR.DANGER, bold: true }]],  // 单格覆盖样式
  ],
  [2800, 6560],   // 设计稿基准列宽（任意比例，会缩放到 CONTENT_WIDTH）
  { zebra: true } // 隔行底
);

// 警示 callout
callout([
  "⚠️ 8 项 must 一票否决",
  "按 SSoT rating-rubric.md 上线类型刚性规则……",
], { fill: COLOR.DANGER_BG, borderColor: COLOR.DANGER, textColor: COLOR.DANGER });
```

## 文档外壳模板

```javascript
const doc = new Document({
  creator: "...", title: "...", description: "...",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: COLOR.TEXT } } },
    paragraphStyles: [
      // 必须用 ID "Heading1"/"Heading2"/"Heading3" 覆盖内置样式（否则 TOC 用默认蓝）
      // outlineLevel 必填（0/1/2），否则 TOC 抓不到
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: COLOR.PRIMARY, font: FONT },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      // ... H2 / H3 同模式
    ],
  },
  numbering: {
    config: [{ reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] }],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: MARGIN } },
    headers: { default: new Header({ children: [/* 评审 ID / 公司 logo 等 */] }) },
    footers: { default: new Footer({ children: [/* 页码 + 关键警示 */] }) },
    children: content,  // 内容数组
  }],
});

Packer.toBuffer(doc).then(buf => fs.writeFileSync(target, buf));
```

## 11 个 pitfall（踩过的坑）

| # | 坑 | 解决 |
|:-:|---|---|
| 1 | 中文字体没指定 → LibreOffice 渲染丑 | 每个 TextRun 都带 `font: "PingFang SC"`（不能依赖 default styles） |
| 2 | 表格列宽 auto → 长字段强制换行 | 设计稿基准列宽 + `scaleWidths` 缩到 `CONTENT_WIDTH`；table.width + cell.width **两处都设** |
| 3 | `WidthType.PERCENTAGE` 在 Google Docs 渲染异常 | 全部用 `WidthType.DXA` |
| 4 | `ShadingType.SOLID` 让 cell 整块变黑 | 用 `ShadingType.CLEAR`（这是 docx 协议惯例反直觉的地方） |
| 5 | 段前段后 spacing 用默认 → 文档膨胀 30% | H1=240/120、H2=160/80、p=40/40、表格周边=30/30 |
| 6 | `PageBreak` 单独放 → 生成无效 XML | 必须在 Paragraph 里：`new Paragraph({ children: [new PageBreak()] })` 或 `pageBreakBefore: true` |
| 7 | bullet 用 `• Item` 字面字符 | 必须 `numbering.config` + `LevelFormat.BULLET` + Paragraph 的 `numbering: { reference: "bullets", level: 0 }` |
| 8 | docx-js 默认 A4，国内场景 OK；但海外项目要 Letter | A4: 11906×16838 / Letter: 12240×15840（都是 DXA） |
| 9 | cell margins **不计入** columnWidths → 实际可用窗口比想象小 | columnWidths 总和 == table.width；cell 内 padding 是 margins 单独算 |
| 10 | TOC 标题没出现 | Heading1/2/3 必须用确切 ID 覆盖样式 + `outlineLevel` 必填 |
| 11 | `validate.py` 依赖 defusedxml 可能没装 | 跳过 validate.py，用 `pandoc → plain` 反向读 + `unzip -l` 看结构替代 |

## 生成 → 预览 → 反馈闭环

```bash
# 1. 安装依赖
npm install -g docx

# 2. 写脚本到 /tmp/gen.js（不要写到项目目录，跑完即弃）

# 3. 跑生成
NODE_PATH=$(npm root -g) node /tmp/gen.js

# 4. 转 PDF 看效果（LibreOffice 会用 PingFang SC fallback）
python3 .claude/skills/docx/scripts/office/soffice.py --headless --convert-to pdf output.docx

# 5. 截图前 6 页
pdftoppm -jpeg -r 110 -f 1 -l 6 output.pdf /tmp/preview

# 6. Read JPG 验证视觉
#    （如有问题：改 token / 列宽 / spacing，回到 3）

# 7. 反向 pandoc 验证内容完整性
pandoc output.docx -t plain | head -60
```

**关键**：截图给用户看比 review JS 代码有效 10 倍。**像设计师一样反复看渲染图，不是像程序员一样 review 代码**。

## 用户反馈映射（常见 → 调整）

| 用户反馈 | 你要调的 token |
|---|---|
| "格式混乱" / "看着不专业" | 整体路径换 docx-js（不要再用 pandoc 默认） |
| "页边距太宽" | `MARGIN` 左右 1440 → 720；重算 `CONTENT_WIDTH` |
| "表格分行" | 同上 + 重新分配 `widthsBefore`（让长字段列更宽） |
| "段前段后大" | H1 H2 H3 + p 的 spacing 全局缩 50% |
| "颜色太花" / "正式场合" | 砍掉 OK 绿 / WARN 黄，只保留 PRIMARY + DANGER + MUTED |
| "中文字体丑" | 检查每个 TextRun 是否带 `font: FONT`；考虑加 `Microsoft YaHei` 备选 |
| "想要封面页" | section 0 加居中大标题 + 元信息 + 红框 callout |
| "想要目录" | 加 `new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" })`；Word 打开后 F9 刷新 |
| "页码不对 / 没页眉" | section.headers/footers + `PageNumber.CURRENT` / `TOTAL_PAGES` |

## 结构化数据 → 表格（必学技巧）

**反面**：每行手写 `new TableRow({...})` 几十次 → 难维护
**正面**：

```javascript
const data = [
  ["LA-7", "TA", "35", "API 网关未注册"],
  ["LA-12", "SEC", "25", "安全确认表缺失"],
  // ... 数据驱动
];

tableOf(
  ["要素", "责任", "评分", "依据"],
  data.map(row => [
    row[0],
    row[1],
    [row[2], { color: COLOR.DANGER, bold: true }],  // 第 3 列根据值染色
    row[3],
  ]),
  [1000, 1000, 800, 6560]  // 基准列宽
);
```

**判定颜色的逻辑写在 `.map` 里**（如 `score < 60 → DANGER`），不要复制粘贴 N 次手工染色。

## 决策矩阵 — 不需要 docx-js 的反例

| 场景 | 用什么 | 原因 |
|---|---|---|
| 1 页备忘录 | pandoc | 不值得写 600 行 JS |
| 内部 README | 留 markdown | 别强行 docx |
| 含复杂数学公式 | LaTeX → PDF | docx 公式渲染不稳 |
| 1000+ 行数据表 | xlsx skill | docx 表格大了渲染慢 |
| 简历 / 投递书 | Word 模板手填 | 别造轮子 |
| 含截图 / 图片 | docx-js + ImageRun（必须带 `type` 参数） | OK 但要算图片尺寸（EMU 单位，914400 = 1 inch） |

## 模板脚本（直接抄）

完整可跑的脚本骨架见本评审实战：参考本仓库 commit 中 `/tmp/gen-decision-docx.js`（v2 版本，30.8KB / 15 页 A4 / 9 节内容 / 封面页 / TOC / 页眉页脚 / 多 callout）。复用清单：

1. 顶部 `const { FONT, COLOR, MARGIN, CONTENT_WIDTH } = ...` 一键改主题色
2. 9 个 helper 函数完全无 4A 业务耦合
3. content 数组逐节 push → `h1` → 段落 → `tableOf` → `callout` → 下一节
4. 最后 `new Document({ styles, numbering, sections })` 包装

## 自检清单（交付前 5 项）

- [ ] 所有 TextRun 都带 `font: FONT`（grep `new TextRun({` 看有没漏的）
- [ ] 所有 Table 都用 `WidthType.DXA`（grep `PERCENTAGE` 应该为空）
- [ ] 所有 ShadingType 都是 `CLEAR`（grep `SOLID` 应该为空）
- [ ] 跑一次生成 + soffice 转 PDF + 第 1 / 3 / 5 页截图，自己先看一遍像不像一份"正式报告"
- [ ] 反向 `pandoc x.docx -t plain | head -60` 验证内容没丢

通过 = 可交付用户。
