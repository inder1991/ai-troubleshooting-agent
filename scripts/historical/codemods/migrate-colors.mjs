#!/usr/bin/env node
// Migrates raw Tailwind color classes to wr-* tokens.
// Large mapping table — review the diff carefully per module.
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const DEFAULT_ROOT = path.resolve(__dirname, '..', '..', 'frontend', 'src');
const EXTS = new Set(['.ts', '.tsx', '.jsx']);

// Allow narrowing the scope by passing a subpath as argv[2]
// e.g. `node migrate-colors.mjs components/shared`
const SUBPATH = process.argv[2];
const ROOT = SUBPATH ? path.join(DEFAULT_ROOT, SUBPATH) : DEFAULT_ROOT;

function walk(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (EXTS.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

// ORDER MATTERS: longer/more-specific patterns must come first so they don't
// get shadowed by a shorter prefix match.
const MAP = [
  // Backgrounds — page/surface (with opacity variants first)
  ['bg-slate-900/50', 'bg-wr-bg/50'],
  ['bg-slate-900',    'bg-wr-bg'],
  ['bg-slate-800/60', 'bg-wr-surface/60'],
  ['bg-slate-800/50', 'bg-wr-surface/50'],
  ['bg-slate-800/40', 'bg-wr-surface/40'],
  ['bg-slate-800',    'bg-wr-surface'],
  ['bg-slate-700/50', 'bg-wr-inset/50'],
  ['bg-slate-700',    'bg-wr-inset'],
  // Borders
  ['border-slate-800/50', 'border-wr-border/50'],
  ['border-slate-800',    'border-wr-border'],
  ['border-slate-700/50', 'border-wr-border-strong/50'],
  ['border-slate-700/40', 'border-wr-border-strong/40'],
  ['border-slate-700',    'border-wr-border-strong'],
  ['border-slate-600',    'border-wr-border-strong'],
  // Severity — red
  ['bg-red-500/30',     'bg-wr-severity-high/30'],
  ['bg-red-500/20',     'bg-wr-severity-high/20'],
  ['bg-red-500/10',     'bg-wr-severity-high/10'],
  ['border-red-500/30', 'border-wr-severity-high/30'],
  // Severity — amber
  ['bg-amber-500/20',     'bg-wr-severity-medium/20'],
  ['bg-amber-500/10',     'bg-wr-severity-medium/10'],
  ['border-amber-500/30', 'border-wr-severity-medium/30'],
  // NOTE: we intentionally do NOT migrate `text-slate-*` or `text-white`
  // in this sweep — Phase 1 already raised contrast and the type ramp is
  // stable; a color-token swap here would produce a visible shift.
  // Likewise we skip bare `bg-red-500`, `bg-amber-500`, `bg-green-500`,
  // `text-red-*`, `text-amber-*`, `text-green-*` because they show up in
  // badges whose local meaning we don't want to tamper with in bulk.
];

const files = walk(ROOT);
let filesChanged = 0;
let total = 0;

for (const file of files) {
  const original = fs.readFileSync(file, 'utf8');
  let updated = original;
  let perFile = 0;
  for (const [from, to] of MAP) {
    // Escape special regex chars; use a literal-string match with word-ish
    // boundaries (classNames are separated by whitespace or quotes).
    const esc = from.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
    const re = new RegExp(`(?<![A-Za-z0-9_-])${esc}(?![A-Za-z0-9_-])`, 'g');
    const count = (updated.match(re) || []).length;
    if (count > 0) {
      updated = updated.replace(re, to);
      perFile += count;
    }
  }
  if (perFile > 0) {
    fs.writeFileSync(file, updated);
    filesChanged += 1;
    total += perFile;
  }
}

console.log(`Modified ${filesChanged} files, ${total} replacements. Root: ${ROOT}`);
