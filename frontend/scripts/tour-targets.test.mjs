// Issue #59: the guided tour must never point at something that does not exist.
//
// Run with `pnpm test` (Node's built-in test runner, no extra dependency).
// It reads the tour definition (lib/tour.json) and checks that every target id
// is set as a `data-tour` attribute by some component, so renaming or removing
// an element fails CI instead of leaving a tour step pointing at nothing.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const tour = JSON.parse(readFileSync(join(root, 'lib', 'tour.json'), 'utf8'));

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (name === 'node_modules' || name === '.next') return [];
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.tsx?$/.test(name) ? [path] : [];
  });
}

// Every id a component can put in a data-tour attribute, either written
// directly (data-tour="x"), through a conditional ('x' : undefined), or taken
// from a link table (tour: 'x').
function idsInSource() {
  const ids = new Set();
  for (const dir of ['app', 'components']) {
    for (const file of sourceFiles(join(root, dir))) {
      const text = readFileSync(file, 'utf8');
      for (const m of text.matchAll(/data-tour=(?:"([\w-]+)"|\{([^}]*)\})/g)) {
        if (m[1]) ids.add(m[1]);
        else for (const q of m[2].matchAll(/'([\w-]+)'/g)) ids.add(q[1]);
      }
      for (const m of text.matchAll(/\btour:\s*'([\w-]+)'/g)) ids.add(m[1]);
    }
  }
  return ids;
}

test('every tour step names at least one target, a title and a body', () => {
  for (const [page, steps] of Object.entries(tour.pages)) {
    assert.ok(steps.length >= 2, `page "${page}" needs at least 2 steps`);
    for (const step of steps) {
      assert.ok(step.targets?.length > 0, `${page}/${step.id}: no targets`);
      assert.ok(step.title && step.body, `${page}/${step.id}: missing title or body`);
    }
  }
});

test('every tour target is a data-tour id that some component sets', () => {
  const available = idsInSource();
  const missing = [];
  for (const [page, steps] of Object.entries(tour.pages)) {
    for (const step of steps) {
      for (const target of step.targets) {
        if (!available.has(target)) missing.push(`${page}/${step.id} -> "${target}"`);
      }
    }
  }
  assert.deepEqual(missing, [], `tour targets no component sets:\n  ${missing.join('\n  ')}`);
});

test('step ids are unique within a page', () => {
  for (const [page, steps] of Object.entries(tour.pages)) {
    const ids = steps.map((s) => s.id);
    assert.equal(new Set(ids).size, ids.length, `duplicate step id on page "${page}"`);
  }
});
