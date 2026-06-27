import { readFileSync, writeFileSync, readdirSync } from 'node:fs';

const files = readdirSync('.').filter((file) => /preview\.html$/.test(file)).sort();

function mainBounds(html){
  const open = html.match(/<main\b[^>]*class=(["'])[^"']*\bcontent\b[^"']*\1[^>]*>/i);
  if(!open) return null;
  const start = open.index + open[0].length;
  const close = html.indexOf('</main>', start);
  if(close < 0) return null;
  return { openStart: open.index, start, close };
}

function extractBalancedContentDiv(fragment){
  const starts = Array.from(fragment.matchAll(/<div\b[^>]*class=(["'])[^"']*\bcontent\b[^"']*\1[^>]*>/gi));
  if(!starts.length) return '';
  const startMatch = starts[starts.length - 1];
  const openEnd = startMatch.index + startMatch[0].length;
  let depth = 1;
  const tagRe = /<\/?div\b[^>]*>/gi;
  tagRe.lastIndex = openEnd;
  let match;
  while((match = tagRe.exec(fragment))){
    if(match[0].startsWith('</')) depth -= 1;
    else depth += 1;
    if(depth === 0) return fragment.slice(openEnd, match.index);
  }
  return '';
}

let cleaned = 0;
for(const file of files){
  const html = readFileSync(file, 'utf8');
  const bounds = mainBounds(html);
  if(!bounds) continue;
  const currentMain = html.slice(bounds.start, bounds.close);
  if(!/<nav class="sidebar"|<header class="header"|<div class="app">/i.test(currentMain)) continue;
  const inner = extractBalancedContentDiv(currentMain);
  if(!inner) continue;
  const next = html.slice(0, bounds.start) + '\n' + inner.trim().split('\n').map((line)=>`      ${line}`).join('\n') + '\n    ' + html.slice(bounds.close);
  writeFileSync(file, next);
  cleaned += 1;
}

console.log(`Cleaned ${cleaned} nested legacy shells`);
