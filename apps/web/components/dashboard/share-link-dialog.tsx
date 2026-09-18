'use client';

// The share dialog (collaboration §8.4, P4). Link-first: the link IS the
// dialog. Opening it on a target that already has a live link shows that link
// and a Copy button — the one-click path that covers almost every reopen.
// With no link yet, the same slot holds a small composer (who can open it,
// expiry, and for a project the kind and filters) and a Create button that
// mints the link and copies it in one go. Everything else — other links,
// revoke — is behind a disclosure so the default view is one field and one
// button.
//
// The "People" tab (per-project grants) is P5; it is not drawn until it works.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Copy,
  Eye,
  Globe,
  Link2,
  Loader2,
  Lock,
  Trash2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import type {
  ShareAudience,
  ShareBoardFilters,
  ShareKind,
  ShareLinkResponse,
  ShareSessionsFilters,
  TaskLabelResponse,
  TaskStatus,
} from '@/lib/backend-api';
import { shareUrl } from '@/lib/public-share-api';
import { useCopyToClipboard } from '@/lib/hooks/use-session-operations';
import { STATUS_CONFIG, STATUS_ORDER } from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';

/**
 * The exact line every link-creation surface must carry (§8.4). Redaction is
 * a non-goal (§10.1); this sentence is the mitigation, so it is not softened.
 */
export const SHARE_SECRETS_WARNING =
  'Anyone with this link can read the full transcript, including any file contents or credentials the agent printed.';

export type ShareTarget =
  | { kind: 'session'; instanceId: string; title: string }
  | {
      kind: 'project';
      projectId: string;
      name: string;
      /** Which project kind the dialog opens on (the board header opens on the board). */
      initialKind?: 'project_sessions' | 'project_board';
    };

const EXPIRY_OPTIONS: { value: string; label: string; days: number | null }[] = [
  { value: 'never', label: 'Never', days: null },
  { value: '1', label: 'In 1 day', days: 1 },
  { value: '7', label: 'In 7 days', days: 7 },
  { value: '30', label: 'In 30 days', days: 30 },
  { value: '90', label: 'In 90 days', days: 90 },
];

const AUDIENCE_LABEL: Record<ShareAudience, string> = {
  public: 'Anyone with the link',
  authenticated: 'Vicoa users only',
};

function AudienceIcon({ audience, className }: { audience: ShareAudience; className?: string }) {
  return audience === 'public' ? <Globe className={className} /> : <Lock className={className} />;
}

