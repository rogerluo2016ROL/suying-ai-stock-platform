import { readFileSync } from 'node:fs';

const html = readFileSync('suying-ai-workbench-redesign.html', 'utf8');
const css = readFileSync('assets/app.css', 'utf8');
const failures = [];

function fail(message) {
  failures.push(message);
}

const requiredHtml = [
  ['id="marketLoading"', 'workbench needs a persistent loading status region'],
  ['id="degradedNotice"', 'workbench needs a persistent degraded/error notice'],
  ['id="clearSearch"', 'candidate search needs a clear action'],
  ['id="ticketStatus"', 'trade ticket needs a live status summary'],
  ['id="submitReview"', 'trade ticket needs an explicit submit/review action'],
  ['role="list"', 'candidate list should expose list semantics'],
  ['aria-controls="candidateList"', 'candidate filters should declare their target'],
  ['aria-live="polite"', 'state changes should be announced politely'],
  ['aria-describedby="degradedNotice"', 'degrade action should describe the persistent impact'],
  ['data-loading-text=', 'loading actions need stable loading labels'],
];

for (const [needle, message] of requiredHtml) {
  if (!html.includes(needle)) fail(message);
}

const requiredCss = [
  [':root{', 'shared CSS should define default design tokens'],
  ['--bg:#f4f6fa', 'day theme should be the default background token'],
  [':root[data-theme="dark"]', 'dark theme should be explicitly opt-in'],
  [':focus-visible', 'shared CSS needs a visible keyboard focus state'],
  ['.btn:disabled', 'shared CSS needs disabled button styling'],
  ['@media (prefers-reduced-motion: reduce)', 'shared CSS needs reduced-motion fallback'],
  ['.state-banner', 'shared CSS needs a persistent state banner component'],
  ['.btn.is-loading', 'shared CSS needs loading button state'],
  ['.candidate[aria-pressed="true"]', 'workbench CSS needs semantic selected candidate state'],
  ['.svc-card.downline', 'workbench CSS needs persistent degraded service state'],
  ['.sticky-ticket', 'workbench CSS needs desktop sticky trade ticket behavior'],
];

for (const [needle, message] of requiredCss) {
  if (!css.includes(needle) && !html.includes(needle)) fail(message);
}

const defaultRootBlock = css.match(/^:root\{([\s\S]*?)\n\}/m)?.[1] || '';
if (defaultRootBlock.includes('--bg:#0b0e14')) {
  fail('dark theme tokens must not be the global default');
}

if (!/localStorage\.getItem\('suying_theme'\) \|\| 'light'/.test(readFileSync('assets/shell.js', 'utf8'))) {
  fail('shared shell should default first-time visitors to light theme');
}

if (/<[^>]+\sstyle="/.test(html)) {
  fail('workbench should not rely on inline style attributes for core layout');
}

if (/scrollIntoView/.test(html + css)) {
  fail('workbench must not use scrollIntoView in embedded preview');
}

if (failures.length) {
  console.error('Workbench polish check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Workbench polish passed');
