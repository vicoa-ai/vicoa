'use client';

// The share dialog (collaboration §8.4, P4). Link-first: the link IS the
// dialog. Opening it on a target that already has a live link shows that link
// and a Copy button — the one-click path that covers almost every reopen.
// With no link yet, the same slot holds a small composer (who can open it,
// expiry, and for a project the filters) and a Create button that mints the
// link and copies it in one go. Its settings and the other links stay folded
// away, so the default view is one field and one button.
//
// The facts line under the link is also the way into its settings: it already
// says what the controls say, so it opens them rather than standing beside a
// button that does. Editing is not a mode and there is no Save — each change
// is a PATCH, and that line is the receipt, re-rendered from the server's
// answer. The token never changes, so every copy of the URL already sent out
// keeps working and starts obeying the new settings.
//
// The two rare things you can do to a live link — revoke it, mint a second one
// — sit in a footer at a weight that says so, where neither competes with Copy
// for the eye or for the click.
//
// One dialog shares one subject: a session, or a project. A project link is
// one URL with a content selection — "Tasks" and "Sessions", the same two
// halves a project grant names — rather than one link per kind of content,
// which made sharing a project twice produce two URLs that had to explain
// themselves to each other. Where the dialog was opened only decides which
// half starts ticked. Sharing is never a page.
//
// `ShareLinkPanel` is the body without the Dialog chrome, for any other host.
//
// The "People" tab (per-project grants) is P5; it is not drawn until it works.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
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
import type BackendAPI from '@/lib/backend-api';
import type {
  ShareAudience,
  ShareLinkResponse,
  ShareScope,
  TaskLabelResponse,
  TaskStatus,
  UpdateShareLinkRequest,
  UserProfile,
} from '@/lib/backend-api';
import { shareUrl } from '@/lib/public-share-api';
import {
  buildShareFilters,
  filterFieldsFromLink,
  formDiffersFromLink,
  KEEP_EXPIRY,
  SCOPE_ORDER,
  settingsKey,
} from '@/lib/share-link-settings';
import { useCopyToClipboard } from '@/lib/hooks/use-session-operations';
import { DatePickerPill, STATUS_CONFIG, STATUS_ORDER } from '@/components/dashboard/task-ui';
import { cn } from '@/lib/utils';

export type ShareTarget =
  | { kind: 'session'; instanceId: string; title: string }
  | {
      kind: 'project';
      projectId: string;
      name: string;
      /** Which half the composer starts on: the Tasks page ticks tasks, the sidebar sessions. */
      initialScope: ShareScope;
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

const SCOPE_LABEL: Record<ShareScope, string> = { tasks: 'Tasks', sessions: 'Sessions' };

/** "Tasks and sessions" / "Tasks" — what a project link carries, in words. */
function describeScopes(scopes: ShareScope[]): string {
  const named = SCOPE_ORDER.filter((s) => scopes.includes(s)).map((s) => SCOPE_LABEL[s]);
  return named.length === 2 ? 'Tasks and sessions' : (named[0] ?? 'Nothing');
}

/** How long a burst of changes collects before it becomes one PATCH. */
const LIVE_SAVE_DELAY_MS = 450;

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
  const { tasks, sessions } = f;
  if (tasks?.statuses?.length) parts.push(`${tasks.statuses.length} status${tasks.statuses.length === 1 ? '' : 'es'}`);
  if (tasks?.label_ids?.length) parts.push(`${tasks.label_ids.length} label${tasks.label_ids.length === 1 ? '' : 's'}`);
  if (sessions?.statuses?.length) parts.push('incl. archived');
  if (sessions?.date_from || sessions?.date_to) parts.push('date range');
  return parts.length ? parts.join(' · ') : null;
}

