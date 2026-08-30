'use client';

import { Monitor } from 'lucide-react';
import Image from 'next/image';
import { cn } from '@/lib/utils';

/**
 * The shared intro slide deck.
 *
 * Two surfaces render these: the web `OnboardingModal` (which appends its own
 * referral-survey step) and the desktop `/desktop-intro` page. Only the slide
 * data and the presentation are shared — each surface keeps its own step
 * machine, because the web one is entangled with referral/survey logic the
 * desktop flow does not have.
 */

/** Natural size of every slide screenshot in /public/images/onboard. They are
    all shot at the same dimensions; keep new ones matching, or give the Slide
    its own size fields. */
const IMAGE_WIDTH = 1431;
const IMAGE_HEIGHT = 884;

export interface Slide {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  hasImage?: boolean;
  imageSrc?: string;
  /** Intrinsic size of this slide's screenshot. Defaults to the 1431×884 the
      original onboard shots all share; set it when a slide uses a differently
      proportioned image (e.g. the hero or a feature capture). */
  imageWidth?: number;
  imageHeight?: number;
  /** Round the screenshot's own corners. On for cropped shots (tasks,
      automations) that lack the app window's built-in rounded corners. */
  imageRounded?: boolean;
  /** Extra gradient-mat padding — more margin around the shot. On for the
      single-window feature screenshots that read better with breathing room;
      the full-scene hero keeps its tighter mat. */
  wideMat?: boolean;
  /** Show the agent-logo strip under the image (the "runs every agent" slide). */
  showAgents?: boolean;
  imagePlaceholderLabel?: string;
}

/** Agent marks for the logo strip on the "runs every agent" slide. Icon-only
    SVGs (not wordmarks) so they line up as even chips, each on a light chip so
    the dark marks (OpenAI, Cursor, Copilot, OpenCode) stay visible against the
    dark intro background. */
const AGENT_LOGOS: { src: string; alt: string }[] = [
  { src: '/images/integrations/claude-color.svg', alt: 'Claude Code' },
  { src: '/images/integrations/openai.svg', alt: 'Codex' },
  { src: '/images/integrations/gemini-color.svg', alt: 'Gemini' },
  { src: '/images/integrations/opencode-dark.svg', alt: 'OpenCode' },
  { src: '/images/integrations/cursor.svg', alt: 'Cursor' },
  { src: '/images/integrations/githubcopilot.svg', alt: 'GitHub Copilot' },
  { src: '/images/integrations/kimi-dark.svg', alt: 'Kimi' },
  { src: '/images/integrations/openrouter.svg', alt: 'OpenRouter' },
];

export const INTRO_SLIDES: Slide[] = [
  {
    id: 'welcome',
    title: 'Welcome to Vicoa',
    subtitle: '',
    description:
      'Run a team of coding agents in parallel, automate tasks and workflows, and get 10× more done even while you sleep.',
    hasImage: false,
  },
  {
    id: 'desktop-mobile-sync',
    title: 'Start on desktop, pick up on mobile',
    subtitle: 'Agent team on any device',
    description:
      'Orchestrate Claude Code, Codex, and many more AI agents side by side on your own machine, then start a task on your desktop and pick it up on your phone. Every message and file change synced in real time.',
    hasImage: true,
    imageSrc: '/images/hero.webp',
    imageWidth: 4116,
    imageHeight: 2488,
    showAgents: true,
    imagePlaceholderLabel: 'Desktop → mobile sync screenshot',
  },
  {
    id: 'tasks',
    title: 'Capture work as tasks, start sessions from them',
    subtitle: 'Never lose an idea',
    description:
      'Capture what needs to get done on your task board, then launch an agent session directly from any task. When you hit a rate limit or have a new idea, park it on the board and come back to it later without losing momentum.',
    hasImage: true,
    imageSrc: '/images/features/tasks-start-a-new-session.webp',
    imageWidth: 1762,
    imageHeight: 1060,
    imageRounded: true,
    wideMat: true,
    imagePlaceholderLabel: 'Task board screenshot',
  },
  {
    id: 'automations',
    title: 'Automate your workflow, get more done while you sleep',
    subtitle: 'Schedule Automations',
    description:
      'Schedule AI coding agents to handle recurring tasks and workflows automatically. They keep working while you focus on what matters, so you can come back to completed work and review the results.',
    hasImage: true,
    imageSrc: '/images/features/automation.webp',
    imageWidth: 2423,
    imageHeight: 1466,
    imageRounded: true,
    wideMat: true,
    imagePlaceholderLabel: 'Automations schedule screenshot',
  },
  {
    id: 'dev-tools',
    title: 'Your Files, Git Worktree & Changes, Terminals',
    subtitle: 'Agentic IDE',
    description:
      'Every session is a full workspace: terminals, isolated git worktrees so agents never touch each other’s files, a commit graph with rich diffs, and a file tree you can browse and edit in place.',
    hasImage: true,
    imageSrc: '/images/features/dev-features.webp',
    imageWidth: 1168,
    imageHeight: 799,
    wideMat: true,
    imagePlaceholderLabel: 'Desktop command center screenshot',
  },  
];

