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
  if (principal.type !== 'user') return null; // teams/agents get images in P3/P1
  const version = principal.updatedAt ? `?v=${encodeURIComponent(principal.updatedAt)}` : '';
  return `/api/users/${principal.id}/avatar${version}`;
}

/** Deterministic palette color for a principal (seeded by id, then name). */
export function principalColor(principal: Principal): string {
  return projectAvatarColor(principal.id || principal.name || principal.type);
}

/** Up to two initials from a display name — `null` when there is no name. */
export function principalInitials(name: string | null | undefined): string | null {
  const trimmed = (name ?? '').trim();
  if (!trimmed) return null;
  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (projectInitial(words[0]) + projectInitial(words[1])).slice(0, 2);
  }
  return projectInitial(trimmed);
}