/** "Anyone with the link · Never expires · 12 views · comments" for one link. */
function LinkFacts({ link, className }: { link: ShareLinkResponse; className?: string }) {
  const filterNote = describeFilters(link);
  return (
    <span className={cn('inline-flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5', className)}>
      {link.kind === 'project' && (
        <>
          <span className="text-foreground/80">{describeScopes(link.scopes)}</span>
          <span>·</span>
        </>
      )}
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

/**
 * The panel's own buttons: no browser outline, a thin ring on keyboard focus
 * only — a click must not leave a ring behind on the thing it picked.
 */
const FOCUS_RING = 'outline-none focus-visible:ring-1 focus-visible:ring-ring';

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
        FOCUS_RING,
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
        className={cn(
          'flex w-fit cursor-pointer items-center gap-1 rounded text-[11px] text-muted-foreground transition-colors hover:text-foreground',
          FOCUS_RING,
        )}
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

/** A labelled switch, inline: the panel's boolean control (see "Allow comments"). */
function SwitchOption({
  id,
  checked,
  onCheckedChange,
  disabled,
  children,
}: {
  id: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  /** For the one switch that may not be turned off: a project link's last scope. */
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
      <Label
        htmlFor={id}
        className={cn('cursor-pointer text-xs font-normal', disabled && 'cursor-default opacity-60')}
      >
        {children}
      </Label>
    </div>
  );
}

/**
 * Set a display name from inside the dialog.
 *
 * The backend never falls back to an email on a public surface (§10.4), so an
 * account with no `display_name` publishes as "Owner" even with the switch on
 * — which reads as the switch not working. Most accounts get a name from their
 * identity provider (the backend backfills it on sign-in); this is for the
 * ones whose provider publishes none: fix it here rather than sending someone
 * to Settings in the middle of sharing.
 */
function OwnerNameField({ api, onSaved }: { api: BackendAPI | null; onSaved: (name: string) => void }) {
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = useCallback(async () => {
    const name = draft.trim();
    if (!api || !name) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateUserProfile({ display_name: name });
      onSaved(name);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save your name');
    } finally {
      setSaving(false);
    }
  }, [api, draft, onSaved]);

  return (
    <div className="grid gap-2 rounded-md border border-border px-3 py-2">
      <span className="text-[11px] leading-snug text-muted-foreground">
        Your account has no name yet, so the page would call you “Owner”.
      </span>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void save();
            }
          }}
          placeholder="Your name"
          aria-label="Your name"
          className="h-8 min-w-0 flex-1 text-xs"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 shrink-0 text-xs"
          disabled={!draft.trim() || saving}
          onClick={() => void save()}
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save'}
        </Button>
      </div>
      {error && <span className="text-[11px] text-destructive">{error}</span>}
    </div>
  );
}

/** A target's identity as a string, for keys and effect deps. */
export function shareTargetKey(target: ShareTarget): string {
  return target.kind === 'session'
    ? `session:${target.instanceId}`
    : `project:${target.projectId}:${target.initialScope}`;
}

/**
 * The link-first body: the current link (or the composer for the first one),
 * its settings, and the other links. Mount it fresh per target
 * (`key={shareTargetKey(target)}`) — its form state is per target.
 */
