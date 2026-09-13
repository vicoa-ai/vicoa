import { describe, expect, it } from 'vitest';
import type { AgentInstanceResponse, ProjectResponse } from '@/lib/backend-api';
import {
  distinctAgentNames,
  distinctProjects,
  filterWantsActiveOnly,
  getLastPathPart,
  groupSessions,
  projectGroupKey,
  splitProjectByWorktree,
  worktreeSessionPaths,
  type LiveWorktree,
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

const proj = (over: Partial<ProjectResponse> & { id: string }): ProjectResponse => ({
  name: over.id,
  key: null,
  git_remote_url: null,
  color: null,
  icon: null,
  icon_image_uri: null,
  icon_source: null,
  is_inbox: false,
  is_archived: false,
  archived_at: null,
  directories: [],
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-01-01T00:00:00.000Z',
  ...over,
});

const projectMap = (...ps: ProjectResponse[]) =>
  new Map(ps.map((p) => [p.id, p]));

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

describe('groupSessions archived projects', () => {
  it('drops archived projects, keeps no-project sessions and pinned ones', () => {
    const a = make({ id: 'a', project: '/x/alpha', project_id: 'PA' });
    const b = make({ id: 'b', project: '/x/beta', project_id: 'PB' });
    const none = make({ id: 'n', project: null });
    // Pinned sessions bypass filters (explicit "keep visible"), even if archived.
    const pinnedBeta = make({
      id: 'pinned-beta',
      project: '/x/beta',
      project_id: 'PB',
      pinned_at: '2026-01-01T00:00:00.000Z',
    });

    const map = projectMap(proj({ id: 'PA' }), proj({ id: 'PB', is_archived: true }));
    const groups = groupSessions([a, b, none, pinnedBeta], 'all', 'time', 'all', [], map);
    const ids = groups.flatMap((g) => g.instances.map((i) => i.id));
    expect(ids).toEqual(['pinned-beta', 'a', 'n']);
  });

  it('labels a project group with the DB name, not the path basename', () => {
    const a = make({ id: 'a', project: '/home/me/alpha', project_id: 'PA' });
    const map = projectMap(proj({ id: 'PA', name: 'Alpha Project' }));
    const groups = groupSessions([a], 'all', 'project', 'all', [], map);
    expect(groups.find((g) => g.key === 'PA')?.label).toBe('Alpha Project');
  });
});

describe('splitProjectByWorktree (git-driven)', () => {
  const at = (iso: string) => ({ latest_message_at: iso });
  const wt = (path: string, branch: string, managed = true, extra: Partial<LiveWorktree> = {}) =>
    ({ path, branch, managed, ...extra });

  it('separates main-checkout sessions from worktree sessions by folder', () => {
    const main = make({ id: 'main', project: '~/app', ...at('2026-01-04T00:00:00.000Z') });
    const a = make({ id: 'a', project: '~/vicoa/workspaces/app-worktrees/brave/app', worktree_name: 'brave', ...at('2026-01-03T00:00:00.000Z') });
    const b = make({ id: 'b', project: '~/vicoa/workspaces/app-worktrees/calm/app', worktree_name: 'calm', ...at('2026-01-02T00:00:00.000Z') });

    const { mainInstances, worktrees } = splitProjectByWorktree(
      [main, a, b],
      [
        wt('/home/u/vicoa/workspaces/app-worktrees/brave/app', 'brave', true, { display_path: '~/vicoa/workspaces/app-worktrees/brave/app' }),
        wt('/home/u/vicoa/workspaces/app-worktrees/calm/app', 'calm', true, { display_path: '~/vicoa/workspaces/app-worktrees/calm/app' }),
      ],
    );

    expect(mainInstances.map((i) => i.id)).toEqual(['main']);
    expect(worktrees.map((w) => w.branch)).toEqual(['brave', 'calm']);
    expect(worktrees.map((w) => w.instances.map((i) => i.id))).toEqual([['a'], ['b']]);
    expect(worktrees.every((w) => !w.missing)).toBe(true);
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
    expect(worktrees[0].missing).toBe(false);
  });

  it('prefers the home-collapsed display_path for a session-less worktree', () => {
    const { worktrees } = splitProjectByWorktree(
      [],
      [wt('/home/u/wt/app', 'empty', true, { display_path: '~/wt/app' })],
    );

    // The daemon expands `~` in every path RPC, and this is the form a session
    // started there will register — so the node's identity is stable over time.
    expect(worktrees[0].path).toBe('~/wt/app');
  });

  it('keeps a removed worktree session under its own node, flagged missing — never jumps to main', () => {
    const main = make({ id: 'main', project: '~/app', ...at('2026-01-05T00:00:00.000Z') });
    const orphan = make({ id: 'orphan', project: '~/gone/app', worktree_name: 'deleted', ...at('2026-01-04T00:00:00.000Z') });
    const live = make({ id: 'live', project: '~/live/app', worktree_name: 'brave', ...at('2026-01-03T00:00:00.000Z') });

    const { mainInstances, worktrees } = splitProjectByWorktree(
      [main, orphan, live],
      [wt('/home/u/live/app', 'brave', true, { display_path: '~/live/app' })], // git no longer lists `~/gone/app`
    );

    // The orphan does NOT fold into main; it keeps its own worktree node,
    // ordered by recency ahead of the still-live `brave`.
    expect(mainInstances.map((i) => i.id)).toEqual(['main']);
    expect(worktrees.map((w) => w.branch)).toEqual(['deleted', 'brave']);
    const deleted = worktrees.find((w) => w.branch === 'deleted');
    expect(deleted?.instances.map((i) => i.id)).toEqual(['orphan']);
    expect(deleted?.path).toBe('~/gone/app'); // path derived from the session cwd
    expect(deleted?.missing).toBe(true);
    expect(worktrees.find((w) => w.branch === 'brave')?.missing).toBe(false);
  });

  it('treats a prunable registration (folder gone, git entry left) as missing', () => {
    const s = make({ id: 's', project: '~/wt/app', worktree_name: 'featX' });

    const { worktrees } = splitProjectByWorktree(
      [s],
      [wt('/home/u/wt/app', 'featX', true, { display_path: '~/wt/app', prunable: true })],
    );

    expect(worktrees).toHaveLength(1);
    expect(worktrees[0].missing).toBe(true);
    expect(worktrees[0].instances.map((i) => i.id)).toEqual(['s']);
  });

  it('never flags missing without a git list', () => {
    const s = make({ id: 's', project: '~/gone/app', worktree_name: 'deleted' });

    const { worktrees } = splitProjectByWorktree([s], null);

    expect(worktrees[0].missing).toBe(false);
  });

  it('only calls a folder missing when the list was fetched knowing it', () => {
    // A "new worktree" session arrives right after the daemon created its
    // folder — the list on hand predates it, so it must not read as deleted.
    const fresh = make({ id: 'fresh', project: '~/wt/new/app', worktree_name: 'new' });
    const gone = make({ id: 'gone', project: '~/wt/old/app', worktree_name: 'old' });
    const judgeable = new Set(['~/wt/old/app']); // what the fetch was issued against

    const { worktrees } = splitProjectByWorktree([fresh, gone], [], judgeable);

    expect(worktrees.find((w) => w.branch === 'new')?.missing).toBe(false);
    expect(worktrees.find((w) => w.branch === 'old')?.missing).toBe(true);

    // Once refetched with the folder known (and still absent), it is judged.
    const later = splitProjectByWorktree([fresh, gone], [], new Set(['~/wt/new/app', '~/wt/old/app']));
    expect(later.worktrees.every((w) => w.missing)).toBe(true);
  });

  it('keeps a session in its folder when the worktree switched branches, relabelled live', () => {
    const s = make({ id: 's', project: '/abs/wt/app', worktree_name: 'featX', ...at('2026-01-02T00:00:00.000Z') });

    const { mainInstances, worktrees } = splitProjectByWorktree(
      [s],
      [wt('/abs/wt/app', 'featY')], // same folder, git now reports branch featY
    );

    expect(mainInstances).toEqual([]);
    // One node for the folder — the live branch is the label; no phantom
    // empty `featY` node alongside a `featX` one.
    expect(worktrees.map((w) => w.branch)).toEqual(['featY']);
    expect(worktrees[0].instances.map((i) => i.id)).toEqual(['s']);
    expect(worktrees[0].missing).toBe(false);
  });

  it('groups sessions started on different branches of one folder together', () => {
    // Session `old` started on the worktree's original branch; `new` after a
    // `git checkout -b` inside the same folder. Same folder → same group.
    const old = make({ id: 'old', project: '~/vicoa/workspaces/app-worktrees/mellow/app', worktree_name: 'mellow', ...at('2026-01-01T00:00:00.000Z') });
    const fresh = make({ id: 'new', project: '~/vicoa/workspaces/app-worktrees/mellow/app/', worktree_name: 'feat/steer', ...at('2026-01-02T00:00:00.000Z') });

    const withGit = splitProjectByWorktree(
      [fresh, old],
      [wt('/home/u/vicoa/workspaces/app-worktrees/mellow/app', 'feat/steer', true, { display_path: '~/vicoa/workspaces/app-worktrees/mellow/app' })],
    );
    expect(withGit.worktrees).toHaveLength(1);
    expect(withGit.worktrees[0].branch).toBe('feat/steer');
    expect(withGit.worktrees[0].instances.map((i) => i.id)).toEqual(['new', 'old']);

    // Without git the newest session's stored branch labels the folder.
    const withoutGit = splitProjectByWorktree([fresh, old], null);
    expect(withoutGit.worktrees).toHaveLength(1);
    expect(withoutGit.worktrees[0].branch).toBe('feat/steer');
    expect(withoutGit.worktrees[0].instances.map((i) => i.id)).toEqual(['new', 'old']);
  });

  it("hides an agent's own scratch worktree unless a session runs in it", () => {
    const inScratch = make({ id: 's', project: '~/app/.claude/worktrees/used', worktree_name: 'worktree-used' });

    const { worktrees } = splitProjectByWorktree(
      [inScratch],
      [
        wt('/home/u/app/.claude/worktrees/used', 'worktree-used', false, { display_path: '~/app/.claude/worktrees/used' }),
        wt('/home/u/app/.claude/worktrees/idle', 'worktree-idle', false, { display_path: '~/app/.claude/worktrees/idle' }),
      ],
    );

    expect(worktrees.map((w) => w.branch)).toEqual(['worktree-used']);
  });

  it('orders worktrees by most-recent session, empty ones last', () => {
    const stale = make({ id: 'stale', worktree_name: 'aardvark', project: '/abs/a', ...at('2026-01-01T00:00:00.000Z') });
    const fresh = make({ id: 'fresh', worktree_name: 'zebra', project: '/abs/z', ...at('2026-01-09T00:00:00.000Z') });

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
    it('groups by the sessions own folder, labelled by worktree_name; main-checkout sessions to main', () => {
      const main = make({ id: 'main', project: '~/app' });
      const w = make({ id: 'w', project: '~/vicoa/workspaces/app-worktrees/brave/app', worktree_name: 'brave' });

      const { mainInstances, worktrees } = splitProjectByWorktree([main, w], null);

      expect(mainInstances.map((i) => i.id)).toEqual(['main']);
      expect(worktrees.map((x) => x.branch)).toEqual(['brave']);
      expect(worktrees[0].path).toBe('~/vicoa/workspaces/app-worktrees/brave/app');
      expect(worktrees[0].managed).toBe(true); // path under ~/vicoa/workspaces
      expect(worktrees[0].instances.map((i) => i.id)).toEqual(['w']);
    });
  });
});

describe('worktreeSessionPaths', () => {
  it('lists the distinct worktree folders, normalized and sorted; main sessions excluded', () => {
    const instances = [
      make({ id: 'b', project: '~/wt/b/app/', worktree_name: 'b' }),
      make({ id: 'a1', project: '~/wt/a/app', worktree_name: 'a' }),
      make({ id: 'a2', project: '~/wt/a/app', worktree_name: 'feat/a2' }), // same folder
      make({ id: 'main', project: '~/app' }),
    ];

    expect(worktreeSessionPaths(instances)).toEqual(['~/wt/a/app', '~/wt/b/app']);
  });
});

describe('groupSessions by project_id', () => {
  it('merges different folder names sharing a project_id, splits shared basenames', () => {
    const laptop = make({ id: 'laptop', project: '/home/me/vicoa', project_id: 'P1' });
    const worktree = make({
      id: 'wt',
      project: '/tmp/ws/vicoa-worktrees/x/vicoa',
      project_id: 'P1',
      worktree_name: 'x',
    });
    // Same basename 'vicoa' but a DIFFERENT project → a separate group.
    const other = make({ id: 'other', project: '/work/vicoa', project_id: 'P2' });

    const groups = groupSessions([laptop, worktree, other], 'all', 'project');
    const p1 = groups.find((g) => g.key === 'P1');
    const p2 = groups.find((g) => g.key === 'P2');
    expect(p1?.instances.map((i) => i.id).sort()).toEqual(['laptop', 'wt']);
    expect(p2?.instances.map((i) => i.id)).toEqual(['other']);
    expect(p1?.label).toBe('vicoa'); // display stays the basename, not the id
  });

  it('drops an archived linked project by its project_id', () => {
    const a = make({ id: 'a', project: '/home/me/alpha', project_id: 'PA' });
    const b = make({ id: 'b', project: '/home/me/beta', project_id: 'PB' });

    const map = projectMap(proj({ id: 'PA', is_archived: true }), proj({ id: 'PB' }));
    const groups = groupSessions([a, b], 'all', 'project', 'all', [], map);
    const ids = groups.flatMap((g) => g.instances.map((i) => i.id));
    expect(ids).toEqual(['b']);
  });
});

describe('projectGroupKey', () => {
  it('prefers project_id, falls back to basename, then no-project sentinel', () => {
    expect(projectGroupKey(make({ project: '/x/alpha', project_id: 'P1' }))).toBe('P1');
    expect(projectGroupKey(make({ project: '/x/alpha' }))).toBe('alpha');
    expect(projectGroupKey(make({ project: null }))).toBe('__no_project__');
  });
});

describe('distinctProjects', () => {
  it('returns {key,label}: project_id when linked, basename otherwise; skips null', () => {
    const list = [
      make({ id: '1', project: '/x/beta' }),
      make({ id: '2', project: '/y/alpha' }),
      make({ id: '3', project: '/z/beta' }), // dup basename, no id → same 'beta' key
      make({ id: '4', project: '/w/gamma', project_id: 'G1' }),
      make({ id: '5', project: null }),
    ];
    expect(distinctProjects(list)).toEqual([
      { key: 'alpha', label: 'alpha' },
      { key: 'beta', label: 'beta' },
      { key: 'G1', label: 'gamma' },
    ]);
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
