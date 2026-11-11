import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PLUGIN_ICON_NAMES } from '@/components/plugins/plugin-icon';
import { THEME_TOKEN_WHITELIST } from './types';

// The daemon validates manifests against allow-lists in Python; the renderer
// keeps its own copies. A name on one side only is either dropped by the
// daemon or drawn as the fallback glyph, so the lists must match exactly.
const manifestPy = readFileSync(
  join(process.cwd(), '../../backend/src/protocol/plugin_manifest.py'),
  'utf8',
);

function pythonSet(name: string): string[] {
  const body = manifestPy.match(new RegExp(`${name}: frozenset\\[str\\] = frozenset\\(\\s*\\{([^}]*)\\}`))?.[1];
  if (!body) throw new Error(`${name} not found in plugin_manifest.py`);
  return [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
}

describe('plugin manifest allow-lists', () => {
  it('icon names match the backend ICON_WHITELIST', () => {
    expect([...PLUGIN_ICON_NAMES].sort()).toEqual(pythonSet('ICON_WHITELIST'));
  });

  it('theme tokens match the backend THEME_TOKEN_WHITELIST', () => {
    expect([...THEME_TOKEN_WHITELIST].sort()).toEqual(pythonSet('THEME_TOKEN_WHITELIST'));
  });
});
