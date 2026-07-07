const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat,
} = require('docx');

const FONT = 'PingFang SC';
const MARGIN = { top: 900, right: 720, bottom: 900, left: 720 };
const CONTENT_WIDTH = 11906 - MARGIN.left - MARGIN.right;
const COLOR = {
  TEXT: '1F1F1F',
  MUTED: '595959',
  PRIMARY: '1F4E79',
  PRIMARY_LIGHT: 'D9E2F3',
  DANGER: 'C00000',
  DANGER_BG: 'FCE4E4',
  WARN: 'BF8F00',
  WARN_BG: 'FFF2CC',
  OK: '548235',
  BORDER: 'BFBFBF',
  ALT_ROW: 'F7F7F7',
};

const border = { style: BorderStyle.SINGLE, size: 4, color: COLOR.BORDER };
const cellBorders = { top: border, bottom: border, left: border, right: border };

const scaleWidths = (widths, target = CONTENT_WIDTH) => {
  const sum = widths.reduce((a, b) => a + b, 0);
  const scaled = widths.map((w) => Math.round((w * target) / sum));
  scaled[scaled.length - 1] += target - scaled.reduce((a, b) => a + b, 0);
  return scaled;
};

const txt = (text, opts = {}) => new TextRun({
  text: String(text),
  font: FONT,
  size: opts.size || 22,
  bold: !!opts.bold,
  color: opts.color || COLOR.TEXT,
  italics: !!opts.italics,
});

const p = (children, opts = {}) => new Paragraph({
  alignment: opts.align || AlignmentType.LEFT,
  spacing: { before: opts.before ?? 40, after: opts.after ?? 40, line: opts.line ?? 280 },
  children: Array.isArray(children) ? children : [children],
  numbering: opts.numbering,
});

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 240, after: 120 },
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

const bullet = (text) => p(txt(text), { numbering: { reference: 'bullets', level: 0 }, before: 30, after: 30 });

const cellOf = (content, opts = {}) => {
  const para = Array.isArray(content) ? content : [content];
  const children = para.map((c) => {
    if (typeof c === 'string') {
      return p(txt(c, { size: opts.size || 20, bold: opts.bold, color: opts.color }), {
        align: opts.align,
        before: 0,
        after: 0,
        line: 260,
      });
    }
    return c;
  });
  return new TableCell({
    width: { size: opts.width, type: WidthType.DXA },
    borders: cellBorders,
    shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR, color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
    children,
  });
};

const rowOf = (cells, opts = {}) => new TableRow({ tableHeader: !!opts.header, children: cells });

const tableOf = (headers, rows, widthsBefore, opts = {}) => {
  const widths = scaleWidths(widthsBefore);
  const total = widths.reduce((a, b) => a + b, 0);
  const headerCells = headers.map((header, index) => cellOf(header, {
    width: widths[index],
    fill: COLOR.PRIMARY_LIGHT,
    bold: true,
    size: 20,
    align: AlignmentType.CENTER,
  }));
  const bodyRows = rows.map((row, rowIndex) => rowOf(row.map((cell, cellIndex) => {
    const cellOpts = {
      width: widths[cellIndex],
      size: 20,
      align: opts.bodyAlign?.[cellIndex] || AlignmentType.LEFT,
      fill: opts.zebra && rowIndex % 2 === 1 ? COLOR.ALT_ROW : undefined,
    };
    return Array.isArray(cell)
      ? cellOf(cell[0], { ...cellOpts, ...cell[1] })
      : cellOf(cell, cellOpts);
  })));
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [rowOf(headerCells, { header: true }), ...bodyRows],
  });
};

const callout = (lines, opts = {}) => new Table({
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
    shading: { fill: opts.fill || COLOR.PRIMARY_LIGHT, type: ShadingType.CLEAR, color: 'auto' },
    margins: { top: 120, bottom: 120, left: 200, right: 200 },
    children: lines.map((line, index) => p(txt(line, {
      color: opts.textColor || COLOR.TEXT,
      bold: opts.bold || index === 0,
      size: opts.size || 22,
    }), { before: index === 0 ? 0 : 30, after: index === lines.length - 1 ? 0 : 30 })),
  })])],
});

const content = [];

content.push(
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 180, after: 120 },
    children: [new TextRun({ text: '产业链预期差选股模型逻辑说明', font: FONT, size: 38, bold: true, color: COLOR.PRIMARY })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 180 },
    children: [txt('模型 key：supply_chain_expectation_gap_v1    版本：V1.0    状态：staging', { color: COLOR.MUTED })],
  }),
  callout([
    '核心定位',
    '本模型用于寻找“产业链业务真实推进较快，但市场尚未充分反应”的公司。当前定位是候选池和研究线索，不是自动买入清单。',
  ], { fill: COLOR.WARN_BG, borderColor: COLOR.WARN, textColor: COLOR.TEXT }),
);

