const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
        ShadingType, PageNumber, PageBreak, LevelFormat } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };
const bw = 9026; // A4 content width
const A4 = { width: 11906, height: 16838 };

function hdrCell(text, width) {
    return new TableCell({ borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
        shading: { fill: "1F4E79", type: ShadingType.CLEAR },
        children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Microsoft YaHei", size: 20 })] })] });
}
function cell(text, width, opts = {}) {
    return new TableCell({ borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
        shading: opts.shading ? { fill: opts.shading, type: ShadingType.CLEAR } : undefined,
        children: [new Paragraph({ children: [new TextRun({ text: String(text), font: "Microsoft YaHei", size: 18, ...opts })] })] });
}
function makeTable(headers, rows, colWidths) {
    const hdrRow = new TableRow({ children: headers.map((h, i) => hdrCell(h, colWidths[i])) });
    const dataRows = rows.map((row, ri) => new TableRow({
        children: row.map((c, ci) => cell(String(c), colWidths[ci], ri % 2 === 0 ? {} : { shading: "F2F7FB" }))
    }));
    return new Table({ width: { size: bw, type: WidthType.DXA }, columnWidths: colWidths, rows: [hdrRow, ...dataRows] });
}

function h1(text) { return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text, font: "Microsoft YaHei", bold: true, size: 32 })] }); }
function h2(text) { return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, font: "Microsoft YaHei", bold: true, size: 28 })] }); }
function h3(text) { return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text, font: "Microsoft YaHei", bold: true, size: 24 })] }); }
function p(text) { return new Paragraph({ children: [new TextRun({ text, font: "Microsoft YaHei", size: 20 })] }); }
function pb() { return new Paragraph({ children: [new PageBreak()] }); }

