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

const nav = Function(`return ${extractLiteral('NAV', ';\n  function svg')}`)().filter((item) => item.k);
const moduleTabs = Function(`return ${extractLiteral('MODULE_TABS', ';\n  const MODULE_CONTEXT')}`)();
const failures = [];

function fail(message) {
  failures.push(message);
}

function sectionFor(html, tabs, index) {
  const anchor = tabs[index].anchor;
  const start = html.indexOf(`id="${anchor}"`);
  if (start < 0) return '';

  let end = html.length;
  for (let i = index + 1; i < tabs.length; i += 1) {
    const next = html.indexOf(`id="${tabs[i].anchor}"`, start + 1);
    if (next > start && next < end) end = next;
  }
  return html.slice(start, end);
}

for (const item of nav) {
  if (!existsSync(item.f)) {
    fail(`Missing page: ${item.f}`);
    continue;
  }
  const html = readFileSync(item.f, 'utf8');
  const tabs = moduleTabs[item.k] || [];
  for (let index = 0; index < tabs.length; index += 1) {
    const tab = tabs[index];
    const section = sectionFor(html, tabs, index);
    if (!section) {
      fail(`${item.t} / ${tab.n} missing section #${tab.anchor}`);
      continue;
    }
    const hasAction = /<(button|a|input|select|textarea)\b/.test(section);
    const hasData = /<(table)\b|class="[^"]*(kpi|li-row|svc|node|chart|card|tbl|bar|tag|led|state-note)/.test(section);
    const hasState = /aria-|role=|data-toast|empty|warn|risk|状态|校验|闸门|复核|延迟|异常|降级/.test(section);
    if (!hasAction && !(hasData && hasState)) {
      fail(`${item.t} / ${tab.n} is not actionable enough: section #${tab.anchor} needs an action, table, or persistent state`);
    }
  }
}

if (failures.length) {
  console.error('Module actionability check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`Module actionability passed: ${nav.length} modules checked`);
