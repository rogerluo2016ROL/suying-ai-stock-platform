// 4A 评审决议书 docx 生成器 — 阅读友好版 v2
// v2: 页边距收窄 / 表格列宽放大避免换行 / 段前段后收紧

const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber,
} = require('docx');

const FONT = "PingFang SC";
const FONT_EN = "Arial";

// 页面：A4 (11906x16838 DXA)；左右边距 720 (0.5")，上下 900 (0.625")
const MARGIN = { top: 900, right: 720, bottom: 900, left: 720 };
const CONTENT_WIDTH = 11906 - MARGIN.left - MARGIN.right; // = 10466 DXA（原 9026 → +1440）

const COLOR = {
  TEXT: "1F1F1F",
  MUTED: "595959",
  PRIMARY: "1F4E79",
  PRIMARY_LIGHT: "D9E2F3",
  DANGER: "C00000",
  DANGER_BG: "FCE4E4",
  WARN: "BF8F00",
  WARN_BG: "FFF2CC",
  OK: "548235",
  BORDER: "BFBFBF",
  ALT_ROW: "F7F7F7",
};

const border = { style: BorderStyle.SINGLE, size: 4, color: COLOR.BORDER };
const cellBorders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBordersAll = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

// ─── helper ────────────────────────────────────────────
// 列宽按比例缩到 CONTENT_WIDTH（之前以 9360 为基准设计）
const scaleWidths = (widths, target = CONTENT_WIDTH) => {
  const sum = widths.reduce((a, b) => a + b, 0);
  const scaled = widths.map(w => Math.round(w * target / sum));
  // 修正取整误差，全部塞回最后一列
  const diff = target - scaled.reduce((a, b) => a + b, 0);
  scaled[scaled.length - 1] += diff;
  return scaled;
};

const txt = (text, opts = {}) => new TextRun({
  text: String(text),
  font: FONT,
  size: opts.size || 22,
  bold: !!opts.bold,
  color: opts.color || COLOR.TEXT,
  highlight: opts.highlight,
  italics: !!opts.italics,
});

// 段落 spacing 全局收紧（v2: before/after 默认 40，line 280）
const p = (children, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.LEFT,
  spacing: { before: opts.before ?? 40, after: opts.after ?? 40, line: opts.line ?? 280 },
  children: Array.isArray(children) ? children : [children],
  pageBreakBefore: !!opts.pageBreakBefore,
  numbering: opts.numbering,
});

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 240, after: 120 },
  pageBreakBefore: true,
  children: [new TextRun({ text, font: FONT, size: 32, bold: true, color: COLOR.PRIMARY })],
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 160, after: 80 },
  children: [new TextRun({ text, font: FONT, size: 26, bold: true, color: COLOR.PRIMARY })],
});

const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 120, after: 60 },
  children: [new TextRun({ text, font: FONT, size: 23, bold: true, color: COLOR.MUTED })],
});

// cell margins 收紧（v2: 60/60/100/100）
const cellOf = (content, opts = {}) => {
  const para = Array.isArray(content) ? content : [content];
  const children = para.map(c => {
    if (typeof c === 'string') {
      return p(txt(c, { size: opts.size || 20, bold: opts.bold, color: opts.color }),
        { align: opts.align, before: 0, after: 0, line: 260 });
    }
    return c;
  });
  return new TableCell({
    width: { size: opts.width, type: WidthType.DXA },
    borders: opts.borderless ? noBordersAll : cellBorders,
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
    children,
  });
};

const rowOf = (cells, opts = {}) => new TableRow({
  tableHeader: !!opts.header,
  children: cells,
});

const tableOf = (headers, rows, widthsBefore, opts = {}) => {
  const widths = scaleWidths(widthsBefore);
  const totalWidth = widths.reduce((a, b) => a + b, 0);
  const headerCells = headers.map((h, i) => cellOf(h, {
    width: widths[i], fill: COLOR.PRIMARY_LIGHT, bold: true, size: 20,
    align: opts.headerAlign || AlignmentType.CENTER,
  }));
  const bodyRows = rows.map((row, rIdx) =>
    rowOf(row.map((cell, cIdx) => {
      const cellOpts = {
        width: widths[cIdx], size: 20,
        align: opts.bodyAlign?.[cIdx] || AlignmentType.LEFT,
        fill: opts.zebra && rIdx % 2 === 1 ? COLOR.ALT_ROW : undefined,
      };
      if (Array.isArray(cell)) {
        return cellOf(cell[0], { ...cellOpts, ...cell[1] });
      }
      return cellOf(cell, cellOpts);
    }))
  );
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: [rowOf(headerCells, { header: true }), ...bodyRows],
  });
};

// callout 框（v2: 宽度跟随 CONTENT_WIDTH）
const callout = (lines, opts = {}) => {
  const paras = lines.map((line, i) => {
    if (typeof line === 'string') {
      return p(txt(line, { color: opts.textColor, bold: opts.bold || i === 0, size: opts.size || 22 }),
        { before: i === 0 ? 0 : 30, after: i === lines.length - 1 ? 0 : 30, line: 280 });
    }
    return line;
  });
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

const spacer = (size = 60) => new Paragraph({ spacing: { before: size, after: size }, children: [new TextRun("")] });

// ─── 文档内容 ────────────────────────────────────────
const content = [];

// COVER
content.push(
  new Paragraph({
    spacing: { before: 1800, after: 160 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "4A 架构评审最终决议书", font: FONT, size: 56, bold: true, color: COLOR.PRIMARY })],
  }),
  new Paragraph({
    spacing: { before: 80, after: 400 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Final Decision of the 4A Architecture Review", font: FONT_EN, size: 24, color: COLOR.MUTED, italics: true })],
  }),
  new Paragraph({
    spacing: { before: 120, after: 120 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "呼叫中心系统（CCS）改善项目", font: FONT, size: 36, bold: true })],
  }),
  new Paragraph({
    spacing: { before: 0, after: 500 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "终验收议案 · 上线试运行评审（刚性）", font: FONT, size: 24, color: COLOR.MUTED })],
  }),
);

