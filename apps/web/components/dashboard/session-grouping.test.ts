import { describe, expect, it } from 'vitest';
import type { AgentInstanceResponse } from '@/lib/backend-api';
import {
  distinctAgentNames,
  distinctProjectNames,
  filterWantsActiveOnly,
  getLastPathPart,
  groupSessions,
  splitProjectByWorktree,
} from './session-grouping';

const base: AgentInstanceResponse = {
  id: 'x',
  agent_type_id: 't',
  agent_type_name: 'claude',
  name: null,
  status: 'ACTIVE',
  started_at: '2026-01-01T00:00:00.000Z',
  ended_at: null,
  latest_message: null,
  latest_message_at: null,
  chat_length: 0,
  project: null,
  pinned_at: null,
};

const make = (over: Partial<AgentInstanceResponse>): AgentInstanceResponse => ({
  ...base,
  ...over,
});

describe('getLastPathPart', () => {
  it('returns the last segment, ignoring trailing slashes', () => {
    expect(getLastPathPart('/Users/dev/projects/vicoa-web/')).toBe('vicoa-web');
    expect(getLastPathPart('/a/b/c')).toBe('c');
    expect(getLastPathPart('solo')).toBe('solo');
  });
});

describe('filterWantsActiveOnly', () => {
  it('is false for terminal / all filters, true otherwise', () => {
    expect(filterWantsActiveOnly('all')).toBe(false);
    expect(filterWantsActiveOnly('done')).toBe(false);
    expect(filterWantsActiveOnly('closed')).toBe(false);
    expect(filterWantsActiveOnly('not_closed')).toBe(true);
    expect(filterWantsActiveOnly('in_progress')).toBe(true);
    expect(filterWantsActiveOnly('in_review')).toBe(true);
  });
});

describe('groupSessions', () => {
  it('sorts newest first and pulls pinned into a leading Pinned group', () => {
    const older = make({ id: 'older', latest_message_at: '2026-01-01T00:00:00.000Z' });
    const newer = make({ id: 'newer', latest_message_at: '2026-06-01T00:00:00.000Z' });
    const pinned = make({ id: 'pinned', latest_message_at: '2020-01-01T00:00:00.000Z', pinned_at: '2026-01-01T00:00:00.000Z' });

    const groups = groupSessions([older, newer, pinned], 'all', 'time');
    expect(groups[0].key).toBe('PINNED');
    expect(groups[0].instances.map((i) => i.id)).toEqual(['pinned']);

    // pinned excluded from the time groups; newer before older within a group
    const allNonPinned = groups.slice(1).flatMap((g) => g.instances.map((i) => i.id));
    expect(allNonPinned).toEqual(['newer', 'older']);
  });

  it('filters by status (in_review only shows AWAITING_INPUT)', () => {
    const active = make({ id: 'a', status: 'ACTIVE' });
    const awaiting = make({ id: 'b', status: 'AWAITING_INPUT' });
    const done = make({ id: 'c', status: 'REVIEWED' });

    const groups = groupSessions([active, awaiting, done], 'in_review', 'time');
    const ids = groups.flatMap((g) => g.instances.map((i) => i.id));
    expect(ids).toEqual(['b']);
  });

  it('groups by project using the last path segment, no-project last', () => {
    const p1 = make({ id: 'p1', project: '/home/me/alpha' });
    const p2 = make({ id: 'p2', project: '/home/me/beta' });
    const none = make({ id: 'none', project: null });

    const groups = groupSessions([p1, p2, none], 'all', 'project');
    expect(groups.map((g) => g.label)).toEqual(['alpha', 'beta', null]);
    expect(groups[2].instances.map((i) => i.id)).toEqual(['none']);
  });

  it('groups by status and only includes the Archived group for all/closed filters', () => {
    const active = make({ id: 'a', status: 'ACTIVE' });
    const closed = make({ id: 'c', status: 'COMPLETED' });

    const all = groupSessions([active, closed], 'all', 'status');
    const archived = all.find((g) => g.key === 'CLOSED');
    expect(archived?.label).toBe('Archived');

    const notClosed = groupSessions([active, closed], 'not_closed', 'status');
    expect(notClosed.map((g) => g.key)).not.toContain('CLOSED');
  });

  it('filters by agent, leaving pinned sessions visible', () => {
    const claude = make({ id: 'claude', agent_type_name: 'Claude Code' });
    const codex = make({ id: 'codex', agent_type_name: 'Codex' });
    const pinnedCodex = make({
      id: 'pinned-codex',
      agent_type_name: 'Codex',
      pinned_at: '2026-01-01T00:00:00.000Z',
    });

    const groups = groupSessions([claude, codex, pinnedCodex], 'all', 'time', 'Claude Code');
    const ids = groups.flatMap((g) => g.instances.map((i) => i.id));
    expect(ids).toEqual(['pinned-codex', 'claude']);

    const all = groupSessions([claude, codex, pinnedCodex], 'all', 'time', 'all');
    expect(all.flatMap((g) => g.instances)).toHaveLength(3);
  });
});

