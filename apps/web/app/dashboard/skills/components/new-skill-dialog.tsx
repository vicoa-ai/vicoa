'use client';

// The "+ New Skill" chooser: a small dialog offering the ways to add a skill —
// install from a Git repo, or open a new session to author/install one with an
// agent. Room to grow (a marketplace, templates, …) as more paths land.

import type { ReactNode } from 'react';
import { ChevronRight, GitBranch, Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

interface NewSkillDialogProps {
  open: boolean;
  /** Git install needs a reachable, up-to-date machine selected. */
  canInstall: boolean;
  onOpenChange: (open: boolean) => void;
  onInstall: () => void;
  onCreateWithAgent: () => void;
}

export function NewSkillDialog({
  open,
  canInstall,
  onOpenChange,
  onInstall,
  onCreateWithAgent,
}: NewSkillDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New skill</DialogTitle>
          <DialogDescription>Choose how to add a skill to this machine.</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Option
            icon={<GitBranch className="size-[18px]" />}
            title="Install from a Git repository"
            body="Clone a public repo whose root (or a subfolder) has a SKILL.md."
            disabled={!canInstall}
            disabledHint="Select an online machine to install."
            onClick={onInstall}
          />
          <Option
            icon={<Sparkles className="size-[18px]" />}
            title="Create with an agent"
            body="Open a new session seeded to author or install a skill for you."
            onClick={onCreateWithAgent}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Option({
  icon,
  title,
  body,
  onClick,
  disabled,
  disabledHint,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  onClick: () => void;
  disabled?: boolean;
  disabledHint?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={disabled ? disabledHint : undefined}
      className={cn(
        'flex w-full items-start gap-3 rounded-lg border border-border bg-card p-3 text-left transition-colors',
        disabled
          ? 'cursor-not-allowed opacity-50'
          : 'cursor-pointer hover:border-primary/40 hover:bg-accent/40',
      )}
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm text-foreground">{title}</div>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
          {disabled && disabledHint ? disabledHint : body}
        </p>
      </div>
      <ChevronRight className="mt-1.5 size-4 shrink-0 text-muted-foreground" />
    </button>
  );
}
