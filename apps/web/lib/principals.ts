/**
 * Principal identity helpers — the data half of `<PrincipalAvatar>`.
 *
 * Collaboration has three principals (user, team, agent) and they all render
 * the same way, so the fallback chain lives in one place: stored image →
 * initials on a deterministic palette color → a generic glyph. The palette and
 * hash are the ones project icons already use (`lib/project-icons.ts`), so a
 * principal and a project seeded from the same id get the same color.
 */

import { projectAvatarColor, projectInitial } from './project-icons';

export type PrincipalType = 'user' | 'team' | 'agent';

export type Principal = {
  type: PrincipalType;
  /** Stable id — seeds the fallback color and addresses the stored image. */
  id?: string | null;
  /**
   * Display name — the seed for initials and the default tooltip.
   *
   * On a shared or public surface this must be a display name and nothing
   * else: an email may never appear there (P0 privacy rule). In the signed-in
   * user's own chrome, falling back to their own email for an initial is fine
   * — it is already on screen next to the avatar.
   */
  name?: string | null;
  /** Backend-relative served URL (e.g. `users.avatar_image_uri`), or null. */
  avatarImageUri?: string | null;
  /**
   * A picked emoji, rendered when there is no image.
   *
   * Sits *between* the image and the generated initial rather than replacing
   * either: an uploaded photo still wins (it is the more specific choice), and
   * clearing the photo reveals an emoji picked earlier instead of discarding
   * it. Same role as `projects.icon`.
   */
  emoji?: string | null;
  /** Cache-buster — the row's `updated_at`; the avatar URL itself is stable. */
  updatedAt?: string | null;
};

/**
 * <img src> for a principal's stored avatar, or null (→ initials/glyph).
 *
 * Like project icons, an <img> can't send the backend bearer, so this points at
 * the web's own same-origin cookie-authed proxy rather than at the backend or —
 * never — at the identity provider's CDN.
 */
export function principalAvatarSrc(principal: Principal | null | undefined): string | null {
  if (!principal?.id || !principal.avatarImageUri) return null;
  if (principal.type === 'team') return null; // teams get images in P3
  const version = principal.updatedAt ? `?v=${encodeURIComponent(principal.updatedAt)}` : '';
  const base = principal.type === 'agent' ? 'agents' : 'users';
  return `/api/${base}/${principal.id}/avatar${version}`;
}

/**
 * Map the backend's `PrincipalResponse` onto the client shape.
 *
 * The two disagree on one field name — `avatar_image_uri` on the wire (it
 * mirrors the DB column) versus `avatarImageUri` here — and §8.1 asked whoever
 * shipped the first backend serializer to pick one and make the other follow
 * rather than let them drift. This is that one place; nothing else should be
 * hand-rolling the conversion.
 */
export function principalFromResponse(
  response: {
    type: 'user' | 'agent' | 'system';
    id: string | null;
    name: string | null;
    avatar_image_uri: string | null;
    emoji: string | null;
    updated_at: string | null;
  } | null
  | undefined,
): Principal | null {
  if (!response) return null;
  return {
    // 'system' is an actor, not a principal that can hold an avatar; it falls
    // back to the agent glyph, which is what an automated action reads as.
    type: response.type === 'system' ? 'agent' : response.type,
    id: response.id,
    name: response.name,
    avatarImageUri: response.avatar_image_uri,
    emoji: response.emoji,
    updatedAt: response.updated_at,
  };
}

/**
 * What to call a principal on screen.
 *
 * `users.display_name` is nullable and a lot of accounts have none (an
 * email/password signup carries no full name), so the raw name is often null
 * and "Unknown" is the wrong thing to show someone about themselves. The
 * backend deliberately does NOT fall back to the email — that serializer also
 * feeds shared and public surfaces, where §10.4 says an email may never appear.
 *
 * The viewer is the one principal whose email is already on screen in their own
 * chrome, so the fallback is resolved here, client-side, and only for them.
 */
export function principalDisplayName(
  principal: Principal | null | undefined,
  viewer?: Principal | null,
): string {
  const name = principal?.name?.trim();
  if (name) return name;
  if (viewer && principal?.id && principal.id === viewer.id) {
    const own = viewer.name?.trim();
    if (own) return own;
    return 'You';
  }
  return principal?.type === 'agent' ? 'Agent' : 'Unknown';
}

/**
 * The principal to hand `<PrincipalAvatar>`, with the viewer fallback applied.
 *
 * Separate from `principalDisplayName` because the avatar wants a *real* name or
 * nothing at all. A letter is a better fallback than the generic glyph — the
 * account menu already seeds one from the email when `display_name` is null, and
 * a row reading "test1@gmail.com" next to a featureless person icon is the same
 * identity rendered two different ways on one screen.
 *
 * But only when the name is real. Seeding a monogram from "You" would stamp a Y
 * on every author, and seeding one from "Deleted user" invents an identity mark
 * for someone who is not there. Those keep the glyph, which is the honest
 * rendering of "we don't know who this is".
 */
export function principalForAvatar(
  principal: Principal | null | undefined,
  viewer?: Principal | null,
): Principal {
  if (!principal) return { type: 'user' };
  if (principal.name?.trim()) return principal;
  const isViewer = !!viewer && !!principal.id && principal.id === viewer.id;
  const own = viewer?.name?.trim();
  return isViewer && own ? { ...principal, name: own } : principal;
}

/** Deterministic palette color for a principal (seeded by id, then name). */
export function principalColor(principal: Principal): string {
  return projectAvatarColor(principal.id || principal.name || principal.type);
}

/**
 * A principal's single initial — `null` when there is no name.
 *
 * One letter, not two: a monogram reads as a mark at any size, while "AL" in a
 * 24px circle is two shapes fighting for the same space and starts to look like
 * a label. Same rule the project icons already follow (`projectInitial`); the
 * wrapper exists because they render `·` for an empty name and this has to
 * return null so the caller can fall through to the glyph.
 */
export function principalInitial(name: string | null | undefined): string | null {
  const trimmed = (name ?? '').trim();
  return trimmed ? projectInitial(trimmed) : null;
}
