// Issue #76: fonts are committed files, never downloads.
//
// `next/font/google` fetches each font from Google on every build. When one
// fetch fails the whole build fails, in CI and on Vercel. Run with `pnpm test`
// (Node's built-in test runner, no extra dependency).

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (name === 'node_modules' || name === '.next') return [];
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.tsx?$/.test(name) ? [path] : [];
  });
}

test('no code imports next/font/google', () => {
  const offenders = [];
  for (const dir of ['app', 'components', 'lib']) {
    for (const file of sourceFiles(join(root, dir))) {
      // an import or require of the module; a comment that mentions it is fine
      if (/(?:from|import|require\()\s*\(?\s*['"]next\/font\/google['"]/.test(readFileSync(file, 'utf8'))) {
        offenders.push(file.replace(root + '/', ''));
      }
    }
  }
  assert.deepEqual(
    offenders,
    [],
    `use next/font/local with a committed file instead:\n  ${offenders.join('\n  ')}`,
  );
});

test('every font file the layout names exists', () => {
  const layout = readFileSync(join(root, 'app', 'layout.tsx'), 'utf8');
  const files = [...layout.matchAll(/'\.\/(font-[\w-]+\.woff2)'/g)].map((m) => m[1]);
  assert.ok(files.length >= 5, 'layout.tsx should name its local font files');
  for (const file of files) {
    assert.ok(statSync(join(root, 'app', file)).size > 1000, `${file} is missing or empty`);
  }
});
