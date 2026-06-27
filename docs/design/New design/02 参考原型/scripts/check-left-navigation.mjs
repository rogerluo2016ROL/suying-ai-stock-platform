import { existsSync, readFileSync } from 'node:fs';

const shellPath = 'assets/shell.js';
const shell = readFileSync(shellPath, 'utf8');

function extractLiteral(name, terminator) {
  const start = shell.indexOf(`const ${name} = `);
  if (start < 0) throw new Error(`Missing ${name}`);
  const bodyStart = start + `const ${name} = `.length;
  const end = shell.indexOf(terminator, bodyStart);
  if (end < 0) throw new Error(`Cannot locate end of ${name}`);
  return shell.slice(bodyStart, end);
}

const nav = Function(`return ${extractLiteral('NAV', ';\n  function svg')}`)();
const moduleTabs = Function(`return ${extractLiteral('MODULE_TABS', ';\n  const MODULE_CONTEXT')}`)();
const moduleContext = Function(`return ${extractLiteral('MODULE_CONTEXT', ';\n\n  let navHTML')}`)();

const failures = [];
const navItems = nav.filter((item) => item.k);
const navKeys = navItems.map((item) => item.k);
const navLabels = navItems.map((item) => item.t);

function fail(message) {
  failures.push(message);
}

function pageText(file) {
  if (!existsSync(file)) {
    fail(`Missing page file: ${file}`);
    return '';
  }
  return readFileSync(file, 'utf8');
}

for (const item of navItems) {
  const html = pageText(item.f);
  if (!html) continue;

  if (!moduleTabs[item.k]) fail(`Missing module tabs for ${item.k} (${item.t})`);
  if (!moduleContext[item.k]) fail(`Missing module context for ${item.k} (${item.t})`);

  if (item.k === 'workbench') {
    if (!html.includes('data-page="workbench"')) fail('Workbench must declare data-page="workbench"');
    if (!html.includes('id="sidebar-mount"') || !html.includes('id="header-mount"')) {
      fail('Workbench must use shared shell mounts instead of a local navigation shell');
    }
    if (!html.includes('assets/shell.js')) fail('Workbench must mount shared shell.js');
    if (html.includes('class="side"') || html.includes('class="topbar"') || html.includes('class="subnav"')) {
      fail('Workbench still contains old local side/topbar/subnav shell classes');
    }
  } else {
    if (!html.includes(`data-page="${item.k}"`)) fail(`${item.f} has wrong or missing data-page="${item.k}"`);
    if (!html.includes('assets/shell.js')) fail(`${item.f} does not mount shared shell`);
  }

  const tabs = moduleTabs[item.k] || [];
  for (const tab of tabs) {
    if (tab.f) {
      fail(`${item.t} / ${tab.n} is a module tab but links to ${tab.f}; module tabs must stay on ${item.f} with an in-page anchor`);
    }
    if (tab.anchor && !html.includes(`id="${tab.anchor}"`) && !html.includes(`id='${tab.anchor}'`)) {
      fail(`${item.f} missing anchor #${tab.anchor} for ${item.t} / ${tab.n}`);
    }
  }
}

for (const key of Object.keys(moduleTabs)) {
  if (!navKeys.includes(key)) fail(`MODULE_TABS has orphan key ${key}`);
}

for (const key of Object.keys(moduleContext)) {
  if (!navKeys.includes(key)) fail(`MODULE_CONTEXT has orphan key ${key}`);
}

for (const label of navLabels) {
  if (!shell.includes(label)) fail(`Shared shell left menu missing ${label}`);
}

if (shell.includes('aria-label="核心业务流"') || shell.includes('workflow-nav') || shell.includes('trading-context')) {
  fail('Shared shell still contains old fixed workflow navigation wording');
}

if (failures.length) {
  console.error('Left navigation regression failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Left navigation regression passed: ${navItems.length} modules checked`);