const doc = new Document({
    styles: {
        default: { document: { run: { font: "Microsoft YaHei", size: 20 } } },
        paragraphStyles: [
            { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 32, bold: true, font: "Microsoft YaHei", color: "1F4E79" },
              paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
            { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 28, bold: true, font: "Microsoft YaHei", color: "2E75B6" },
              paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
            { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
              run: { size: 24, bold: true, font: "Microsoft YaHei", color: "404040" },
              paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
        ]
    },
    sections: [
        // ═══════════════ COVER PAGE ═══════════════
        { properties: { page: { size: A4, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
          children: [
            new Paragraph({ spacing: { before: 3000 } }),
            new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "匪爷可转债选债模型", font: "Microsoft YaHei", bold: true, size: 52, color: "1F4E79" })] }),
            new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "完整技术规格书", font: "Microsoft YaHei", bold: true, size: 40, color: "2E75B6" })] }),
            new Paragraph({ spacing: { before: 600 } }),
            new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "日内竞价选债 V6.1  +  底价选债 V3", font: "Microsoft YaHei", size: 24, color: "666666" })] }),
            new Paragraph({ spacing: { before: 1200 } }),
            new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "速赢AI证券投资管理平台", font: "Microsoft YaHei", size: 22, color: "888888" })] }),
            new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "2026年6月", font: "Microsoft YaHei", size: 20, color: "888888" })] }),
        ]},

        // ═══════════════ MODEL 1 ═══════════════
        { properties: { page: { size: A4, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
          headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "匪爷可转债选债模型 — 完整技术规格书", font: "Microsoft YaHei", size: 16, color: "999999" })] })] }) },
          footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "第 ", font: "Microsoft YaHei", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], font: "Microsoft YaHei", size: 16 })] })] }) },
          children: [

        h1("一、日内竞价选债模型 V6.1"),

        h2("1.1 模型定位"),
        makeTable(["属性", "值"], [
            ["选股时点", "T日 9:25（竞价结束后立即执行）"],
            ["持仓周期", "日内（不持仓过夜）"],
            ["风格", "激进短线"],
            ["ML增强", "✅ Ensemble (RF + LightGBM + CatBoost)"],
            ["SpearmanR", "0.740"],
            ["1年回测", "488笔 | +2.09%均值 | 73.6%胜率"],
        ], [3000, 6026]),

        h2("1.2 选股流水线"),
        p("Step 1 — 板块强度：stk_auction_o (T日竞价) → JOIN stocks 按行业聚合竞价涨幅 → 归一化评分 → Top 10强势行业 → 回退ths_daily → neutral全市场"),
        p("Step 2 — 转债候选池：强势行业 → cb_concept概念映射 (6192条,153概念,1109只转债) → 精确+模糊匹配 → ≤150只上限 → 不足10只时neutral补充"),
        p("Step 3 — 预取辅助数据：cb_daily(溢价率/成交额) + daily_kline(T-1昨涨) + 近5日均量 + cb_call(强赎) + cb_price_chg(下修)"),
        p("Step 4 — 四因子线性评分 → 等级 → ML Ensemble重排(11维) → ML≥2.0过滤 → Top N"),

        h2("1.3 因子评分细则"),
        makeTable(["#", "因子", "权重", "数据源", "评分逻辑"],
        [
            ["1", "流动性", "35%", "cb_daily.amount + 近5日均量", "绝对额(60%): ≥5000万→100, ≥100万→40; 相对量(40%): 放量1.2x→80-100"],
            ["2", "昨日动量", "30%", "daily_kline.change_pct (T-1)", "1-5%温和上涨→85-100(最优); >5%→0(不入); 0-1%→55-80; -3~-1%→30-40; <-3%→10-25"],
            ["3", "板块竞价", "20%", "stk_auction_o行业聚合", "≥4%→100; 2-4%→85-100; 1-2%→70-85; 0.5-1%→55-70; +规模加成max10分"],
            ["4", "溢价率", "15%", "cb_daily.cb_over_rate", "≤-10%→100; 0~-5%→85-95; 0-20%→85→25; >50%→接近0分"],
            ["+", "下修加分", "—", "cb_price_chg (近90天)", "5-10%下修 近10天→+4, 近30天→+3; <5%→+1; >10%→+2"],
            ["+", "强赎惩罚", "—", "cb_call", "最后3天→-20; 最后7天→-10; 提示强赎→-3"],
        ], [800, 1200, 800, 2000, 4226]),

        h2("1.4 ML增强"),
        makeTable(["环节", "说明"], [
            ["模型架构", "RandomForest + LightGBM + CatBoost 三模型预测取均值"],
            ["特征维度", "11维: 4因子分 + rev_bonus + call_penalty + premium_rate% + yesterday_pct% + cb_amount_wan + remain_size + ATR%"],
            ["训练样本", "380 (V6.1重训)"],
            ["SpearmanR", "0.740"],
            ["过滤阈值", "ML ≥ 2.0"],
            ["排序", "ML分降序 → Top N"],
        ], [2000, 7026]),

        pb(),

        h2("1.5 过滤规则"),
        makeTable(["#", "规则", "条件", "动作"], [
            ["1", "昨暴涨", "yesterday_pct > 5%", "跳过不入池"],
            ["2", "昨暴跌", "yesterday_pct < -5%", "跳过不入池"],
            ["3", "强赎到期", "call_reg_date < today", "跳过"],
            ["4", "到期临近", "maturity - today < 90天", "跳过"],
            ["5", "候选超量", "candidates > 150", "截断取前150"],
            ["6", "候选不足", "candidates < 10", "neutral补充至30"],
        ], [600, 1200, 2600, 4626]),

        h2("1.6 交易规则"),
        h3("入场规则"),
        makeTable(["规则", "说明"], [
            ["入场时点", "T日 9:25 竞价结束后"],
            ["入场价", "cb_daily.open（当日开盘价）"],
            ["入场质量检查", "开盘前6根5min bar(30min)均价须 > VWAP, 否则不入"],
            ["仓位", "A级15% | B级10% | C级5%"],
        ], [2500, 6526]),

        h3("出场规则（优先级从高到低）"),
        makeTable(["优先级", "规则", "触发条件", "出场价"], [
            ["①", "自适应止盈", "正股日内涨幅 ≥ 目标% (ATR驱动: 2%~5%)", "cb_open × (1+stock_ret×delta)"],
            ["②", "回撤止损", "从日内高点回撤 ≥ 2%", "触发bar的close"],
            ["③", "KDJ信号", "close > VWAP 且 KDJ_J > 95", "触发bar的close"],
            ["④", "VWAP止损", "持续低于VWAP ≥ 45分钟 (下跌日30min)", "触发bar的close"],
            ["⑤", "尾盘平仓", "14:30前未触发任何信号", "cb_daily.close"],
        ], [800, 1500, 3500, 3226]),

        h3("自适应止盈目标"),
        makeTable(["ATR(5)%", "止盈目标", "逻辑"], [
            ["≥5%", "5%", "高波动, 让利润奔跑"],
            ["3~5%", "4%", "中高波动"],
            ["2~3%", "3%", "正常波动"],
            ["<2%", "2%", "低波动, 见好就收"],
        ], [2000, 2000, 5026]),

        h3("风控规则"),
        makeTable(["规则", "条件"], [
            ["单日熔断", "累计亏损 > 3% → 停止交易"],
            ["连续止损熔断", "连续3笔止损 → 当日停牌"],
            ["下跌日保护", "上证跌 > 1% → KDJ阈值提到100, 止损缩到30min"],
            ["早盘保护", "10:00前 KDJ_J 需 > 100 (噪声大)"],
        ], [2500, 6526]),

        h2("1.7 回测成绩"),
        makeTable(["周期", "笔数", "均值", "胜率", "备注"], [
            ["1年期(2025/6~2026/6,244天)", "488", "+2.09%", "73.6%", "181天有交易"],
            ["A级", "87", "+4.14%", "91%", "ML高分优质标的"],
            ["B级", "—", "+2.98%", "89%", "主力仓位"],
            ["止盈", "73%", "+4.24%", "100%", "自适应2~5%目标"],
            ["回撤止损", "18%", "+0.43%", "60%", "接近打平"],
        ], [3200, 1000, 1200, 1200, 2426]),

        pb(),

        // ═══════════════ MODEL 2 ═══════════════
        h1("二、底价选债模型 V3"),

        h2("2.1 模型定位"),
        makeTable(["属性", "值"], [
            ["选股时点", "T日收盘后"],
            ["持仓周期", "1-4周"],
            ["风格", "稳健价值"],
            ["ML增强", "❌ 样本不足 (日均选股0.3只, SpearmanR仅0.034)"],
            ["日内适用", "❌ (因子设计为中长周期: RSI/MACD/YTM/布林)"],
        ], [2500, 6526]),

        h2("2.2 因子评分细则"),
        makeTable(["#", "因子", "权重", "评分逻辑"], [
            ["1", "溢价率", "25%", "≤-15%→100; -10~-15%→97-100; 0~-5%→85-93; 0-10%→85→55; >50%→5→0"],
            ["2", "RSI趋势(6)", "15%", "40-60→80-82(健康); 30-40→60-80(超卖恢复); <30→30-60(深超卖); >70→10-90"],
            ["3", "到期收益率", "10%", "自算:(年息+(面值-现价)/剩余年)/现价×100; ≥8%→100; 3-5%→60-80; <0%→5-20"],
            ["4", "MACD动能", "10%", "MACD>0→50+min(30,macd×100); MACD<0→50+max(-30,macd×100); 金叉+10"],
            ["5", "近10日下修", "10%", "10天内有下修→100; 全历史有→60; 无→30"],
            ["6", "热门概念", "5%", "匹配当日ths_daily强势概念→80; 有概念→60; 无→40"],
            ["7", "布林带位置", "5%", "下轨→90(超卖反弹); 中轨→70; 上轨→30(超买风险)"],
            ["8", "下修历史", "5%", "≥3次→100; 2次→85; 1次→70; 0次→20"],
            ["9", "剩余规模", "5%", "≤0.5亿→100; 1-3亿→75-90; >20亿→5-10"],
            ["10", "成交量", "5%", "≥500万手→100; 100-500万→60-100; <10万→5-20"],
            ["11", "评级惩罚", "—", "AAA/AA/A→0; BBB→-5; BB→-10; B以下→-15; 无→-10"],
            ["+", "RSI超卖", "—", "RSI(6)<30 → +10"],
            ["+", "MACD金叉", "—", "dif上穿dea且macd>0 → +8"],
        ], [600, 1500, 700, 6226]),

        h2("2.3 交易规则"),
        p("⚠️ cb_floor 是纯选股模型, 不含止盈止损。入场: T+1开盘价, 持仓: 1-4周, 出场由用户自行判断。"),

        h2("2.4 回测成绩"),
        makeTable(["周期", "均值", "胜率"], [
            ["1日", "-1.45%", "10%"],
            ["3日", "-1.34%", "10%"],
            ["5日", "-1.32%", "20%"],
            ["10日", "+1.58%", "70%"],
        ], [3000, 3013, 3013]),

        pb(),

        // ═══════════════ COMPARISON ═══════════════
        h1("三、两模型对比"),

        makeTable(["维度", "日内竞价 V6.1", "底价选债 V3"], [
            ["选股时点", "T日 9:25 竞价后", "T日收盘后"],
            ["入场时点", "T日 9:25", "T+1 开盘"],
            ["持仓周期", "日内 (不过夜)", "1-4 周"],
            ["核心因子", "流动性>动量>板块>溢价率", "溢价率>RSI>YTM>MACD"],
            ["因子数", "4 + 2修正项", "11 + 3修正项"],
            ["ML增强", "✅ Ensemble (380样本, SR=0.740)", "❌ (SR=0.034)"],
            ["出场策略", "5级优先级自动化", "无内置"],
            ["风控", "单日熔断/连续止损/下跌日/早盘", "无内置"],
            ["日内适用", "✅", "❌"],
            ["长线适用", "❌ (不过夜)", "✅ 10日 +1.58%"],
        ], [2000, 3513, 3513]),

    ]}] // end sections
});

Packer.toBuffer(doc).then(buf => {
    fs.writeFileSync("outputs/匪爷可转债选债模型规格.docx", buf);
    console.log("Word doc saved: outputs/匪爷可转债选债模型规格.docx");
});
