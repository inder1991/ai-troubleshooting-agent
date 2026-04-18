#!/usr/bin/env node
// Raises sub-12px text to readable minimums.
//
// Rule:
//   text-nano / text-[8px]                    → text-chrome  (11px, chrome only)
//   text-micro / text-[9px] / text-[10px]     → text-body-xs (12px)
//   text-[11px]                               → text-body-xs (12px)
//
// Scope: all .ts/.tsx/.jsx files under frontend/src
// Safety:
//   - does literal className-token replacements only
//   - does not touch text-[12px] or larger
//   - does not touch inline-styles or numeric sizes in JS
//
// Survivors (template literals, multi-line className concats) are
// intentionally left for Task 1.5 hand-fixing.
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..', 'frontend', 'src');

const EXTS = new Set(['.ts', '.tsx', '.jsx']);

/** @returns {string[]} */
function walk(dir) {
  /** @type {string[]} */
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if (EXTS.has(path.extname(entry.name))) {
      out.push(full);
    }
  }
  return out;
}

const REPLACEMENTS = [
  [/\btext-nano\b/g, 'text-chrome'],
  [/\btext-\[8px\]/g, 'text-chrome'],
  [/\btext-micro\b/g, 'text-body-xs'],
  [/\btext-\[9px\]/g, 'text-body-xs'],
  [/\btext-\[10px\]/g, 'text-body-xs'],
  [/\btext-\[11px\]/g, 'text-body-xs'],
];

const files = walk(ROOT);
let totalReplacements = 0;
let filesChanged = 0;

for (const file of files) {
  const original = fs.readFileSync(file, 'utf8');
  let updated = original;
  let perFile = 0;
  for (const [pattern, replacement] of REPLACEMENTS) {
    updated = updated.replace(pattern, (match) => {
      perFile += 1;
      return replacement;
    });
  }
  if (perFile > 0) {
    fs.writeFileSync(file, updated);
    filesChanged += 1;
    totalReplacements += perFile;
  }
}

console.log(`Modified ${filesChanged} files, ${totalReplacements} replacements.`);
