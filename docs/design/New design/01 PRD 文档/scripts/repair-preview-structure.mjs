import { readFileSync, writeFileSync, readdirSync } from 'node:fs';

const files = readdirSync('.').filter((file) => /preview\.html$/.test(file)).sort();

let changedCount = 0;

function findLastMainCloseBeforeToast(html){
  const toastIndex = html.indexOf('<div class="toast"');
  if(toastIndex < 0) return -1;
  return html.lastIndexOf('</main>', toastIndex);
}

function cleanMainBody(body){
  let next = body;

  next = next.replace(
    /\s*<!--\s*(?:=+\s*)?(?:Tab Navigation|横向\s*Tab\s*导航)(?:\s*=+)?\s*-->\s*<\/div>\s*/gi,
    '\n'
  );

  next = next.replace(
    /\s*<!--\s*Tab Nav\s*-->\s*<div\b[^>]*style="[^"]*display:flex;gap:2px;background:var\(--surface\);border:1px solid var\(--border\)[^"]*"[^>]*>[\s\S]*?<\/div>\s*/gi,
    '\n'
  );

  next = next.replace(
    /\s*<\/main>\s*<\/div>\s*<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]*?<\/script>\s*/gi,
    '\n'
  );

  next = next.replace(
    /\s*<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]*?<\/script>\s*/gi,
    '\n'
  );

  next = next.replace(/\s*<\/main>\s*/gi, '\n');
  next = next.replace(/\n{3,}/g, '\n\n');

  return next.trim();
}

for(const file of files){
  const before = readFileSync(file, 'utf8');
  const mainOpen = before.match(/<main class="content">/);
  if(!mainOpen) continue;

  const mainOpenStart = mainOpen.index;
  const mainOpenEnd = mainOpenStart + mainOpen[0].length;
  const mainCloseStart = findLastMainCloseBeforeToast(before);
  if(mainCloseStart < 0 || mainCloseStart < mainOpenEnd) continue;

  const prefix = before.slice(0, mainOpenEnd);
  const body = before.slice(mainOpenEnd, mainCloseStart);
  const suffix = before.slice(mainCloseStart);

  const repairedBody = cleanMainBody(body);
  const after = `${prefix}\n${repairedBody}\n    ${suffix}`;

  if(after !== before){
    writeFileSync(file, after);
    changedCount += 1;
  }
}

console.log(`Repaired preview structure in ${changedCount} files`);
