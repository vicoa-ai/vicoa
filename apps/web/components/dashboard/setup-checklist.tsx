'use client';

/**
 * Floating "Continue setup" checklist — a persistent onboarding guide that
 * floats at the bottom-left of the dashboard content pane. It renders for any
 * signed-in user (web *and* the desktop app); it hides itself when there's no
 * signed-in Supabase user, i.e. desktop local-only mode, where the cloud
 * fetches below wouldn't be authenticated. Each row is derived from live
 * account data (not stored flags), so it can't drift out of the real state:
 *
 *   • Connect a coding agent   → any registered agent instance (free, from ctx)
 *   • Send your first message  → activity.total_user_messages > 0
 *   • Create a task            → listTasks().length > 0
 *   • Create an automation     → listAutomations().length > 0
 *
 * A mobile-app step was intentionally left out: the only backend signal is an
 * active push token, which Vicoa registers ONLY when notifications are enabled
 * (push_notifications_handler.dart gates on checkPermission), so ~28% of users
 * who provably use the app have no token — the card would never auto-hide for
 * them. Re-add once a real "logged in on mobile" signal exists.
 *
 * Persisted UI state (dismissed / collapsed / cached completion) is keyed by
 * the signed-in user id, so two accounts on the same browser don't leak state
 * into each other.
 *
 * API-call discipline: completion is monotonic (you can't un-connect, un-send,
 * etc.), so each satisfied step is cached and never re-checked. A step's backend
 * call is skipped once it's known-done; once every step is done (or the user
 * dismisses the card) the component makes zero backend calls on later loads and
 * renders nothing.
 *
 * Rows are actionable: clicking one routes to the relevant flow. The card
 * collapses to a compact pill and auto-hides at 100% or on dismiss.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import posthog from 'posthog-js';
import {
  Check,
  ChevronDown,
  Bot,
  MessageCirclePlus,
  ListTodo,
  CalendarClock,
  X,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { readBrowserIdentity } from '@/lib/auth/browser-token';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { subscribeOnboardingProgress } from '@/lib/onboarding-progress';

const DISMISSED_KEY = 'vicoa_setup_checklist_dismissed';
const COLLAPSED_KEY = 'vicoa_setup_checklist_collapsed';
const CHECKS_KEY = 'vicoa_setup_checklist_checks';

type StepId = 'connect' | 'message' | 'task' | 'automation';
const STEP_IDS: StepId[] = ['connect', 'message', 'task', 'automation'];
type Checks = Record<StepId, boolean>;
const EMPTY_CHECKS: Checks = {
  connect: false,
  message: false,
  task: false,
  automation: false,
};

interface Step {
  id: StepId;
  label: string;
  hint: string;
  icon: LucideIcon;
  done: boolean;
  onClick: () => void;
}

function readChecks(uid: string): Checks {
  if (typeof window === 'undefined') return EMPTY_CHECKS;
  try {
    const raw = localStorage.getItem(`${CHECKS_KEY}:${uid}`);
    if (!raw) return EMPTY_CHECKS;
    return { ...EMPTY_CHECKS, ...(JSON.parse(raw) as Partial<Checks>) };
  } catch {
    return EMPTY_CHECKS;
  }
}

export function SetupChecklist() {
  const router = useRouter();
  const { api, recentInstances } = useAgentDashboard();

  // Nothing renders until we know who's signed in. `userId` null after resolve
  // means local-only desktop / logged-out → the card stays hidden. Resolving
  // the user here also lets us key persisted state per-account (no cross-user
  // leak on a shared browser).
  const [hydrated, setHydrated] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [checks, setChecks] = useState<Checks>(EMPTY_CHECKS);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let uid: string | null = null;
      try {
        uid = (await readBrowserIdentity())?.id ?? null;
      } catch {
        /* treat as signed-out */
      }
      if (cancelled) return;
      setUserId(uid);
      if (uid) {
        setDismissed(localStorage.getItem(`${DISMISSED_KEY}:${uid}`) === 'true');
        setCollapsed(localStorage.getItem(`${COLLAPSED_KEY}:${uid}`) === 'true');
        // Merge cache over any completion already derived in-memory (e.g. the
        // connect effect) so seeding never clobbers a fresh true.
        const cached = readChecks(uid);
        setChecks((prev) => {
          const merged: Checks = { ...cached };
          for (const k of STEP_IDS) if (prev[k]) merged[k] = true;
          return merged;
        });
      }
      setHydrated(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Connecting an agent shows up in the shared instance list (free — the
  // context loads it regardless). Fold it into `checks` so it caches too.
  useEffect(() => {
    if (recentInstances.length > 0 && !checks.connect) {
      setChecks((c) => ({ ...c, connect: true }));
    }
  }, [recentInstances.length, checks.connect]);

  // A snapshot of `checks` for the fetch to read without being a dependency
  // (so a step flipping done doesn't retrigger the whole fetch).
  const checksRef = useRef(checks);
  checksRef.current = checks;

  // Re-run the checks when the session set changes (a new session may have
  // added the first message, etc.). We key on `latest_message_at` as well as
  // `chat_length` because sending a message advances the former live — the
  // context's WS `onNewMessage` handler patches `latest_message_at`, but
  // nothing updates `chat_length` on a sent message (the `instance-update`
  // frame omits it). Without it, `instanceSig` never changes on a sent
  // message, so `getActivity()` is never re-checked and the "Send your first
  // message" step stays stale until a full page reload.
  const instanceSig = useMemo(
    () =>
      recentInstances
        .map((i) => `${i.id}:${i.chat_length}:${i.latest_message_at ?? ''}`)
        .join(','),
    [recentInstances],
  );

  const refresh = useCallback(async () => {
    if (!api) return;
    const c = checksRef.current;
    const jobs: Promise<void>[] = [];
    if (!c.message) {
      jobs.push(
        api
          .getActivity()
          .then((a) => {
            if ((a?.total_user_messages ?? 0) > 0) setChecks((p) => ({ ...p, message: true }));
          })
          .catch(() => {}),
      );
    }
    if (!c.task) {
      jobs.push(
        api
          .listTasks()
          .then((t) => {
            if ((t?.length ?? 0) > 0) setChecks((p) => ({ ...p, task: true }));
          })
          .catch(() => {}),
      );
    }
    if (!c.automation) {
      jobs.push(
        api
          .listAutomations()
          .then((a) => {
            if ((a?.length ?? 0) > 0) setChecks((p) => ({ ...p, automation: true }));
          })
          .catch(() => {}),
      );
    }
    if (jobs.length) await Promise.all(jobs);
  }, [api]);

  useEffect(() => {
    if (!hydrated || !userId || dismissed) return;
    const c = checksRef.current;
    // Everything already known-done → no backend calls at all.
    if (STEP_IDS.every((id) => c[id])) return;
    void refresh();
  }, [refresh, instanceSig, dismissed, hydrated, userId]);

  // Creating a task or automation touches neither the instance list nor the WS
  // stream, so `instanceSig` never changes and the effect above wouldn't
  // re-check those steps. The create flows emit an onboarding-progress nudge —
  // re-run the checks on it (still gated by the monotonic per-step cache in
  // `refresh`, so satisfied steps are never re-fetched and an all-done card
  // makes no calls).
  useEffect(() => {
    if (!hydrated || !userId || dismissed) return;
    return subscribeOnboardingProgress(() => {
      if (STEP_IDS.every((id) => checksRef.current[id])) return;
      void refresh();
    });
  }, [refresh, dismissed, hydrated, userId]);

  // Persist completion (per user) so future loads skip the satisfied steps.
  useEffect(() => {
    if (typeof window === 'undefined' || !userId) return;
    try {
      localStorage.setItem(`${CHECKS_KEY}:${userId}`, JSON.stringify(checks));
    } catch {
      /* ignore quota / privacy-mode errors */
    }
  }, [checks, userId]);

  const dismiss = useCallback(() => {
    if (userId) localStorage.setItem(`${DISMISSED_KEY}:${userId}`, 'true');
    setDismissed(true);
    posthog.capture('setup_checklist_dismissed', {
      completed: STEP_IDS.filter((id) => checksRef.current[id]).length,
    });
  }, [userId]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      if (userId) localStorage.setItem(`${COLLAPSED_KEY}:${userId}`, String(next));
      posthog.capture('setup_checklist_toggle', { collapsed: next });
      return next;
    });
  }, [userId]);

  const go = useCallback((id: StepId, action: () => void) => {
    posthog.capture('setup_checklist_step_click', { step: id });
    action();
  }, []);

  const steps: Step[] = [
    {
      id: 'connect',
      label: 'Connect a coding agent',
      hint: 'Claude Code, Codex, OpenCode, and more',
      icon: Bot,
      done: checks.connect,
      onClick: () => go('connect', () => router.push('/dashboard/settings?tab=providers')),
    },
    {
      id: 'message',
      label: 'Send your first message',
      hint: 'Start a new session and send message',
      icon: MessageCirclePlus,
      done: checks.message,
      onClick: () => go('message', () => router.push('/dashboard/agents/new-session')),
    },
    {
      id: 'task',
      label: 'Create a task',
      hint: 'Track what to build next',
      icon: ListTodo,
      done: checks.task,
      onClick: () => go('task', () => router.push('/dashboard/tasks')),
    },
    {
      id: 'automation',
      label: 'Create an automation',
      hint: 'Schedule recurring agent runs',
      icon: CalendarClock,
      done: checks.automation,
      onClick: () => go('automation', () => router.push('/dashboard/automation')),
    },
  ];

  const completed = steps.filter((s) => s.done).length;
  const total = steps.length;
  const allDone = completed === total;
  const pct = Math.round((completed / total) * 100);
  const doneSig = STEP_IDS.map((id) => (checks[id] ? '1' : '0')).join('');

  // --- Analytics ---------------------------------------------------------
  // "Shown" once per mount when the card is actually visible.
  const shownRef = useRef(false);
  useEffect(() => {
    if (hydrated && userId && !dismissed && !allDone && !shownRef.current) {
      shownRef.current = true;
      posthog.capture('setup_checklist_shown', { completed, total });
    }
  }, [hydrated, userId, dismissed, allDone, completed, total]);

  // Per-step completion, only for transitions during this session (steps
  // already done on arrival are seeded silently so returning users don't
  // re-fire events).
  const reportedRef = useRef<Set<StepId> | null>(null);
  useEffect(() => {
    const doneIds = STEP_IDS.filter((id) => checks[id]);
    if (reportedRef.current === null) {
      reportedRef.current = new Set(doneIds);
      return;
    }
    for (const id of doneIds) {
      if (!reportedRef.current.has(id)) {
        reportedRef.current.add(id);
        posthog.capture('setup_checklist_step_completed', { step: id });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doneSig]);

  // "All done" — once per session, and never for users who arrive complete.
  const completedFiredRef = useRef(false);
  const firstAllDoneRunRef = useRef(true);
  useEffect(() => {
    if (firstAllDoneRunRef.current) {
      firstAllDoneRunRef.current = false;
      if (allDone) completedFiredRef.current = true; // arrived complete → stay quiet
      return;
    }
    if (allDone && !completedFiredRef.current) {
      completedFiredRef.current = true;
      posthog.capture('setup_checklist_completed');
    }
  }, [allDone]);

  if (!hydrated || !userId || dismissed || allDone) return null;

  return (
    <div className="w-full">
      {collapsed ? (
        <button
          type="button"
          onClick={toggleCollapsed}
          className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-sm shadow-sm transition-colors hover:border-border"
        >
          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
            <svg viewBox="0 0 32 32" className="h-3.5 w-3.5 -rotate-90">
              <circle cx="16" cy="16" r="13" className="fill-none stroke-muted" strokeWidth="4" />
              <circle
                cx="16"
                cy="16"
                r="13"
                className="fill-none stroke-primary transition-[stroke-dashoffset] duration-500"
                strokeWidth="4"
                strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 13}
                strokeDashoffset={2 * Math.PI * 13 * (1 - completed / total)}
              />
            </svg>
          </span>
          <span className="font-medium text-foreground">Onboarding</span>
          <span className="ml-auto text-muted-foreground">
            {completed}/{total}
          </span>
          <ChevronDown className="h-3.5 w-3.5 rotate-180 text-muted-foreground" />
        </button>
      ) : (
        <div className="w-full overflow-hidden rounded-lg border border-border/60 bg-muted/40 shadow-sm">
          {/* Header */}
          <div className="flex items-center justify-between gap-2 px-3.5 pt-3 pb-2.5">
            <div className="flex flex-col">
              <span className="text-sm font-medium text-foreground">Onboarding</span>
              <span className="text-xs text-muted-foreground">
                {completed} of {total} done
              </span>
            </div>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={toggleCollapsed}
                aria-label="Collapse"
                className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
              >
                <ChevronDown className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={dismiss}
                aria-label="Dismiss setup checklist"
                className="cursor-pointer rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Progress bar */}
          <div className="mx-3.5 h-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>

          {/* Steps */}
          <div className="p-1.5">
            {steps.map((step) => {
              const StepIcon = step.icon;
              return (
                <button
                  key={step.id}
                  type="button"
                  onClick={step.onClick}
                  className="group flex w-full cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-muted/50"
                >
                  {/* Check circle — small, always visible (not hover-only) */}
                  <span
                    className={cn(
                      'flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors',
                      step.done
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-muted-foreground/50 text-transparent group-hover:border-primary/60',
                    )}
                  >
                    <Check className="h-2.5 w-2.5" strokeWidth={3} />
                  </span>

                  <span className="flex min-w-0 flex-1 flex-col">
                    <span
                      className={cn(
                        'truncate text-sm',
                        step.done ? 'text-muted-foreground line-through' : 'text-foreground',
                      )}
                    >
                      {step.label}
                    </span>
                    {!step.done && (
                      <span className="truncate text-xs text-muted-foreground/70">{step.hint}</span>
                    )}
                  </span>

                  <StepIcon
                    className={cn(
                      'h-4 w-4 shrink-0',
                      step.done ? 'text-muted-foreground/40' : 'text-muted-foreground/70',
                    )}
                  />
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
