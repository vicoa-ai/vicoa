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
 * not fit it. One shape, one hover state, everywhere. The one opt-out is
 * `plain`, which drops the disc for rows that sit beside bare provider glyphs.
 *
 * Nothing else should render an avatar `<img>`: hot-linking an identity
 * provider's CDN leaks a viewer's IP to it, and hashed-email services like
 * avatar.vercel.sh / gravatar put an email on the wire. On a shared or public
 * surface a principal may show a display name and a picture, never an email —
 * see the `name` prop on `Principal`.
 */

import { useEffect, useState } from 'react';
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

// `plain` marks are sized like the icons they sit beside — at `xs`, a 12px
// provider glyph in a 16px text row: the slot is as tall as the disc would be
// (`line` is that height as a line-height, see the prop) but only as wide as
// the icon, so the label after a plain mark starts where it does after an
// icon, and the mark's left edge sits on the same column.
const PLAIN: Record<
  PrincipalAvatarSize,
  { box: string; line: string; image: string; glyph: string }
> = {
  xs: { box: 'h-4 w-3', line: 'leading-4', image: 'size-3', glyph: 'size-3' },
  sm: { box: 'h-6 w-4', line: 'leading-6', image: 'size-4', glyph: 'size-4' },
  md: { box: 'h-8 w-5', line: 'leading-8', image: 'size-5', glyph: 'size-5' },
  lg: { box: 'h-14 w-7', line: 'leading-14', image: 'size-7', glyph: 'size-7' },
  xl: { box: 'h-20 w-9', line: 'leading-20', image: 'size-9', glyph: 'size-9' },
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
  plain = false,
}: {
  principal: Principal;
  size?: PrincipalAvatarSize;
  className?: string;
  /** Tooltip text. Defaults to `principal.name`. */
  title?: string;
  /**
   * No disc: the mark sits directly on the row, the way a provider glyph does,
   * at the icon's size (`PLAIN`). For a list that mixes saved agents with bare
   * provider icons (the agent picker), a disc on every other row is the odd
   * one out. A stored image keeps its circular clip — a picture needs a
   * shape, a glyph does not.
   *
   * A plain emoji or initial is typeset like the text beside it — inherited
   * font size, line-height equal to the box — so it sits on the same baseline
   * as that text, which is the alignment emoji fonts are drawn for. Centring
   * a smaller glyph in the box instead (the disc's recipe) leaves an emoji
   * visibly high: its ink is not centred on its own em box.
   */
  plain?: boolean;
}) {
  const dims = SIZES[size];
  const flat = PLAIN[size];
  const box = cn('shrink-0', plain ? flat.box : dims.box, className);
  const disc = cn('shrink-0 overflow-hidden rounded-full', plain ? flat.image : dims.box, className);
  const label = title ?? principal.name ?? undefined;

  const src = principalAvatarSrc(principal);
  // The image rides the cookie-authed proxy, which a public share page's
  // anonymous visitor cannot use (401) — and any image can 404 after a
  // replacement. Either way the next rung of the chain is the right answer,
  // not a broken-image glyph. Reset when the src changes so a fixed image
  // gets another chance.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  useEffect(() => {
    setFailedSrc(null);
  }, [src]);
  if (src && failedSrc !== src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- authed proxy stream, not a static asset
      <img
        src={src}
        alt=""
        aria-hidden="true"
        title={label}
        className={cn('object-cover', disc)}
        onError={() => setFailedSrc(src)}
      />
    );
  }

  // On `bg-muted`, not the hash-palette colour the initial uses: an emoji already
  // carries its own colour, and a saturated disc behind it puts two hues in the
  // same 24px circle. Same neutral the glyph fallback sits on.
  // Plain: flush left, not centred. An emoji glyph's advance box is wider than
  // its ink (Apple Color Emoji carries a right-side bearing) and wider than
  // the slot, so centring it hangs the ink over the column's left edge by a
  // pixel or so; starting it at the edge lines it up with the icon column.
  if (principal.emoji) {
    return (
      <span
        title={label}
        aria-hidden="true"
        className={cn(
          'inline-flex items-center',
          plain
            ? cn('justify-start', flat.line, box)
            : cn('justify-center bg-muted leading-none', dims.emoji, disc),
        )}
      >
        {principal.emoji}
      </span>
    );
  }

  // A principal with no id is a placeholder, not a person — "Owner" on a public
  // page whose link hides the owner, "Deleted user" — and a monogram would
  // invent an identity mark for it. Those get the glyph (`principalForAvatar`
  // makes the same call for a name-less viewer).
  const initial = principal.id ? principalInitial(principal.name) : null;
  if (initial) {
    // Without a disc the letter is the whole mark, so it takes the palette
    // colour itself, and the 0.25-0.30 ratio above no longer applies: that is
    // about fitting inside a circle, and there is no circle to fit.
    return (
      <span
        title={label}
        aria-hidden="true"
        style={plain ? { color: principalColor(principal) } : { backgroundColor: principalColor(principal) }}
        className={cn(
          'inline-flex items-center justify-center uppercase',
          plain
            ? cn('font-semibold', flat.line, box)
            : cn('font-normal leading-none text-white', dims.text, disc),
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
      className={cn(
        'inline-flex items-center justify-center text-muted-foreground',
        plain ? box : cn('bg-muted', disc),
      )}
    >
      <Glyph className={plain ? flat.glyph : dims.glyph} />
    </span>
  );
}
