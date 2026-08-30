import Image from 'next/image';
import { MessageCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CLOSED_STATUSES } from '@/components/dashboard/session-grouping';

// `isOpenAI` really means "monochrome dark glyph that needs inverting on dark
// surfaces" — the monochrome brand marks reuse it alongside openai.svg.
// `boxedWhite` is the alternative for a dark glyph we'd rather not invert:
// on a dark surface it renders as-is on a white rounded chip (keeps detail).
const AGENT_LOGOS: { match: string; src: string; alt: string; isOpenAI?: boolean; boxedWhite?: boolean }[] = [
  { match: 'claude',    src: '/images/integrations/claude-color.svg',  alt: 'Claude' },
  { match: 'codex',     src: '/images/integrations/openai.svg',        alt: 'Codex', isOpenAI: true },
  { match: 'opencode',  src: '/images/integrations/opencode.svg',      alt: 'OpenCode' },
  { match: 'cursor',    src: '/images/integrations/cursor.svg',        alt: 'Cursor', isOpenAI: true },
  { match: 'gemini',    src: '/images/integrations/gemini-color.svg',  alt: 'Gemini' },
  { match: 'copilot',   src: '/images/integrations/githubcopilot.svg', alt: 'Copilot', isOpenAI: true },
  { match: 'kimi',      src: '/images/integrations/kimi-color.svg',    alt: 'Kimi' },
  { match: 'hermes',    src: '/images/integrations/hermes.svg',        alt: 'Hermes', boxedWhite: true },
];

export function getAgentLogoSrc(agentTypeName: string | null | undefined): { src: string; alt: string; isOpenAI?: boolean; boxedWhite?: boolean } | null {
  if (!agentTypeName) return null;
  const name = agentTypeName.toLowerCase();
  return AGENT_LOGOS.find(({ match }) => name.includes(match)) ?? null;
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
  const logo = getAgentLogoSrc(agentTypeName);
  if (!logo) return null;

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
        whiteForOpenAI && logo.isOpenAI && 'invert',
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
  const logo = getAgentLogoSrc(agentTypeName);

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