content.push(
  callout([
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 40, after: 60 },
      children: [new TextRun({ text: "决议结论", font: FONT, size: 22, color: COLOR.DANGER, bold: true })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 40, after: 60 },
      children: [new TextRun({ text: "强制不通过 / 禁止上线", font: FONT, size: 48, bold: true, color: COLOR.DANGER })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 60, after: 40 },
      children: [new TextRun({ text: "★ 触发 8 项 must 一票否决（凌驾任何柔性映射） ★", font: FONT, size: 20, color: COLOR.DANGER })],
    }),
  ], { fill: COLOR.DANGER_BG, borderColor: COLOR.DANGER, bold: false }),
);

content.push(spacer(300));

// 封面元信息表（无边框，居中）
const coverMetaWidth = 9000;
const coverMetaWidths = [3200, coverMetaWidth - 3200];
content.push(new Table({
  width: { size: coverMetaWidth, type: WidthType.DXA },
  columnWidths: coverMetaWidths,
  alignment: AlignmentType.CENTER,
  rows: [
    ["评审 ID", "LA-20260511-001"],
    ["评审类型", "Launch（上线试运行 / 终验收）"],
    ["决议日期", "2026-05-11"],
    ["评审主席", "PMO（pmo@LA20260511Team）"],
    ["评审团队", "PMO + AA + TA + DA + SEC + DEP（共 6 角色）"],
    ["整体评分", "50.60 / 100（5 专家平均）"],
    ["must 触发", "8 / 9"],
  ].map(([k, v]) => rowOf([
    new TableCell({
      width: { size: coverMetaWidths[0], type: WidthType.DXA },
      borders: noBordersAll,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: [p(txt(k, { color: COLOR.MUTED, size: 20 }), { before: 0, after: 0, line: 260 })],
    }),
    new TableCell({
      width: { size: coverMetaWidths[1], type: WidthType.DXA },
      borders: noBordersAll,
      margins: { top: 40, bottom: 40, left: 80, right: 80 },
      children: [p(txt(v, { bold: true, size: 22 }), { before: 0, after: 0, line: 260 })],
    }),
  ])),
}));

// ── 目录 ──
content.push(
  new Paragraph({
    pageBreakBefore: true,
    spacing: { before: 0, after: 200 },
    children: [new TextRun({ text: "目录", font: FONT, size: 36, bold: true, color: COLOR.PRIMARY })],
  }),
  new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
);

// ── 一、评审基本信息 ──
content.push(h1("一、评审基本信息"));
content.push(tableOf(
  ["字段", "内容"],
  [
    ["评审 ID", "LA-20260511-001"],
    ["评审主席", "PMO（pmo@LA20260511Team）"],
    ["评审团队", "LA20260511Team（PMO + AA + TA + DA + SEC + DEP 共 6 角色）"],
    ["评审启动日期", "2026-05-11"],
    ["决议出具日期", "2026-05-11"],
    ["待评审材料", "关于呼叫中心系统(CCS)改善项目终验收的议案.pptx（13 张幻灯片 / 7.1MB）"],
    ["项目名称", "呼叫中心系统（CCS）改善项目"],
    ["项目分类", "系统类 / 新建"],
    ["业务 OWNER", "用户服务部 / 杨杭组长"],
    ["责任部门", "数字化部（汇报）+ 用户服务部（业务方）"],
    ["立项金额", "109.7 万元"],
    ["合同金额", "87.4 万元（合同 < 立项，节约 22.3 万）"],
    ["项目时间线", "立项 2024.12 → 蓝图 2025.5 → 已上线 2025.12 → 验收 2026.4 → 本次评审 2026.5"],
    ["上线状态", "已上线 5 个月（本次为终验收议案）"],
    ["公司要素表", "09_一体化项目上线试运行评审要素表-系统类-V4.0.xlsx（26 项）"],
  ],
  [2800, 6560], { zebra: true }
));

// ── 二、决议过程时间轴 ──
content.push(h1("二、决议过程时间轴"));
content.push(p(txt("5 阶段流程；阶段 4 / 5 由用户决策跳过", { color: COLOR.MUTED, size: 20 })));
content.push(tableOf(
  ["阶段", "Skill", "主要产出", "状态", "关键产物"],
  [
    ["0", "—", "评审章程 + 材料提取 + 澄清问题", ["✅ 完成", { color: COLOR.OK, bold: true }], "00-charter.md / material.txt"],
    ["1", "4a-summarizing-plan", "PMO 客观摘要（10 节）", ["✅ 完成", { color: COLOR.OK, bold: true }], "01-summary.md"],
    ["2", "4a-independent-review", "5 专家独立评审，26 条意见", ["✅ 完成", { color: COLOR.OK, bold: true }], "02-individual-opinions/*.md × 5"],
    ["3", "4a-roundtable-discussion", "圆桌讨论 + 团队汇总 + 一轮预评分", ["✅ 完成", { color: COLOR.OK, bold: true }], "03-roundtable.md / 04-team-consolidated.md"],
    ["4", "4a-defense-qa", "21 个封闭问题（用户决策不答辩 → 改作整改清单）", ["⚠️ 跳过", { color: COLOR.WARN, bold: true }], "05-defense-questions.md"],
    ["5", "4a-second-round-review", "二轮评审 + 最终决议", ["⚠️ 跳过", { color: COLOR.WARN, bold: true }], "直接出本文件"],
    ["5+", "—", "蓝图一致性 + 上轮整改闭环", ["⚠️ 无法做", { color: COLOR.WARN, bold: true }], "详见第八节"],
  ],
  [500, 1800, 2900, 1100, 3060],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.LEFT] }
));

