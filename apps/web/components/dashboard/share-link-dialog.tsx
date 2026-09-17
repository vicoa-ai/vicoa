'use client';

// The share dialog (collaboration §8.4, P4): the "Link" tab. Mint a public or
// signed-in-only read link to a session, a project's sessions, or a project's
// task board; list the live links on that target; copy; revoke.
//
// The "People" tab (per-project grants) is P5 and sits here as a disabled tab
// so the seam is visible in the product rather than bolted on later.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Copy, Eye, Globe, Loader2, Lock, Trash2, Users } from 'lucide-react';
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
  { value: '1', label: '1 day', days: 1 },
  { value: '7', label: '7 days', days: 7 },
  { value: '30', label: '30 days', days: 30 },
  { value: '90', label: '90 days', days: 90 },
];

function kindLabel(kind: ShareKind): string {
  switch (kind) {
    case 'session':
      return 'Session';
    case 'project_sessions':
      return 'Sessions';
    case 'project_board':
      return 'Board';
  }
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
  const [audience, setAudience] = useState<ShareAudience>('public');
  const [expiry, setExpiry] = useState('never');
  const [allowComments, setAllowComments] = useState(false);
  const [statuses, setStatuses] = useState<TaskStatus[]>([]);
  const [labelIds, setLabelIds] = useState<string[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [labels, setLabels] = useState<TaskLabelResponse[]>([]);

  const [links, setLinks] = useState<ShareLinkResponse[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [justCreated, setJustCreated] = useState<string | null>(null);

  // Reset the form each time the dialog opens on a target.
  useEffect(() => {
    if (!open || !target) return;
    setKind(target.kind === 'session' ? 'session' : (target.initialKind ?? 'project_sessions'));
    setAudience('public');
    setExpiry('never');
    setAllowComments(false);
    setStatuses([]);
    setLabelIds([]);
    setIncludeArchived(false);
    setDateFrom('');
    setDateTo('');
    setCreateError(null);
    setJustCreated(null);
  }, [open, target]);

  const listTarget = useMemo(() => {
    if (!target) return null;
    return target.kind === 'session'
      ? { agent_instance_id: target.instanceId }
      : { project_id: target.projectId };
  }, [target]);

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
    if (!open || !api || !target || target.kind !== 'project') return;
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
  }, [open, api, target]);

  // Comments ride on a signed-in board link only; drop the flag when either
  // precondition goes away rather than letting the server 422.
  useEffect(() => {
    if (allowComments && (audience !== 'authenticated' || kind !== 'project_board')) {
      setAllowComments(false);
    }
  }, [allowComments, audience, kind]);

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
        expires_in_days: days,
        filters,
      });
      setJustCreated(link.id);
      setLinks((prev) => [link, ...(prev ?? [])]);
      void copy(shareUrl(link.token), link.id);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create link');
    } finally {
      setCreating(false);
    }
  }, [api, target, expiry, kind, statuses, labelIds, includeArchived, dateFrom, dateTo, audience, allowComments, copy]);

  const handleRevoke = useCallback(
    async (linkId: string) => {
      if (!api) return;
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
    [api],
  );

  const isProject = target?.kind === 'project';
  const showsTranscripts = kind !== 'project_board';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="custom-scrollbar font-mono sm:max-w-lg max-h-[90vh] overflow-y-auto overflow-x-hidden grid-cols-[minmax(0,1fr)]">
        <DialogHeader>
          <DialogTitle className="truncate">
            Share {target ? (target.kind === 'session' ? target.title || 'session' : target.name) : ''}
          </DialogTitle>
          <DialogDescription>
            A link is read-only. Anyone who opens it sees a live view — it keeps
            showing whatever happens next until you revoke it.
          </DialogDescription>
        </DialogHeader>

        {/* Tabs: Link (this phase) · People (P5). */}
        <div className="flex items-center gap-1 border-b border-border text-xs">
          <span className="border-b-2 border-foreground px-2 py-1.5 font-medium">Link</span>
          <span
            className="cursor-not-allowed px-2 py-1.5 text-muted-foreground/60"
            title="Invite people by email — coming soon"
          >
            <Users className="mr-1 inline h-3 w-3" />
            People
          </span>
        </div>

        {/* The one line that must never be softened (§8.4, §10.1). */}
        {showsTranscripts && (
          <div className="flex min-w-0 gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 break-words">{SHARE_SECRETS_WARNING}</span>
          </div>
        )}

        <div className="grid gap-3 text-xs">
          {isProject && (
            <div className="grid gap-1.5">
              <Label className="text-xs">What to share</Label>
              <div className="flex gap-1">
                {(['project_sessions', 'project_board'] as const).map((k) => (
                  <Button
                    key={k}
                    type="button"
                    size="sm"
                    variant={kind === k ? 'default' : 'outline'}
                    className="h-7 text-xs"
                    onClick={() => setKind(k)}
                  >
                    {k === 'project_sessions' ? 'Sessions' : 'Task board'}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="grid gap-1.5">
            <Label className="text-xs">Who can open it</Label>
            <div className="flex gap-1">
              <Button
                type="button"
                size="sm"
                variant={audience === 'public' ? 'default' : 'outline'}
                className="h-7 gap-1.5 text-xs"
                onClick={() => setAudience('public')}
              >
                <Globe className="h-3 w-3" />
                Anyone with the link
              </Button>
              <Button
                type="button"
                size="sm"
                variant={audience === 'authenticated' ? 'default' : 'outline'}
                className="h-7 gap-1.5 text-xs"
                onClick={() => setAudience('authenticated')}
              >
                <Lock className="h-3 w-3" />
                Vicoa users only
              </Button>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label className="text-xs">Expires</Label>
            <Select value={expiry} onValueChange={setExpiry}>
              <SelectTrigger className="h-8 w-40 text-xs">
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

          {kind === 'project_board' && (
            <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
              <div className="grid gap-0.5">
                <Label htmlFor="share-allow-comments" className="text-xs">
                  Allow comments
                </Label>
                <span className="text-[11px] text-muted-foreground">
                  {audience === 'authenticated'
                    ? 'Signed-in viewers can comment on tasks as themselves. Nothing else becomes editable.'
                    : 'Needs "Vicoa users only" — comments are attributed to a real account.'}
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
            <div className="grid gap-2">
              <Label className="text-xs">Narrow the board (optional)</Label>
              <div className="flex flex-wrap gap-1">
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
                <div className="flex flex-wrap gap-1">
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
          )}

          {kind === 'project_sessions' && (
            <div className="grid gap-2">
              <Label className="text-xs">Narrow the sessions (optional)</Label>
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex cursor-pointer items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={includeArchived}
                    onChange={(e) => setIncludeArchived(e.target.checked)}
                  />
                  Include archived sessions
                </label>
                <div className="flex items-center gap-1.5">
                  <span className="text-muted-foreground">From</span>
                  <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="h-7 w-36 text-xs" />
                  <span className="text-muted-foreground">to</span>
                  <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="h-7 w-36 text-xs" />
                </div>
              </div>
              <span className="text-[11px] text-muted-foreground">
                New sessions in this project appear automatically while the link is live.
              </span>
            </div>
          )}

          {createError && <p className="text-xs text-destructive">{createError}</p>}
          <Button size="sm" className="h-8 text-xs" onClick={() => void handleCreate()} disabled={!api || creating}>
            {creating ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : null}
            Create link
          </Button>
        </div>

        <div className="grid gap-2">
          <Label className="text-xs">Active links</Label>
          {links === null ? (
            <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading…
            </div>
          ) : links.length === 0 ? (
            <p className="py-1 text-xs text-muted-foreground">No links yet.</p>
          ) : (
            <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5">
              {links.map((link) => {
                const url = shareUrl(link.token);
                const isCopied = copied === link.id;
                const filterNote = describeFilters(link);
                return (
                  <li
                    key={link.id}
                    className={cn(
                      'flex min-w-0 items-center gap-2 overflow-hidden rounded-md border px-2.5 py-1.5',
                      justCreated === link.id ? 'border-foreground/40 bg-foreground/5' : 'border-border',
                    )}
                  >
                    {link.audience === 'public' ? (
                      <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <Lock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-xs">
                        <span className="font-medium">{kindLabel(link.kind)}</span>
                        <span className="text-muted-foreground">·</span>
                        <span className="text-muted-foreground">
                          {link.audience === 'public' ? 'anyone' : 'Vicoa users'}
                        </span>
                        {link.allow_comments && (
                          <>
                            <span className="text-muted-foreground">·</span>
                            <span className="text-muted-foreground">comments</span>
                          </>
                        )}
                        {filterNote && (
                          <>
                            <span className="text-muted-foreground">·</span>
                            <span className="text-muted-foreground">{filterNote}</span>
                          </>
                        )}
                      </div>
                      <div className="min-w-0 truncate text-[11px] text-muted-foreground" title={url}>
                        {url}
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                        <span>{formatExpiry(link.expires_at)}</span>
                        <span>·</span>
                        <Eye className="h-3 w-3" />
                        <span>{link.view_count}</span>
                      </div>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-7 gap-1 px-2 text-xs"
                      onClick={() => void copy(url, link.id)}
                    >
                      {isCopied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
                      {isCopied ? 'Copied' : 'Copy'}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                      title="Revoke link"
                      aria-label="Revoke link"
                      disabled={revoking === link.id}
                      onClick={() => void handleRevoke(link.id)}
                    >
                      {revoking === link.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
          {loadError && <p className="text-xs text-destructive">{loadError}</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
