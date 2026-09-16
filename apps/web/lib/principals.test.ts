import { describe, expect, it } from 'vitest';

import {
  principalAvatarSrc,
  principalColor,
  principalDisplayName,
  principalForAvatar,
  principalInitial,
} from './principals';
import { projectAvatarColor } from './project-icons';

describe('principalAvatarSrc', () => {
  it('points at the same-origin authed proxy, cache-busted by updated_at', () => {
    expect(
      principalAvatarSrc({
        type: 'user',
        id: 'u1',
        avatarImageUri: '/api/v1/users/u1/avatar',
        updatedAt: '2026-09-08T00:00:00+00:00',
      }),
    ).toBe('/api/users/u1/avatar?v=2026-09-08T00%3A00%3A00%2B00%3A00');
  });

  it('is null without a stored image, so the caller falls back to initials', () => {
    expect(principalAvatarSrc({ type: 'user', id: 'u1', avatarImageUri: null })).toBeNull();
    expect(principalAvatarSrc(null)).toBeNull();
  });

  it('never hot-links the identity provider even if the URI is absolute', () => {
    const src = principalAvatarSrc({
      type: 'user',
      id: 'u1',
      avatarImageUri: 'https://lh3.googleusercontent.com/a/x',
    });
    expect(src).toBe('/api/users/u1/avatar');
  });

  it('has no image for teams or agents yet (P1/P3)', () => {
    expect(
      principalAvatarSrc({ type: 'team', id: 't1', avatarImageUri: '/api/v1/users/t1/avatar' }),
    ).toBeNull();
  });
});

describe('principalColor', () => {
  it('is deterministic and shares the project-icon palette', () => {
    const principal = { type: 'user' as const, id: 'u1', name: 'Ada' };
    expect(principalColor(principal)).toBe(principalColor(principal));
    expect(principalColor(principal)).toBe(projectAvatarColor('u1'));
  });

  it('seeds by name when there is no id', () => {
    expect(principalColor({ type: 'team', name: 'Platform' })).toBe(
      projectAvatarColor('Platform'),
    );
  });
});

describe('principalInitial', () => {
  it('is one letter, whatever the name is made of', () => {
    expect(principalInitial('Ada Lovelace')).toBe('A');
    expect(principalInitial('  ada   lovelace  king ')).toBe('A');
    expect(principalInitial('ada')).toBe('A');
  });

  it('handles non-ASCII names by code point, not byte', () => {
    expect(principalInitial('Émile Borel')).toBe('É');
    expect(principalInitial('张伟')).toBe('张');
    // A surrogate pair must not be sliced in half into a replacement glyph.
    expect(principalInitial('🙂 nick')).toBe('🙂');
  });

  it('is null with no name, so the caller falls through to the glyph', () => {
    expect(principalInitial('')).toBeNull();
    expect(principalInitial('   ')).toBeNull();
    expect(principalInitial(null)).toBeNull();
  });
});

describe('principalDisplayName', () => {
  const viewer = { type: 'user' as const, id: 'u1', name: 'test1@gmail.com' };

  it('prefers the principal own name', () => {
    expect(principalDisplayName({ type: 'user', id: 'u2', name: 'Ada' }, viewer)).toBe('Ada');
  });

  it('falls back to the viewer own label for the viewer', () => {
    // display_name is null on plenty of accounts (an email/password signup
    // carries no full name). Showing the signed-in user "Unknown" about their
    // own comment is the bug this exists to prevent.
    expect(principalDisplayName({ type: 'user', id: 'u1', name: null }, viewer)).toBe(
      'test1@gmail.com',
    );
  });

  it('says You when even the viewer has no label', () => {
    expect(
      principalDisplayName({ type: 'user', id: 'u1', name: null }, { type: 'user', id: 'u1' }),
    ).toBe('You');
  });

  it('does not borrow the viewer label for someone else', () => {
    expect(principalDisplayName({ type: 'user', id: 'u2', name: null }, viewer)).toBe('Unknown');
  });

  it('names a nameless agent as an agent', () => {
    expect(principalDisplayName({ type: 'agent', id: 'a1', name: null }, viewer)).toBe('Agent');
  });
});

describe('principalForAvatar', () => {
  const viewer = { type: 'user' as const, id: 'u1', name: 'test1@gmail.com' };

  it('keeps a real name so the monogram is drawn', () => {
    const out = principalForAvatar({ type: 'user', id: 'u2', name: 'Ada' }, viewer);
    expect(out.name).toBe('Ada');
  });

  it('lends the viewer their own label', () => {
    // The account menu already seeds a letter from the email when display_name
    // is null; the timeline must not render the same person as a blank glyph.
    const out = principalForAvatar({ type: 'user', id: 'u1', name: null }, viewer);
    expect(out.name).toBe('test1@gmail.com');
  });

  it('leaves a nameless stranger nameless, so the glyph wins', () => {
    // "Unknown"/"Deleted user" must never become a monogram: a letter is an
    // identity mark, and there is no identity here to mark.
    const out = principalForAvatar({ type: 'user', id: 'u2', name: null }, viewer);
    expect(out.name).toBeNull();
  });

  it('does not invent a letter when the viewer has no label either', () => {
    const out = principalForAvatar(
      { type: 'user', id: 'u1', name: null },
      { type: 'user', id: 'u1' },
    );
    expect(out.name).toBeNull();
  });
});
