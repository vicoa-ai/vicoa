import { describe, expect, it } from 'vitest';

import type { ShareLinkResponse, ShareProjectFilters, ShareScope } from '@/lib/backend-api';
import {
  buildShareFilters,
  filterFieldsFromLink,
  formDiffersFromLink,
  KEEP_EXPIRY,
  linkSettingsKey,
  settingsKey,
} from '@/lib/share-link-settings';

/**
 * The share dialog's settings have no Save button: a change to the form *is*
 * the request, fired on the difference between the form and the link. So the
 * property under test is that a form seeded from a link differs from it in
 * nothing — the panel would otherwise save, re-seed, and save again forever.
 */
function link(over: Partial<ShareLinkResponse> = {}): ShareLinkResponse {
  return {
    id: 'link-1',
    token: 'tok',
    kind: 'project',
    agent_instance_id: null,
    project_id: 'proj-1',
    scopes: ['tasks'],
    audience: 'public',
    filters: null,
    allow_comments: false,
    show_owner: false,
    show_branch: false,
    expires_at: null,
    revoked_at: null,
    last_accessed_at: null,
    view_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    created_by: null,
    ...over,
  };
}

/** Seed the form from a link, the way the panel's `seedForm` does. */
function seed(from: ShareLinkResponse) {
  const fields = filterFieldsFromLink(from);
  return {
    settings: {
      audience: from.audience,
      allow_comments: from.allow_comments,
      show_owner: from.show_owner,
      show_branch: from.show_branch,
      scopes: from.scopes,
      filters: buildShareFilters({ ...fields, scopes: from.scopes }),
    },
    expiry: from.expires_at ? KEEP_EXPIRY : 'never',
  };
}

describe('a form seeded from a link differs from it in nothing', () => {
  const cases: [string, ShareLinkResponse][] = [
    ['a bare session link', link({ kind: 'session', scopes: [], project_id: null, agent_instance_id: 'a-1' })],
    ['every switch on', link({ scopes: ['tasks', 'sessions'], audience: 'authenticated', allow_comments: true, show_owner: true, show_branch: true })],
    ['a link that expires', link({ expires_at: '2026-03-03T12:00:00Z' })],
    [
      'task filters',
      link({ filters: { tasks: { statuses: ['todo', 'done'], label_ids: ['l-2', 'l-1'] } } }),
    ],
    [
      'session filters',
      link({
        scopes: ['sessions'],
        filters: {
          sessions: {
            statuses: ['ACTIVE', 'COMPLETED'],
            date_from: '2026-02-01T00:00:00Z',
            date_to: '2026-02-28T23:59:59Z',
          },
        },
      }),
    ],
  ];

  for (const [name, row] of cases) {
    it(name, () => {
      const { settings, expiry } = seed(row);
      expect(formDiffersFromLink(row, settings, expiry)).toBe(false);
    });
  }
});

describe('settingsKey', () => {
  it('ignores the order a filter list happens to be in', () => {
    const a: ShareProjectFilters = { tasks: { statuses: ['todo', 'done'], label_ids: ['l-1', 'l-2'] } };
    const b: ShareProjectFilters = { tasks: { statuses: ['done', 'todo'], label_ids: ['l-2', 'l-1'] } };
    expect(linkSettingsKey(link({ filters: a }))).toBe(linkSettingsKey(link({ filters: b })));
  });

  it('ignores the half of a filter the link does not carry', () => {
    // The server trims filters to the scopes the link carries, so what comes
    // back need not be what was sent — and that is not a change either.
    const sent = buildShareFilters({
      scopes: ['tasks'],
      statuses: ['todo'],
      labelIds: [],
      includeArchived: true,
      dateFrom: '2026-02-01',
      dateTo: '',
    });
    expect(sent).toEqual({ tasks: { statuses: ['todo'] } });
  });

  it('compares a deadline by day, not by timestamp', () => {
    const stored = link({
      scopes: ['sessions'],
      filters: { sessions: { date_from: '2026-02-01T00:00:00+00:00' } },
    });
    const { settings, expiry } = seed(stored);
    // The form rebuilds the same day as `…T00:00:00Z`; a serializer that spells
    // the same instant differently must not read as an edit.
    expect(formDiffersFromLink(stored, settings, expiry)).toBe(false);
  });

  it('sees a real change', () => {
    const stored = link({ scopes: ['tasks'] });
    const { settings, expiry } = seed(stored);
    expect(formDiffersFromLink(stored, { ...settings, audience: 'authenticated' }, expiry)).toBe(true);
    expect(formDiffersFromLink(stored, { ...settings, scopes: ['tasks', 'sessions'] as ShareScope[] }, expiry)).toBe(
      true,
    );
    expect(formDiffersFromLink(stored, settings, '7')).toBe(true);
  });

  it('reads "keep" on a link that expires as no change, and "never" as one', () => {
    const expiring = link({ expires_at: '2026-03-03T12:00:00Z' });
    const { settings } = seed(expiring);
    expect(formDiffersFromLink(expiring, settings, KEEP_EXPIRY)).toBe(false);
    expect(formDiffersFromLink(expiring, settings, 'never')).toBe(true);
  });
});
