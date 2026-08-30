'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MobileAppDownload } from '@/components/dashboard/mobile-app-download';
import { X, Eye, EyeOff, Zap, History, Bell, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { createClient } from '@/lib/auth/supabase-client';
import { useMobileSidebarHidden, setMobileSidebarHidden } from '@/lib/mobile-sidebar-pref';

const DEMOS = [
  '/images/mobile/demo-0.webp',
  '/images/mobile/demo-1.webp',
  '/images/mobile/demo-2.webp',
  '/images/mobile/demo-3.webp',
  '/images/mobile/demo-4.webp',
];
const SLIDE_MS = 3500;

const BENEFITS = [
  {
    Icon: Zap,
    title: 'Sync automatically',
    desc: 'Sign in with the same account to pair your phone.',
  },
  {
    Icon: History,
    title: 'Pick up where you left off',
    desc: 'Continue any task or project started from your desktop.',
  },
  {
    Icon: Bell,
    title: 'Stay in the loop',
    desc: 'Get notified when an agent finishes a task.',
  },
  {
    Icon: Send,
    title: 'Start something new',
    desc: 'Just send a message to start a task on your machines.',
  },
];

export default function MobilePage() {
  const router = useRouter();
  const hidden = useMobileSidebarHidden();
  const [email, setEmail] = useState<string | null>(null);
  const [slide, setSlide] = useState(0);

  // Show the signed-in account so the "same account = paired" message is
  // concrete. Best-effort; stays null if unavailable.
  useEffect(() => {
    let cancelled = false;
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) setEmail(data.session?.user?.email ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-advance the screenshot slideshow.
  useEffect(() => {
    const id = setInterval(() => setSlide((s) => (s + 1) % DEMOS.length), SLIDE_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      {/* Toolbar — draggable window strip; interactive children opt out of drag
          so their clicks register in the desktop shell. */}
      <div
        style={DRAG_REGION}
        className="sticky top-0 z-10 flex items-center justify-between border-b border-border/60 bg-background/80 px-6 py-2 backdrop-blur"
      >
        <Button
          type="button"
          variant="outline"
          size="sm"
          style={NO_DRAG}
          className="h-7 text-xs"
          onClick={() => setMobileSidebarHidden(!hidden)}
        >
          {hidden ? (
            <>
              <Eye className="mr-1.5 h-3.5 w-3.5" />
              Show in sidebar
            </>
          ) : (
            <>
              <EyeOff className="mr-1.5 h-3.5 w-3.5" />
              Hide from sidebar
            </>
          )}
        </Button>
        <button
          type="button"
          aria-label="Close"
          title="Close"
          style={NO_DRAG}
          onClick={() => router.push('/dashboard/agents/new-session')}
          className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mx-auto max-w-5xl px-8 py-12">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          {/* Hero */}
          <div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Vicoa Mobile
            </span>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              Control your agents from your phone
            </h1>

            {/* Benefits — divided rows in a rounded bordered card. */}
            <div className="mt-8 divide-y divide-border/60 rounded-2xl border border-border/70 px-5">
              {BENEFITS.map(({ Icon, title, desc }) => (
                <div key={title} className="flex items-start gap-3.5 py-4">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted/40 text-foreground/80">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground">{title}</div>
                    <div className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{desc}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Download — the app-store cards (QR + badges). */}
            <div className="mt-10">
              <MobileAppDownload />
            </div>
          </div>

          {/* Phone slideshow — slides horizontally like switching pages; the
              screenshots carry their own framing, so no extra box/border. */}
          <div className="flex flex-col items-center">
            <div className="w-full max-w-[360px] overflow-hidden">
              <div
                className="flex transition-transform duration-500 ease-in-out"
                style={{ transform: `translateX(-${slide * 100}%)` }}
              >
                {DEMOS.map((src, i) => (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img
                    key={src}
                    src={src}
                    alt={`Vicoa Mobile screenshot ${i + 1}`}
                    className="w-full shrink-0 object-contain"
                  />
                ))}
              </div>
            </div>
            <div className="mt-5 flex gap-1.5">
              {DEMOS.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  aria-label={`Show screenshot ${i + 1}`}
                  onClick={() => setSlide(i)}
                  className={`h-1.5 rounded-full transition-all ${
                    i === slide ? 'w-5 bg-foreground' : 'w-1.5 bg-muted-foreground/40 hover:bg-muted-foreground/70'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
