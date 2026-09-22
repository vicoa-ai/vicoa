import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ACP_CATALOG_AGENTS } from './acp-catalog-agents';
import { acpIconSrc } from './acp-provider-icons';

// The ids the backend actually serves, so the marketing list can't drift
// from what Settings → Providers offers.
const backendIds = [
  ...readFileSync(join(process.cwd(), '../../backend/src/protocol/acp_catalog.py'), 'utf8').matchAll(
    /"id":\s*"([a-z0-9-]+)"/g,
  ),
].map((m) => m[1]);

describe('the /coding-agents catalog list', () => {
  it('lists exactly the backend catalog, no more and no less', () => {
    const listed = ACP_CATALOG_AGENTS.map((a) => a.id).sort();
    expect(listed).toEqual([...backendIds].sort());
  });

  it('has a brand mark for every entry, so no card shows a letter square', () => {
    expect(ACP_CATALOG_AGENTS.filter((a) => acpIconSrc(a.id) === null).map((a) => a.id)).toEqual([]);
  });

  it('has unique names and ids', () => {
    expect(new Set(ACP_CATALOG_AGENTS.map((a) => a.id)).size).toBe(ACP_CATALOG_AGENTS.length);
    expect(new Set(ACP_CATALOG_AGENTS.map((a) => a.name)).size).toBe(ACP_CATALOG_AGENTS.length);
  });
});