export function ImagePlaceholder({ label }: { label: string }) {
  return (
    <div className="w-full flex-1 rounded-2xl bg-gradient-to-br from-[#C9DEFF] to-[#FFEDE2] flex flex-col items-center justify-center gap-3 overflow-hidden relative shadow-lg">
      <div className="relative z-10 flex flex-col items-center gap-2 text-center px-4">
        <div className="h-10 w-10 rounded-lg bg-white/50 border border-black/5 flex items-center justify-center">
          <Monitor className="h-5 w-5 text-slate-600" />
        </div>
        <p className="text-xs text-slate-600/70 font-mono">{label}</p>
      </div>
    </div>
  );
}

/**
 * Off-screen preloader. Eagerly fetches every slide screenshot on mount so
 * moving to a slide paints its image instantly instead of waiting on a fetch +
 * optimize round-trip. Each <Image> uses the same src/width/height/sizes as the
 * visible one, so the browser reuses the already-downloaded variant (same
 * `/_next/image` URL). Render it once per surface, alongside the slide view.
 *
 * Kept in the layout (0×0 + overflow-hidden) rather than `display:none` so the
 * eager request is guaranteed to fire.
 */
export function SlideImagePreloader({ slides }: { slides: Slide[] }) {
  return (
    <div aria-hidden className="pointer-events-none h-0 w-0 overflow-hidden opacity-0">
      {slides.map((slide) =>
        slide.hasImage && slide.imageSrc ? (
          <Image
            key={slide.id}
            src={slide.imageSrc}
            alt=""
            width={slide.imageWidth ?? IMAGE_WIDTH}
            height={slide.imageHeight ?? IMAGE_HEIGHT}
            sizes="(max-width: 768px) 100vw, 1024px"
            loading="eager"
          />
        ) : null
      )}
    </div>
  );
}

export function StepDots({
  total,
  current,
  onSelect,
}: {
  total: number;
  current: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: total }).map((_, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(i)}
          aria-label={`Go to step ${i + 1}`}
          className={cn(
            'rounded-full transition-all duration-300 cursor-pointer',
            i === current
              ? 'h-2 w-6 bg-primary'
              : i < current
              ? 'h-2 w-2 bg-primary/40 hover:bg-primary/70'
              : 'h-2 w-2 bg-border hover:bg-muted-foreground/40'
          )}
        />
      ))}
    </div>
  );
}

/**
 * Type scale per surface.
 *
 * The web modal renders inside a 680px card, where the original sizes are
 * right. The desktop intro owns a whole 1280×860 window, where the same 20px
 * title and 14px body read as lost in space. Same slides, two scales — rather
 * than one compromise that is slightly wrong on both.
 */
export type SlideSize = 'default' | 'lg';

const SLIDE_SCALE: Record<SlideSize, Record<string, string>> = {
  default: {
    logo: 'h-12 mb-8',
    welcomeTitle: 'text-xl mb-4',
    welcomeBody: 'text-sm max-w-sm',
    subtitle: 'text-xs',
    title: 'text-xl',
    body: 'text-sm',
    // Height cap so the shot + header + description (and, on the hero slide, the
    // agent-logo strip) fit the 680px web-modal card.
    image: 'max-h-[360px]',
  },
  // Sized against `/desktop-welcome`, the screen the intro hands off to: it
  // uses an h-12 logo and a text-3xl heading, so anything bigger here makes the
  // brand visibly shrink the moment the user hits Continue.
  lg: {
    logo: 'h-12 mb-8',
    welcomeTitle: 'text-3xl mb-4',
    welcomeBody: 'text-lg max-w-lg',
    subtitle: 'text-sm',
    title: 'text-2xl',
    body: 'text-base',
    // Cap on the tall desktop window so a header + screenshot + description (and
    // the hero slide's agent-logo strip) all fit without the shot dominating.
    image: 'max-h-[460px]',
  },
};

