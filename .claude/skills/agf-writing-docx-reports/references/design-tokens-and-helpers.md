# 设计 token + spacing + 9 个 helper + 文档外壳（docx-js 全套）

> 从 `SKILL.md` 下沉的完整参考。**动手写任何 docx-js 生成脚本前必读本文全文**——token、spacing 数值、helper、外壳、装配顺序全在这里，不要凭记忆手写。

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

## 段落与表格 spacing（收紧版，必背）

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

**经验**：default spacing（before 240+ / after 180+）= 19 页；收紧后 15 页（-21%）。**段前段后是 docx 最易膨胀的维度**。

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

**染色逻辑写在 `.map` 里**（如 `score < 60 → DANGER`），别复制粘贴 N 次手工染色。

## 模板脚本（直接抄）

无独立模板文件——直接用上文"9 个可复用 helper" + "文档外壳模板"两节自拼骨架（实战参考：15 页 A4 / 9 节 / 封面页 / TOC / 页眉页脚 / 多 callout）。装配顺序：

1. 顶部 `const { FONT, COLOR, MARGIN, CONTENT_WIDTH } = ...` 一键改主题色
2. 粘 9 个 helper 函数（完全无业务耦合）
3. content 数组逐节 push → `h1` → 段落 → `tableOf` → `callout` → 下一节
4. 最后 `new Document({ styles, numbering, sections })` 包装
