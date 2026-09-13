import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ACP_ICON_KEYS, acpIconSrc } from './acp-provider-icons';
import { getAgentLogoSrc } from '@/components/dashboard/agent-type-icon';

const ICON_DIR = join(process.cwd(), 'public/images/acp');
const iconFiles = readdirSync(ICON_DIR).filter((f) => f.endsWith('.svg'));

describe('acpIconSrc', () => {
  it('resolves a provider id and the display name a session carries', () => {
    // The picker passes the id; a running session passes the label.
    expect(acpIconSrc('cline')).toBe('/images/acp/cline.svg');
    expect(acpIconSrc('Cline')).toBe('/images/acp/cline.svg');
    expect(acpIconSrc('factory-droid')).toBe('/images/acp/factory-droid.svg');
    expect(acpIconSrc('Factory Droid')).toBe('/images/acp/factory-droid.svg');
    // id and label differ entirely for the `-acp` wrapper packages.
    expect(acpIconSrc('amp-acp')).toBe('/images/acp/amp-acp.svg');
    expect(acpIconSrc('Amp')).toBe('/images/acp/amp-acp.svg');
  });

  it('returns null for anything with no mark, rather than a broken path', () => {
    // Catalog entries we ship no logo for, and ids nobody has ever heard of.
    expect(acpIconSrc('devin')).toBeNull();
    expect(acpIconSrc('kiro')).toBeNull();
    expect(acpIconSrc('my-private-agent')).toBeNull();
    expect(acpIconSrc('')).toBeNull();
    expect(acpIconSrc(null)).toBeNull();
    expect(acpIconSrc(undefined)).toBeNull();
  });

  it('never shadows a built-in agent’s hand-tuned brand mark', () => {
    // AgentTypeIcon consults this map FIRST, and it has no light/dark
    // treatment — a key collision here would silently break Claude or Cursor.
    for (const builtin of ['claude', 'claude code', 'codex', 'opencode', 'cursor', 'gemini', 'copilot', 'kimi', 'hermes', 'pi', 'omp']) {
      expect(acpIconSrc(builtin), builtin).toBeNull();
      expect(getAgentLogoSrc(builtin), builtin).not.toBeNull();
    }
  });
});

describe('the generated index and the files on disk agree', () => {
  it('every key points at a file that exists', () => {
    const missing = ACP_ICON_KEYS.map((key) => acpIconSrc(key))
      .map((src) => src!.replace('/images/acp/', ''))
      .filter((file) => !iconFiles.includes(file));
    expect([...new Set(missing)]).toEqual([]);
  });

  it('every file is reachable through some key', () => {
    const reachable = new Set(ACP_ICON_KEYS.map((key) => acpIconSrc(key)!.replace('/images/acp/', '')));
    expect(iconFiles.filter((file) => !reachable.has(file))).toEqual([]);
    expect(iconFiles.length).toBeGreaterThan(20);
  });
});

describe('the mark files themselves', () => {
  // They are painted as a CSS mask over currentColor, so they must be
  // single-colour: a hardcoded fill would be masked to a flat silhouette on
  // one theme and vanish on the other.
  it('are monochrome currentColor glyphs', () => {
    const offenders = iconFiles.filter((file) => {
      const svg = readFileSync(join(ICON_DIR, file), 'utf8');
      return [...svg.matchAll(/(?:fill|stroke)="([^"]*)"/g)].some(
        ([, value]) => !['currentColor', 'none', 'transparent'].includes(value),
      );
    });
    expect(offenders).toEqual([]);
  });

  // A mask never enters the DOM, so this cannot execute today — but the files
  // are third-party artwork, and the next one might be pasted somewhere that
  // does parse it.
  it('carry no script, event handler or remote reference', () => {
    const offenders = iconFiles.filter((file) => {
      const svg = readFileSync(join(ICON_DIR, file), 'utf8');
      return /<script|\son\w+\s*=|javascript:|<foreignObject|(?:xlink:)?href\s*=\s*["']\s*(?:https?:)?\/\//i.test(svg);
    });
    expect(offenders).toEqual([]);
  });
});
