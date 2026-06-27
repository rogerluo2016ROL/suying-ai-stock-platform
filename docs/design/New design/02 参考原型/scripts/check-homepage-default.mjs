import { readFileSync } from 'node:fs';

function fail(message) {
  console.error(`Homepage default regression failed: ${message}`);
  process.exit(1);
}

const index = readFileSync('index.html', 'utf8');
const workbenchEntry = readFileSync('workbench-redesign.html', 'utf8');
const shell = readFileSync('assets/shell.js', 'utf8');
const spec = readFileSync('design-spec.md', 'utf8');

if (!index.includes('<title>速赢AI · AI 智能看板</title>')) {
  fail('index.html title must be AI 智能看板');
}
if (!index.includes('<body data-page="dashboard" data-title="AI 智能看板">')) {
  fail('index.html body must use dashboard page metadata');
}
if (!workbenchEntry.includes('<title>速赢AI · AI 智能看板</title>')) {
  fail('workbench-redesign.html is the current default design target and must open AI 智能看板');
}
if (!workbenchEntry.includes('<body data-page="dashboard" data-title="AI 智能看板">')) {
  fail('workbench-redesign.html must use dashboard page metadata when opened as the default target');
}
if (!shell.includes("{k:'dashboard',  f:'index.html'") || !shell.includes("t:'AI 智能看板'")) {
  fail('shared navigation must point dashboard module to index.html');
}
if (!/默认首页[^\n]*AI 智能看板/.test(spec)) {
  fail('design-spec.md must state AI 智能看板 is the default homepage');
}

console.log('Homepage default regression passed: AI 智能看板 is the default homepage');
