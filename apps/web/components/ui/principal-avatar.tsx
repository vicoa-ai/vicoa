'use client';

/**
 * PrincipalAvatar — the ONE way an identity is drawn (collaboration P0).
 *
 * Three principal types (user, team, agent) share one component and one
 * fallback chain, so a person looks the same in the sidebar, on a task, in a
 * share dialog and on a public share page:
 *
 *   1. the stored image, served from our own storage through the authed proxy;
 *   2. initials on the deterministic paseo hash-palette color (`lib/principals`);
 *   3. a generic per-type glyph, when there is no name to make initials from.
 *
 * Nothing else should render an avatar `<img>`: hot-linking an identity
 * provider's CDN leaks a viewer's IP to it, and hashed-email services like
 * avatar.vercel.sh / gravatar put an email on the wire. On a shared or public
 * surface a principal may show a display name and a picture, never an email —
 * see the `name` prop on `Principal`.
 */

import { Bot, User as UserIcon, Users } from 'lucide-react';

import { cn } from '@/lib/utils';
import {
  type Principal,
  type PrincipalType,
  principalAvatarSrc,
  principalColor,
  principalInitials,
} from '@/lib/principals';

export type PrincipalAvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

// Box size, plus the type size the initials need to sit right inside it.
const SIZES: Record<PrincipalAvatarSize, { box: string; text: string; glyph: string }> = {
  xs: { box: 'size-4', text: 'text-[8px]', glyph: 'size-2.5' },
  sm: { box: 'size-6', text: 'text-[10px]', glyph: 'size-3.5' },
  md: { box: 'size-8', text: 'text-xs', glyph: 'size-4' },
  lg: { box: 'size-14', text: 'text-lg', glyph: 'size-7' },
  // Profile pages, where the avatar is the page's subject rather than a label.
  xl: { box: 'size-20', text: 'text-2xl', glyph: 'size-9' },
};

// A team is a bag of people; an agent is not a person at all. Only the user
// falls back to the single-person glyph.
const GLYPHS: Record<PrincipalType, typeof UserIcon> = {
  user: UserIcon,
  team: Users,
  agent: Bot,
};

export function PrincipalAvatar({
  principal,
  size = 'md',
  className,
  title,
}: {
  principal: Principal;
  size?: PrincipalAvatarSize;
  className?: string;
  /** Tooltip text. Defaults to `principal.name`. */
  title?: string;
}) {
  const dims = SIZES[size];
  // Agents are square-ish (they are a thing, not a face); people and teams are round.
  const shape = principal.type === 'agent' ? 'rounded-md' : 'rounded-full';
  const box = cn('shrink-0 overflow-hidden', dims.box, shape, className);
  const label = title ?? principal.name ?? undefined;

  const src = principalAvatarSrc(principal);
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- authed proxy stream, not a static asset
      <img
        src={src}
        alt=""
        aria-hidden="true"
        title={label}
        className={cn('object-cover', box)}
      />
    );
  }

  const initials = principalInitials(principal.name);
  if (initials) {
    return (
      <span
        title={label}
        aria-hidden="true"
        style={{ backgroundColor: principalColor(principal) }}
        className={cn(
          'inline-flex items-center justify-center font-semibold leading-none text-white uppercase',
          dims.text,
          box,
        )}
      >
        {initials}
      </span>
    );
  }

  const Glyph = GLYPHS[principal.type];
  return (
    <span
      title={label}
      aria-hidden="true"
      className={cn('inline-flex items-center justify-center bg-muted text-muted-foreground', box)}
    >
      <Glyph className={dims.glyph} />
    </span>
  );
}