content.push(h1('1. 模型定位'));
content.push(
  p(txt('产业链预期差选股模型不是传统财务因子模型，也不是纯题材热度模型。它以“公司-产业链-业务标签”为评分粒度，先判断业务真实进展，再判断市场是否已经定价，最后结合三高属性和证据强度进行排序。')),
  tableOf(
    ['维度', '说明'],
    [
      ['目标', '识别产业链业务推进快、市场预期尚未充分反应的公司'],
      ['粒度', '公司-产业链-业务标签，而不是只看公司整体'],
      ['输出', '强信号、观察池、早期预警及 TopN 排序'],
      ['约束', '当前仍为 staging，不能作为自动买入策略'],
    ],
    [2200, 7600],
    { zebra: true },
  ),
);

content.push(h1('2. 数据来源与股票池'));
content.push(
  p(txt('股票池来自已拆解落库的产业链公司映射。当前覆盖 18 个产业链、1195 家候选公司、2255 条业务标签映射。每家公司可以对应多个产业链或业务标签，模型会在同一股票的多个映射中保留最强映射。')),
  tableOf(
    ['数据层', '典型来源', '用途'],
    [
      ['强证据', '公告、财报、专利、招投标、中标、官方披露', '证明业务存在、研发进展、商用阶段、客户和订单'],
      ['半强证据', '互动易、官网/IR、权威财经新闻、券商研报、政府项目', '补充业务进展、市场预期、景气度判断'],
      ['弱信号', '招聘、社区、自媒体、市场传闻', '只进入预警和待复核，不直接升级阶段或作为硬证据'],
      ['行情数据', '日线、20 日涨幅、行业/产业链代理指标', '衡量市场反应、拥挤度和景气修正'],
    ],
    [1800, 3800, 4200],
    { zebra: true },
  ),
);

content.push(h1('3. 三高评分'));
content.push(
  p(txt('模型先对每个产业链业务标签计算三高情况，用来判断业务质量。三高不是公司整体三高，而是该公司在对应产业链标签上的业务质量。')),
  tableOf(
    ['分项', '含义', '主要证据'],
    [
      ['高成长', '业务收入、订单、产能、客户导入、产业景气是否具备增长性', '收入占比、订单、中标、产能建设、出货和景气代理'],
      ['高盈利', '该业务是否具备毛利、利润贡献或产品结构改善', '毛利率、利润贡献、产品结构、成本下降'],
      ['高壁垒', '是否存在技术、客户、认证、专利、国产替代或卡脖子属性', '专利、标准、客户认证、工艺难度、国产替代证据'],
      ['阶段分', '研发阶段与商业化阶段', 'R1-R6、C1-C5 阶段证据'],
      ['证据分', '证据数量、强度、可信度和维度覆盖', '强证据优先，弱信号不直接确认'],
    ],
    [1600, 3700, 4500],
    { zebra: true },
  ),
);

content.push(h1('4. 预期差评分'));
content.push(
  p([txt('预期差核心公式：', { bold: true }), txt('实际推进 - 市场预期 + 证据增强 + 景气修正 - 风险惩罚')]),
  tableOf(
    ['字段', '含义'],
    [
      ['actual_progress_score', '业务真实推进程度，来自阶段、证据和景气修正'],
      ['market_expectation_score', '市场是否已经充分预期，来自研报/新闻/声明数量和股价反应'],
      ['evidence_delta_score', '新增或累计证据强度'],
      ['prosperity_score', '产业链景气修正'],
      ['risk_penalty_score', '风险证据和负向价格反应扣分'],
      ['expectation_gap_score', '最终预期差分'],
    ],
    [2600, 7200],
    { zebra: true },
  ),
);

content.push(h1('5. 预期差动量'));
content.push(
  p(txt('新增 gap_momentum_score，用来衡量预期差是否正在形成，而不是只看某一天的绝对分。计算时比较当前 gap、上一期 gap 和约 20 个交易日前 gap。')),
  tableOf(
    ['动量方向', '含义', '模型处理'],
    [
      ['上升', '预期差较上一期和 20 日前改善', ['加分', { color: COLOR.OK, bold: true }]],
      ['持平', '预期差没有明显变化', '中性处理'],
      ['下降', '预期差走弱或证据边际恶化', ['扣分', { color: COLOR.DANGER, bold: true }]],
    ],
    [2200, 4200, 3200],
    { zebra: true },
  ),
);

content.push(h1('6. 信号分层'));
content.push(
  tableOf(
    ['层级', '条件', '含义', '使用建议'],
    [
      ['strong', 'gap >= 15', '强信号，正式候选', '重点研究和排序'],
      ['watch', '8 <= gap < 15', '观察池，早期线索', '跟踪证据变化，不直接视作强买点'],
      ['early', '3 <= gap < 8', '早期预警', '进入监控，不进入当前 TopN'],
      ['none', 'gap < 3', '无明显预期差', '不入选'],
    ],
    [1600, 2200, 3000, 3000],
    { zebra: true },
  ),
);