content.push(h3("阶段 4 / 5 跳过说明"));
const bulletList = [
  "用户决策（2026-05-11）：声明本轮不答辩，直接出最终决议",
  "后果：5 专家 26 条一轮意见全部锁定为最终意见（status = open），不进入二轮重审",
  "PMO 自责 3 项 must（LA-18 / 22 / 24）：按 PMO 一轮预判数字锁定（50 / 55 / 35）",
  "整改入口：本决议书第六节 + 05-defense-questions.md 19 项整改 TODO",
];
bulletList.forEach(item => content.push(
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 30, after: 30, line: 280 },
    children: [txt(item)],
  })
));

// ── 三、最终评分 ──
content.push(h1("三、最终评分"));
content.push(h2("3.1 各专家 expert_average（一轮 = 最终，无二轮）"));
content.push(tableOf(
  ["专家", "主责要素", "意见数", "P0/P1/P2", "expert_average", "must 触发"],
  [
    ["AA", "LA-1/2/3", "3", "3 / 0 / 0", "54.33", "0"],
    ["TA", "LA-5/6/7★", "5", "3 / 1 / 1", "58.00", ["1（LA-7）", { color: COLOR.DANGER, bold: true }]],
    ["DA", "LA-8/9/16 + 1 GENERIC", "6", "4 / 1 / 1", "53.67", "0"],
    ["SEC", "LA-12★/13★/14★/15", "4", "4 / 0 / 0", ["26.25", { color: COLOR.DANGER, bold: true }], ["3（LA-12/13/14）", { color: COLOR.DANGER, bold: true }]],
    ["DEP", "LA-4/10/11/17★/19/20★/21/26", "8", "4 / 3 / 1", "60.75", ["1（LA-17）", { color: COLOR.DANGER, bold: true }]],
    [["合计（5 专家）", { bold: true }], "21 主责", ["26", { bold: true }], ["18 / 5 / 3", { bold: true }], "—", ["5", { color: COLOR.DANGER, bold: true }]],
  ],
  [800, 2400, 700, 1300, 1500, 2660],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER] }
));

content.push(h2("3.2 overall_score_final 计算"));
content.push(callout([
  "overall_score_final = (54.33 + 58.00 + 53.67 + 26.25 + 60.75) / 5 = 50.60",
  "柔性映射：50.60 落在 40-59 段 → \"不通过（修订重审）\"",
], { fill: COLOR.PRIMARY_LIGHT, borderColor: COLOR.PRIMARY }));

content.push(h2("3.3 PMO 自责 3 项 must 评分"));
content.push(tableOf(
  ["Excel#", "要素", "rating_score", "状态"],
  [
    [["LA-18 ★", { bold: true }], "SIT / UAT 完成（业务方签字）", ["50", { color: COLOR.DANGER, bold: true }], ["⚠️ < 60 → must 一票否决", { color: COLOR.DANGER }]],
    [["LA-22 ★", { bold: true }], "质量问题关闭符合《公司 IT 系统质量关闭标准》", ["55", { color: COLOR.DANGER, bold: true }], ["⚠️ < 60 → must 一票否决", { color: COLOR.DANGER }]],
    [["LA-24 ★", { bold: true }], "关键交付文档已提交至云盘", ["35", { color: COLOR.DANGER, bold: true }], ["⚠️ < 60 → must 一票否决", { color: COLOR.DANGER }]],
  ],
  [1100, 4500, 1300, 2460],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.LEFT] }
));
content.push(p(txt("PMO 自责 expert_average = (50 + 55 + 35) / 3 = 46.67", { size: 20, color: COLOR.MUTED })));

content.push(h2("3.4 总决议分数"));
content.push(tableOf(
  ["维度", "数值"],
  [
    ["overall_score_final（5 专家平均）", ["50.60", { bold: true, size: 22 }]],
    ["含 PMO 自责的扩展评分（6 视角平均）", ["49.95", { bold: true, size: 22 }]],
    ["柔性结论映射", "不通过 / 修订重审"],
    [["刚性结论（凌驾柔性）", { bold: true, color: COLOR.DANGER }], ["强制不通过 / 禁止上线（8 项 must 一票否决）", { bold: true, color: COLOR.DANGER }]],
  ],
  [4800, 4560],
  { zebra: true }
));

// ── 四、决议结论 ──
content.push(h1("四、决议结论 ★"));
content.push(h2("4.1 总体决议"));
content.push(callout([
  "强制不通过 / 禁止上线 — 触发 8 项 must 一票否决",
  "按 SSoT rating-rubric.md 上线类型刚性规则：任一 must 项 rating_score < 60 → 强制不通过，禁止上线。",
  "本次 8 项 must（LA-7 / LA-12 / LA-13 / LA-14 / LA-17 / LA-18 / LA-22 / LA-24）全部 < 60，刚性触发凌驾任何柔性映射结论。",
], { fill: COLOR.DANGER_BG, borderColor: COLOR.DANGER, textColor: COLOR.DANGER }));

