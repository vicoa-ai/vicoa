'use client';

import { CalendarClock, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { AUTOMATION_TEMPLATES, type AutomationTemplate } from '../lib/templates';

export function AutomationEmptyState({
  onPick,
  onScratch,
  disabled,
  compact,
}: {
  onPick: (template: AutomationTemplate) => void;
  onScratch: () => void;
  disabled?: boolean;
  /** Stack templates in a single column (e.g. when the create panel is open
   *  and this sits in the narrow list column). */
  compact?: boolean;
}) {
  return (
    <div className="custom-scrollbar flex h-full flex-col items-center overflow-y-auto px-6 pt-12 pb-10">
      <div className="w-full max-w-3xl">
        <div className="flex flex-col items-center text-center">
          <CalendarClock className="h-8 w-8 text-muted-foreground/70" />
          <h2 className="mt-4 text-base font-medium">No automations yet</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Schedule recurring tasks for your AI agents. Pick a template or start from scratch.
          </p>
        </div>

        <div
          className={cn(
            'mt-8 grid gap-3',
            compact ? 'grid-cols-1' : 'sm:grid-cols-2 lg:grid-cols-3',
          )}
        >
          {AUTOMATION_TEMPLATES.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                disabled={disabled}
                onClick={() => onPick(t)}
                className={cn(
                  'group flex items-start gap-3 rounded-xl border border-border bg-card/40 p-4 text-left transition-colors',
                  'hover:border-foreground/20 hover:bg-foreground/[0.04]',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                )}
              >
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <div className="text-sm font-medium">{t.title}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{t.description}</div>
                </div>
              </button>
            );
          })}
        </div>

        <div className="mt-6 flex justify-center">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={onScratch}
            disabled={disabled}
          >
            <Plus className="size-3.5" />
            Start from scratch
          </Button>
        </div>
      </div>
    </div>
  );
}
