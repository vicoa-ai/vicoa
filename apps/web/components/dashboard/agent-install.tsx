'use client';

import { Fragment, useState, type ReactNode } from 'react';
import { ChevronDown, ExternalLink } from 'lucide-react';
import { CopyCommand } from '@/components/copy-command';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { PLAN_CHOICES, installStepFor, type InstallOs } from '@/lib/desktop-agent-install';
import { openExternalUrl } from '@/lib/open-external';
import { cn } from '@/lib/utils';

/** Render `code` spans in an otherwise plain sentence. */
function withInlineCode(text: string): ReactNode {
  return text.split('`').map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="rounded bg-foreground/[0.06] px-1 py-px font-mono text-[10.5px] text-muted-foreground">
        {part}
      </code>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/**
 * How to install one agent on one OS: where to run it, the command with a copy
 * button, the setup guide, and what comes after (sign in). Shared by the
 * onboarding scan, the new-session page and Settings → Providers, so a command
 * only ever lives in `lib/desktop-agent-install.ts`.
 */
export function AgentInstallSteps({
  agentId,
  os,
  note,
}: {
  agentId: string;
  os: InstallOs;
  /** One more sentence of hint text, under the rest. */
  note?: string;
}) {
  const step = installStepFor(agentId, os);
  if (!step) return null;
  const hints = [
    step.requires ? `Needs ${step.requires} installed first.` : null,
    step.signIn,
    note ?? null,
  ].filter((hint): hint is string => !!hint);

  return (
    <div className="space-y-2">
      {step.command ? (
        <>
          <p className="text-[11px] text-muted-foreground">Run this in {step.shell}.</p>
          <CopyCommand command={step.command} />
        </>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          There&apos;s no one-line installer for Windows. Follow the setup guide.
        </p>
      )}
      <button
        type="button"
        onClick={() => openExternalUrl(step.docsUrl)}
        className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
      >
        Setup guide
        <ExternalLink className="h-3 w-3" />
      </button>
      {hints.map((hint) => (
        <p key={hint} className="text-[11px] text-muted-foreground/60">
          {withInlineCode(hint)}
        </p>
      ))}
    </div>
  );
}

function Radio({ on }: { on: boolean }) {
  return (
    <span
      className={cn(
        'flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border',
        on ? 'border-primary' : 'border-muted-foreground/40',
      )}
    >
      {on && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
    </span>
  );
}

interface ChoiceAgent {
  id: string;
  label: string;
}

/** One row of the list: the plan-led three carry a plan line, the rest don't. */
interface ChoiceRow extends ChoiceAgent {
  plan: string | null;
  free: boolean;
  note: string | undefined;
}

/**
 * "Which agent should I install?" for a machine that lacks the one wanted.
 *
 * Leads with the plan each agent runs on (`PLAN_CHOICES`): a Claude plan means
 * Claude Code, a ChatGPT plan means Codex, no plan means OpenCode's free
 * models. Every other not-installed agent sits behind "Show N more agents".
 * Nothing is open until the user picks a row, so no agent reads as the
 * recommended one. One row is open at a time, and picking the open row closes
 * it again (`onSelect(null)`). Picking is the caller's to act on (the
 * new-session page also makes it the session's agent, so once it is installed
 * the message goes straight out).
 */
export function AgentInstallChoices({
  agents,
  os,
  selectedId,
  onSelect,
  className,
}: {
  /** Agents not installed on the machine, in display order. */
  agents: ChoiceAgent[];
  os: InstallOs;
  selectedId: string | null;
  onSelect: (agentId: string | null) => void;
  className?: string;
}) {
  const leading: ChoiceRow[] = PLAN_CHOICES.flatMap((choice) => {
    const agent = agents.find((a) => a.id === choice.id);
    return agent ? [{ ...agent, plan: choice.plan, free: !!choice.free, note: choice.note }] : [];
  });
  const rest: ChoiceRow[] = agents
    .filter((a) => !PLAN_CHOICES.some((choice) => choice.id === a.id))
    .map((a) => ({ ...a, plan: null, free: false, note: undefined }));
  // Open the long tail when asked, when there is nothing to lead with (all
  // three are installed already), or when the pick lives there (the picker's
  // Install on Gemini, say) so it never opens hidden behind the toggle.
  const [showMoreClicked, setShowMore] = useState(false);
  const showMore = showMoreClicked || leading.length === 0 || rest.some((a) => a.id === selectedId);
  const rows = showMore ? [...leading, ...rest] : leading;

  return (
    <div className={cn('space-y-2.5', className)}>
      <div className="overflow-hidden rounded-xl border border-border/60 bg-foreground/[0.03]">
        {rows.map((row, i) => {
          const open = row.id === selectedId;
          return (
            <div key={row.id} className={cn(i > 0 && 'border-t border-border')}>
              <button
                type="button"
                onClick={() => onSelect(open ? null : row.id)}
                aria-expanded={open}
                className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-foreground/[0.02]"
              >
                <Radio on={open} />
                <AgentTypeIcon agentTypeName={row.id} size={18} whiteForOpenAI />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] text-foreground">{row.label}</span>
                  {row.plan && <span className="text-xs text-muted-foreground">{row.plan}</span>}
                </span>
                {row.free && (
                  <span className="rounded-md bg-green-500/10 px-1.5 py-0.5 text-[11px] text-green-600 dark:text-green-500">
                    Free
                  </span>
                )}
                <ChevronDown
                  className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground/70 transition-transform', open && 'rotate-180')}
                />
              </button>
              {open && (
                <div className="px-4 pb-4 pl-[3.75rem]">
                  <AgentInstallSteps agentId={row.id} os={os} note={row.note} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      {rest.length > 0 && !showMore && (
        <button
          type="button"
          onClick={() => setShowMore(true)}
          className="inline-flex cursor-pointer items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          Show {rest.length} more {rest.length === 1 ? 'agent' : 'agents'}
          <ChevronDown className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
