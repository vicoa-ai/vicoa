import { describe, expect, it } from 'vitest';
import { AGENT_CATALOG_FALLBACK } from './agent-catalog';
import { AGENT_INSTALL_INFO, RECOMMENDED_AGENT_ID, installInfoFor } from './desktop-agent-install';

describe('AGENT_INSTALL_INFO', () => {
  it('covers every agent in the catalog', () => {
    // The scan lists every catalog agent and offers install instructions for
    // the missing ones. A new agent landing in the catalog without an entry
    // here would render a row with no way to act on it.
    const missing = AGENT_CATALOG_FALLBACK.agents
      .map((agent) => agent.id)
      .filter((id) => !(id in AGENT_INSTALL_INFO));
    expect(missing).toEqual([]);
  });

  it('has no entries the catalog does not know about', () => {
    const catalogIds = new Set(AGENT_CATALOG_FALLBACK.agents.map((agent) => agent.id));
    const extra = Object.keys(AGENT_INSTALL_INFO).filter((id) => !catalogIds.has(id));
    expect(extra).toEqual([]);
  });

  it('gives every agent a runnable command and a docs link', () => {
    for (const [id, info] of Object.entries(AGENT_INSTALL_INFO)) {
      expect(info.command.trim(), `${id} command`).not.toBe('');
      expect(info.docsUrl, `${id} docsUrl`).toMatch(/^https:\/\//);
    }
  });

  it('recommends an agent that exists in the catalog', () => {
    expect(installInfoFor(RECOMMENDED_AGENT_ID)).not.toBeNull();
  });
});

describe('installInfoFor', () => {
  it('returns null for an unknown agent rather than throwing', () => {
    expect(installInfoFor('not-an-agent')).toBeNull();
  });
});
