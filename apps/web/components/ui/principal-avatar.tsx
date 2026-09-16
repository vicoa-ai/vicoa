'use client';

/**
 * PrincipalAvatar — the ONE way an identity is drawn (collaboration P0).
 *
 * Three principal types (user, team, agent) share one component and one
 * fallback chain, so a person looks the same in the sidebar, on a task, in a
 * share dialog and on a public share page:
 *
 *   1. the stored image, served from our own storage through the authed proxy;
 *   2. a picked emoji, on the same hash-palette color;
 *   3. initials on the deterministic paseo hash-palette color (`lib/principals`);
 *   4. a generic per-type glyph, when there is no name to make initials from.
 *
 * Every principal is a circle. An agent used to be a rounded square ("it is a
 * thing, not a face"), but the distinction cost more than it bought: every
 * editor affordance drawn on top of an avatar (the hover scrim, the camera
 * badge) is round, so a square agent avatar hovered into a grey circle that did
 * not fit it. One shape, one hover state, everywhere.
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
  principalInitial,
} from '@/lib/principals';

export type PrincipalAvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

// Box size, plus the type size the initial needs to sit right inside it.
// The letter runs ~0.25-0.30 of the box (it climbs at the small end only
// because 16px has a legibility floor): a monogram wants to read as a mark
// inside the circle, not fill it. Keep the Flutter twin's table in step.
// An emoji is a picture, not a letter: it reads at roughly twice the type size a
// monogram wants, so it gets its own column rather than reusing `text`.
const SIZES: Record<
  PrincipalAvatarSize,
  { box: string; text: string; emoji: string; glyph: string }
> = {
  xs: { box: 'size-4', text: 'text-[8px]', emoji: 'text-[10px]', glyph: 'size-2.5' },
  sm: { box: 'size-6', text: 'text-[9px]', emoji: 'text-sm', glyph: 'size-3.5' },
  md: { box: 'size-8', text: 'text-[11px]', emoji: 'text-lg', glyph: 'size-4' },
  lg: { box: 'size-14', text: 'text-base', emoji: 'text-3xl', glyph: 'size-7' },
  // Profile pages, where the avatar is the page's subject rather than a label.
  xl: { box: 'size-20', text: 'text-xl', emoji: 'text-5xl', glyph: 'size-9' },
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
  const box = cn('shrink-0 overflow-hidden rounded-full', dims.box, className);
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

  // On `bg-muted`, not the hash-palette colour the initial uses: an emoji already
  // carries its own colour, and a saturated disc behind it puts two hues in the
  // same 24px circle. Same neutral the glyph fallback sits on.
  if (principal.emoji) {
    return (
      <span
        title={label}
        aria-hidden="true"
        className={cn(
          'inline-flex items-center justify-center bg-muted leading-none',
          dims.emoji,
          box,
        )}
      >
        {principal.emoji}
      </span>
    );
  }

  const initial = principalInitial(principal.name);
  if (initial) {
    return (
      <span
        title={label}
        aria-hidden="true"
        style={{ backgroundColor: principalColor(principal) }}
        className={cn(
          'inline-flex items-center justify-center font-normal leading-none text-white uppercase',
          dims.text,
          box,
        )}
      >
        {initial}
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