content.push(h1('7. 排序公式与过滤条件'));
content.push(
  p([txt('当前排序公式：', { bold: true }), txt('model_score = 预期差*0.40 + 预期差动量*0.12 + 三高总分*0.25 + 证据强度*0.15 + 壁垒分*0.10 + 景气分*0.10 - 20日涨幅过高惩罚*0.08')]),
  h2('硬过滤条件'),
  bullet('非 ST 股票。'),
  bullet('存在产业链业务映射和当日评分。'),
  bullet('gap_type 属于正向或中性观察信号。'),
  bullet('默认 expectation_gap_score >= 8，覆盖强信号和观察池。'),
  bullet('同一股票多个业务标签时，只保留最强映射。'),
);

content.push(h1('8. 输出字段'));
content.push(
  tableOf(
    ['字段', '说明'],
    [
      ['code / name', '股票代码与名称'],
      ['chain_id / tag_name', '所属产业链与业务标签'],
      ['model_score', '最终排序分'],
      ['expectation_gap_score', '预期差分'],
      ['gap_momentum_score', '预期差动量分'],
      ['three_high_total', '三高总分'],
      ['signal_tier', 'strong / watch / early / none'],
      ['grade', 'S/A/B/C 评级'],
      ['evidence_ids / l1_l8_path', '证据链和 L1-L8 路径'],
    ],
    [2600, 7200],
    { zebra: true },
  ),
);

content.push(h1('9. 当前回测结论'));
content.push(
  tableOf(
    ['口径', '样本', '胜率', '平均收益', '复利收益'],
    [
      ['观察池整体 T+1', '92', '41.30%', ['-0.1627%', { color: COLOR.DANGER, bold: true }], ['-0.7349%', { color: COLOR.DANGER, bold: true }]],
      ['强信号 T+1', '60', '43.33%', ['+0.0772%', { color: COLOR.OK, bold: true }], ['+0.1336%', { color: COLOR.OK, bold: true }]],
      ['观察信号 T+1', '32', '37.50%', ['-0.6124%', { color: COLOR.DANGER, bold: true }], ['-0.8674%', { color: COLOR.DANGER, bold: true }]],
      ['观察信号 T+3', '32', '37.50%', ['-1.1492%', { color: COLOR.DANGER, bold: true }], ['-1.9183%', { color: COLOR.DANGER, bold: true }]],
    ],
    [2800, 1300, 1500, 2100, 2100],
    { zebra: true, bodyAlign: [AlignmentType.LEFT, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER] },
  ),
  callout([
    '当前判断',
    '强信号 T+1 平均收益已经转正，但胜率和样本量仍不足。观察池扩大了样本，但当前明显拖累整体收益。因此本模型适合作为产业链预期差候选池，暂不适合升级为 production。',
  ], { fill: COLOR.DANGER_BG, borderColor: COLOR.DANGER, textColor: COLOR.TEXT }),
);

content.push(h1('10. 使用建议'));
content.push(
  bullet('研究优先级应以 strong 信号为主，watch 信号用于跟踪证据变化。'),
  bullet('观察池不能直接等同于买入池，尤其需要等待新增强证据、商业化进展或价格回调。'),
  bullet('后续需要继续补历史公告、互动易、研报、专利、招投标和产业景气数据，扩大有效样本。'),
  bullet('生产化前必须完成更长周期 T+3/T+5/T+10 回测、分产业链回测、分市值回测和市场环境分层回测。'),
);

const doc = new Document({
  creator: 'Codex',
  title: '产业链预期差选股模型逻辑说明',
  description: '产业链预期差选股模型 V1.0 的数据、评分、排序、回测和使用建议。',
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: COLOR.TEXT } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 32, bold: true, color: COLOR.PRIMARY, font: FONT }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 26, bold: true, color: COLOR.PRIMARY, font: FONT }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 23, bold: true, color: COLOR.MUTED, font: FONT }, paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: '•',
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 480, hanging: 240 } } },
      }],
    }],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: MARGIN } },
    headers: { default: new Header({ children: [p(txt('产业链预期差选股模型逻辑说明', { size: 18, color: COLOR.MUTED }), { after: 0 })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [txt('第 ', { size: 18, color: COLOR.MUTED }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: COLOR.MUTED }), txt(' 页', { size: 18, color: COLOR.MUTED })] })] }) },
    children: content,
  }],
});

const target = path.resolve(__dirname, '../docs/reports/产业链预期差选股模型逻辑说明_20260707.docx');
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(target, buffer);
  console.log(target);
});