export function ShareLinkPanel({ api, target }: { api: BackendAPI | null; target: ShareTarget }) {
  const { copied, copy } = useCopyToClipboard();
  const kind = target.kind;
  const isProject = target.kind === 'project';

  // Composer.
  /** What a project link will carry; a session link carries none. */
  const [scopes, setScopes] = useState<ShareScope[]>(
    target.kind === 'project' ? [target.initialScope] : [],
  );
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
  const [sessionFiltersOpen, setSessionFiltersOpen] = useState(false);
  /**
   * What the link slot is doing. `create` is the composer — the first link, or
   * a second one beside a link that already exists. Editing is not a mode: the
   * current link's settings are live where they are shown.
   */
  const [mode, setMode] = useState<'view' | 'create'>('view');
  /** The current link's settings, open in place under its facts line. */
  const [settingsOpen, setSettingsOpen] = useState(false);
  /**
   * Which link the form mirrors. Live save fires on the difference between the
   * form and the link, so it must never run on a form that was not seeded from
   * that link — it would "correct" a link nobody touched to the form's defaults.
   */
  const [seededFor, setSeededFor] = useState<string | null>(null);
  /** The last settings successfully sent, as a key: never send the same twice. */
  const lastSaved = useRef<string | null>(null);

  const [links, setLinks] = useState<ShareLinkResponse[] | null>(null);
  /** undefined = not loaded; drives the "you have no name" prompt only. */
  const [ownName, setOwnName] = useState<string | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  /** The composer's own failure; the live settings report in `saveError`. */
  const [formError, setFormError] = useState<string | null>(null);
  /** A live settings change that did not stick. */
  const [saveError, setSaveError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [othersOpen, setOthersOpen] = useState(false);

  // Primitive deps: callers may pass a fresh target literal on every render
  // (the session page does, and it re-renders on every WS frame); keying on
  // the object would refetch the links on each of those renders.
  const targetInstanceId = target.kind === 'session' ? target.instanceId : null;
  const targetProjectId = target.kind !== 'session' ? target.projectId : null;
  const initialScope = target.kind === 'project' ? target.initialScope : null;
  const listTarget = useMemo(
    () => (targetInstanceId ? { agent_instance_id: targetInstanceId } : { project_id: targetProjectId ?? '' }),
    [targetInstanceId, targetProjectId],
  );

  const reload = useCallback(async () => {
    if (!api) return;
    try {
      setLoadError(null);
      setLinks(await api.listShareLinks(listTarget));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load links');
      setLinks([]);
    }
  }, [api, listTarget]);

  useEffect(() => {
    setLinks(null);
    void reload();
  }, [reload]);

  // Whether this account has a display name, for the "My name and avatar"
  // switch: with none, the page says "Owner" however the switch is set.
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .getCurrentUserProfile()
      .then((profile: UserProfile) => {
        if (!cancelled) setOwnName(profile.display_name?.trim() || null);
      })
      .catch(() => {
        // Unknown: say nothing rather than claim a name is missing.
        if (!cancelled) setOwnName('');
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  // Task filters need the project's label vocabulary.
  useEffect(() => {
    if (!api || !isProject) return;
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
  }, [api, isProject]);

  // Newest live link on this target is "the link"; the rest are "others".
  // One subject, one list — there is no second kind of link to explain.
  const sorted = useMemo(
    () => (links ?? []).slice().sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [links],
  );
  const current = sorted[0] ?? null;
  const others = sorted.slice(1);
  const showComposer = links !== null && (current === null || mode === 'create');
  /** The form is what the eye is on: the composer, or the open settings. */
  const formDrivesView = showComposer || settingsOpen;
  /**
   * Transcripts are on the page, so the branch switch applies. Where controls
   * are on screen that follows the form; otherwise it follows the link, which
   * need not carry the half the form happens to have ticked.
   */
  const showsTranscripts =
    kind === 'session' ||
    (formDrivesView ? scopes.includes('sessions') : (current?.scopes.includes('sessions') ?? false));
  const sharesTasks = scopes.includes('tasks');
  /** The account has loaded and carries no name (`''` = we could not tell). */
  const needsName = ownName === null;
  /** A link that already has a deadline can only be told to keep it. */
  const expiryOptions = useMemo(
    () =>
      !showComposer && current?.expires_at
        ? [{ value: KEEP_EXPIRY, label: formatExpiry(current.expires_at), days: null }, ...EXPIRY_OPTIONS]
        : EXPIRY_OPTIONS,
    [showComposer, current?.expires_at],
  );
  /**
   * A project link must carry a scope, and the live settings have no Create
   * button to disable instead — so the last one on cannot be turned off.
   */
  const lockLastScope = settingsOpen && !showComposer && scopes.length === 1;

  const toggleScope = useCallback((scope: ShareScope) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : SCOPE_ORDER.filter((s) => s === scope || prev.includes(s)),
    );
  }, []);

  // Comments live on tasks; dropping that half drops the flag rather than
  // letting the server reject the whole link.
  useEffect(() => {
    if (allowComments && !sharesTasks) setAllowComments(false);
  }, [allowComments, sharesTasks]);

  /** The filters the form currently describes; null = no narrowing. */
  const buildFilters = useCallback(
    () => buildShareFilters({ scopes, statuses, labelIds, includeArchived, dateFrom, dateTo }),
    [scopes, statuses, labelIds, includeArchived, dateFrom, dateTo],
  );

  /**
   * Point the composer at a link (edit) or at nothing (a fresh one). Editing
   * has to start from what the link actually says, or the first Save would
   * quietly reset every setting the form never loaded.
   */
  const seedForm = useCallback(
    (link: ShareLinkResponse | null) => {
      setScopes(link ? link.scopes : initialScope ? [initialScope] : []);
      setAudience(link?.audience ?? 'public');
      setExpiry(link?.expires_at ? KEEP_EXPIRY : 'never');
      setAllowComments(link?.allow_comments ?? false);
      setShowOwner(link?.show_owner ?? false);
      setShowBranch(link?.show_branch ?? false);
      const filters = filterFieldsFromLink(link);
      setStatuses(filters.statuses);
      setLabelIds(filters.labelIds);
      setIncludeArchived(filters.includeArchived);
      setDateFrom(filters.dateFrom);
      setDateTo(filters.dateTo);
    },
    [initialScope],
  );

  /** Open (or fold away) the current link's settings, seeded from the link. */
  const toggleSettings = useCallback(() => {
    if (settingsOpen) {
      setSettingsOpen(false);
      return;
    }
    if (current) {
      seedForm(current);
      setSeededFor(current.id);
      lastSaved.current = null;
      setSaveError(null);
    }
    setSettingsOpen(true);
  }, [settingsOpen, current, seedForm]);

  /** A second link: a fresh token is a decision, so it gets the composer. */
  const startNewLink = useCallback(() => {
    seedForm(null);
    setFormError(null);
    setSaveError(null);
    setSettingsOpen(false);
    setSeededFor(null);
    setMode('create');
  }, [seedForm]);

  const handleCreate = useCallback(async () => {
    if (!api) return;
    setCreating(true);
    setFormError(null);
    try {
      const days = EXPIRY_OPTIONS.find((o) => o.value === expiry)?.days ?? null;
      const filters = buildFilters();
      const link = await api.createShareLink({
        kind,
        ...(target.kind === 'session'
          ? { agent_instance_id: target.instanceId }
          : { project_id: target.projectId, scopes }),
        audience,
        allow_comments: sharesTasks && allowComments,
        show_owner: showOwner,
        show_branch: showsTranscripts && showBranch,
        expires_in_days: days,
        filters,
      });
      setLinks((prev) => [link, ...(prev ?? [])]);
      setMode('view');
      // One click: the new link is on the clipboard before the panel re-renders.
      void copy(shareUrl(link.token), link.id);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create link');
    } finally {
      setCreating(false);
    }
  }, [api, target, expiry, kind, scopes, sharesTasks, buildFilters, audience, allowComments, showOwner, showBranch, showsTranscripts, copy]);

  /** What the form says, as the fields a PATCH would carry. */
  const formSettings = useMemo(
    () => ({
      audience,
      allow_comments: sharesTasks && allowComments,
      show_owner: showOwner,
      show_branch: showsTranscripts && showBranch,
      scopes,
      filters: buildFilters(),
    }),
    [audience, sharesTasks, allowComments, showOwner, showsTranscripts, showBranch, scopes, buildFilters],
  );
  /** The form as one string, expiry included: exactly what a save would send. */
  const formKey = `${settingsKey(formSettings)}|${expiry}`;

  /**
   * Push the form onto the current link. Same fields as create, one endpoint
   * apart — and that difference is the whole feature: the token does not
   * change, so every copy of the URL already sent out keeps working and starts
   * obeying these settings.
   */
  const saveSettings = useCallback(async () => {
    if (!api || !current) return;
    setSaving(true);
    setSaveError(null);
    const sentExpiry = expiry;
    const sentKey = formKey;
    try {
      const patch: UpdateShareLinkRequest = {
        audience: formSettings.audience,
        allow_comments: formSettings.allow_comments,
        show_owner: formSettings.show_owner,
        show_branch: formSettings.show_branch,
        filters: formSettings.filters,
        ...(isProject ? { scopes: formSettings.scopes } : {}),
      };
      // Every other option restates the deadline; "keep" is the one that means
      // "leave it alone", and says so by omitting the field.
      if (sentExpiry !== KEEP_EXPIRY) {
        patch.expires_in_days = EXPIRY_OPTIONS.find((o) => o.value === sentExpiry)?.days ?? null;
      }
      const link = await api.updateShareLink(current.id, patch);
      lastSaved.current = sentKey;
      setLinks((prev) => (prev ?? []).map((row) => (row.id === link.id ? link : row)));
      // The picker cannot say "in N days" about a date, so it goes back to
      // naming the deadline the link now has — unless something else has been
      // picked while this was in flight.
      setExpiry((prev) => (prev === sentExpiry ? (link.expires_at ? KEEP_EXPIRY : 'never') : prev));
    } catch (err) {
      // There is no Save to press again, so put the controls back to what the
      // link actually says rather than leaving a lie on screen.
      seedForm(current);
      lastSaved.current = null;
      setSaveError(err instanceof Error ? err.message : 'the request did not go through');
    } finally {
      setSaving(false);
    }
  }, [api, current, expiry, formKey, formSettings, isProject, seedForm]);

  /**
   * Does the form say something the link does not? Only meaningful once the
   * form has been seeded from that very link. `lastSaved` closes the last loop:
   * the server normalises some of what it is sent (it trims a project link's
   * filters to the scopes the link carries), and a difference we already sent
   * is not a new change.
   */
  const settingsDirty =
    current !== null &&
    seededFor === current.id &&
    formKey !== lastSaved.current &&
    formDiffersFromLink(current, formSettings, expiry);

  // Live save: a change *is* the request. A burst (four filter chips in a row)
  // collects into one PATCH, and two never overlap — the effect runs again when
  // `saving` clears, and the difference will still be there.
  useEffect(() => {
    if (!settingsOpen || !settingsDirty || saving) return;
    const timer = setTimeout(() => void saveSettings(), LIVE_SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [settingsOpen, settingsDirty, saving, saveSettings]);

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
        setMode('view');
        // The settings may have been open over the link that just died.
        if (linkId === seededFor) {
          setSettingsOpen(false);
          setSeededFor(null);
          lastSaved.current = null;
          setSaveError(null);
        }
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : 'Failed to revoke link');
      } finally {
        setRevoking(null);
      }
    },
    [api, confirmRevoke, seededFor],
  );

  /**
   * The controls themselves, shared by the composer and the live settings: one
   * definition of what a link's settings are, so the two can never drift.
   */
  const settingsControls = (
    <>
      {isProject && (
        <div className="grid gap-2.5">
          <Label className="text-xs">What this link shares</Label>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
            {SCOPE_ORDER.map((scope) => (
              <SwitchOption
                key={scope}
                id={`share-scope-${scope}`}
                checked={scopes.includes(scope)}
                onCheckedChange={() => toggleScope(scope)}
                disabled={lockLastScope && scopes.includes(scope)}
              >
                {SCOPE_LABEL[scope]}
              </SwitchOption>
            ))}
          </div>
        </div>
      )}

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
              {expiryOptions.map((o) => (
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
          repo-internal like the path, which a public page never shows.
          Off, the page calls you "Owner" everywhere you appear. */}
      <div className="grid gap-2.5">
        <Label className="text-xs">Viewers can see</Label>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
          <SwitchOption id="share-show-owner" checked={showOwner} onCheckedChange={setShowOwner}>
            My name and avatar
          </SwitchOption>
          {showsTranscripts && (
            <SwitchOption id="share-show-branch" checked={showBranch} onCheckedChange={setShowBranch}>
              Branch names
            </SwitchOption>
          )}
        </div>
        {showOwner && needsName && <OwnerNameField api={api} onSaved={setOwnName} />}
      </div>

      {/* Comments are independent of the audience: a public link can take
          them, from viewers who sign in — the page asks them to. */}
      {sharesTasks && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
          <div className="grid gap-0.5">
            <Label htmlFor="share-allow-comments" className="text-xs">
              Allow comments
            </Label>
            <span className="text-[11px] text-muted-foreground">
              Signed-in Vicoa users can comment on tasks as themselves. Nothing else becomes editable.
            </span>
          </div>
          <Switch id="share-allow-comments" checked={allowComments} onCheckedChange={setAllowComments} />
        </div>
      )}

      {sharesTasks && (
        <Disclosure label="Filter tasks" open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}>
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

      {scopes.includes('sessions') && (
        <Disclosure
          label="Filter sessions"
          open={sessionFiltersOpen}
          onToggle={() => setSessionFiltersOpen((v) => !v)}
        >
          <div className="grid gap-3">
            <SwitchOption id="share-include-archived" checked={includeArchived} onCheckedChange={setIncludeArchived}>
              Include archived sessions
            </SwitchOption>
            {/* Same calendar pills as a task's dates. */}
            <div className="flex flex-wrap items-center gap-1.5">
              <DatePickerPill label="Start date" icon="start" value={dateFrom} onChange={setDateFrom} />
              <DatePickerPill label="End date" value={dateTo} onChange={setDateTo} />
            </div>
            <span className="text-[11px] text-muted-foreground">
              Sessions started in this range. New sessions in this project appear automatically while the link is live.
            </span>
          </div>
        </Disclosure>
      )}
    </>
  );

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-6">
      {/* The link slot: the current link with its settings under it, or the
          composer — for the first link, or a second one. */}
      {links === null ? (
        <div className="flex h-9 items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading…
        </div>
      ) : !showComposer && current ? (
        <div className="grid gap-3">
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
          {/* The facts line is also the way into the settings: it already says
              what the controls say, so it opens them instead of standing next
              to a button that does. */}
          <div className="grid gap-4">
            <div className="flex min-w-0 items-center gap-2">
              <button
                type="button"
                onClick={toggleSettings}
                aria-expanded={settingsOpen}
                className={cn(
                  'flex min-w-0 flex-1 cursor-pointer items-center gap-1 rounded text-left text-[11px] text-muted-foreground transition-colors hover:text-foreground',
                  FOCUS_RING,
                )}
              >
                <ChevronRight className={cn('h-3 w-3 shrink-0 transition-transform', settingsOpen && 'rotate-90')} />
                <LinkFacts link={current} className="min-w-0" />
              </button>
              {/* Spins from the moment a control moves until the facts line to
                  its left says the new thing: "not stored yet". Nothing marks
                  success, because that line is already the server's answer. */}
              {(saving || settingsDirty) && (
                <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
              )}
            </div>
            {settingsOpen && (
              <div className="grid gap-5">
                {settingsControls}
                <p className="text-[11px] leading-snug text-muted-foreground">
                  Changes apply as you make them and keep this same URL, so everyone you have already sent it to
                  sees them.
                </p>
                {saveError && (
                  <p className="text-[11px] leading-snug text-destructive">Nothing changed: {saveError}</p>
                )}
              </div>
            )}
          </div>
          {/* With the settings open, the controls carry this prompt themselves. */}
          {!settingsOpen && current.show_owner && needsName && <OwnerNameField api={api} onSaved={setOwnName} />}
        </div>
      ) : (
        <div className="grid gap-5">
          {settingsControls}
          {formError && <p className="text-xs text-destructive">{formError}</p>}
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              className="h-9 flex-1 gap-1.5 text-xs"
              onClick={() => void handleCreate()}
              disabled={!api || creating || (isProject && scopes.length === 0)}
            >
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
              Create link
            </Button>
            {current && (
              <Button type="button" size="sm" variant="ghost" className="h-9 cursor-pointer text-xs" onClick={() => setMode('view')}>
                Cancel
              </Button>
            )}
          </div>
        </div>
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
      {/* What you can do to the link itself. Both are rare and one cannot be
          undone, so they sit at the bottom at a weight that says so — Copy
          stays the only primary, and neither of these shares its row. */}
      {current && !showComposer && (
        <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className={cn(
              'h-8 cursor-pointer gap-1.5 px-2 text-xs text-muted-foreground hover:text-destructive',
              confirmRevoke === current.id && 'text-destructive',
            )}
            disabled={revoking === current.id}
            onClick={() => void handleRevoke(current.id)}
          >
            {revoking === current.id ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
            {revoking === current.id
              ? 'Revoking…'
              : confirmRevoke === current.id
                ? 'Revoke for everyone?'
                : 'Revoke link'}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 cursor-pointer gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={startNewLink}
          >
            <Link2 className="h-3.5 w-3.5" />
            New link
          </Button>
        </div>
      )}
      {loadError && <p className="text-xs text-destructive">{loadError}</p>}
    </div>
  );
}

/** The dialog's title and one-line description, by what is being shared. */
function dialogCopy(target: ShareTarget): { title: string; description: string } {
  switch (target.kind) {
    case 'session':
      return {
        title: `Share “${target.title || 'session'}”`,
        description:
          'Anyone who opens this link follows this session live, and keeps seeing what happens next until you revoke it.',
      };
    case 'project':
      return {
        title: `Share “${target.name}”`,
        description:
          'One link to this project. Pick what it carries; whoever opens it follows along live, new tasks and sessions included, until you revoke it.',
      };
  }
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
  const copy = target ? dialogCopy(target) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="custom-scrollbar max-h-[90vh] grid-cols-[minmax(0,1fr)] gap-6 overflow-y-auto overflow-x-hidden font-mono sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="truncate">{copy?.title}</DialogTitle>
          <DialogDescription>{copy?.description}</DialogDescription>
        </DialogHeader>
        {target && <ShareLinkPanel key={shareTargetKey(target)} api={api} target={target} />}
      </DialogContent>
    </Dialog>
  );
}
