import type { ProjectResponse } from './backend-api';

/**
 * Project image-icon helpers (project-identity-unification §5d).
 *
 * The DB stores a backend-relative `icon_image_uri`, but an <img> can't send the
 * backend bearer, so the web renders through its own same-origin, cookie-authed
 * proxy (`/api/projects/{id}/icon`, mirroring attachments). The served bytes sit
 * behind a stable URL, so we cache-bust with the project's `updated_at`.
 */

type IconProject = Pick<ProjectResponse, 'id'> & {
  icon_image_uri?: string | null;
  updated_at?: string;
};

/** <img src> for a project's uploaded/seeded image, or null (→ emoji/generated). */
export function projectIconSrc(project: IconProject | null | undefined): string | null {
  if (!project?.icon_image_uri) return null;
  const version = project.updated_at ? `?v=${encodeURIComponent(project.updated_at)}` : '';
  return `/api/projects/${project.id}/icon${version}`;
}

// Generated fallback — a paseo-style initial-square: a stable hash of the
// project's identity picks one of a fixed, theme-friendly palette. Deterministic
// so a project keeps the same color across sessions and devices.
export const PROJECT_AVATAR_PALETTE = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#14b8a6', // teal
  '#3b82f6', // blue
  '#6366f1', // indigo
  '#a855f7', // purple
  '#ec4899', // pink
  '#64748b', // slate
] as const;

function hashString(seed: string): number {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0; // 32-bit
  }
  return Math.abs(hash);
}

/** Deterministic palette color for a project (seeded by id, then name). */
export function projectAvatarColor(seed: string): string {
  return PROJECT_AVATAR_PALETTE[hashString(seed) % PROJECT_AVATAR_PALETTE.length];
}

/** First visible character of a name, uppercased (a project's generated initial). */
export function projectInitial(name: string | null | undefined): string {
  const trimmed = (name ?? '').trim();
  return trimmed ? Array.from(trimmed)[0].toUpperCase() : '·';
}
