'use client';

import { useState } from 'react';
import {
  Check,
  ChevronDown,
  Flame,
  Hammer,
  Info,
  Loader2,
  NotebookPen,
  PencilLine,
  Shield,
  SlidersHorizontal,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';

/**
 * Session config as three inline chips — Model (agent icon + model), Effort
 * ("High", "Extra High", …) and Permission/Mode (icon + label) — replacing
 * the old single gear dropdown. Each chip opens its own list; the current
 * choice carries a tick, and picking one applies it and closes the list.
 */

export interface SessionConfigChipsProps {
  disabled?: boolean;
  /** Agent type for the model chip's icon (e.g. 'claude', 'codex'). */
  agentTypeName?: string;
  // Model (all agents)
  models?: { id: string; label: string }[];
  currentModel?: string | null;
  pendingModel?: string | null;
  onModelChange?: (id: string) => void;
  // Effort: "Thinking" for claude, "Reasoning" for codex
  efforts?: { id: string; label: string }[];
  effortLabel?: string;
  currentEffort?: string | null;
  pendingEffort?: string | null;
  onEffortChange?: (id: string) => void;
  // Permission mode (claude / codex)
  permissionModes?: { value: string; label: string }[];
  currentPermissionMode?: string | null;
  pendingPermissionMode?: string | null;
  onPermissionModeChange?: (mode: string) => void;
  showYoloInfo?: boolean;
  // OpenCode mode
  opencodeModes?: { value: string; label: string }[];
  currentOpencodeMode?: string | null;
  pendingOpencodeMode?: string | null;
  onOpencodeMode?: (mode: string) => void;
  /** Kept for API compatibility; chips always render single-column lists. */
  singleColumnModels?: boolean;
}

/** Leading icon for a permission / opencode mode value. */
export function ModeIcon({ value, className }: { value: string; className?: string }) {
  const icons: Record<string, typeof Shield> = {
    default: Shield,
    plan: NotebookPen,
    auto: Zap,
    acceptEdits: PencilLine,
    bypassPermissions: Flame,
    build: Hammer,
  };
  const Icon = icons[value] ?? SlidersHorizontal;
  return <Icon className={className ?? 'h-3.5 w-3.5'} />;
}

const CHIP_CLASS =
  'flex h-6 max-w-44 min-w-0 shrink items-center gap-1.5 rounded-lg px-2 text-xs text-muted-foreground transition-colors hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50';

export function TickItem({
  label,
  isSelected,
  isPending,
  disabled,
  onClick,
  leading,
  yoloInfo,
}: {
  label: string;
  isSelected: boolean;
  isPending: boolean;
  disabled?: boolean;
  onClick: () => void;
  leading?: React.ReactNode;
  yoloInfo?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="group/item relative flex w-full cursor-pointer select-none items-center gap-2 rounded-sm border-0 px-3 py-1.5 text-xs outline-none transition-colors duration-100 hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
    >
      {leading}
      <span className="min-w-0 flex-1 truncate text-left">{label}</span>
      <span className="flex w-4 flex-shrink-0 items-center justify-center">
        {isPending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : isSelected ? (
          <Check className="h-3.5 w-3.5" />
        ) : null}
      </span>
      {yoloInfo && (
        <span className="relative inline-flex flex-shrink-0 items-center text-muted-foreground" aria-label="YOLO mode availability">
          <span className="group inline-flex items-center" tabIndex={0}>
            <Info className="h-3.5 w-3.5" />
            <span className="pointer-events-none absolute right-full top-0 z-50 mr-2 w-72 rounded-md border border-border bg-popover px-2 py-1 text-[11px] font-normal normal-case text-foreground opacity-0 shadow-md transition-opacity duration-100 group-hover:opacity-100 group-focus-visible:opacity-100">
              YOLO mode appears only for sessions started from the web or mobile, or launched with --dangerously-skip-permissions in the CLI.
            </span>
          </span>
        </span>
      )}
    </button>
  );
}

/** One chip + its dropdown list. */
export function ChipDropdown({
  chip,
  title,
  disabled,
  children,
  contentClassName,
  side = 'top',
}: {
  chip: React.ReactNode;
  title: string;
  disabled?: boolean;
  children: (close: () => void) => React.ReactNode;
  contentClassName?: string;
  /** Which side to prefer; Radix flips on collision. New-session opens up
   *  (chips sit at the screen bottom); the automation panel opens down. */
  side?: 'top' | 'bottom';
}) {
  const [open, setOpen] = useState(false);
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button type="button" title={title} disabled={disabled} className={CHIP_CLASS}>
          {chip}
          <ChevronDown className="h-3 w-3 flex-shrink-0 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side={side}
        className={cn(
          // Lifted border so the list clearly separates from the input surface.
          'max-h-72 overflow-y-auto rounded-xl border border-foreground/15 p-1 font-mono shadow-xl custom-scrollbar',
          contentClassName,
        )}
      >
        {/* Dimmed panel label, pinned while the list scrolls. Left padding
            matches the items' px-3 so it lines up with their content column. */}
        <div className="sticky top-0 z-10 bg-menu px-3 pb-1.5 pt-1 text-xs text-muted-foreground/60">
          {title}
        </div>
        {children(() => setOpen(false))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function SessionConfigChips({
  disabled,
  agentTypeName,
  models,
  currentModel,
  pendingModel,
  onModelChange,
  efforts,
  effortLabel = 'Thinking',
  currentEffort,
  pendingEffort,
  onEffortChange,
  permissionModes,
  currentPermissionMode,
  pendingPermissionMode,
  onPermissionModeChange,
  showYoloInfo = false,
  opencodeModes,
  currentOpencodeMode,
  pendingOpencodeMode,
  onOpencodeMode,
}: SessionConfigChipsProps) {
  const hasModels = models && models.length > 0 && !!onModelChange;
  const hasEfforts = efforts && efforts.length > 0 && !!onEffortChange;
  const hasPermissions = permissionModes && permissionModes.length > 0 && !!onPermissionModeChange;
  const hasOpencode = opencodeModes && opencodeModes.length > 0 && !!onOpencodeMode;

  if (!hasModels && !hasEfforts && !hasPermissions && !hasOpencode) return null;

  const modelLabel =
    (pendingModel && models?.find((m) => m.id === pendingModel)?.label) ??
    models?.find((m) => m.id === currentModel)?.label ??
    currentModel ??
    'Model';
  const effortChipLabel =
    (pendingEffort && efforts?.find((e) => e.id === pendingEffort)?.label) ??
    efforts?.find((e) => e.id === currentEffort)?.label ??
    effortLabel;
  const permissionValue = pendingPermissionMode ?? currentPermissionMode ?? 'default';
  const permissionLabel =
    permissionModes?.find((m) => m.value === permissionValue)?.label ?? 'Permission';
  const opencodeValue = pendingOpencodeMode ?? currentOpencodeMode ?? 'build';
  const opencodeLabel =
    opencodeModes?.find((m) => m.value === opencodeValue)?.label ?? 'Mode';

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      {hasModels && (
        <ChipDropdown
          title="Model"
          disabled={disabled}
          contentClassName="w-56"
          chip={
            <>
              {pendingModel ? (
                <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" />
              ) : (
                <AgentTypeIcon agentTypeName={agentTypeName ?? null} size={12} whiteForOpenAI />
              )}
              <span className="min-w-0 truncate">{modelLabel}</span>
            </>
          }
        >
          {(close) =>
            models!.map((m) => (
              <TickItem
                key={m.id}
                label={m.label}
                isSelected={m.id === currentModel}
                isPending={m.id === pendingModel}
                disabled={!!pendingModel}
                onClick={() => { onModelChange!(m.id); close(); }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {hasEfforts && (
        <ChipDropdown
          title={effortLabel}
          disabled={disabled}
          contentClassName="w-44"
          chip={
            <>
              {pendingEffort && <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" />}
              <span className="min-w-0 truncate">{effortChipLabel}</span>
            </>
          }
        >
          {(close) =>
            efforts!.map((e) => (
              <TickItem
                key={e.id}
                label={e.label}
                isSelected={e.id === currentEffort}
                isPending={e.id === pendingEffort}
                disabled={!!pendingEffort}
                onClick={() => { onEffortChange!(e.id); close(); }}
              />
            ))
          }
        </ChipDropdown>
      )}

      {hasPermissions && (
        <ChipDropdown
          title="Mode"
          disabled={disabled}
          contentClassName="w-52"
          chip={
            <>
              {pendingPermissionMode ? (
                <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" />
              ) : (
                <ModeIcon value={permissionValue} className="h-3.5 w-3.5 flex-shrink-0" />
              )}
              <span className="min-w-0 truncate">{permissionLabel}</span>
            </>
          }
        >
          {(close) =>
            permissionModes!.map((mode) => (
              <TickItem
                key={mode.value}
                label={mode.label}
                leading={<ModeIcon value={mode.value} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                isSelected={mode.value === currentPermissionMode}
                isPending={mode.value === pendingPermissionMode}
                disabled={!!pendingPermissionMode}
                onClick={() => { onPermissionModeChange!(mode.value); close(); }}
                yoloInfo={showYoloInfo && mode.value === 'bypassPermissions'}
              />
            ))
          }
        </ChipDropdown>
      )}

      {hasOpencode && (
        <ChipDropdown
          title="Mode"
          disabled={disabled}
          contentClassName="w-44"
          chip={
            <>
              {pendingOpencodeMode ? (
                <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin" />
              ) : (
                <ModeIcon value={opencodeValue} className="h-3.5 w-3.5 flex-shrink-0" />
              )}
              <span className="min-w-0 truncate">{opencodeLabel}</span>
            </>
          }
        >
          {(close) =>
            opencodeModes!.map((mode) => (
              <TickItem
                key={mode.value}
                label={mode.label}
                leading={<ModeIcon value={mode.value} className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />}
                isSelected={mode.value === currentOpencodeMode}
                isPending={mode.value === pendingOpencodeMode}
                disabled={!!pendingOpencodeMode}
                onClick={() => { onOpencodeMode!(mode.value); close(); }}
              />
            ))
          }
        </ChipDropdown>
      )}
    </div>
  );
}