content.push(h2("4.2 8 项 must 一票否决核对表"));
const mustData = [
  ["1", "LA-7", "对外接口已全部注册到 API 网关", "TA", "35", "全文 grep \"API/网关/gateway/注册\" 0 命中", "R-LA-TA-001"],
  ["2", "LA-12", "《安全需求确认表》must 项全部满足", "SEC", "25", "全文 grep \"安全 / 等保\" 0 命中", "R-LA-SEC-002"],
  ["3", "LA-13", "严重高危漏洞 100% 修复", "SEC", "25", "全文 grep \"漏洞 / SCA / 渗透测试\" 0 命中", "R-LA-SEC-003"],
  ["4", "LA-14", "权限矩阵 + 关键岗位安全责任书签批", "SEC", "20", "全文 grep \"权限矩阵 / 责任书\" 0 命中", "R-LA-SEC-001"],
  ["5", "LA-17", "系统数据备份按方案配置完成", "DEP", "30", "全文 grep \"备份/恢复/容灾/RTO/RPO\" 0 命中（事实风险 NR-001）", "R-LA-DEP-004"],
  ["6", "LA-18", "完成 SIT、UAT", "PMO", "50", "Slide 3 仅 \"100% 完成\"声称，无 UAT 业务方签字单", "PMO 自评"],
  ["7", "LA-22", "质量问题关闭符合 IT 系统质量关闭标准", "PMO", "55", "Slide 3 \"126 BUG 100% 关闭\"无严重度分级 + 关闭准则引用", "PMO 自评"],
  ["8", "LA-24", "关键交付文档已提交至云盘", "PMO", "35", "全文未见\"云盘/归档/SharePoint\"等关键词", "PMO 自评"],
];
content.push(tableOf(
  ["#", "Excel#", "公司要素", "责任", "score", "触发依据", "来源意见"],
  mustData.map(row => [
    row[0],
    [row[1], { bold: true, color: COLOR.DANGER }],
    row[2],
    row[3],
    [row[4], { color: COLOR.DANGER, bold: true }],
    row[5],
    row[6],
  ]),
  [400, 800, 2600, 600, 600, 3260, 1100],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER] }
));
content.push(p(txt("must 项责任分布：SEC 持 3 / DEP 持 1 / TA 持 1 / PMO 自责 3 = 共 8 项", { color: COLOR.MUTED })));

content.push(h2("4.3 一票否决解除路径"));
content.push(tableOf(
  ["must 项", "解除条件", "整改对接"],
  [
    ["LA-7", "API 网关注册率 100% 或集团技术架构办公室豁免备案", "Q-TA-01"],
    ["LA-12", "《安全需求确认表》签批 + 等保备案", "Q-SEC-01"],
    ["LA-13", "SAST + SCA + DAST 三类报告齐 + 严重高危 100% 修复（独立第三方出具）", "Q-SEC-02 / Q-CROSS-02"],
    ["LA-14", "权限矩阵签批 + 关键岗位安全责任书签批", "Q-SEC-03"],
    ["LA-17", "备份方案 + 首次成功时间戳 + 恢复演练记录", "Q-DEP-01"],
    ["LA-18", "SIT/UAT 完整报告 + 业务方签字凭证", "Q-PMO-01"],
    ["LA-22", "126 BUG 严重度分级 + 关闭标准引用", "Q-PMO-02"],
    ["LA-24", "关键文档清单（12+ 项）已云盘归档", "Q-PMO-03"],
  ],
  [900, 6700, 1760],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER] }
));
content.push(p(txt("任一条件未达成则维持 must 不通过 — 8 项全部解除是新一轮评审通过的必要条件。", { bold: true, color: COLOR.DANGER })));

// ── 五、关键风险清单 ──
content.push(h1("五、关键风险清单"));
content.push(h2("5.1 上线后事实风险（建议立即走集团 IT 应急上报口径）"));
content.push(callout([
  "⚠️ 以下两项不是\"未来潜在风险\"，而是已发生且持续 150+ 天的事实风险敞口",
], { fill: COLOR.WARN_BG, borderColor: COLOR.WARN, textColor: COLOR.WARN }));

content.push(h3("NR-001 ★ 5 个月零备份事实风险"));
content.push(tableOf(
  ["字段", "内容"],
  [
    ["触发依据", "DEP-004 全文 grep 0 命中 + 系统已上线 2025.12，截至 2026.5 持续 150+ 天"],
    ["风险性质", ["持续性事实风险（非未来风险）", { color: COLOR.DANGER, bold: true }]],
    ["业务影响", "5 个月内任何数据丢失 / 损坏事件均无法恢复；客档 / 工单 / 通话录音 / 1000+ 用户数据全暴露在不可逆损失风险下"],
    ["应急建议", "不仅是评审整改问题 — 建议立即走集团 IT 应急上报口径：① 即刻部署备份方案 + 首次全量备份；② 评估 2025.12 至首备日之间的数据丢失风险窗口；③ 若有运营事件需追溯，按数据丢失事故处理"],
    ["责任跟踪", "IT 经理（吕来源）+ 备份负责人（章程 LA-17 主责）+ 数字化部"],
  ],
  [1400, 7960],
  { zebra: true }
));

