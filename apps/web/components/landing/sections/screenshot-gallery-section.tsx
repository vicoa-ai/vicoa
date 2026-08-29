'use client';

import { useEffect, useRef } from 'react';
import Image from 'next/image';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { MobileDownloadCta } from '@/components/landing/cta/mobile-download-cta';

// The mobile screenshots ship with a device frame on a transparent background,
// so they self-frame — use `drop-shadow` (follows the phone silhouette) rather
// than a rectangular card/box-shadow. Shown a few at a time at full viewing
// size; arrows page through them and each carries a caption for identity.
//
// Order matters: Agent Sessions / Chat / Notifications sit together in the
// middle so the default (centered) view opens on that trio — see START_TITLE
// below.
const SHOTS = [
  {
    src: '/images/mobile/changes.webp',
    title: 'Changes',
    desc: 'Review changes agents made',
    alt: 'Reviewing a staged git diff in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/files.webp',
    title: 'Files',
    desc: 'Browse and open any file',
    alt: 'Browsing the repository file tree in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/chat-text.webp',
    title: 'Conversation',
    desc: 'Read replies and reasoning in full',
    alt: 'Reading an agent conversation in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/home.webp',
    title: 'Agent Sessions',
    desc: 'View your agents at a glance',
    alt: 'Vicoa mobile home listing coding sessions grouped by project',
  },
  {
    src: '/images/mobile/chat.webp',
    title: 'Chat',
    desc: 'Talk to any agent and approve changes',
    alt: 'Chatting with a coding agent in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/notifications.webp',
    title: 'Notifications',
    desc: 'Get pinged when an agent needs you',
    alt: 'Lock-screen push notifications when Claude Code needs your input',
  },
  {
    src: '/images/mobile/search.webp',
    title: 'Search',
    desc: 'Jump to any session, task, automation',
    alt: 'Searching sessions, tasks, and automations in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/tasks.webp',
    title: 'Tasks',
    desc: 'Plan work for your agents',
    alt: 'A task board with backlog, todo, and in-progress columns in the Vicoa mobile app',
  },
  {
    src: '/images/mobile/automations.webp',
    title: 'Automations',
    desc: 'Schedule agents to run themselves',
    alt: 'A list of scheduled automations in the Vicoa mobile app',
  },
];

// The screen that anchors the default (left of the centered trio):
// Agent Sessions / Chat / Notifications fill the opening view.
const START_TITLE = 'Agent Sessions';

export function ScreenshotGallerySection() {
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Open on the Agent Sessions / Chat / Notifications trio: left-align the first
  // so those three fill the default view. Aligning to a card boundary keeps
  // snap-mandatory happy.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const first = el.querySelector<HTMLElement>('[data-card]');
    const gap = parseFloat(getComputedStyle(el).columnGap) || 32;
    const pitch = first ? first.getBoundingClientRect().width + gap : 0;
    const startIndex = Math.max(0, SHOTS.findIndex((s) => s.title === START_TITLE));
    el.scrollLeft = startIndex * pitch;
  }, []);

  // Advance by exactly one viewport of cards. The visible cards span the
  // content box (clientWidth minus the side gutters); adding one gap makes that
  // an exact multiple of the card pitch, so a click always lands on a card edge.
  // At either end it wraps around, so you can loop from the last screens back to
  // the first (and the reverse).
  const page = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    const cs = getComputedStyle(el);
    const gap = parseFloat(cs.columnGap) || 32;
    const contentW = el.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
    const maxScroll = el.scrollWidth - el.clientWidth;
    if (dir === 1 && el.scrollLeft >= maxScroll - 8) {
      el.scrollTo({ left: 0, behavior: 'smooth' });
    } else if (dir === -1 && el.scrollLeft <= 8) {
      el.scrollTo({ left: maxScroll, behavior: 'smooth' });
    } else {
      el.scrollBy({ left: dir * (contentW + gap), behavior: 'smooth' });
    }
  };

  return (
    <section className="overflow-hidden bg-background py-20 sm:py-28">
      <div className="mx-auto mb-14 max-w-3xl px-4 text-center sm:mb-16 sm:px-6 lg:px-8">
        <div className="mb-4 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Vicoa Mobile
        </div>
        <h2 className="mb-5 text-3xl tracking-tight text-foreground sm:text-4xl lg:text-5xl">
          Your phone is the remote control
        </h2>
        <p className="text-lg leading-relaxed text-muted-foreground sm:text-xl">
          Approve changes, review diffs, and steer your agents from anywhere. 
        </p>
      </div>

      {/* Carousel: exactly three phones per view (fewer on small screens). The
          scroller's side gutters (px) hold the arrows clear of the phones;
          arrows page by a full view, touch can swipe. */}
      <div className="relative mx-auto max-w-[1240px]">
        {/* Prev / next — sit in the side gutter, clear of the end phones. */}
        <button
          type="button"
          aria-label="Previous screenshots"
          onClick={() => page(-1)}
          className="absolute left-2 top-[44%] z-20 hidden h-12 w-12 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-black/10 bg-white text-neutral-900 shadow-lg transition hover:bg-neutral-100 active:scale-95 sm:flex lg:left-4"
        >
          <ChevronLeft className="h-6 w-6" />
        </button>
        <button
          type="button"
          aria-label="Next screenshots"
          onClick={() => page(1)}
          className="absolute right-2 top-[44%] z-20 hidden h-12 w-12 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-black/10 bg-white text-neutral-900 shadow-lg transition hover:bg-neutral-100 active:scale-95 sm:flex lg:right-4"
        >
          <ChevronRight className="h-6 w-6" />
        </button>

        {/* py-8 gives the hover zoom room to grow — overflow-x-auto also clips
            the vertical axis, so without it the scaled top gets cut off. The
            side padding (matched by scroll-px) is the arrow gutter. */}
        <div
          ref={scrollerRef}
          className="flex snap-x snap-mandatory gap-8 overflow-x-auto py-8 px-4 scroll-px-4 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:gap-10 sm:px-16 sm:scroll-px-16 lg:px-24 lg:scroll-px-24"
        >
          {SHOTS.map((shot) => (
            <figure
              key={shot.src}
              data-card
              className="w-[82%] shrink-0 snap-start sm:w-[calc((100%-2.5rem)/2)] lg:w-[calc((100%-5rem)/3)]"
            >
              <div className="transition-transform duration-300 ease-out will-change-transform hover:scale-[1.03]">
                <Image
                  src={shot.src}
                  alt={shot.alt}
                  width={641}
                  height={1309}
                  sizes="(min-width: 1024px) 340px, (min-width: 640px) 45vw, 82vw"
                  quality={90}
                  className="h-auto w-full drop-shadow-2xl"
                />
              </div>
              <figcaption className="mt-6 text-center">
                <div className="text-base font-medium text-foreground">{shot.title}</div>
                <div className="mt-1 text-sm leading-relaxed text-muted-foreground">{shot.desc}</div>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-[85rem] px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-6xl">
          <MobileDownloadCta />
        </div>
      </div>
    </section>
  );
}
