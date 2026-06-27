import { readFileSync, readdirSync } from 'node:fs';

const files = readdirSync('.').filter((file) => /preview\.html$/.test(file)).sort();
const failures = [];

function fail(message){ failures.push(message); }

if(files.length !== 63) fail(`expected 63 preview files, found ${files.length}`);

for(const file of files){
  const html = readFileSync(file, 'utf8');
  const htmlWithoutScriptsAndStyles = html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '');
  const required = [
    '<!doctype html>',
    'lang="zh-CN"',
    'class="legacy-preview"',
    'data-page=',
    'data-title=',
    'id="sidebar-mount"',
    'id="header-mount"',
    'assets/app.css',
    'assets/preview-adapter.css',
    'assets/shell.js',
    'assets/preview-interactions.js',
    '<main class="content">'
  ];
  for(const needle of required){
    if(!html.includes(needle)) fail(`${file} missing ${needle}`);
  }
  if(/<nav class="sidebar"|<header class="header"/.test(html)) {
    fail(`${file} still contains hard-coded legacy shell`);
  }
  if(/html lang="zh-CN" data-theme="dark"/.test(html)) {
    fail(`${file} still forces dark theme at document root`);
  }

  const mainOpenCount = (htmlWithoutScriptsAndStyles.match(/<main\b/g) || []).length;
  const mainCloseCount = (htmlWithoutScriptsAndStyles.match(/<\/main>/g) || []).length;
  const main = htmlWithoutScriptsAndStyles.match(/<main class="content">([\s\S]*?)<\/main>/)?.[1] || '';
  if(mainOpenCount !== 1) fail(`${file} should contain exactly one <main>, found ${mainOpenCount}`);
  if(mainCloseCount !== 1) fail(`${file} should contain exactly one </main>, found ${mainCloseCount}`);
  if(/<script\b/.test(main)) fail(`${file} contains a script inside main content`);
  if(/<!--[^>]*(?:Tab Navigation|横向\s*Tab\s*导航|Tab Nav)[\s\S]{0,120}-->\s*<\/div>/.test(main)) {
    fail(`${file} contains orphan duplicate-tab closing markup`);
  }
  if(/<!--\s*(?:Tab Navigation|横向\s*Tab\s*导航|Tab Nav|SubTabBar|Sub Tab Bar)\s*-->/.test(main)) {
    fail(`${file} contains orphan duplicate-tab comment`);
  }
  if(/<div\b[^>]*class="[^"]*(?:\bstb\b|\bpill-tabs\b|\bsubtab-bar\b|\btab-nav\b|\blegacy-local-tabs\b)[^"]*"/.test(main)) {
    fail(`${file} still contains visible duplicate/local tab navigation`);
  }
  if(/<a\b[^>]*href="(?:#|javascript:void\(0\)|)"/i.test(main)) {
    fail(`${file} contains empty or void href in main content`);
  }
  if(/class="[^"]*(?:context-bar|ctx-bar)[^"]*"/.test(main)) {
    fail(`${file} still contains local workflow context/status bar`);
  }
  if(/data-page="supply-chain"/.test(html) && /class="progress-bar"/.test(main) && /P[123]|政策梳理|产业链解构|多维度分析/.test(main)) {
    fail(`${file} still contains duplicate supply-chain phase progress bar`);
  }
  const duplicateIds = [];
  const seenIds = new Set();
  for(const idMatch of htmlWithoutScriptsAndStyles.matchAll(/\bid="([^"]+)"/g)){
    if(seenIds.has(idMatch[1])) duplicateIds.push(idMatch[1]);
    seenIds.add(idMatch[1]);
  }
  if(duplicateIds.length) fail(`${file} contains duplicate ids: ${[...new Set(duplicateIds)].join(', ')}`);
}

const interactionExpectations = [
  ['7.0 trade-center-preview.html', ['function confirmOrder', 'function setDirection', 'function recalcAmount']],
  ['1.1 sentiment-dashboard-preview.html', ['echarts.init(gaugeDom', 'echarts.init(trendDom']],
  ['5.1 single-stock-preview.html', ['echarts.init']],
  ['8.2 strategy-config-preview.html', ['function', 'onclick']],
  ['13.2 mlflow-experiment-preview.html', ['showToast', 'mlflow-link', 'pill-tab']]
];

for(const [file, needles] of interactionExpectations){
  const html = readFileSync(file, 'utf8');
  for(const needle of needles){
    if(!html.includes(needle)) fail(`${file} lost expected interaction/chart marker: ${needle}`);
  }
}

const shell = readFileSync('assets/shell.js', 'utf8');
for(const key of ['dashboard','opening-decision','screener','trade','auto-trade','risk-control','runtime-status']){
  if(!shell.includes(`${key}`)) fail(`assets/shell.js missing module ${key}`);
}
if(!shell.includes('suying_preview_theme')) fail('assets/shell.js must persist preview theme');

const adapter = readFileSync('assets/preview-adapter.css', 'utf8');
for(const needle of ['.legacy-local-tabs','@media (max-width:760px)', '.toast.show', '.platform-scope-strip']){
  if(!adapter.includes(needle)) fail(`assets/preview-adapter.css missing ${needle}`);
}

const interactions = readFileSync('assets/preview-interactions.js', 'utf8');
for(const needle of ['window.suyingToast', '[data-toast]', '.seg .s', 'echarts.getInstanceByDom']){
  if(!interactions.includes(needle)) fail(`assets/preview-interactions.js missing ${needle}`);
}

const duplicateNavPatterns = [
  /legacy-local-tabs/,
  /display:flex;gap:0[^>]+border-bottom:2px solid var\(--border\)/,
  /display:flex;gap:2px;background:var\(--surface\);border:1px solid var\(--border\)/,
  /class="pill-tabs"/,
  /class="tab-nav"/,
  /class="stb"/
];
for(const file of files){
  const html = readFileSync(file, 'utf8');
  const main = html.match(/<main class="content">([\s\S]*?)<\/main>/)?.[1] || '';
  const earlyMain = main.slice(0, 2200);
  for(const pattern of duplicateNavPatterns){
    if(pattern.test(earlyMain)) fail(`${file} still contains duplicate module navigation near top: ${pattern}`);
  }
  if(/class="subtab-bar"/.test(earlyMain)) {
    fail(`${file} still contains duplicate subtab module navigation near top`);
  }
}

if(failures.length){
  console.error('Upgraded preview check failed:');
  for(const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Upgraded preview check passed: ${files.length} preview files`);
