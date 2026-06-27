import { readFileSync } from 'node:fs';

const shell = readFileSync('assets/shell.js', 'utf8');
const css = readFileSync('assets/app.css', 'utf8');

const checks = [
  ['shared shell keeps decision cockpit in primary nav', shell.includes("k:'workbench'") && shell.includes('开盘决策舱')],
  ['decision cockpit link points to current canonical file', shell.includes("f:'suying-ai-workbench-redesign.html'")],
  ['shared shell defines module-specific tab sets', shell.includes('MODULE_TABS') && shell.includes("dashboard:") && shell.includes("screener:")],
  ['dashboard tabs are dashboard functions', shell.includes('市场情绪') && shell.includes('竞价意图') && shell.includes('信号总览') && shell.includes('运行状态')],
  ['screener tabs are screener functions', shell.includes('策略入口') && shell.includes('因子筛选') && shell.includes('候选清单') && shell.includes('批量动作') && shell.includes('诊断联动')],
  ['shared shell renders module tab nav', shell.includes('module-tabs') && shell.includes('aria-label="模块功能页签"')],
  ['shared shell renders module context strip', shell.includes('module-context') && shell.includes('当前模块') && shell.includes('功能板块')],
  ['module tabs use in-page hash links only', !shell.includes('currentFile +') && shell.includes("item.anchor ? '#'+item.anchor : '#'")],
  ['css defines module tab layout', css.includes('.module-tabs') && css.includes('.module-tab')],
  ['css defines module context layout', css.includes('.module-context') && css.includes('.context-card')],
  ['old fixed workflow labels are removed from shared shell', !shell.includes('aria-label="核心业务流"')],
];

const failed = checks.filter(([, ok]) => !ok);
if (failed.length) {
  console.error('Design shell regression failed:');
  for (const [name] of failed) console.error(`- ${name}`);
  process.exit(1);
}

console.log(`Design shell regression passed: ${checks.length} checks`);