function formatExpiry(iso: string | null): string {
  if (!iso) return 'Never expires';
  const when = new Date(iso);
  if (when.getTime() < Date.now()) return 'Expired';
  return `Expires ${when.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
}

function describeFilters(link: ShareLinkResponse): string | null {
  const f = link.filters;
  if (!f) return null;
  const parts: string[] = [];
  if (link.kind === 'project_board') {
    const board = f as ShareBoardFilters;
    if (board.statuses?.length) parts.push(`${board.statuses.length} status${board.statuses.length === 1 ? '' : 'es'}`);
    if (board.label_ids?.length) parts.push(`${board.label_ids.length} label${board.label_ids.length === 1 ? '' : 's'}`);
  } else if (link.kind === 'project_sessions') {
    const sessions = f as ShareSessionsFilters;
    if (sessions.statuses?.length) parts.push('incl. archived');
    if (sessions.date_from || sessions.date_to) parts.push('date range');
  }
  return parts.length ? parts.join(' · ') : null;
}

/** "Anyone with the link · Never expires · 12 views · comments" for one link. */
function LinkFacts({ link, className }: { link: ShareLinkResponse; className?: string }) {
  const filterNote = describeFilters(link);
  return (
    <span className={cn('inline-flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5', className)}>
      <span className="inline-flex items-center gap-1">
        <AudienceIcon audience={link.audience} className="h-3 w-3" />
        {AUDIENCE_LABEL[link.audience]}
      </span>
      <span>·</span>
      <span>{formatExpiry(link.expires_at)}</span>
      <span>·</span>
      <span className="inline-flex items-center gap-1" title="Views">
        <Eye className="h-3 w-3" />
        {link.view_count}
      </span>
      {link.allow_comments && (
        <>
          <span>·</span>
          <span>Comments on</span>
        </>
      )}
      {link.show_owner && (
        <>
          <span>·</span>
          <span>Name shown</span>
        </>
      )}
      {link.show_branch && (
        <>
          <span>·</span>
          <span>Branches shown</span>
        </>
      )}
      {filterNote && (
        <>
          <span>·</span>
          <span>{filterNote}</span>
        </>
      )}
    </span>
  );
}

function ToggleChip({
  active,
  onClick,
  children,
  style,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={style}
      className={cn(
        'cursor-pointer rounded-full border px-2 py-0.5 text-[11px] transition-colors',
        active
          ? 'border-foreground/40 bg-foreground/10 text-foreground'
          : 'border-border text-muted-foreground hover:bg-muted',
      )}
    >
      {children}
    </button>
  );
}

/** A collapsed row that opens into its children; the chevron is the only affordance it needs. */
function Disclosure({
  label,
  open,
  onToggle,
  children,
}: {
  label: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-fit cursor-pointer items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronRight className={cn('h-3 w-3 transition-transform', open && 'rotate-90')} />
        {label}
      </button>
      {open && children}
    </div>
  );
}

/**
 * The stock trigger rings on `focus:`, so a mouse pick leaves a ring on the
 * closed select. Ring on keyboard focus only.
 */
const SELECT_TRIGGER = 'h-9 text-xs focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-ring';

/** A labelled switch, inline: the dialog's boolean control (see "Allow comments"). */
function SwitchOption({
  id,
  checked,
  onCheckedChange,
  children,
}: {
  id: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
      <Label htmlFor={id} className="cursor-pointer text-xs font-normal">
        {children}
      </Label>
    </div>
  );
}

/** Two-way pill switch, for the project kinds. */
function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="tablist" className="inline-flex w-fit rounded-md bg-muted p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'cursor-pointer rounded-[5px] px-2.5 py-1 text-xs transition-colors',
            value === o.value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ShareLinkDialog({
  open,
  onOpenChange,
  target,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: ShareTarget | null;
}) {
  const { api } = useAgentDashboard();
  const { copied, copy } = useCopyToClipboard();

  const [kind, setKind] = useState<ShareKind>('session');
  // Composer.
  const [audience, setAudience] = useState<ShareAudience>('public');
  const [expiry, setExpiry] = useState('never');
  const [allowComments, setAllowComments] = useState(false);
  const [showOwner, setShowOwner] = useState(false);
  const [showBranch, setShowBranch] = useState(false);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [labelIds, setLabelIds] = useState<string[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [labels, setLabels] = useState<TaskLabelResponse[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  /** The visitor asked for a new link although one already exists. */
  const [composing, setComposing] = useState(false);

  const [links, setLinks] = useState<ShareLinkResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [othersOpen, setOthersOpen] = useState(false);

  // The target's identity as a string. Callers may pass a fresh object literal
  // on every render (the session page does, and it re-renders on every WS
  // frame); keying the effects on the object would reset the form and refetch
  // the links on each of those renders, which reads as the dialog twitching.
  const targetKey = target
    ? target.kind === 'session'
      ? `session:${target.instanceId}`
      : `project:${target.projectId}:${target.initialKind ?? ''}`
    : null;
  const initialKind: ShareKind =
    target?.kind === 'project' ? (target.initialKind ?? 'project_sessions') : 'session';

  // Reset the form each time the dialog opens on a target.
  useEffect(() => {
    if (!open || !targetKey) return;
    setKind(initialKind);
    setAudience('public');
    setExpiry('never');
    setAllowComments(false);
    setShowOwner(false);
    setShowBranch(false);
    setStatuses([]);
    setLabelIds([]);
    setIncludeArchived(false);
    setDateFrom('');
    setDateTo('');
    setFiltersOpen(false);
    setComposing(false);
    setCreateError(null);
    setConfirmRevoke(null);
    setOthersOpen(false);
  }, [open, targetKey, initialKind]);

  // Switching kind is switching subject: back to that kind's link, not the
  // composer, and the other kind's filters do not carry over.
  useEffect(() => {
    setComposing(false);
    setConfirmRevoke(null);
    setFiltersOpen(false);
    setStatuses([]);
    setLabelIds([]);
    setIncludeArchived(false);
    setDateFrom('');
    setDateTo('');
  }, [kind]);

  const targetInstanceId = target?.kind === 'session' ? target.instanceId : null;
  const targetProjectId = target?.kind === 'project' ? target.projectId : null;
  const listTarget = useMemo(() => {
    if (targetInstanceId) return { agent_instance_id: targetInstanceId };
    if (targetProjectId) return { project_id: targetProjectId };
    return null;
  }, [targetInstanceId, targetProjectId]);

  const reload = useCallback(async () => {
    if (!api || !listTarget) return;
    try {
      setLoadError(null);
      setLinks(await api.listShareLinks(listTarget));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load links');
      setLinks([]);
    }
  }, [api, listTarget]);

  useEffect(() => {
    if (!open) return;
    setLinks(null);
    void reload();
  }, [open, reload]);

  // Board filters need the project's label vocabulary.
  useEffect(() => {
    if (!open || !api || !targetProjectId) return;
    let cancelled = false;
    api
      .listTaskLabels()
      .then((rows) => {
        if (!cancelled) setLabels(rows);
      })
      .catch(() => {
        if (!cancelled) setLabels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, api, targetProjectId]);

  // Comments ride on a signed-in board link only; drop the flag when either
  // precondition goes away rather than letting the server 422.
  useEffect(() => {
    if (allowComments && (audience !== 'authenticated' || kind !== 'project_board')) {
      setAllowComments(false);
    }
  }, [allowComments, audience, kind]);

  // Newest live link of the current kind is "the link"; the rest are "others".
  const kindLinks = useMemo(
    () =>
      (links ?? [])
        .filter((l) => l.kind === kind)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [links, kind],
  );
  const current = kindLinks[0] ?? null;
  const others = kindLinks.slice(1);
  const showComposer = links !== null && (current === null || composing);
  const showsTranscripts = kind !== 'project_board';

  const handleCreate = useCallback(async () => {
    if (!api || !target) return;
    setCreating(true);
    setCreateError(null);
    try {
      const days = EXPIRY_OPTIONS.find((o) => o.value === expiry)?.days ?? null;
      let filters: ShareBoardFilters | ShareSessionsFilters | null = null;
      if (kind === 'project_board') {
        const f: ShareBoardFilters = {};
        if (statuses.length) f.statuses = statuses;
        if (labelIds.length) f.label_ids = labelIds;
        filters = Object.keys(f).length ? f : null;
      } else if (kind === 'project_sessions') {
        const f: ShareSessionsFilters = {};
        if (includeArchived) {
          f.statuses = ['STARTING', 'ACTIVE', 'AWAITING_INPUT', 'REVIEWED', 'PAUSED', 'STALE', 'COMPLETED', 'FAILED', 'KILLED', 'DISCONNECTED'];
        }
        if (dateFrom) f.date_from = `${dateFrom}T00:00:00Z`;
        if (dateTo) f.date_to = `${dateTo}T23:59:59Z`;
        filters = Object.keys(f).length ? f : null;
      }
      const link = await api.createShareLink({
        kind,
        ...(target.kind === 'session'
          ? { agent_instance_id: target.instanceId }
          : { project_id: target.projectId }),
        audience,
        allow_comments: allowComments,
        show_owner: showOwner,
        show_branch: showsTranscripts && showBranch,
        expires_in_days: days,
        filters,
      });
      setLinks((prev) => [link, ...(prev ?? [])]);
      setComposing(false);
      // One click: the new link is on the clipboard before the dialog re-renders.
      void copy(shareUrl(link.token), link.id);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create link');
    } finally {
      setCreating(false);
    }
  }, [api, target, expiry, kind, statuses, labelIds, includeArchived, dateFrom, dateTo, audience, allowComments, showOwner, showBranch, showsTranscripts, copy]);

  const handleRevoke = useCallback(
    async (linkId: string) => {
      if (!api) return;
      // Revoking kills the link for everyone who has it: ask once, inline.
      if (confirmRevoke !== linkId) {
        setConfirmRevoke(linkId);
        return;
      }
      setConfirmRevoke(null);
      setRevoking(linkId);
      try {
        await api.revokeShareLink(linkId);
        setLinks((prev) => (prev ?? []).filter((l) => l.id !== linkId));
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : 'Failed to revoke link');
      } finally {
        setRevoking(null);
      }
    },
    [api, confirmRevoke],
  );

  const isProject = target?.kind === 'project';
  const title = target ? (target.kind === 'session' ? target.title || 'session' : target.name) : '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="custom-scrollbar max-h-[90vh] grid-cols-[minmax(0,1fr)] gap-6 overflow-y-auto overflow-x-hidden font-mono sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="truncate">Share “{title}”</DialogTitle>
          <DialogDescription>
            Anyone who opens this link gets a live, read-only view that keeps updating until you revoke it.
          </DialogDescription>
        </DialogHeader>

        {isProject && (
          <Segmented
            value={kind as 'project_sessions' | 'project_board'}
            onChange={(k) => setKind(k)}
            options={[
              { value: 'project_sessions', label: 'Sessions' },
              { value: 'project_board', label: 'Task board' },
            ]}
          />
        )}

        {/* The link slot: the current link, or the composer for the first one. */}
        {links === null ? (
          <div className="flex h-9 items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading…
          </div>
        ) : !showComposer && current ? (
          <div className="grid gap-2.5">
            <div className="flex gap-2">
              <Input
                readOnly
                value={shareUrl(current.token)}
                onFocus={(e) => e.currentTarget.select()}
                aria-label="Share link"
                className="h-9 min-w-0 flex-1 text-xs"
              />
              <Button
                type="button"
                size="sm"
                className="h-9 w-[6.5rem] shrink-0 gap-1.5 px-3 text-xs"
                onClick={() => void copy(shareUrl(current.token), current.id)}
              >
                {copied === current.id ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied === current.id ? 'Copied' : 'Copy link'}
              </Button>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
              <LinkFacts link={current} className="min-w-0 flex-1" />
              <span className="ml-auto inline-flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => setComposing(true)}
                  className="cursor-pointer underline-offset-2 hover:text-foreground hover:underline"
                >
                  New link
                </button>
                <button
                  type="button"
                  onClick={() => void handleRevoke(current.id)}
                  disabled={revoking === current.id}
                  className={cn(
                    'cursor-pointer underline-offset-2 hover:underline',
                    confirmRevoke === current.id ? 'text-destructive' : 'hover:text-destructive',
                  )}
                >
                  {revoking === current.id ? 'Revoking…' : confirmRevoke === current.id ? 'Revoke for everyone?' : 'Revoke'}
                </button>
              </span>
            </div>
          </div>
        ) : (
          <div className="grid gap-5">
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label className="text-xs">Who can open it</Label>
                <Select value={audience} onValueChange={(v) => setAudience(v as ShareAudience)}>
                  <SelectTrigger className={SELECT_TRIGGER}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="font-mono text-xs">
                    {(['public', 'authenticated'] as const).map((a) => (
                      <SelectItem key={a} value={a} className="text-xs">
                        <span className="inline-flex items-center gap-1.5">
                          <AudienceIcon audience={a} className="h-3 w-3" />
                          {AUDIENCE_LABEL[a]}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label className="text-xs">Expires</Label>
                <Select value={expiry} onValueChange={setExpiry}>
                  <SelectTrigger className={SELECT_TRIGGER}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="font-mono text-xs">
                    {EXPIRY_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value} className="text-xs">
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* What the page says about you and the work. Both off by default:
                the share is the transcript, not the person; a branch name is
                repo-internal like the path, which a public page never shows. */}
            <div className="grid gap-2.5">
              <Label className="text-xs">Viewers can see</Label>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
                <SwitchOption id="share-show-owner" checked={showOwner} onCheckedChange={setShowOwner}>
                  My name
                </SwitchOption>
                {showsTranscripts && (
                  <SwitchOption id="share-show-branch" checked={showBranch} onCheckedChange={setShowBranch}>
                    Branch names
                  </SwitchOption>
                )}
              </div>
            </div>

            {kind === 'project_board' && (
              <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
                <div className="grid gap-0.5">
                  <Label htmlFor="share-allow-comments" className="text-xs">
                    Allow comments
                  </Label>
                  <span className="text-[11px] text-muted-foreground">
                    {audience === 'authenticated'
                      ? 'Signed-in viewers can comment on tasks as themselves. Nothing else becomes editable.'
                      : 'Needs “Vicoa users only” so comments are attributed to a real account.'}
                  </span>
                </div>
                <Switch
                  id="share-allow-comments"
                  checked={allowComments}
                  disabled={audience !== 'authenticated'}
                  onCheckedChange={setAllowComments}
                />
              </div>
            )}

            {kind === 'project_board' && (
              <Disclosure label="Narrow the board (optional)" open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}>
                <div className="grid gap-3">
                  <div className="flex flex-wrap gap-1.5">
                    {STATUS_ORDER.map((status) => (
                      <ToggleChip
                        key={status}
                        active={statuses.includes(status)}
                        onClick={() =>
                          setStatuses((prev) =>
                            prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
                          )
                        }
                      >
                        {STATUS_CONFIG[status].label}
                      </ToggleChip>
                    ))}
                  </div>
                  {labels.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {labels.map((label) => (
                        <ToggleChip
                          key={label.id}
                          active={labelIds.includes(label.id)}
                          onClick={() =>
                            setLabelIds((prev) =>
                              prev.includes(label.id) ? prev.filter((id) => id !== label.id) : [...prev, label.id],
                            )
                          }
                          style={labelIds.includes(label.id) ? { borderColor: label.color, color: label.color } : undefined}
                        >
                          {label.name}
                        </ToggleChip>
                      ))}
                    </div>
                  )}
                  <span className="text-[11px] text-muted-foreground">
                    Nothing selected shares every task. Filters apply live, so tasks that match later appear too.
                  </span>
                </div>
              </Disclosure>
            )}

            {kind === 'project_sessions' && (
              <Disclosure label="Narrow the sessions (optional)" open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}>
                <div className="grid gap-3">
                  <SwitchOption id="share-include-archived" checked={includeArchived} onCheckedChange={setIncludeArchived}>
                    Include archived sessions
                  </SwitchOption>
                  <div className="flex flex-wrap items-center gap-1.5 text-xs">
                    <span className="text-muted-foreground">From</span>
                    <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="h-7 w-36 text-xs" />
                    <span className="text-muted-foreground">to</span>
                    <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="h-7 w-36 text-xs" />
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    New sessions in this project appear automatically while the link is live.
                  </span>
                </div>
              </Disclosure>
            )}

            {createError && <p className="text-xs text-destructive">{createError}</p>}
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                className="h-9 flex-1 gap-1.5 text-xs"
                onClick={() => void handleCreate()}
                disabled={!api || creating}
              >
                {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
                Create link
              </Button>
              {current && (
                <Button type="button" size="sm" variant="ghost" className="h-9 text-xs" onClick={() => setComposing(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}

        {/* The one line that must never be softened (§8.4, §10.1). */}
        {showsTranscripts && (
          <p className="flex min-w-0 gap-1.5 text-[11px] leading-snug text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="min-w-0 break-words">{SHARE_SECRETS_WARNING}</span>
          </p>
        )}

        {others.length > 0 && (
          <Disclosure
            label={`${others.length} other ${others.length === 1 ? 'link' : 'links'}`}
            open={othersOpen}
            onToggle={() => setOthersOpen((v) => !v)}
          >
            <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5">
              {others.map((link) => {
                const url = shareUrl(link.token);
                return (
                  <li
                    key={link.id}
                    className="flex min-w-0 items-center gap-2 overflow-hidden rounded-md border border-border px-2.5 py-1.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[11px]" title={url}>
                        {url.replace(/^https?:\/\//, '')}
                      </div>
                      <LinkFacts link={link} className="text-[11px] text-muted-foreground" />
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                      title="Copy link"
                      aria-label="Copy link"
                      onClick={() => void copy(url, link.id)}
                    >
                      {copied === link.id ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className={cn(
                        'h-7 gap-1 px-1.5 text-[11px] text-muted-foreground hover:text-destructive',
                        confirmRevoke === link.id && 'text-destructive',
                      )}
                      title="Revoke link"
                      aria-label="Revoke link"
                      disabled={revoking === link.id}
                      onClick={() => void handleRevoke(link.id)}
                    >
                      {revoking === link.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <>
                          <Trash2 className="h-3 w-3" />
                          {confirmRevoke === link.id && 'Sure?'}
                        </>
                      )}
                    </Button>
                  </li>
                );
              })}
            </ul>
          </Disclosure>
        )}
        {loadError && <p className="text-xs text-destructive">{loadError}</p>}
      </DialogContent>
    </Dialog>
  );
}
