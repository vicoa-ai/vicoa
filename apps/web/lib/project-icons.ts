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

// Generated fallback — an initial-square filled with one of a fixed palette,
// picked by a stable hash of the project's identity. The palette is paseo's
// `IDENTITY_COLORS` (packages/app/src/styles/identity-colors.ts): muted,
// low-chroma tones tuned to one 4.2–4.8:1 contrast band against a white letter,
// so the color *identifies* a project without shouting. Deterministic → a
// project keeps its color across sessions and devices.
export const PROJECT_AVATAR_PALETTE = [
  '#7a6aa8', // violet
  '#3d7ea6', // sky
  '#388068', // emerald
  '#a4673a', // orange
  '#b05c80', // pink
  '#6a70b8', // indigo
  '#368080', // teal
  '#b06260', // red
  '#8f7838', // amber
  '#5179b0', // blue
] as const;

// paseo's hashIdentityKey (hash*31 + charCode, unsigned) so the mapping matches.
function hashString(seed: string): number {
  let hash = 0;
  for (const character of seed) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }
  return hash;
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