content.push(h3("NR-002 ★ 5 个月安全裸奔事实风险"));
content.push(tableOf(
  ["字段", "内容"],
  [
    ["触发依据", "SEC 全文 grep \"安全 / 漏洞 / 权限矩阵 / SOC / 日志审计\" 0 命中 + 已上线 5 个月"],
    ["风险性质", ["持续性事实风险（非未来风险）", { color: COLOR.DANGER, bold: true }]],
    ["业务影响", "① 期间若发生安全事件 / 数据泄露 → 无日志可溯、无人察觉；② PII 高敏（客档 + 通话录音 + 车联网实名 + 流量 + 置换补贴）+ 国家《个人信息保护法》直接适用场景；③ 8 年关基类系统 + 全国 400 客服热线 → 等保级别建议 ≥ 2 级但未备案；④ Java + Vue + ES 技术栈 Log4Shell/Spring4Shell/ES 未授权访问等 CVE 未评估"],
    ["应急建议", "建议立即走集团合规上报 + 集团信息安全应急口径：① 立即组织 SAST/SCA/DAST 三类安全扫描；② 5 个月内 SOC 日志补查；③ 等保定级备案；④ PII 字段级分类分级 + PIA 评估"],
    ["责任跟踪", "安全专员 + 信息安全团队 + 法务合规（个保法对接）"],
  ],
  [1400, 7960],
  { zebra: true }
));

content.push(h2("5.2 评审风险（未来潜在）"));
content.push(tableOf(
  ["#", "名称", "触发依据", "处理建议"],
  [
    ["NR-003", "关基类系统等保定级未提及", "SEC 红队思维 + 全国 400 客服热线 + 月均故障 8.7 次", "建议至少等保 2 级备案"],
    ["NR-004", "8 年老系统 → 新系统切换数据完整性风险", "DA-003 \"迁移 100% 完成\"四字无验证 + 1000+ 用户 + 历史工单 / 通话录音", "迁移条数对账 + 抽样校验 + 回滚预案"],
    ["NR-005", "AA + TA 同人兼任 + SoD 控制风险", "ISO 27001 A.6.1.2 + 等保 2.0 第 7.1.10；数据组与实施组成员重叠", "引入独立第三方 / 签订《职责分离声明》"],
  ],
  [800, 2600, 3500, 2460],
  { zebra: true }
));

content.push(h2("5.3 26 条专家意见全表（最终锁定，status = open）"));
const opinions = [
  ["R-LA-AA-001", "AA", "LA-01", "P0", "55", "risk", "open"],
  ["R-LA-AA-002", "AA", "LA-02", "P0", "50", "risk", "open"],
  ["R-LA-AA-003", "AA", "LA-03", "P0", "58", "risk", "open"],
  ["R-LA-TA-001", "TA", "LA-07 ★", "P0", "35", "risk", "open"],
  ["R-LA-TA-002", "TA", "LA-05", "P0", "50", "risk", "open"],
  ["R-LA-TA-003", "TA", "LA-06", "P0", "55", "risk", "open"],
  ["R-LA-TA-004", "TA", "技术栈对齐", "P1", "65", "sensitivity", "open"],
  ["R-LA-TA-005", "TA", "TPS 笔误", "P2", "85", "non-risk", "open"],
  ["R-LA-DA-001", "DA", "LA-08", "P0", "35", "risk", "open"],
  ["R-LA-DA-002", "DA", "LA-09", "P0", "45", "risk", "open"],
  ["R-LA-DA-003", "DA", "LA-16", "P0", "40", "risk", "open"],
  ["R-LA-DA-004", "DA", "PII-001", "P0", "50", "risk", "open"],
  ["R-LA-DA-005", "DA", "data owner", "P1", "70", "risk", "open"],
  ["R-LA-DA-006", "DA", "数据生命周期", "P2", "82", "non-risk", "open"],
  ["R-LA-SEC-001", "SEC", "LA-14 ★", "P0", "20", "risk", "open"],
  ["R-LA-SEC-002", "SEC", "LA-12 ★", "P0", "25", "risk", "open"],
  ["R-LA-SEC-003", "SEC", "LA-13 ★", "P0", "25", "risk", "open"],
  ["R-LA-SEC-004", "SEC", "LA-15", "P0", "35", "risk", "open"],
  ["R-LA-DEP-001", "DEP", "LA-04", "P1", "68", "risk", "open"],
  ["R-LA-DEP-002", "DEP", "LA-10", "P0", "55", "risk", "open"],
  ["R-LA-DEP-003", "DEP", "LA-11", "P0", "50", "risk", "open"],
  ["R-LA-DEP-004", "DEP", "LA-17 ★", "P0", "30", "risk", "open"],
  ["R-LA-DEP-005", "DEP", "LA-19", "P1", "78", "risk", "open"],
  ["R-LA-DEP-006", "DEP", "LA-20 ★", "P2", "85", "non-risk", "open"],
  ["R-LA-DEP-007", "DEP", "LA-21", "P1", "65", "risk", "open"],
  ["R-LA-DEP-008", "DEP", "LA-26", "P0", "55", "risk", "open"],
];
content.push(tableOf(
  ["编号", "角色", "公司要素", "priority", "rating", "ATAM", "status"],
  opinions.map(row => {
    const isMust = row[2].includes("★");
    const isP0 = row[3] === "P0";
    const isLowScore = parseInt(row[4]) < 60;
    return [
      [row[0], { size: 18 }],
      row[1],
      [row[2], isMust ? { bold: true, color: COLOR.DANGER } : {}],
      [row[3], isP0 ? { color: COLOR.DANGER, bold: true } : { color: COLOR.MUTED }],
      [row[4], isLowScore ? { color: COLOR.DANGER, bold: true } : {}],
      [row[5], { size: 18, color: COLOR.MUTED }],
      [row[6], { size: 18, color: COLOR.MUTED }],
    ];
  }),
  [1800, 700, 1600, 900, 900, 1700, 1760],
  { zebra: true, bodyAlign: [AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER] }
));
content.push(p(txt("注：LA-20（性能压测）虽是 must 项但 rating = 85 ≥ 60，该 must 项已满足要求 — 是 8 项 must 触发外的唯一通过 must。", { color: COLOR.OK, bold: true })));

