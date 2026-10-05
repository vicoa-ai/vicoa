'use client';

// The share dialog's People tab (collaboration §8.4, P5): who, by name, can
// reach this project or this session, and at what role. The Link tab shares
// with anyone holding a URL; this one shares with specific people or teams,
// who then find the project under "Shared with me" in their own sidebar.
//
// Notion-shaped: one composer row on top (an address or a team, a role, for a
// project which parts it covers, Invite), then the list. The owner row is
// pinned first and read-only. Every other row changes role, scopes or goes
// away from its `⋯` menu, and each change is applied as it is made — like the
// Link tab, there is no Save.
//
// Addresses only ever appear because the backend sent them, and it sends
// them only to someone who administers the grants (§10.4).
//
// A 402 means the action takes a seat the plan does not have (§6); it is
// shown inline by `SeatLimitNotice`, the one handler for it. The open build
// never answers 402.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Loader2, MoreHorizontal, Users, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { SeatLimitNotice } from '@/components/billing/seat-limit-notice';
import type BackendAPI from '@/lib/backend-api';
import {
  seatLimitFromError,
  type GrantRole,
  type GrantScope,
  type ProjectPerson,
  type SessionShare,
  type TeamSummary,
} from '@/lib/backend-api';
import { principalFromResponse, type Principal } from '@/lib/principals';
import {
  GRANT_ROLE_OPTIONS,
  SCOPE_LABELS,
  SCOPE_ORDER,
  SESSION_ACCESS_OPTIONS,
  automationsDeniedMessage,
  inviteOutcome,
  looksLikeEmail,
  personLines,
  reachCount,
  roleLabel,
  scopeSummary,
  sessionReach,
  sessionShareLines,
  toggleScope,
  type PersonLines,
  type RoleOption,
} from '@/lib/share-people';
import { cn } from '@/lib/utils';

export type PeopleTarget =
  | {
      kind: 'session';
      instanceId: string;
      /** The session's project, for the "inherited from the project" block. */
      projectId?: string | null;
      projectName?: string | null;
    }
  | { kind: 'project'; projectId: string; name: string };

const FOCUS_RING = 'outline-none focus-visible:ring-1 focus-visible:ring-ring';
const SELECT_TRIGGER =
  'h-9 text-xs focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-ring';
/** What a new grant covers until the inviter unticks something: everything. */
const ALL_SCOPES: GrantScope[] = SCOPE_ORDER;

/** Failure state shared by both variants: a seat limit, or anything else. */
interface Failure {
  seat: { detail: string } | null;
  message: string | null;
}

/** `denied` is the plain-words reason for a refusal the caller recognised
 *  (see `automationsDeniedMessage`); it wins over the server's generic text. */
function failureFrom(err: unknown, fallback: string, denied: string | null = null): Failure {
  const seat = seatLimitFromError(err);
  if (seat) return { seat: { detail: seat.detail }, message: null };
  if (denied) return { seat: null, message: denied };
  return { seat: null, message: err instanceof Error ? err.message : fallback };
}

function FailureNotice({ failure }: { failure: Failure | null }) {
  if (!failure) return null;
  if (failure.seat) return <SeatLimitNotice detail={failure.seat.detail} />;
  return failure.message ? <p className="text-xs text-destructive">{failure.message}</p> : null;
}

/** My teams, for the composer's team picker. Empty until loaded, or for no teams. */
function useMyTeams(api: BackendAPI | null): TeamSummary[] {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .listTeams()
      .then((rows) => {
        if (!cancelled) setTeams(rows);
      })
      .catch(() => {
        // The picker simply offers no teams; the address field still works.
      });
    return () => {
      cancelled = true;
    };
  }, [api]);
  return teams;
}

function teamPrincipal(team: TeamSummary): Principal {
  return { type: 'team', id: team.id, name: team.name, avatarImageUri: team.avatar_image_uri };
}

// --- composer ---------------------------------------------------------------

