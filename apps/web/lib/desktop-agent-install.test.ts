import { describe, expect, it } from 'vitest';
import { AGENT_CATALOG_FALLBACK } from './agent-catalog';
import {
  AGENT_INSTALL_INFO,
  PLAN_CHOICES,
  installInfoFor,
  installOsForPlatform,
  installStepFor,
} from './desktop-agent-install';

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

  it('never hands a Windows user a bash or brew line', () => {
    // PowerShell has no bash and no brew: such a line fails where it is pasted.
    // Agents without a Windows one-liner say so (null) and point at the guide.
    for (const id of Object.keys(AGENT_INSTALL_INFO)) {
      const command = installStepFor(id, 'windows')?.command ?? null;
      if (command === null) continue;
      expect(command, id).not.toMatch(/\|\s*(ba)?sh\b|^brew /);
    }
  });
});

describe('PLAN_CHOICES', () => {
  it('leads with agents the catalog knows, each installable on both OSes', () => {
    for (const choice of PLAN_CHOICES) {
      expect(installInfoFor(choice.id), choice.id).not.toBeNull();
      expect(installStepFor(choice.id, 'unix')?.command, choice.id).toBeTruthy();
      expect(installStepFor(choice.id, 'windows')?.command, choice.id).toBeTruthy();
    }
  });
});

describe('installStepFor', () => {
  it('returns null for an unknown agent rather than throwing', () => {
    expect(installStepFor('not-an-agent', 'unix')).toBeNull();
  });

  it('gives Windows its own installer and says where to run it', () => {
    expect(installStepFor('claude', 'windows')).toMatchObject({
      command: 'irm https://claude.ai/install.ps1 | iex',
      shell: 'PowerShell',
      requires: null,
    });
    expect(installStepFor('claude', 'unix')).toMatchObject({
      command: 'curl -fsSL https://claude.ai/install.sh | bash',
      shell: 'a terminal',
    });
  });

  it('reuses an npm command on Windows and names Node.js as the prerequisite', () => {
    expect(installStepFor('gemini', 'windows')).toMatchObject({
      command: 'npm install -g @google/gemini-cli',
      requires: 'Node.js',
    });
  });

  it('has no command when the agent documents no Windows one-liner', () => {
    expect(installStepFor('kimi', 'windows')?.command).toBeNull();
  });
});

describe('installOsForPlatform', () => {
  it('reads the daemon platform string', () => {
    expect(installOsForPlatform('Windows-11-10.0.26100-SP0')).toBe('windows');
    expect(installOsForPlatform('macOS-15.4-arm64-arm-64bit')).toBe('unix');
    expect(installOsForPlatform('Linux-6.8.0-x86_64-with-glibc2.39')).toBe('unix');
    expect(installOsForPlatform(null)).toBe('unix');
  });
});