content.push(h2("5.4 PMO 自责 must 项整改要求"));
content.push(tableOf(
  ["Excel#", "整改要求", "责任人"],
  [
    ["LA-18", "SIT 报告 + UAT 报告 + 业务方（用户服务部 / 杨杭组长）签字单", "项目经理"],
    ["LA-22", "126 BUG 严重度分级 + 引用《公司 IT 系统质量关闭标准》具体版本号 + 关闭准则条款 + 遗留 BUG 清单", "项目经理"],
    ["LA-24", "12+ 项关键交付文档（含立项 / 蓝图 / 设计书 / SOW / SIT / UAT / 性能 / 安全 / 部署 / 培训 / 上线试运行报告 / 应急预案）已云盘归档清单 + 路径 + 日期", "PMO + 数字化部"],
  ],
  [900, 6900, 1560],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.CENTER] }
));

// ── 六、整改清单 ──
content.push(h1("六、整改清单"));
content.push(callout([
  "整改 TODO 全文：docs/4a-review/LA-20260511-001/05-defense-questions.md（19 项封闭式问题模板，每问含来源意见 ID + 期望证据格式）",
  "完成判定：用户在新一轮评审启动时提交 — (1) 19 项整改 TODO 全部书面应答 + 证据；(2) 26 条专家意见 status → resolved（PMO 校验通过）；(3) 8 项 must rating_score 全部 ≥ 60",
], { fill: COLOR.PRIMARY_LIGHT, borderColor: COLOR.PRIMARY }));

content.push(h2("6.1 19 项 TODO 配额（对应 8 项 must + 11 项 P0/P1 附属）"));
content.push(tableOf(
  ["整改组", "问题数", "关联 must", "整改输入物"],
  [
    [["SEC", { bold: true, color: COLOR.DANGER }], "3", ["LA-12 / LA-13 / LA-14（3 must）", { color: COLOR.DANGER }], "Q-SEC-01/02/03 → 安全需求确认表 + 三类报告 + 权限矩阵 + 责任书"],
    [["DEP", { bold: true }], "3", "LA-17（1 must）+ LA-10/11 P0 + 回滚", "Q-DEP-01/02/03 → 备份方案 + 生产环境申请 + 回滚预案"],
    [["TA", { bold: true }], "3", "LA-7（1 must）+ LA-5/6 P0", "Q-TA-01/02/03 → API 网关注册 + 接口文档 + 部署文档"],
    [["PMO", { bold: true }], "3", "LA-18 / LA-22 / LA-24（3 must）", "Q-PMO-01/02/03 → SIT/UAT + BUG 关闭标准 + 云盘归档"],
    [["DA", { bold: true }], "3", "间接 LA-12 PII", "Q-DA-01/02/03 → 数据入湖 + 主数据 + PII 分级"],
    [["AA", { bold: true }], "3", "间接 LA-18 / LA-22", "Q-AA-01/02/03 → 蓝图基线 + 外部对接 + 业务架构对照"],
    [["T-008 跨角色", { bold: true }], "3", "间接 LA-13 / LA-14", "Q-CROSS-01/02/03 → 独立第三方 + SoD 控制"],
  ],
  [1300, 800, 2700, 4560],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.LEFT] }
));

content.push(h2("6.2 整改优先级"));
content.push(tableOf(
  ["优先级", "整改组", "何时必须完成"],
  [
    [["🚨 紧急（应急上报）", { color: COLOR.DANGER, bold: true }], ["NR-001（备份）+ NR-002（安全裸奔）", { color: COLOR.DANGER }], ["立即（不等新一轮评审）", { color: COLOR.DANGER, bold: true }]],
    [["⚠️ 高（must 解除）", { color: COLOR.WARN, bold: true }], "8 项 must 对应整改组", "新一轮评审启动前"],
    ["📋 中（一致性基线）", "Q-AA-01 蓝图三件套", "新一轮评审启动前（影响 AA/TA/DA 全部核对）"],
    [["📋 低（P1 通用增强）", { color: COLOR.MUTED }], "TA-004 / DA-005/006 / AA-003 中台决策", "新一轮评审前 6 个月内"],
  ],
  [2100, 3600, 3660],
  { zebra: true }
));

// ── 七、跨角色冲突调和 ──
content.push(h1("七、跨角色冲突调和（T-008 同人兼任 AA + TA）"));
content.push(p(txt("本次评审唯一的 disputed 议题，PMO 已完成调和", { color: COLOR.MUTED, size: 20 })));

