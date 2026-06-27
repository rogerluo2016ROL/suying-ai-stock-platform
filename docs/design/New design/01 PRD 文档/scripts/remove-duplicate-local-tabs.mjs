import { readFileSync, writeFileSync, readdirSync } from 'node:fs';

const files = readdirSync('.').filter((file) => /preview\.html$/.test(file)).sort();

const labelsByPage = {
  dashboard: ['市场情绪', '竞价意图', '信号总览', '自选跟踪'],
  'opening-decision': ['决策总览', '竞价分析', '信号扫描', '候选池', '执行监控'],
  screener: ['选股工作台', '模型对比', '因子分析'],
  'supply-chain': ['政策梳理', '产业链解构', '多维度分析'],
  predictions: ['预测总览', '单股预测', '多股对比', '准确率回测'],
  signals: ['信号详情', '信号总览', '信号历史', '风险扫描'],
  trade: ['交易中心', '下单面板', '持仓监控', '订单管理', '账户总览', '券商管理'],
  'auto-trade': ['策略广场', '策略配置', '策略监控', '策略日志'],
  plans: ['方案列表', '方案详情', '方案对比', '结算报告'],
  'risk-control': ['风控总览', '持仓风险', '策略风险', '市场风险', '事件审计'],
  backtest: ['回测总览', '回测运行', '策略对比', '交易明细'],
  diagnosis: ['诊断总览', '综合诊断', '模型视角', '多股对比', '风险扫描'],
  training: ['模型训练', '训练任务', 'MLflow'],
  'model-registry': ['模型注册'],
  'data-update': ['数据更新', '数据总览', '全部数据表', '同步调度'],
  'runtime-status': ['运行状态']
};

function pageFor(html){
  return html.match(/data-page="([^"]+)"/)?.[1] || '';
}

function textOnly(html){
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function compactLabel(value){
  return value
    .replace(/[^\p{Script=Han}A-Za-z0-9]+/gu, '')
    .replace(/总览$/u, '')
    .replace(/管理$/u, '')
    .replace(/监控$/u, '')
    .replace(/面板$/u, '')
    .replace(/中心$/u, '')
    .replace(/分析$/u, '')
    .replace(/运行$/u, '')
    .replace(/扫描$/u, '')
    .replace(/配置$/u, '')
    .trim();
}

function localNavLabels(block){
  const labels = [];
  const itemRe = /<(?:a|button|span)\b[^>]*>([\s\S]*?)<\/(?:a|button|span)>/gi;
  let match;
  while((match = itemRe.exec(block))){
    const label = textOnly(match[1]);
    const compact = compactLabel(label);
    if(compact.length >= 2) labels.push(compact);
  }
  return labels;
}

function labelsMatch(local, canonical){
  const normalized = compactLabel(canonical);
  if(local.length < 2 || normalized.length < 2) return false;
  return local.includes(normalized) || normalized.includes(local);
}

function looksLikeDuplicateNav(block, page){
  const labels = labelsByPage[page] || [];
  if(!labels.length) return false;
  const text = textOnly(block);
  const localLabels = localNavLabels(block);
  const hits = labels.filter((label) => {
    if(text.includes(label)) return true;
    return localLabels.some((local) => labelsMatch(local, label));
  }).length;
  return hits >= Math.min(2, labels.length);
}

function removeMatchingBlocks(html, page, pattern){
  let changed = false;
  const next = html.replace(pattern, (block) => {
    if(!looksLikeDuplicateNav(block, page)) return block;
    changed = true;
    return '';
  });
  return { html: next, changed };
}

function findTagEnd(source, openEnd){
  let depth = 1;
  const tagRe = /<\/?div\b[^>]*>/gi;
  tagRe.lastIndex = openEnd;
  let match;
  while((match = tagRe.exec(source))){
    if(match[0].startsWith('</')) depth -= 1;
    else depth += 1;
    if(depth === 0) return tagRe.lastIndex;
  }
  return -1;
}

function removeBalancedDuplicateDivs(html, page){
  const classRe = /<div\b[^>]*class="(?:pill-tabs|subtab-bar|tab-nav|stb)"[^>]*>/gi;
  let result = '';
  let cursor = 0;
  let changed = false;
  let match;
  while((match = classRe.exec(html))){
    const start = match.index;
    const end = findTagEnd(html, classRe.lastIndex);
    if(end < 0) continue;
    const block = html.slice(start, end);
    if(looksLikeDuplicateNav(block, page)){
      result += html.slice(cursor, start);
      cursor = end;
      changed = true;
    }
    classRe.lastIndex = end;
  }
  if(!changed) return html;
  return result + html.slice(cursor);
}

let totalChanged = 0;

for(const file of files){
  let html = readFileSync(file, 'utf8');
  const page = pageFor(html);
  const before = html;

  html = html.replace(/\s*<div class="legacy-local-tabs">[\s\S]*?<\/div>\s*/g, '');
  html = removeBalancedDuplicateDivs(html, page);

  for(const pattern of [
    /\s*<!--\s*(?:=+\s*)?(?:Tab Nav|顶部\s*Tab\s*导航|Pill Tabs|SubTabBar)(?:\s*=+)?\s*-->\s*<div\b[^>]*(?:style="[^"]*border-bottom:2px solid var\(--border\)[^"]*"|class="(?:pill-tabs|subtab-bar|tab-nav)"[^>]*)[\s\S]*?<\/div>\s*/gi,
    /\s*<div\b[^>]*style="[^"]*display:flex;gap:0[^"]*border-bottom:2px solid var\(--border\)[^"]*"[^>]*>[\s\S]*?<\/div>\s*/gi,
    /\s*<div\b[^>]*class="(?:pill-tabs|subtab-bar|tab-nav)"[^>]*>[\s\S]*?<\/div>\s*/gi
  ]){
    const result = removeMatchingBlocks(html, page, pattern);
    html = result.html;
  }

  if(html !== before){
    writeFileSync(file, html);
    totalChanged += 1;
  }
}

console.log(`Removed duplicate local tab bars from ${totalChanged} files`);