/**
 * One slide's body. The `welcome` slide is centered with the logo; every other
 * slide is a subtitle/title header, a stretching image, then the description.
 * `children` renders under the description (the web modal's referral options).
 */
export function SlideView({
  slide,
  size = 'default',
  fillHeight = true,
  children,
}: {
  slide: Slide;
  size?: SlideSize;
  /**
   * When true (the web modal, whose card is height-capped at 680px), the image
   * grows to fill the available height. When false (the desktop intro, which
   * owns an uncapped full-height window), the image sizes to its content so the
   * whole slide can be centered as a group with constant spacing — otherwise a
   * very tall window strands empty space around the width-capped landscape
   * screenshot, pushing the header to the top and the description to the bottom.
   */
  fillHeight?: boolean;
  children?: React.ReactNode;
}) {
  const s = SLIDE_SCALE[size];

  if (slide.id === 'welcome') {
    return (
      <>
        <Image
          src="/images/vicoa-light.webp"
          alt="Vicoa Logo"
          width={0}
          height={0}
          quality={50}
          sizes="100vw"
          className={cn('w-auto opacity-90', s.logo)}
        />
        <h2 className={cn('font-semibold text-foreground leading-tight', s.welcomeTitle)}>
          {slide.title}
        </h2>
        <p className={cn('text-muted-foreground leading-relaxed', s.welcomeBody)}>
          {slide.description}
        </p>
      </>
    );
  }

  return (
    <>
      <div className="mb-5 shrink-0">
        <p
          className={cn(
            'text-muted-foreground/60 uppercase tracking-wide font-mono mb-1',
            s.subtitle
          )}
        >
          {slide.subtitle}
        </p>
        <h2 className={cn('font-semibold text-foreground leading-tight', s.title)}>{slide.title}</h2>
      </div>

      {/* Screenshots keep their real aspect ratio (intrinsic width/height +
          object-contain); the fixed max-h from the scale caps them so a header,
          shot, and description all fit. The gradient "mat" wraps the shot with
          even padding; cropped shots (imageRounded) round their own corners so
          they read like the windowed captures that already have rounded edges. */}
      {slide.hasImage && (
        <div
          className={cn(
            'mb-5 flex min-h-0 flex-col items-center justify-center',
            fillHeight && 'flex-1'
          )}
        >
          {slide.imageSrc ? (
            <div
              className={cn(
                'flex max-w-full rounded-2xl bg-gradient-to-br from-[#C9DEFF] to-[#FFEDE2] shadow-lg',
                slide.wideMat ? 'p-6 sm:p-10' : 'p-3 sm:p-4'
              )}
            >
              <Image
                src={slide.imageSrc}
                alt={slide.title}
                width={slide.imageWidth ?? IMAGE_WIDTH}
                height={slide.imageHeight ?? IMAGE_HEIGHT}
                sizes="(max-width: 768px) 100vw, 1024px"
                // sizes={SLIDE_IMAGE_SIZES}
                className={cn(
                  'w-auto max-w-full object-contain',
                  slide.imageRounded && 'rounded-xl',
                  s.image
                )}
              />
            </div>
          ) : slide.imagePlaceholderLabel ? (
            <ImagePlaceholder label={slide.imagePlaceholderLabel} />
          ) : null}
        </div>
      )}

      {slide.showAgents && (
        <div className="mb-5 flex shrink-0 flex-wrap items-center justify-center gap-2.5">
          {AGENT_LOGOS.map((a) => (
            <div
              key={a.src}
              title={a.alt}
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-white shadow-sm ring-1 ring-black/5"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={a.src} alt={a.alt} className="h-5 w-5 object-contain" />
            </div>
          ))}
        </div>
      )}

      <p className={cn('text-muted-foreground leading-relaxed shrink-0', s.body)}>
        {slide.description}
      </p>
      {children}
    </>
  );
}
