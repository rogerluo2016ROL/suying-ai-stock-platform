import { existsSync, readFileSync } from 'node:fs';

const pages = [
  'index.html',
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
];

const shell = readFileSync('assets/shell.js', 'utf8');
const moduleTabs = Function(`return ${shell.slice(shell.indexOf('const MODULE_TABS = ') + 'const MODULE_TABS = '.length, shell.indexOf(';\n  const MODULE_CONTEXT'))}`)();
const failures = [];

function fail(message) { failures.push(message); }

for (const file of pages) {
  if (!existsSync(file)) {
    fail(`Missing page: ${file}`);
    continue;
  }
  const html = readFileSync(file, 'utf8');
  if (!html.startsWith('<!doctype html>')) fail(`${file} must use standard doctype`);
  if (!html.includes('lang="zh-CN"')) fail(`${file} must be localized to zh-CN`);
  if (!html.includes('assets/app.css')) fail(`${file} must use shared app.css`);
  if (!html.includes('assets/shell.js')) fail(`${file} must mount shared shell.js`);
  if (!html.includes('id="sidebar-mount"') || !html.includes('id="header-mount"')) fail(`${file} must use shared shell mounts`);
  if (/demo|prototype|viewport selector|theme knob|设计器控件|演示用/i.test(html)) fail(`${file} contains demo/prototype wording`);
  if (/Feature One|Feature Two|lorem ipsum|placeholder text/i.test(html)) fail(`${file} contains template placeholder copy`);

  const pageMatch = html.match(/data-page="([^"]+)"/);
  if (!pageMatch) {
    fail(`${file} missing data-page`);
    continue;
  }
  const key = pageMatch[1];
  const tabs = moduleTabs[key] || [];
  if (!tabs.length) fail(`${file} has no module tab configuration`);
  for (const tab of tabs) {
    if (tab.anchor && !html.includes(`id="${tab.anchor}"`) && !html.includes(`id='${tab.anchor}'`)) {
      fail(`${file} missing module tab target #${tab.anchor}`);
    }
  }
}

if (failures.length) {
  console.error('Product readiness check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Product readiness passed: ${pages.length} product pages checked`);