content.push(h2("7.1 议题概要"));
content.push(p([txt("议题 ID：", { color: COLOR.MUTED }), txt("T-008", { bold: true })]));
content.push(p([txt("类型：", { color: COLOR.MUTED }), txt("P1 冲突嫌疑 → 升级为 P0 SoD 违反风险（SEC 阶段 3 微调采纳后）")]));
content.push(p([txt("触发：", { color: COLOR.MUTED }), txt("Slide 13 显示 IT 经理伍明航同时担任 AA + TA；数据组成员（张敏、张健）与实施组成员重叠")]));

content.push(h2("7.2 各专家立场调和"));
content.push(tableOf(
  ["角色", "一轮立场", "圆桌讨论中", "最终调和"],
  [
    ["AA", "主动标记（R-LA-AA-002 责任栏 + 自评偏宽风险）", "主发言", ["认定存在风险", { color: COLOR.DANGER, bold: true }]],
    ["TA", "未否认", "圆桌交叉确认未回复（PMO SendMessage 30 分钟超时）", ["默认 disputed", { color: COLOR.WARN, bold: true }]],
    ["SEC", "阶段 2 弃权", "阶段 3 主动升级\"补充\"立场：触及 ISO 27001 A.6.1.2 + 等保 2.0 第 7.1.10", ["认定存在 SoD 双重风险", { color: COLOR.DANGER, bold: true }]],
    ["PMO", "关切", "章程已记录 → 决议书风险栏", "认定为决议书风险"],
    ["DA / DEP", "弃权（视角外）", "—", "弃权"],
  ],
  [900, 1900, 3500, 3060],
  { zebra: true, bodyAlign: [AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.LEFT, AlignmentType.LEFT] }
));

content.push(h2("7.3 PMO 调和结论"));
const conclusions = [
  "AA + SEC 两方书面立场一致（一治理风险 + 一 SoD 控制）→ T-008 共识转 agreed_with_caveat",
  "TA 未做书面反驳（PMO 已 SendMessage 但未在窗口内回复）→ 不视为 \"TA 反对\"",
  "PMO 不替专家拍板（铁律 5）：将 T-008 调和结果直接写入决议书风险栏 NR-005 + 整改 TODO 3 个跨角色问题（Q-CROSS-01/02/03），由用户在新一轮评审时书面应答",
];
conclusions.forEach(item => content.push(
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 30, after: 30, line: 280 },
    children: [txt(item)],
  })
));

// ── 八、下一步建议 ──
content.push(h1("八、下一步建议"));
content.push(h2("8.1 立即行动（不等新一轮评审）"));
content.push(callout([
  "🚨 NR-001 应急上报：5 个月零备份是事实风险，建议数字化部 + IT 经理立即走集团 IT 应急上报口径；同步部署备份方案 + 评估数据丢失风险窗口",
  "🚨 NR-002 应急上报：5 个月安全裸奔是事实风险，建议安全专员 + 法务合规走集团信息安全应急 + 个保法合规上报口径",
], { fill: COLOR.DANGER_BG, borderColor: COLOR.DANGER, textColor: COLOR.DANGER }));

content.push(h2("8.2 新一轮评审准备（建议 30-90 天内完成）"));
content.push(tableOf(
  ["项", "动作"],
  [
    ["8 项 must 整改证据齐全", "按第四节 4.3 解除路径补全"],
    ["基线文档三件套", "蓝图 + 系统设计说明书 + 技术协议书路径提供 — 这是 AA / TA / DA 全部一致性核对的根基"],
    ["PMO 自责 3 项 must 闭环", "项目经理 + 数字化部牵头补全 SIT/UAT 业务方签字 + BUG 分级 + 云盘归档"],
    ["跨角色调和（T-008）", "引入独立第三方做接口治理 / 部署架构 / 安全测试审查；或签订《职责分离声明》"],
  ],
  [2400, 6960],
  { zebra: true }
));

content.push(h2("8.3 新一轮评审启动方式"));
content.push(tableOf(
  ["方式", "适用场景", "启动命令"],
  [
    [["方式 A（推荐）", { bold: true, color: COLOR.OK }], "完成 8.1 + 8.2 后整改证据齐全", "/4a-review-launch <新材料路径>（建议复用前缀，新序号如 LA-20260801-001）"],
    ["方式 B", "整改后业务功能或架构有重大变更", "/4a-review-blueprint <蓝图材料> 退回蓝图评审"],
  ],
  [2000, 3700, 3660],
  { zebra: true }
));

content.push(h2("8.4 蓝图一致性 / 上轮整改闭环 文件未做说明"));
content.push(p(txt("按章程 launch 类型应产出：")));
const notDone = [
  "09-consistency-with-blueprint.md（蓝图一致性矩阵）",
  "10-action-closure-from-blueprint.md（上轮蓝图整改闭环验证）",
];
notDone.forEach(item => content.push(
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 30, after: 30, line: 280 },
    children: [txt(item)],
  })
));
content.push(p([
  txt("未做原因：", { bold: true, color: COLOR.DANGER }),
  txt("用户在阶段 0 答复\"材料后补\"含蓝图评审决议路径 — 基线缺失无法做一致性核对。"),
  txt("新一轮评审前用户必须提供：① 蓝图评审决议书 ② 蓝图整改清单，PMO 即可补出两份文件。", { bold: true }),
]));