interface ComposerSubmit<R extends string> {
  email: string | null;
  team: TeamSummary | null;
  role: R;
  scopes: GrantScope[];
}

function PeopleComposer<R extends string>({
  teams,
  roleOptions,
  defaultRole,
  withScopes,
  defaultScopes = ALL_SCOPES,
  busy,
  onSubmit,
}: {
  teams: TeamSummary[];
  roleOptions: RoleOption<R>[];
  defaultRole: R;
  withScopes: boolean;
  /** The scopes ticked to start with; all of them unless the caller can't share some. */
  defaultScopes?: GrantScope[];
  busy: boolean;
  /** Resolves true when the invite landed, so the fields can clear. */
  onSubmit: (value: ComposerSubmit<R>) => Promise<boolean>;
}) {
  const [text, setText] = useState('');
  const [team, setTeam] = useState<TeamSummary | null>(null);
  const [role, setRole] = useState<R>(defaultRole);
  const [scopes, setScopes] = useState<GrantScope[]>(defaultScopes);
  const [hint, setHint] = useState<string | null>(null);

  const ready = team !== null || text.trim().length > 0;

  const submit = async () => {
    if (!ready || busy) return;
    if (!team && !looksLikeEmail(text)) {
      setHint('Enter an email address, or pick a team.');
      return;
    }
    setHint(null);
    const ok = await onSubmit({
      email: team ? null : text.trim(),
      team,
      role,
      scopes,
    });
    if (ok) {
      setText('');
      setTeam(null);
    }
  };

  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          {team ? (
            <div className="flex h-9 items-center gap-2 rounded-md border border-border px-2 text-xs">
              <PrincipalAvatar principal={teamPrincipal(team)} size="xs" />
              <span className="min-w-0 flex-1 truncate">{team.name}</span>
              <button
                type="button"
                aria-label="Clear team"
                onClick={() => setTeam(null)}
                className={cn('cursor-pointer rounded text-muted-foreground hover:text-foreground', FOCUS_RING)}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <Input
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setHint(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void submit();
                }
              }}
              placeholder={teams.length ? 'Email or team' : 'Email address'}
              aria-label="Email address"
              className={cn('h-9 text-xs', teams.length && 'pr-9')}
            />
          )}
          {!team && teams.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="Share with a team"
                  title="Share with a team"
                  className={cn(
                    'absolute right-1.5 top-1/2 -translate-y-1/2 cursor-pointer rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground',
                    FOCUS_RING,
                  )}
                >
                  <Users className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 font-mono text-xs">
                <DropdownMenuLabel className="text-[0.8rem] font-normal text-muted-foreground">
                  Your teams
                </DropdownMenuLabel>
                {teams.map((t) => (
                  <DropdownMenuItem
                    key={t.id}
                    className="cursor-pointer gap-2 text-xs"
                    onSelect={() => {
                      setTeam(t);
                      setHint(null);
                    }}
                  >
                    <PrincipalAvatar principal={teamPrincipal(t)} size="xs" />
                    <span className="min-w-0 flex-1 truncate">{t.name}</span>
                    <span className="text-muted-foreground">{t.member_count}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
        <Select value={role} onValueChange={(v) => setRole(v as R)}>
          <SelectTrigger className={cn(SELECT_TRIGGER, 'w-[7.5rem] shrink-0 cursor-pointer')} aria-label="Role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="font-mono">
            {roleOptions.map((o) => (
              <SelectItem key={o.value} value={o.value} className="cursor-pointer text-xs">
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          size="sm"
          className="h-9 shrink-0 cursor-pointer disabled:cursor-not-allowed"
          disabled={!ready || busy}
          onClick={() => void submit()}
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Invite'}
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground">
        {roleOptions.find((o) => o.value === role)?.description}
      </p>
      {withScopes && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span>Can see</span>
          {ALL_SCOPES.map((scope) => {
            const on = scopes.includes(scope);
            return (
              <button
                key={scope}
                type="button"
                aria-pressed={on}
                onClick={() => setScopes((prev) => toggleScope(prev, scope))}
                className={cn(
                  'cursor-pointer rounded-full border px-2 py-0.5 transition-colors',
                  FOCUS_RING,
                  on
                    ? 'border-foreground/40 bg-foreground/10 text-foreground'
                    : 'border-border text-muted-foreground hover:bg-muted',
                )}
              >
                {SCOPE_LABELS[scope]}
              </button>
            );
          })}
        </div>
      )}
      {hint && <p className="text-xs text-destructive">{hint}</p>}
    </div>
  );
}

// --- rows -------------------------------------------------------------------

function PersonRow({
  principal,
  lines,
  isSelf,
  trailing,
}: {
  principal: Principal;
  lines: PersonLines;
  isSelf: boolean;
  trailing: React.ReactNode;
}) {
  return (
    <li className="flex items-center gap-3 py-2">
      <PrincipalAvatar principal={principal} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-foreground">
          {lines.primary}
          {isSelf && <span className="text-muted-foreground"> (you)</span>}
        </p>
        {lines.secondary && (
          <p className="truncate text-[11px] text-muted-foreground">{lines.secondary}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">{trailing}</div>
    </li>
  );
}

function RoleSubmenu<R extends string>({
  label,
  options,
  current,
  onPick,
}: {
  label: string;
  options: RoleOption<R>[];
  current: string;
  onPick: (value: R) => void;
}) {
  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="cursor-pointer text-xs">{label}</DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-64 font-mono">
        {options.map((o) => (
          <DropdownMenuItem
            key={o.value}
            className="cursor-pointer items-start gap-2 text-xs"
            onSelect={() => {
              if (o.value !== current) onPick(o.value);
            }}
          >
            <Check className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', o.value !== current && 'invisible')} />
            <span className="grid gap-0.5">
              <span>{o.label}</span>
              <span className="text-[11px] text-muted-foreground">{o.description}</span>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

function RowMenu({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={label}
          className={cn('cursor-pointer rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground', FOCUS_RING)}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48 font-mono">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RoleText({ children, busy }: { children: React.ReactNode; busy?: boolean }) {
  return (
    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
      {busy && <Loader2 className="h-3 w-3 animate-spin" />}
      {children}
    </span>
  );
}

/** Edit access that dropped to read and comment because the seat paying for
 *  it lapsed (the payer's Team subscription ended). It comes back with seats,
 *  or when someone picks a role here. */
function LapsedNote({ was }: { was: string }) {
  return (
    <span className="text-warning" title={`Was ${was.toLowerCase()} until the seat paying for it lapsed`}>
      {' '}
      · seat lapsed
    </span>
  );
}

// --- project ----------------------------------------------------------------

function ProjectPeople({
  api,
  projectId,
  onChanged,
}: {
  api: BackendAPI | null;
  projectId: string;
  onChanged?: () => void;
}) {
  const teams = useMyTeams(api);
  const [people, setPeople] = useState<ProjectPerson[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [pendingRow, setPendingRow] = useState<string | null>(null);
  // What the caller may hand out: the scopes their own standing covers (all
  // of them for the owner or the owning team). An admin whose grant predates
  // automations starts without it ticked, which is also the server's default.
  const [shareable, setShareable] = useState<GrantScope[]>(ALL_SCOPES);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .listProjects()
      .then((list) => {
        const own = list.find((p) => p.id === projectId)?.scopes;
        if (!cancelled && own && own.length > 0) {
          setShareable(ALL_SCOPES.filter((s) => own.includes(s)));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api, projectId]);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      setPeople(await api.listProjectPeople(projectId));
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load people.');
    }
  }, [api, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const invite = async (value: ComposerSubmit<GrantRole>): Promise<boolean> => {
    if (!api) return false;
    setInviting(true);
    setFailure(null);
    setNotice(null);
    try {
      const created = value.team
        ? await api.createProjectGrant(projectId, {
            team_id: value.team.id,
            role: value.role,
            scopes: value.scopes,
          })
        : await api.createProjectGrant(projectId, {
            email: value.email ?? '',
            role: value.role,
            scopes: value.scopes,
          });
      setNotice(inviteOutcome(created));
      await load();
      onChanged?.();
      return true;
    } catch (err) {
      setFailure(
        failureFrom(err, 'Failed to share.', automationsDeniedMessage(err, value.scopes, 'invite')),
      );
      return false;
    } finally {
      setInviting(false);
    }
  };

  const update = async (person: ProjectPerson, data: { role?: GrantRole; scopes?: GrantScope[] }) => {
    if (!api || !person.id) return;
    setPendingRow(person.id);
    setFailure(null);
    setNotice(null);
    try {
      const next = await api.updateProjectGrant(projectId, person.id, data);
      setPeople((rows) => rows?.map((r) => (r.id === next.id ? next : r)) ?? rows);
      onChanged?.();
    } catch (err) {
      // Standing is checked over what the grant covered and what it will cover.
      const touched = [...person.scopes, ...(data.scopes ?? [])];
      setFailure(
        failureFrom(err, 'Failed to update access.', automationsDeniedMessage(err, touched, 'change')),
      );
    } finally {
      setPendingRow(null);
    }
  };

  const remove = async (person: ProjectPerson) => {
    if (!api || !person.id) return;
    setPendingRow(person.id);
    setFailure(null);
    setNotice(null);
    try {
      await api.deleteProjectGrant(projectId, person.id);
      setPeople((rows) => rows?.filter((r) => r.id !== person.id) ?? rows);
      onChanged?.();
    } catch (err) {
      setFailure(
        failureFrom(err, 'Failed to remove access.', automationsDeniedMessage(err, person.scopes, 'remove')),
      );
    } finally {
      setPendingRow(null);
    }
  };

  return (
    <div className="grid gap-4">
      <PeopleComposer
        // Remount once the caller's own scopes are known, so the defaults follow.
        key={shareable.join(',')}
        teams={teams}
        roleOptions={GRANT_ROLE_OPTIONS}
        defaultRole="viewer"
        withScopes
        defaultScopes={shareable}
        busy={inviting}
        onSubmit={invite}
      />
      <FailureNotice failure={failure} />
      {notice && <p className="text-xs text-muted-foreground">{notice}</p>}

      {people === null && !loadError && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading people…
        </p>
      )}
      {loadError && <p className="text-xs text-destructive">{loadError}</p>}
      {people && (
        <ul className="divide-y divide-border/50">
          {people.map((person) => {
            const principal = principalFromResponse(person.principal) ?? { type: 'user' as const };
            const busy = pendingRow !== null && pendingRow === person.id;
            if (person.is_owner) {
              return (
                <PersonRow
                  key="owner"
                  principal={principal}
                  lines={personLines(person)}
                  isSelf={person.is_self}
                  trailing={<RoleText>Owner</RoleText>}
                />
              );
            }
            return (
              <PersonRow
                key={person.id}
                principal={principal}
                lines={personLines(person)}
                isSelf={person.is_self}
                trailing={
                  <>
                    <RoleText busy={busy}>
                      {roleLabel(person.role)}
                      {person.lapsed_role && <LapsedNote was={roleLabel(person.lapsed_role)} />}
                      {person.scopes.length < ALL_SCOPES.length && (
                        <span className="text-muted-foreground/70"> · {scopeSummary(person.scopes)}</span>
                      )}
                    </RoleText>
                    <RowMenu label={`Access for ${personLines(person).primary}`}>
                      <RoleSubmenu
                        label="Change role"
                        options={GRANT_ROLE_OPTIONS}
                        current={person.role}
                        onPick={(role) => void update(person, { role })}
                      />
                      <DropdownMenuSub>
                        <DropdownMenuSubTrigger className="cursor-pointer text-xs">Can see</DropdownMenuSubTrigger>
                        <DropdownMenuSubContent className="w-40 font-mono">
                          {ALL_SCOPES.map((scope) => {
                            const on = person.scopes.includes(scope);
                            const last = on && person.scopes.length === 1;
                            return (
                              <DropdownMenuCheckboxItem
                                key={scope}
                                checked={on}
                                disabled={last}
                                className={cn('text-xs', last ? 'cursor-not-allowed' : 'cursor-pointer')}
                                onSelect={(e) => {
                                  e.preventDefault();
                                  if (!last) {
                                    void update(person, { scopes: toggleScope(person.scopes, scope) });
                                  }
                                }}
                              >
                                {SCOPE_LABELS[scope]}
                              </DropdownMenuCheckboxItem>
                            );
                          })}
                        </DropdownMenuSubContent>
                      </DropdownMenuSub>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="cursor-pointer text-xs text-destructive focus:text-destructive"
                        onSelect={() => void remove(person)}
                      >
                        Remove
                      </DropdownMenuItem>
                    </RowMenu>
                  </>
                }
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

// --- session ----------------------------------------------------------------

/**
 * "Everyone the project is shared with (sessions scope) can open this too" —
 * read-only, with a way to the project's own People tab. Hidden when the
 * caller cannot administer the project's grants (the list 403s) or nobody
 * reaches this session that way.
 */
function InheritedFromProject({
  api,
  projectId,
  projectName,
  onManage,
}: {
  api: BackendAPI | null;
  projectId: string;
  projectName: string | null;
  onManage?: () => void;
}) {
  const [reach, setReach] = useState<ProjectPerson[] | null>(null);
  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    api
      .listProjectPeople(projectId)
      .then((people) => {
        if (!cancelled) setReach(sessionReach(people));
      })
      .catch(() => {
        if (!cancelled) setReach([]);
      });
    return () => {
      cancelled = true;
    };
  }, [api, projectId]);

  if (!reach || reach.length === 0) return null;
  const n = reachCount(reach);
  return (
    <div className="flex items-center gap-3 rounded-md border border-border/60 bg-foreground/[0.03] px-3 py-2">
      <div className="flex -space-x-1.5">
        {reach.slice(0, 3).map((p) => (
          <PrincipalAvatar
            key={p.id ?? 'x'}
            principal={principalFromResponse(p.principal) ?? { type: 'user' }}
            size="xs"
            className="ring-2 ring-background"
          />
        ))}
      </div>
      <p className="min-w-0 flex-1 text-[11px] text-muted-foreground">
        {n} {n === 1 ? 'person sees' : 'people see'} this through{' '}
        {projectName ? (
          <>
            the project <span className="text-foreground">{projectName}</span>
          </>
        ) : (
          'its project'
        )}
        .
      </p>
      {onManage && (
        <button
          type="button"
          onClick={onManage}
          className={cn('shrink-0 cursor-pointer text-[11px] text-foreground underline underline-offset-2', FOCUS_RING)}
        >
          Manage
        </button>
      )}
    </div>
  );
}

function SessionPeople({
  api,
  instanceId,
}: {
  api: BackendAPI | null;
  instanceId: string;
}) {
  const teams = useMyTeams(api);
  const [shares, setShares] = useState<SessionShare[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [pendingRow, setPendingRow] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      setShares(await api.listSessionShares(instanceId));
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load people.');
    }
  }, [api, instanceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const invite = async (value: ComposerSubmit<'READ' | 'WRITE'>): Promise<boolean> => {
    if (!api) return false;
    setInviting(true);
    setFailure(null);
    setNotice(null);
    try {
      const created = value.team
        ? await api.createSessionShare(instanceId, { team_id: value.team.id, access: value.role })
        : await api.createSessionShare(instanceId, { email: value.email ?? '', access: value.role });
      setNotice(`Shared with ${sessionShareLines(created).primary}.`);
      await load();
      return true;
    } catch (err) {
      setFailure(failureFrom(err, 'Failed to share.'));
      return false;
    } finally {
      setInviting(false);
    }
  };

  const setAccess = async (share: SessionShare, access: 'READ' | 'WRITE') => {
    if (!api) return;
    setPendingRow(share.id);
    setFailure(null);
    try {
      const next = await api.updateSessionShare(instanceId, share.id, access);
      setShares((rows) => rows?.map((r) => (r.id === next.id ? next : r)) ?? rows);
    } catch (err) {
      setFailure(failureFrom(err, 'Failed to update access.'));
    } finally {
      setPendingRow(null);
    }
  };

  const remove = async (share: SessionShare) => {
    if (!api) return;
    setPendingRow(share.id);
    setFailure(null);
    try {
      await api.deleteSessionShare(instanceId, share.id);
      setShares((rows) => rows?.filter((r) => r.id !== share.id) ?? rows);
    } catch (err) {
      setFailure(failureFrom(err, 'Failed to remove access.'));
    } finally {
      setPendingRow(null);
    }
  };

  return (
    <div className="grid gap-4">
      <PeopleComposer
        teams={teams}
        roleOptions={SESSION_ACCESS_OPTIONS}
        defaultRole="READ"
        withScopes={false}
        busy={inviting}
        onSubmit={invite}
      />
      <FailureNotice failure={failure} />
      {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
      {shares === null && !loadError && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading people…
        </p>
      )}
      {loadError && <p className="text-xs text-destructive">{loadError}</p>}
      {shares && (
        <ul className="divide-y divide-border/50">
          {shares.map((share) => {
            const principal: Principal =
              share.principal_type === 'team'
                ? { type: 'team', id: share.team_id, name: share.display_name, avatarImageUri: share.avatar_image_uri }
                : { type: 'user', id: share.user_id, name: share.display_name, avatarImageUri: share.avatar_image_uri };
            const lines = sessionShareLines(share);
            if (share.is_owner) {
              return (
                <PersonRow key="owner" principal={principal} lines={lines} isSelf={false} trailing={<RoleText>Owner</RoleText>} />
              );
            }
            return (
              <PersonRow
                key={share.id}
                principal={principal}
                lines={lines}
                isSelf={false}
                trailing={
                  <>
                    <RoleText busy={pendingRow === share.id}>
                      {roleLabel(share.access)}
                      {share.lapsed && <LapsedNote was={roleLabel('WRITE')} />}
                    </RoleText>
                    <RowMenu label={`Access for ${lines.primary}`}>
                      <RoleSubmenu
                        label="Change role"
                        options={SESSION_ACCESS_OPTIONS}
                        current={share.access}
                        onPick={(access) => void setAccess(share, access)}
                      />
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="cursor-pointer text-xs text-destructive focus:text-destructive"
                        onSelect={() => void remove(share)}
                      >
                        Remove
                      </DropdownMenuItem>
                    </RowMenu>
                  </>
                }
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

// --- entry ------------------------------------------------------------------

export function SharePeoplePanel({
  api,
  target,
  onOpenProject,
  onChanged,
}: {
  api: BackendAPI | null;
  target: PeopleTarget;
  /** The session variant's "Manage" on the inherited block. */
  onOpenProject?: (projectId: string, name: string) => void;
  /** After any grant change on a project, so an avatar stack can refresh. */
  onChanged?: () => void;
}) {
  const inherited = useMemo(
    () =>
      target.kind === 'session' && target.projectId
        ? { projectId: target.projectId, projectName: target.projectName ?? null }
        : null,
    [target],
  );

  if (target.kind === 'project') {
    return <ProjectPeople api={api} projectId={target.projectId} onChanged={onChanged} />;
  }
  return (
    <div className="grid gap-4">
      {inherited && (
        <InheritedFromProject
          api={api}
          projectId={inherited.projectId}
          projectName={inherited.projectName}
          onManage={
            onOpenProject
              ? () => onOpenProject(inherited.projectId, inherited.projectName ?? 'Project')
              : undefined
          }
        />
      )}
      <SessionPeople api={api} instanceId={target.instanceId} />
    </div>
  );
}
