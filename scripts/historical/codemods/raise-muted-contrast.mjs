#!/usr/bin/env node
// Raises muted text contrast on dark backgrounds.
//
// Rule (applied in order — 600→500 FIRST so we don't double-shift):
//   text-slate-600 → text-slate-500
//   text-slate-500 → text-slate-400
//
// The dark-only theme has no light-background exceptions.
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..', 'frontend', 'src');
const EXTS = new Set(['.ts', '.tsx', '.jsx']);

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (EXTS.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

// Sentinel to avoid the 600→500→400 cascade when done in two passes.
const SENTINEL = '\u0001SLATE_500_BUMP\u0001';

const files = walk(ROOT);
let filesChanged = 0;
let total = 0;

for (const file of files) {
  const original = fs.readFileSync(file, 'utf8');
  let updated = original;
  let count = 0;

  // Step 1: mark existing text-slate-500 so they don't double-shift.
  updated = updated.replace(/\btext-slate-500\b/g, () => {
    return SENTINEL;
  });

  // Step 2: shift text-slate-600 -> text-slate-500.
  updated = updated.replace(/\btext-slate-600\b/g, () => {
    count += 1;
    return 'text-slate-500';
  });

  // Step 3: unmark the original 500s, bumping them to 400.
  updated = updated.replace(new RegExp(SENTINEL, 'g'), () => {
    count += 1;
    return 'text-slate-400';
  });

  if (updated !== original) {
    fs.writeFileSync(file, updated);
    filesChanged += 1;
    total += count;
  }
}

console.log(`Modified ${filesChanged} files, ${total} replacements.`);
