import { describe, expect, it, vi } from 'vitest';

import type { AgentInstanceResponse, TaskResponse, TaskStatus } from './backend-api';
import {
  ARCHIVE_TASK_ACTIONS,
  ARCHIVE_TASK_CHOICES,
  applyStandingAnswerToTasks,
  archiveChoiceStatus,
  countOtherOpenSessions,
  defaultArchiveChoice,
  loadArchiveTaskContext,
  standingTaskStatus,
} from './archive-task';

function task(id: string, status: TaskStatus): TaskResponse {
  return { id, status, identifier: null, title: id } as TaskResponse;
}

function session(id: string, status: AgentInstanceResponse['status']) {
  return { id, status } as AgentInstanceResponse;
}

/** A task API over fixed tasks and their sessions, recording each update. */
function fakeApi(
  tasks: Record<string, TaskStatus>,
  sessions: Record<string, AgentInstanceResponse[]> = {},
) {
  const updateTask = vi.fn(async (id: string, data: { status?: TaskStatus }) =>
    task(id, data.status ?? tasks[id]),
  );
  return {
    getTask: vi.fn(async (id: string) => task(id, tasks[id])),
    listTaskSessions: vi.fn(async (id: string) => sessions[id] ?? []),
    updateTask,
  };
}

describe('archive choices', () => {
  it('lists no change first and the statuses in board order', () => {
    expect(ARCHIVE_TASK_CHOICES).toEqual(['no_change', 'todo', 'in_progress', 'in_review', 'done']);
  });

  it('maps a choice to the status it sets, and no change to none', () => {
    expect(archiveChoiceStatus('no_change')).toBeNull();
    expect(archiveChoiceStatus('in_review')).toBe('in_review');
  });

  it('preselects done for the last open session, no change while another is open', () => {
    expect(defaultArchiveChoice({ otherOpenSessions: 0 })).toBe('done');
    expect(defaultArchiveChoice({ otherOpenSessions: 2 })).toBe('no_change');
  });
});

describe('countOtherOpenSessions', () => {
  it('counts sessions still running or waiting, leaving out the ones being archived', () => {
    const sessions = [
      session('a', 'ACTIVE'),
      session('b', 'AWAITING_INPUT'),
      session('c', 'PAUSED'),
      session('d', 'REVIEWED'),
      session('e', 'COMPLETED'),
      session('f', 'FAILED'),
    ];
    expect(countOtherOpenSessions(sessions, ['a'])).toBe(2);
    expect(countOtherOpenSessions(sessions, ['a', 'b', 'c'])).toBe(0);
  });
});

describe('loadArchiveTaskContext', () => {
  it.each<TaskStatus>(['in_progress', 'in_review'])('offers to move a task that is %s', async (status) => {
    const api = fakeApi({ t: status }, { t: [session('s', 'ACTIVE'), session('o', 'AWAITING_INPUT')] });
    const context = await loadArchiveTaskContext(api, 't', ['s']);
    expect(context?.task.status).toBe(status);
    expect(context?.otherOpenSessions).toBe(1);
  });

  it.each<TaskStatus>(['backlog', 'todo', 'blocked', 'done', 'cancelled'])(
    'leaves a task that is %s without asking',
    async (status) => {
      expect(await loadArchiveTaskContext(fakeApi({ t: status }), 't', ['s'])).toBeNull();
    },
  );
});

describe('standingTaskStatus', () => {
  const last = { task: task('t', 'in_progress'), otherOpenSessions: 0 };
  const shared = { task: task('t', 'in_progress'), otherOpenSessions: 1 };

  it('marks done only for mark_done on the last open session', () => {
    expect(standingTaskStatus('mark_done', last)).toBe('done');
    expect(standingTaskStatus('mark_done', shared)).toBeNull();
    expect(standingTaskStatus('mark_done', null)).toBeNull();
  });

  it('does nothing without asking for ask or leave', () => {
    expect(standingTaskStatus('ask', last)).toBeNull();
    expect(standingTaskStatus('leave', last)).toBeNull();
  });
});

describe('applyStandingAnswerToTasks', () => {
  it('does nothing unless the answer is mark_done', async () => {
    for (const action of ['ask', 'leave'] as const) {
      const api = fakeApi({ t: 'in_progress' });
      expect(await applyStandingAnswerToTasks(api, [{ id: 's', task_id: 't' }], action)).toEqual([]);
      expect(api.getTask).not.toHaveBeenCalled();
      expect(api.updateTask).not.toHaveBeenCalled();
    }
  });

  it('marks each task done once when all its open sessions were in the batch', async () => {
    const api = fakeApi(
      { t: 'in_progress', u: 'in_progress' },
      {
        t: [session('a', 'ACTIVE'), session('b', 'AWAITING_INPUT')],
        u: [session('c', 'ACTIVE'), session('elsewhere', 'ACTIVE')],
      },
    );
    const failed = await applyStandingAnswerToTasks(
      api,
      [
        { id: 'a', task_id: 't' },
        { id: 'b', task_id: 't' },
        { id: 'c', task_id: 'u' },
        { id: 'd', task_id: null },
      ],
      'mark_done',
    );
    expect(failed).toEqual([]);
    expect(api.updateTask).toHaveBeenCalledTimes(1);
    expect(api.updateTask).toHaveBeenCalledWith('t', { status: 'done' });
  });

  it('leaves a task that is not under way, and reports the ones it could not update', async () => {
    const api = fakeApi({ t: 'blocked', u: 'in_review' });
    api.updateTask.mockRejectedValueOnce(new Error('403'));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const failed = await applyStandingAnswerToTasks(
      api,
      [
        { id: 'a', task_id: 't' },
        { id: 'b', task_id: 'u' },
      ],
      'mark_done',
    );
    expect(api.updateTask).toHaveBeenCalledTimes(1);
    expect(api.updateTask).toHaveBeenCalledWith('u', { status: 'done' });
    expect(failed).toEqual(['u']);
  });
});

describe('archive preference options', () => {
  it('offers ask, mark done and leave, in that order, with no em or en dashes', () => {
    expect(ARCHIVE_TASK_ACTIONS.map((option) => option.value)).toEqual(['ask', 'mark_done', 'leave']);
    for (const option of ARCHIVE_TASK_ACTIONS) {
      expect(`${option.label}${option.description}`).not.toMatch(/[–—]/);
    }
  });
});