describe('groupSessions project order', () => {
  it('ranks projects by the custom order, unranked alphabetical, no-project last', () => {
    const a = make({ id: 'a', project: '/x/alpha' });
    const b = make({ id: 'b', project: '/x/beta' });
    const c = make({ id: 'c', project: '/x/gamma' });
    const none = make({ id: 'n', project: null });

    const groups = groupSessions([a, b, c, none], 'all', 'project', 'all', ['gamma', 'alpha']);
    expect(groups.map((g) => g.label)).toEqual(['gamma', 'alpha', 'beta', null]);
  });
});

describe('groupSessions hidden projects', () => {
  it('hides deselected projects, keeps no-project sessions and pinned ones', () => {
    const a = make({ id: 'a', project: '/x/alpha' });
    const b = make({ id: 'b', project: '/x/beta' });
    const none = make({ id: 'n', project: null });
    const pinnedBeta = make({
      id: 'pinned-beta',
      project: '/x/beta',
      pinned_at: '2026-01-01T00:00:00.000Z',
    });

    const groups = groupSessions([a, b, none, pinnedBeta], 'all', 'time', 'all', [], ['beta']);
    const ids = groups.flatMap((g) => g.instances.map((i) => i.id));
    expect(ids).toEqual(['pinned-beta', 'a', 'n']);
  });
});

