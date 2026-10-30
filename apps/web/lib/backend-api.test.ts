import { describe, expect, it } from 'vitest';

import { refusalReason, type BackendApiError } from './backend-api';

function apiError(status: number, detail?: string): BackendApiError {
  const message = detail ?? `Backend API error: ${status} Error`;
  return Object.assign(new Error(message), { status, detail });
}

describe('refusalReason', () => {
  it("passes on a 4xx's written reason", () => {
    expect(refusalReason(apiError(409, 'A project with that name already exists'))).toBe(
      'A project with that name already exists',
    );
  });

  it('drops a 4xx that only has the generic HTTP text', () => {
    expect(refusalReason(apiError(422))).toBeUndefined();
  });

  it('drops a server error, even one with a detail', () => {
    expect(refusalReason(apiError(500, 'Internal error'))).toBeUndefined();
  });

  it('drops a network failure', () => {
    expect(refusalReason(new TypeError('Failed to fetch'))).toBeUndefined();
    expect(refusalReason('nope')).toBeUndefined();
  });
});
