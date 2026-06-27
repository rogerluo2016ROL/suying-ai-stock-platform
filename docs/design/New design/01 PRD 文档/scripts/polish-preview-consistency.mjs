import { readFileSync, writeFileSync, readdirSync } from 'node:fs';

function replaceFile(file, updater){
  const before = readFileSync(file, 'utf8');
  const after = updater(before);
  if(after !== before){
    writeFileSync(file, after);
    return true;
  }
  return false;
}

function findBalancedDivEnd(source, openStart){
  const openEnd = source.indexOf('>', openStart) + 1;
  if(openEnd <= 0) return -1;
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

function removeBlocksByClass(html, classNames){
  const classPattern = classNames.join('|');
  const re = new RegExp(`<div\\b[^>]*class="[^"]*(?:${classPattern})[^"]*"[^>]*>`, 'gi');
  let result = '';
  let cursor = 0;
  let changed = false;
  let match;
  while((match = re.exec(html))){
    const start = match.index;
    const end = findBalancedDivEnd(html, start);
    if(end < 0) continue;
    result += html.slice(cursor, start);
    cursor = end;
    changed = true;
    re.lastIndex = end;
  }
  return changed ? result + html.slice(cursor) : html;
}

function removeSupplyChainPhaseProgress(html){
  const comment = html.search(/<!--\s*Phase Progress\s*-->/i);
  if(comment < 0) return html;
  const start = html.indexOf('<div class="progress-bar"', comment);
  if(start < 0) return html.replace(/<!--\s*Phase Progress\s*-->/i, '');
  const end = findBalancedDivEnd(html, start);
  if(end < 0) return html;
  return (html.slice(0, comment) + '\n' + html.slice(end)).replace(/\n{3,}/g, '\n\n');
}

let changed = 0;

for(const file of [
  '4.1 policy-analysis-preview.html',
  '4.2 chain-decompose-preview.html',
  '4.3 company-analysis-preview.html'
]){
  changed += replaceFile(file, (html) => {
    let next = removeBlocksByClass(html, ['context-bar', 'ctx-bar']);
    next = removeSupplyChainPhaseProgress(next);
    next = next.replace(
      /document\.querySelector\('\.context-bar \.cb-view'\)\.textContent = mode === 'trader' \? '操盘手模式' : '投资者模式';/,
      "const contextView = document.querySelector('.context-bar .cb-view');\n  if (contextView) contextView.textContent = mode === 'trader' ? '操盘手模式' : '投资者模式';"
    );
    return next;
  }) ? 1 : 0;
}

changed += replaceFile('4.2 chain-decompose-preview.html', (html) => html.replace(
  /\s*<div class="tp-h">\s*<h3>产业链公司列表<\/h3>\s*<span class="meta" id="tableMeta">共 12 家公司<\/span>\s*<\/div>/,
  ''
)) ? 1 : 0;

const linkFixes = [
  ['1.2 auction-dashboard-preview.html', /<a href="#" onclick="alert\('跳转到诊断页面: ' \+ document\.getElementById\('si-code'\)\.innerText\)">→ 跳转诊断<\/a>/g, '<a href="12.0 diagnosis-preview.html">→ 跳转诊断</a>'],
  ['10.1 risk-overview-preview.html', /<a class="alert-action" href="#">查看 →<\/a>/g, '<button type="button" class="alert-action" data-toast="已打开风险详情">查看 →</button>'],
  ['10.1 risk-overview-preview.html', /<a class="alert-action" href="#">诊断 →<\/a>/g, '<a class="alert-action" href="12.0 diagnosis-preview.html">诊断 →</a>'],
  ['12.1 diagnosis-overview-preview.html', /<a class="bc-link" href="javascript:void\(0\)" onclick="showToast\('返回候选池'\)">候选池<\/a>/g, '<a class="bc-link" href="2.4 candidate-pool-preview.html">候选池</a>'],
  ['12.2 model-perspective-preview.html', /<a class="bc-link" href="javascript:void\(0\)" onclick="showToast\('返回候选池'\)">候选池<\/a>/g, '<a class="bc-link" href="2.4 candidate-pool-preview.html">候选池</a>'],
  ['12.3 diagnosis-compare-preview.html', /<a class="bc-link" href="javascript:void\(0\)" onclick="showToast\('返回候选池'\)">候选池<\/a>/g, '<a class="bc-link" href="2.4 candidate-pool-preview.html">候选池</a>'],
  ['12.4 diagnosis-risk-preview.html', /<a class="bc-link" href="javascript:void\(0\)" onclick="showToast\('返回候选池'\)">候选池<\/a>/g, '<a class="bc-link" href="2.4 candidate-pool-preview.html">候选池</a>'],
  ['13.0 model-training-preview.html', /<a class="mlflow-link" href="#" onclick="event\.preventDefault\(\);showToast\('MLflow: http:\/\/localhost:5000','info'\)">/g, '<a class="mlflow-link" href="http://localhost:5000" target="_blank" rel="noopener">'],
  ['13.2 mlflow-experiment-preview.html', /<a class="mlflow-link" href="#" onclick="event\.preventDefault\(\);showToast\('MLflow Dashboard: http:\/\/localhost:5000','info'\)">/g, '<a class="mlflow-link" href="http://localhost:5000" target="_blank" rel="noopener">'],
  ['7.5 broker-management-preview.html', /<div class="log-card">/, '<div class="log-card" id="connection-history">'],
  ['7.5 broker-management-preview.html', /<a class="view-all" href="#" onclick="return false">查看全部 →<\/a>/g, '<a class="view-all" href="#connection-history">查看全部 →</a>'],
  ['4.3 company-analysis-preview.html', /href="4\.2%20chain-decompose-preview\.html"/g, 'href="4.2 chain-decompose-preview.html"'],
  ['9.2 plan-detail-preview.html', /href="6\.0 plan-manager-preview\.html"/g, 'href="9.1 plan-list-preview.html"']
];

for(const [file, pattern, replacement] of linkFixes){
  changed += replaceFile(file, (html) => html.replace(pattern, replacement)) ? 1 : 0;
}

const tabCommentRe = /\s*<!--\s*(?:=+\s*)?(?:Tab Navigation|横向\s*Tab\s*导航|Tab Nav|SubTabBar(?::[^-]*)?|Sub Tab Bar|Context Bar(?: \(bottom\))?)(?:\s*=+)?\s*-->\s*/gi;
for(const file of readdirSync('.').filter((name) => /preview\.html$/.test(name))){
  changed += replaceFile(file, (html) => html.replace(tabCommentRe, '\n')) ? 1 : 0;
}

console.log(`Polished preview consistency in ${changed} file updates`);