describe('splitProjectByWorktree (git-driven)', () => {
  const at = (iso: string) => ({ latest_message_at: iso });
  const wt = (path: string, branch: string, managed = true) => ({ path, branch, managed });

  it('separates main-checkout sessions from worktree sessions by branch', () => {
    const main = make({ id: 'main', project: '~/app', ...at('2026-01-04T00:00:00.000Z') });
    const a = make({ id: 'a', project: '~/vicoa/workspaces/app-worktrees/brave/app', worktree_name: 'brave', ...at('2026-01-03T00:00:00.000Z') });
    const b = make({ id: 'b', project: '~/vicoa/workspaces/app-worktrees/calm/app', worktree_name: 'calm', ...at('2026-01-02T00:00:00.000Z') });

    const { mainInstances, worktrees } = splitProjectByWorktree(
      [main, a, b],
      [wt('/abs/brave/app', 'brave'), wt('/abs/calm/app', 'calm')],
    );

    expect(mainInstances.map((i) => i.id)).toEqual(['main']);
    expect(worktrees.map((w) => w.branch)).toEqual(['brave', 'calm']);
    expect(worktrees.map((w) => w.instances.map((i) => i.id))).toEqual([['a'], ['b']]);
  });

  it('shows a worktree with no sessions (#4)', () => {
    const main = make({ id: 'main', project: '~/app' });

    const { worktrees } = splitProjectByWorktree(
      [main],
      [wt('/abs/empty/app', 'empty')],
    );

    expect(worktrees.map((w) => w.branch)).toEqual(['empty']);
    expect(worktrees[0].instances).toEqual([]);
    expect(worktrees[0].path).toBe('/abs/empty/app');
  });

  it('folds a session whose worktree no longer exists into main (#3)', () => {
    const main = make({ id: 'main', project: '~/app', ...at('2026-01-05T00:00:00.000Z') });
    const orphan = make({ id: 'orphan', project: '~/gone/app', worktree_name: 'deleted', ...at('2026-01-04T00:00:00.000Z') });
    const live = make({ id: 'live', project: '~/live/app', worktree_name: 'brave', ...at('2026-01-03T00:00:00.000Z') });

    const { mainInstances, worktrees } = splitProjectByWorktree(
      [main, orphan, live],
      [wt('/abs/brave/app', 'brave')],
    );

    expect(mainInstances.map((i) => i.id)).toEqual(['main', 'orphan']);
    expect(worktrees.map((w) => w.branch)).toEqual(['brave']);
    expect(worktrees[0].instances.map((i) => i.id)).toEqual(['live']);
  });

  it('orders worktrees by most-recent session, empty ones last', () => {
    const stale = make({ id: 'stale', worktree_name: 'aardvark', project: '~/a', ...at('2026-01-01T00:00:00.000Z') });
    const fresh = make({ id: 'fresh', worktree_name: 'zebra', project: '~/z', ...at('2026-01-09T00:00:00.000Z') });

    const { worktrees } = splitProjectByWorktree(
      [stale, fresh],
      [wt('/abs/a', 'aardvark'), wt('/abs/z', 'zebra'), wt('/abs/e', 'empty')],
    );

    expect(worktrees.map((w) => w.branch)).toEqual(['zebra', 'aardvark', 'empty']);
  });

  it('carries the managed flag from the git list', () => {
    const { worktrees } = splitProjectByWorktree(
      [],
      [wt('/abs/mine', 'mine', true), wt('/elsewhere/ext', 'ext', false)],
    );

    expect(worktrees.find((w) => w.branch === 'mine')?.managed).toBe(true);
    expect(worktrees.find((w) => w.branch === 'ext')?.managed).toBe(false);
  });

  describe('baseline (git list not loaded → null)', () => {
    it('groups by the sessions own worktree_name and treats none as orphaned', () => {
      const main = make({ id: 'main', project: '~/app' });
      const w = make({ id: 'w', project: '~/vicoa/workspaces/app-worktrees/brave/app', worktree_name: 'brave' });

      const { mainInstances, worktrees } = splitProjectByWorktree([main, w], null);

      expect(mainInstances.map((i) => i.id)).toEqual(['main']);
      expect(worktrees.map((x) => x.branch)).toEqual(['brave']);
      expect(worktrees[0].managed).toBe(true); // path under ~/vicoa/workspaces
      expect(worktrees[0].instances.map((i) => i.id)).toEqual(['w']);
    });
  });
});

describe('distinctProjectNames', () => {
  it('returns sorted unique last path parts, skipping null projects', () => {
    const list = [
      make({ id: '1', project: '/x/beta' }),
      make({ id: '2', project: '/y/alpha' }),
      make({ id: '3', project: '/z/beta' }),
      make({ id: '4', project: null }),
    ];
    expect(distinctProjectNames(list)).toEqual(['alpha', 'beta']);
  });
});

describe('distinctAgentNames', () => {
  it('returns sorted unique names, skipping nulls', () => {
    const list = [
      make({ id: '1', agent_type_name: 'Codex' }),
      make({ id: '2', agent_type_name: 'Claude Code' }),
      make({ id: '3', agent_type_name: 'Codex' }),
      make({ id: '4', agent_type_name: null }),
    ];
    expect(distinctAgentNames(list)).toEqual(['Claude Code', 'Codex']);
  });
});
