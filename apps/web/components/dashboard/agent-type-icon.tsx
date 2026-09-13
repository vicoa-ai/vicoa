import Image from 'next/image';
import { MessageCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { acpIconSrc } from '@/lib/acp-provider-icons';
import { projectAvatarColor, projectInitial } from '@/lib/project-icons';
import { CLOSED_STATUSES } from '@/components/dashboard/session-grouping';

// Brand-mark treatment, per logo. The marks were authored for the old
// always-dark UI, so several need theme-aware handling now that a light theme
// exists (all applied only when `whiteForOpenAI`, i.e. on the themed surfaces):
//   • `isOpenAI` — a monochrome dark glyph (currentColor → black). Inverts to
//     white on a DARK theme; stays dark (legible) on light. (Codex, Cursor, Copilot)
//   • `invertForLight` — a two-tone mark built for dark (near-white outer): invert
//     it on LIGHT so the outer goes dark, leave it untouched on dark. (OpenCode)
//   • `darkPlate` — a white-on-transparent mark that vanishes on light: sit it on a
//     dark rounded plate (only where needed; transparent on dark). (Kimi)
//   • `boxedWhite` — a dark glyph we'd rather not invert: a white rounded chip. (Hermes)
const AGENT_LOGOS: {
  match: string;
  src: string;
  alt: string;
  isOpenAI?: boolean;
  invertForLight?: boolean;
  darkPlate?: boolean;
  boxedWhite?: boolean;
}[] = [
  { match: 'claude',    src: '/images/integrations/claude-color.svg',  alt: 'Claude' },
  { match: 'codex',     src: '/images/integrations/openai.svg',        alt: 'Codex', isOpenAI: true },
  { match: 'opencode',  src: '/images/integrations/opencode.svg',      alt: 'OpenCode', invertForLight: true },
  { match: 'cursor',    src: '/images/integrations/cursor.svg',        alt: 'Cursor', isOpenAI: true },
  { match: 'gemini',    src: '/images/integrations/gemini-color.svg',  alt: 'Gemini' },
  { match: 'copilot',   src: '/images/integrations/githubcopilot.svg', alt: 'Copilot', isOpenAI: true },
  { match: 'kimi',      src: '/images/integrations/kimi-color.svg',    alt: 'Kimi', darkPlate: true },
  { match: 'hermes',    src: '/images/integrations/hermes.svg',        alt: 'Hermes', boxedWhite: true },
  // ORDER MATTERS BELOW. Matching is `name.includes(match)` over this array
  // in order, and 'pi' is a substring of 'copilot' — so a bare 'pi' entry
  // placed any earlier would swallow Copilot (and anything else containing
  // those two letters). Keep 'omp' / 'oh my pi' ahead of it, 'pi' LAST.
  { match: 'oh my pi',  src: '/images/integrations/omp.svg',          alt: 'Oh My Pi', isOpenAI: true },
  { match: 'omp',       src: '/images/integrations/omp.svg',          alt: 'Oh My Pi', isOpenAI: true },
  { match: 'pi',        src: '/images/integrations/pi.svg',           alt: 'Pi', isOpenAI: true },
];

export function getAgentLogoSrc(agentTypeName: string | null | undefined): { src: string; alt: string; isOpenAI?: boolean; invertForLight?: boolean; darkPlate?: boolean; boxedWhite?: boolean } | null {
  if (!agentTypeName) return null;
  const name = agentTypeName.toLowerCase();
  return AGENT_LOGOS.find(({ match }) => name.includes(match)) ?? null;
}

/**
 * A catalog agent's brand mark (`public/images/acp/*.svg`).
 *
 * These are single-colour glyphs authored with `fill="currentColor"`, so they
 * are painted as a CSS mask over `currentColor` rather than loaded as an
 * `<img>`: an SVG behind `<img>` resolves `currentColor` against nothing and
 * comes out black — invisible on the dark theme. The mask keeps them inheriting
 * the row's text colour on both themes, costs no JS (the file never enters the
 * DOM, so there is nothing to sanitise), and means a new mark is just a file.
 */
function AcpProviderMark({
  src,
  name,
  size,
  className,
  spinning,
}: {
  src: string;
  name: string;
  size: number;
  className?: string;
  spinning?: boolean;
}) {
  const mask = `url(${src})`;
  return (
    <span
      role="img"
      aria-label={name}
      title={name}
      className={cn('inline-block flex-shrink-0', spinning && 'animate-logo-fade', className)}
      style={{
        width: size,
        height: size,
        // Inline rather than Tailwind's `bg-current`: a caller passing its own
        // `bg-*` in `className` would otherwise win and paint a solid block.
        backgroundColor: 'currentColor',
        maskImage: mask,
        WebkitMaskImage: mask,
        maskSize: 'contain',
        WebkitMaskSize: 'contain',
        maskRepeat: 'no-repeat',
        WebkitMaskRepeat: 'no-repeat',
        maskPosition: 'center',
        WebkitMaskPosition: 'center',
      }}
    />
  );
}

interface AgentTypeIconProps {
  agentTypeName: string | null | undefined;
  size?: number;
  className?: string;
  spinning?: boolean;
  whiteForOpenAI?: boolean;
}

export function AgentTypeIcon({
  agentTypeName,
  size = 10,
  className,
  spinning,
  whiteForOpenAI = false,
}: AgentTypeIconProps) {
  // Catalog agents first, and by EXACT key: `AGENT_LOGOS` matches on
  // `name.includes(match)`, which is fine for ten hand-picked marks and would
  // not be for another thirty — `kilo`/`kiro`, `nova` and `grok` are all
  // substrings waiting to collide.
  const acp = acpIconSrc(agentTypeName);
  if (acp && agentTypeName) {
    return (
      <AcpProviderMark
        src={acp}
        name={agentTypeName}
        size={size}
        className={className}
        spinning={spinning}
      />
    );
  }

  const logo = getAgentLogoSrc(agentTypeName);

  // A provider with no mark at all: one the user defined in
  // ~/.vicoa/config.json, or a catalog entry whose logo we don't ship. Adding
  // an agent must never need a client release, so this has to degrade rather
  // than fail — returning null rendered nothing, which read as a broken row.
  // Fall back to a deterministic initial-square, the same treatment generated
  // project icons get, so a custom agent is visually stable and distinguishable.
  if (!logo) {
    if (!agentTypeName) return null;
    return (
      <span
        aria-label={agentTypeName}
        title={agentTypeName}
        className={cn(
          'flex-shrink-0 inline-flex items-center justify-center font-semibold text-white select-none',
          spinning && 'animate-logo-fade',
          className,
        )}
        style={{
          width: size,
          height: size,
          borderRadius: size * 0.24,
          backgroundColor: projectAvatarColor(agentTypeName.toLowerCase()),
          fontSize: Math.max(8, Math.round(size * 0.56)),
          lineHeight: 1,
        }}
      >
        {projectInitial(agentTypeName)}
      </span>
    );
  }

  // Hermes (and any boxedWhite glyph) on a dark surface: render the dark glyph
  // centered on a white rounded square instead of inverting it to a bare white
  // mark. On light surfaces it falls through to the plain dark glyph below.
  if (whiteForOpenAI && logo.boxedWhite) {
    const glyph = Math.round(size * 0.82);
    return (
      <span
        className={cn('flex-shrink-0 inline-flex items-center justify-center bg-white', className)}
        style={{ width: size, height: size, borderRadius: size * 0.24 }}
      >
        <Image
          src={logo.src}
          alt={logo.alt}
          width={glyph}
          height={glyph}
          unoptimized
          className={cn(spinning && 'animate-logo-fade')}
          style={{ width: glyph, height: glyph }}
        />
      </span>
    );
  }

  // Kimi (white-on-transparent): invisible on a light surface. Sit it on a dark
  // rounded plate in light (bg-foreground = near-black), transparent in dark
  // where the surface already supplies the contrast.
  if (whiteForOpenAI && logo.darkPlate) {
    const glyph = Math.round(size * 0.82);
    return (
      <span
        className={cn(
          'flex-shrink-0 inline-flex items-center justify-center bg-foreground dark:bg-transparent',
          className,
        )}
        style={{ width: size, height: size, borderRadius: size * 0.24 }}
      >
        <Image
          src={logo.src}
          alt={logo.alt}
          width={glyph}
          height={glyph}
          unoptimized
          className={cn(spinning && 'animate-logo-fade')}
          style={{ width: glyph, height: glyph }}
        />
      </span>
    );
  }

  return (
    <Image
      src={logo.src}
      alt={logo.alt}
      width={size}
      height={size}
      unoptimized
      className={cn(
        'flex-shrink-0',
        spinning && 'animate-logo-fade',
        // Monochrome dark glyphs go white only on a dark theme; dark & legible on light.
        whiteForOpenAI && logo.isOpenAI && 'dark:invert',
        // Two-tone marks built for dark invert on light, natural on dark.
        whiteForOpenAI && logo.invertForLight && 'invert dark:invert-0',
        className
      )}
      style={{ width: size, height: size }}
    />
  );
}

/**
 * Leading session indicator used by the sidebar-style session rows (search
 * palette, task dialog): the agent's brand logo, desaturated + dimmed once the
 * session is closed so finished work reads gray. Falls back to a generic
 * message glyph for agents without a brand mark.
 */
export function SessionAgentIcon({
  agentTypeName,
  status,
  size = 16,
  className,
}: {
  agentTypeName: string | null | undefined;
  status: string;
  size?: number;
  className?: string;
}) {
  const closed = CLOSED_STATUSES.has(status);
  const dim = closed ? 'opacity-50 grayscale' : undefined;
  // A catalog agent has a mark too — without this a cline session in the
  // search palette fell through to the generic message glyph.
  const logo = getAgentLogoSrc(agentTypeName) ?? acpIconSrc(agentTypeName);

  if (!logo) {
    return (
      <MessageCircle
        className={cn('shrink-0 text-muted-foreground', dim, className)}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <AgentTypeIcon
      agentTypeName={agentTypeName}
      size={size}
      whiteForOpenAI
      className={cn(dim, className)}
    />
  );
}
