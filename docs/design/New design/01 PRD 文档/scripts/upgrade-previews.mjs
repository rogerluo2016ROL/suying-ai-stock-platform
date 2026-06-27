import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { basename, join } from 'node:path';

const root = process.cwd();
const files = readdirSync(root).filter((file) => /preview\.html$/.test(file)).sort();

const pageMeta = [
  [/^1\./, 'dashboard'],
  [/^2\./, 'opening-decision'],
  [/^3\./, 'screener'],
  [/^4\./, 'supply-chain'],
  [/^5\./, 'predictions'],
  [/^6\./, 'signals'],
  [/^7\./, 'trade'],
  [/^8\./, 'auto-trade'],
  [/^9\./, 'plans'],
  [/^10\./, 'risk-control'],
  [/^11\./, 'backtest'],
  [/^12\./, 'diagnosis'],
  [/^13\./, 'training'],
  [/^14\./, 'model-registry'],
  [/^15\./, 'data-update'],
  [/^16\./, 'runtime-status']
];

function pageFor(file){
  return pageMeta.find(([rx]) => rx.test(file))?.[1] || 'dashboard';
}

function titleFor(html, file){
  const docTitle = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim();
  if(docTitle) return docTitle.replace(/^速赢AI\s*[·|-]\s*/,'').replace(/预览$/,'').trim();
  return basename(file, '.html').replace(/^\d+(?:\.\d+)?\s*/,'').replace(/-preview$/,'').replace(/-/g,' ');
}

function collectStyle(html){
  const styles = [];
  html.replace(/<style[^>]*>([\s\S]*?)<\/style>/gi, (_, css) => {
    styles.push(css.trim());
    return '';
  });
  return styles.join('\n\n');
}

function collectScripts(html){
  const external = [];
  const inline = [];
  html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi, (_, attrs, code) => {
    const src = attrs.match(/\bsrc=(["'])(.*?)\1/i)?.[2];
    if(src){
      if(!/assets\/shell\.js|assets\/preview-interactions\.js/i.test(src)) external.push(src);
    }else if(code.trim()){
      inline.push(code.trim());
    }
    return '';
  });
  return { external: Array.from(new Set(external)), inline };
}

function extractMain(html){
  const main = html.match(/<main\b[^>]*class=(["'])[^"']*\bcontent\b[^"']*\1[^>]*>([\s\S]*?)<\/main>/i);
  let content = main?.[2];
  if(!content){
    content = extractBalancedContentDiv(html) || html.match(/<body[^>]*>([\s\S]*?)<\/body>/i)?.[1] || '';
  }

  content = content
    .replace(/<!--\s*=+\s*顶部\s*Tab\s*导航\s*=+\s*-->[\s\S]*?(?=<!--\s*=+\s*页面标题|<!--\s*=+\s*顶部|<div class="page-head"|<div class="top-bar")/i, '')
    .replace(/<div style="display:flex;gap:0;margin-bottom:16px;border-bottom:2px solid var\(--border\)">[\s\S]*?<\/div>\s*(?=<!--|<div class="page-head"|<div class="top-bar")/i, (block)=>`<div class="legacy-local-tabs">${block}</div>`)
    .replace(/\s*<div class="legacy-local-tabs">[\s\S]*?<\/div>\s*/g, '')
    .replace(/<div class="toast" id="toast"><\/div>/gi, '');

  return content.trim();
}

function extractBalancedContentDiv(html){
  const starts = Array.from(html.matchAll(/<div\b[^>]*class=(["'])[^"']*\bcontent\b[^"']*\1[^>]*>/gi));
  if(!starts.length) return '';
  const startMatch = starts[starts.length - 1];
  const openEnd = startMatch.index + startMatch[0].length;
  let depth = 1;
  const tagRe = /<\/?div\b[^>]*>/gi;
  tagRe.lastIndex = openEnd;
  let match;
  while((match = tagRe.exec(html))){
    if(match[0].startsWith('</')) depth -= 1;
    else depth += 1;
    if(depth === 0) return html.slice(openEnd, match.index);
  }
  return '';
}

function doc({ file, html }){
  const title = titleFor(html, file);
  const page = pageFor(file);
  const styles = collectStyle(html);
  const scripts = collectScripts(html);
  const main = extractMain(html);
  const externalScripts = scripts.external
    .filter((src) => !/assets\/app\.css/i.test(src))
    .map((src) => `<script src="${src}"></script>`)
    .join('\n');
  const inlineScripts = scripts.inline.map((code) => `<script>\n${code}\n</script>`).join('\n\n');

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>速赢AI · ${title}</title>
${externalScripts}
${styles ? `<style class="legacy-page-style">\n${styles}\n</style>` : ''}
<link rel="stylesheet" href="assets/app.css" />
<link rel="stylesheet" href="assets/preview-adapter.css" />
</head>
<body class="legacy-preview" data-page="${page}" data-title="${title}">
<div class="app">
  <div id="sidebar-mount"></div>
  <div class="main">
    <div id="header-mount"></div>
    <main class="content">
${main.split('\n').map((line) => `      ${line}`).join('\n')}
    </main>
  </div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script src="assets/shell.js"></script>
${inlineScripts}
<script src="assets/preview-interactions.js"></script>
</body>
</html>
`;
}

let changed = 0;
for(const file of files){
  const path = join(root, file);
  const html = readFileSync(path, 'utf8');
  const next = doc({ file, html });
  writeFileSync(path, next);
  changed += 1;
}

console.log(`Upgraded ${changed} preview files`);
