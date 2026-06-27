import { existsSync, readFileSync } from 'node:fs';

const shell = readFileSync('assets/shell.js', 'utf8');

function extractLiteral(name, terminator) {
  const start = shell.indexOf(`const ${name} = `);
  if (start < 0) throw new Error(`Missing ${name}`);
  const bodyStart = start + `const ${name} = `.length;
  const end = shell.indexOf(terminator, bodyStart);
  if (end < 0) throw new Error(`Cannot locate end of ${name}`);
  return shell.slice(bodyStart, end);
}

const moduleTabs = Function(`return ${extractLiteral('MODULE_TABS', ';\n  const MODULE_CONTEXT')}`)();

const expected = {
  dashboard: ['市场情绪', '竞价意图', '信号总览', '自选跟踪', '运行状态'],
  workbench: ['开盘闸门', '候选决策', 'K线推演', '风控交易', '链路审计'],
  screener: ['策略入口', '因子筛选', '候选清单', '批量动作', '诊断联动'],
  'supply-chain': ['产业图谱', '链路证据', '核心公司', '风险传导', '加入选股'],
  predictions: ['标的选择', 'K线走势', '概率路径', '关键价位', '生成信号'],
  strategy: ['方案列表', '参数组合', '执行计划', '回测复核'],
  signals: ['信号总览', '买入触发', '风险提示', '订阅策略'],
  trade: ['交易票', '风控校验', '持仓资金', '委托回报'],
  'auto-trade': ['策略实例', '运行监控', '风控开关', '执行日志'],
  backtest: ['回测参数', '收益曲线', '交易拆解', '失败样本'],
  diagnosis: ['个股画像', '风险雷达', '历史信号', '操作建议'],
  training: ['训练任务', '损失曲线', '数据校验', '发布闸门'],
  'model-registry': ['模型列表', '指标对比', '部署阶段', '审计记录'],
  'data-update': ['同步总览', '质量检查', '修复动作', '同步日志'],
};

const failures = [];
function fail(message) { failures.push(message); }

for (const [key, labels] of Object.entries(expected)) {
  const actual = (moduleTabs[key] || []).map((tab) => tab.n);
  const missing = labels.filter((label) => !actual.includes(label));
  if (missing.length) fail(`${key} missing functional tabs: ${missing.join(', ')}`);
}

const dashboard = readFileSync('index.html', 'utf8');
const marketStart = dashboard.indexOf('id="market-sentiment"');
const auctionStart = dashboard.indexOf('id="auction-intent"');
const signalStart = dashboard.indexOf('id="signal-overview"');
const kpiStart = dashboard.indexOf('class="kpis"');
const marketModel = dashboard.indexOf('市场情绪 · 多维度模型');
const auctionKpi = dashboard.indexOf('竞价看多标的');

if (marketStart < 0) fail('AI 智能看板 missing #market-sentiment functional section');
if (auctionStart < 0) fail('AI 智能看板 missing #auction-intent functional section');
if (signalStart < 0) fail('AI 智能看板 missing #signal-overview functional section');
if (!(marketStart < kpiStart && kpiStart < auctionStart)) {
  fail('市场情绪页签必须覆盖第一排市场状态指标，而不是只落到单张情绪模型卡');
}
if (!(marketStart < marketModel && marketModel < auctionStart)) {
  fail('市场情绪多维模型必须归属市场情绪页签');
}
if (auctionKpi > marketStart && auctionKpi < auctionStart) {
  fail('竞价相关指标不能放在市场情绪页签范围内');
}

for (const file of [
  'suying-ai-workbench-redesign.html',
  'screener.html',
  'supply-chain.html',
  'predictions.html',
  'strategy.html',
  'signals.html',
  'trade.html',
  'auto-trade.html',
  'backtest.html',
  'diagnosis.html',
  'training.html',
  'model-registry.html',
  'data-update.html',
]) {
  if (!existsSync(file)) {
    fail(`Missing product page ${file}`);
    continue;
  }
  const html = readFileSync(file, 'utf8');
  const page = html.match(/data-page="([^"]+)"/)?.[1];
  if (!page) {
    fail(`${file} missing data-page`);
    continue;
  }
  for (const tab of moduleTabs[page] || []) {
    if (tab.anchor && !html.includes(`id="${tab.anchor}"`) && !html.includes(`id='${tab.anchor}'`)) {
      fail(`${file} missing functional section #${tab.anchor} for ${tab.n}`);
    }
  }
}

if (failures.length) {
  console.error('Functional taxonomy check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Functional taxonomy passed: ${Object.keys(expected).length} modules checked`);
