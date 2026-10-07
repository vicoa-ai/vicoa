import { describe, expect, it } from 'vitest';
import type { InstanceBody } from '@/lib/ws-client';
import { bodyToInstancePatch } from './use-ws-stream';

function body(extra: Partial<InstanceBody> = {}): InstanceBody {
  return {
    t: 'instance-update',
    id: 's-1',
    user_agent_id: 'a-1',
    status: 'ACTIVE',
    name: null,
    project: '~/src/app',
    home_dir: '/Users/t',
    started_at: null,
    ended_at: null,
    last_heartbeat_at: null,
    instance_metadata: null,
    has_git_changes: false,
    updated_at: '2026-10-07T00:00:00Z',
    ...extra,
  };
}

describe('bodyToInstancePatch — project_id', () => {
  it('carries the project a session was filed under, so the row regroups live', () => {
    expect(bodyToInstancePatch(body({ project_id: 'p-2' })).project_id).toBe('p-2');
  });

  it('carries an explicit null (moved to No project)', () => {
    const patch = bodyToInstancePatch(body({ project_id: null }));
    expect('project_id' in patch).toBe(true);
    expect(patch.project_id).toBeNull();
  });

  it("leaves the row's project alone when an older server sends none", () => {
    expect('project_id' in bodyToInstancePatch(body())).toBe(false);
  });
});