// ── 九、签署 ──
content.push(h1("九、签署"));
content.push(tableOf(
  ["字段", "内容"],
  [
    ["评审主席", "PMO（pmo@LA20260511Team），评审性质：4A 架构评审"],
    ["决议出具日期", "2026-05-11"],
    ["决议依据", "SSoT rating-rubric.md 上线类型刚性规则 + 公司 LA-1~LA-26 主责要素表"],
    [["决议刚性", { bold: true, color: COLOR.DANGER }], ["强制不通过 / 禁止上线（8 项 must 一票否决，凌驾任何柔性映射）", { bold: true, color: COLOR.DANGER }]],
    ["评审专家签字", "AA / TA / DA / SEC / DEP 5 位专家书面意见已 hook 校验通过（先引后判 + 100 分制 + ATAM + 公司要素号 + grep 反查 100% 命中）"],
    ["用户确认状态", "待 team-lead 转用户审阅"],
  ],
  [2200, 7160],
  { zebra: true }
));

// ── 配套交付物 ──
content.push(h1("配套交付物归档清单"));
const archive = [
  ["00-charter.md", "评审章程（阶段 0）", "✅"],
  ["01-summary.md", "PMO 客观摘要 10 节（阶段 1）", "✅"],
  ["02-individual-opinions/AA-review.md", "3 条意见 / avg=54.33", "✅"],
  ["02-individual-opinions/TA-review.md", "5 条意见 / avg=58.00 / 1 must 触发", "✅"],
  ["02-individual-opinions/DA-review.md", "6 条意见 / avg=53.67", "✅"],
  ["02-individual-opinions/SEC-review.md", "4 条意见 / avg=26.25 / 3 must 触发", "✅"],
  ["02-individual-opinions/DEP-review.md", "8 条意见 / avg=60.75 / 1 must 触发", "✅"],
  ["03-roundtable.md", "8 核心 + 3 附录议题 + 立场矩阵（阶段 3）", "✅"],
  ["04-team-consolidated.md", "一轮预评分 + 共识 + 5 项新发现风险（阶段 3）", "✅"],
  ["05-defense-questions.md", "改作整改 TODO 清单（阶段 4 跳过）", "⚠️"],
  ["06-user-responses.md", "用户骨架（未填写，保留为新一轮答辩模板）", "⚠️"],
  ["08-final-decision.md / .docx", "本文件（最终决议）", "✅"],
  ["_extracted/material.txt", "PPTX 提取 13 张幻灯片 / 195 行", "✅"],
  ["07-individual-opinions-r2/", "阶段 5 跳过 → 无二轮意见", "⚠️"],
  ["09-consistency-with-blueprint.md", "用户未提供蓝图基线 → 无法产出", "⚠️"],
  ["10-action-closure-from-blueprint.md", "用户未提供蓝图整改清单 → 无法产出", "⚠️"],
];
content.push(tableOf(
  ["文件", "说明", "状态"],
  archive.map(row => [
    [row[0], { size: 18 }],
    [row[1], { size: 20 }],
    [row[2], { color: row[2] === "✅" ? COLOR.OK : COLOR.WARN, bold: true, size: 22 }],
  ]),
  [3700, 4900, 760],
  { zebra: true, bodyAlign: [AlignmentType.LEFT, AlignmentType.LEFT, AlignmentType.CENTER] }
));

content.push(spacer(200));
content.push(callout([
  "本次评审结束。本决议书 = 评审最终交付物。新一轮评审需按第八节 8.3 重新启动。",
  "决议可追溯性声明：本文件第四 / 五 / 七节每条结论均可回溯到 02-individual-opinions/{ROLE}-review.md 中的具体 opinion_id；评分计算可回溯到 04-team-consolidated.md 第一节；调和过程可回溯到 03-roundtable.md 各议题立场矩阵 + PMO 编排记录。",
], { fill: COLOR.PRIMARY_LIGHT, borderColor: COLOR.PRIMARY }));

// ─── Document ────────────────────────────────────────
const doc = new Document({
  creator: "4A 评审团队 LA20260511Team",
  title: "4A 评审最终决议书 — CCS 改善项目终验收",
  description: "评审 ID: LA-20260511-001 / 决议: 强制不通过-禁止上线",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: COLOR.TEXT } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: COLOR.PRIMARY, font: FONT },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: COLOR.PRIMARY, font: FONT },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, color: COLOR.MUTED, font: FONT },
        paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 480, hanging: 240 } } },
      }],
    }],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: MARGIN,
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          spacing: { after: 0 },
          children: [
            new TextRun({ text: "4A 评审最终决议书 ", font: FONT, size: 18, color: COLOR.MUTED }),
            new TextRun({ text: "· LA-20260511-001", font: FONT, size: 18, color: COLOR.MUTED, italics: true }),
          ],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0 },
          children: [
            new TextRun({ text: "强制不通过 / 禁止上线 · ", font: FONT, size: 18, color: COLOR.DANGER }),
            new TextRun({ text: "第 ", font: FONT, size: 18, color: COLOR.MUTED }),
            new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: COLOR.MUTED }),
            new TextRun({ text: " 页 / 共 ", font: FONT, size: 18, color: COLOR.MUTED }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: 18, color: COLOR.MUTED }),
            new TextRun({ text: " 页", font: FONT, size: 18, color: COLOR.MUTED }),
          ],
        })],
      }),
    },
    children: content,
  }],
});

const target = '/Users/pc2026/Documents/DevApps/TopConsultant/docs/4a-review/LA-20260511-001/08-final-decision.docx';
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(target, buf);
  console.log(`✓ 已生成 v2: ${target} (${(buf.length / 1024).toFixed(1)} KB)`);
}).catch(err => {
  console.error('生成失败:', err);
  process.exit(1);
});
