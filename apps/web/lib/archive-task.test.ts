import { describe, expect, it } from 'vitest';

import {
  ARCHIVE_TASK_ACTIONS,
  ARCHIVE_TASK_CHOICES,
  archiveChoiceStatus,
  archiveStatusBody,
  defaultArchiveChoice,
} from './archive-task';

describe('archiveStatusBody', () => {
  it('names no task choice when none was made, so the server follows the preference', () => {
    expect(archiveStatusBody()).toEqual({ status: 'COMPLETED' });
    expect('task_status' in archiveStatusBody()).toBe(false);
  });

  it('carries the choice, including leaving the task alone', () => {
    expect(archiveStatusBody('done')).toEqual({ status: 'COMPLETED', task_status: 'done' });
    expect(archiveStatusBody('no_change')).toEqual({
      status: 'COMPLETED',
      task_status: 'no_change',
    });
  });
});

describe('archive choices', () => {
  it('lists no change first and the statuses in board order', () => {
    expect(ARCHIVE_TASK_CHOICES).toEqual(['no_change', 'todo', 'in_progress', 'in_review', 'done']);
  });

  it('maps a choice to the status it sets, and no change to none', () => {
    expect(archiveChoiceStatus('no_change')).toBeNull();
    expect(archiveChoiceStatus('in_review')).toBe('in_review');
  });

  it('preselects what the server suggests', () => {
    expect(defaultArchiveChoice({ default: 'done' })).toBe('done');
    expect(defaultArchiveChoice({ default: 'no_change' })).toBe('no_change');
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
