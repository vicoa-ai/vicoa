import { describe, expect, test } from 'vitest';
import { isReferenceHref, referenceHref } from './reference-links';

const id = '0f8fad5b-d9cb-469f-a165-70867728950e';

describe('referenceHref', () => {
  test('opens the page cmd+K opens for the same item', () => {
    expect(referenceHref('task', id)).toBe(`/dashboard/tasks/${id}`);
    expect(referenceHref('session', id)).toBe(`/dashboard/sessions/${id}`);
    expect(referenceHref('automation', id)).toBe(`/dashboard/automation?automation=${id}`);
  });

  test('is recognized by isReferenceHref, and nothing looser is', () => {
    for (const kind of ['task', 'session', 'automation'] as const) {
      expect(isReferenceHref(referenceHref(kind, id))).toBe(true);
    }
    expect(isReferenceHref('/dashboard/tasks/42')).toBe(false);
    expect(isReferenceHref(`https://vicoa.ai/dashboard/tasks/${id}`)).toBe(false);
    expect(isReferenceHref(`/dashboard/automation?automation=${id}&x=1`)).toBe(false);
  });
});
