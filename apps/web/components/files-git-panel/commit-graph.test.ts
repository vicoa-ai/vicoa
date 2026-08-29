import { describe, it, expect } from 'vitest';
import type { CommitEntry, CommitRef } from './rpc';
import {
  buildCommitViewModels,
  buildDefaultColorMap,
  getLaneIndex,
  getMergeParentLaneIndex,
  buildGraphRow,
} from './commit-graph';

function commit(id: string, parents: string[], refs: CommitRef[] = []): CommitEntry {
  return {
    id,
    short_id: id.slice(0, 7),
    parent_ids: parents,
    subject: id,
    body: '',
    author_name: 'T',
    author_email: 't@e',
    timestamp: 1,
    refs,
  };
}

describe('buildCommitViewModels', () => {
  it('keeps a linear branch in one lane with a stable color', () => {
    const commits = [
      commit('C', ['B'], [{ name: 'main', kind: 'branch' }]),
      commit('B', ['A']),
      commit('A', []),
    ];
    const current = { name: 'main', revision: 'C' };
    const vms = buildCommitViewModels(commits, buildDefaultColorMap(current), current);
    expect(vms.map((v) => v.kind)).toEqual(['HEAD', 'node', 'node']);
    expect(vms[0].outputSwimlanes).toEqual([{ id: 'B', color: 'git-graph-ref' }]);
    expect(vms[1].inputSwimlanes).toEqual([{ id: 'B', color: 'git-graph-ref' }]);
    expect(vms[1].outputSwimlanes).toEqual([{ id: 'A', color: 'git-graph-ref' }]);
  });

  it('allocates a new right lane for a merge parent', () => {
    const commits = [
      commit('M', ['A', 'B'], [{ name: 'feature', kind: 'branch' }]),
      commit('A', ['C']),
      commit('B', ['C']),
      commit('C', []),
    ];
    const current = { name: 'feature', revision: 'M' };
    const vms = buildCommitViewModels(commits, buildDefaultColorMap(current), current);
    expect(vms[0].outputSwimlanes).toEqual([
      { id: 'A', color: 'git-graph-ref' },
      { id: 'B', color: 'git-graph-lane-1' },
    ]);
    expect(getMergeParentLaneIndex(vms[0], 'B')).toBe(1);
  });

  it('node column is the first waiting input lane', () => {
    const commits = [commit('C', ['B']), commit('B', ['A']), commit('A', [])];
    const vms = buildCommitViewModels(commits, new Map(), { name: 'main', revision: 'C' });
    expect(getLaneIndex(vms[1])).toBe(0); // B waited in lane 0
  });
});

describe('buildGraphRow', () => {
  it('draws in/out stubs and one circle for a linear middle commit', () => {
    const commits = [commit('C', ['B']), commit('B', ['A']), commit('A', [])];
    const vms = buildCommitViewModels(commits, new Map(), { name: 'main', revision: 'C' });
    const row = buildGraphRow(vms[1]);
    expect(row.circles.length).toBe(1);
    expect(row.paths.some((p) => p.d.includes('V 12'))).toBe(true); // into-node stub
    expect(row.paths.some((p) => p.d.includes('V 24'))).toBe(true); // out-of-node stub
  });

  it('marks a merge commit with a donut (two circles)', () => {
    const commits = [commit('M', ['A', 'B']), commit('A', []), commit('B', [])];
    const vms = buildCommitViewModels(commits, new Map(), { name: 'x', revision: 'zzz' });
    const row = buildGraphRow(vms[0]);
    expect(row.circles.length).toBe(2); // donut = filled + bg hole
    expect(row.paths.some((p) => p.color === 'git-graph-lane-2')).toBe(true); // 2nd parent lane
  });
});
