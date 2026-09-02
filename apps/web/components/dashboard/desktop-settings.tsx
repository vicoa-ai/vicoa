'use client';

import { useEffect, useMemo, useReducer, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { LogIn, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { createClient } from '@/lib/auth/supabase-client';
import {
  getDesktopNotificationsBridge,
  getDesktopNotificationsMode,
  getSilencePhoneWhenFocused,
  readNotificationAuthorization,
  setDesktopNotificationsMode,
  setSilencePhoneWhenFocused,
  type NotificationAuthorizationStatus,
  type NotificationMode,
} from '@/lib/desktop-notifications';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getDesktopConfig, type DesktopRuntimeConfig } from '@/lib/runtime-config';
import { ThemeSelect } from '@/components/plugins/theme-select';
import {
  checkForUpdates,
  downloadUpdate,
  getAppVersion,
  getDesktopUpdatesBridge,
  quitAndInstallUpdate,
  useDesktopUpdateStatus,
  type UpdateStatus,
} from '@/lib/desktop-updates';
import {
  cliButtonLabel,
  cliRowDescription,
  getCliStatus,
  getDesktopCliBridge,
  installCli,
  type CliInstallResult,
  type CliLinkStatus,
} from '@/lib/desktop-cli';
import { DRAG_REGION } from '@/lib/app-region';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { computeStreaks, formatCompact, formatDays } from '@/lib/profile-stats';
import {
  loadCache,
  loadProfileActivity,
  toProfileActivity,
  type ProfileActivity,
} from '@/lib/profile-activity';
import { ActivityHeatmap } from './activity-heatmap';
import {
  SHORTCUT_DEFS,
  clearShortcutOverride,
  comboKeycaps,
  findShortcutConflict,
  getShortcutCombo,
  isMacPlatform,
  isModifierCode,
  isShortcutOverridden,
  primaryModifierLabel,
  setShortcutOverride,
  subscribeShortcuts,
  type ShortcutId,
} from '@/lib/desktop-shortcuts';
import { activeSettingsTab } from './desktop-settings-sidebar';
import { ProvidersSettingsSection } from './providers-settings-section';
import { MachinesSettingsSection } from './machines-settings-section';
import { PluginsSettingsSection } from './plugins-settings-section';
import { WorktreeSetupSection } from './worktree-setup-section';
import { ProjectDisplaySection } from './project-display-section';
import { useMobileSidebarHidden, setMobileSidebarHidden } from '@/lib/mobile-sidebar-pref';

/**
 * Middle-panel content for the desktop settings page. The tab comes from the
 * ?tab= param, driven by DesktopSettingsSidebar; no right panel here.
 */
export function DesktopSettings() {
  const searchParams = useSearchParams();
  const tab = activeSettingsTab(searchParams.get('tab'));

  return (
    <div className="flex h-full flex-1 flex-col font-mono">
      {/* No header on settings routes, so the top strip is the drag region. */}
      <div style={DRAG_REGION} className="h-11 shrink-0" />
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="mx-auto w-full max-w-3xl px-8 pb-12">
          {tab === 'shortcuts' ? (
            <ShortcutsSection />
          ) : tab === 'appearance' ? (
            <AppearanceSection />
          ) : tab === 'profile' ? (
            <ProfileSection />
          ) : tab === 'providers' ? (
            <ProvidersSettingsSection />
          ) : tab === 'machines' ? (
            <MachinesSettingsSection />
          ) : tab === 'plugins' ? (
            <PluginsSettingsSection />
          ) : tab === 'project' ? (
            <ProjectSection
              projectId={searchParams.get('projectId') ?? ''}
              machineId={searchParams.get('machineId') ?? ''}
              dir={searchParams.get('dir') ?? ''}
              label={searchParams.get('label') ?? ''}
            />
          ) : (
            <GeneralSection />
          )}
        </div>
      </div>
    </div>
  );
}

/** Per-project settings pane (worktree setup, room to grow). Reached from the
 *  sidebar project 3-dots → "Project settings" and the settings nav's Projects
 *  group; carries the repo's machineId + dir. */
function ProjectSection({
  projectId,
  machineId,
  dir,
  label,
}: {
  projectId: string;
  machineId: string;
  dir: string;
  label: string;
}) {
  return (
    <section className="flex flex-col gap-6">
      <div>
        <SectionTitle>{label || 'Project settings'}</SectionTitle>
        {dir && <p className="mt-1 truncate text-xs text-muted-foreground">{dir}</p>}
      </div>
      {projectId || (machineId && dir) ? (
        <>
          <ProjectDisplaySection
            projectId={projectId || undefined}
            machineId={machineId || undefined}
            dir={dir || undefined}
          />
          {machineId && dir && <WorktreeSetupSection machineId={machineId} dir={dir} />}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Pick a project from the list to edit its settings.
        </p>
      )}
    </section>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="text-2xl font-light tracking-tight text-foreground">{children}</h1>;
}

function ProfileSection() {
  const router = useRouter();
  const { api } = useAgentDashboard();
  const [config, setConfig] = useState<DesktopRuntimeConfig | null>(null);
  const [mounted, setMounted] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [activity, setActivity] = useState<ProfileActivity | null>(null);
  const [activityLoading, setActivityLoading] = useState(true);

  // Runtime config is preload-injected, so read it post-mount (same pattern as
  // the desktop sidebar) to keep the SSR pass consistent.
  useEffect(() => {
    setConfig(getDesktopConfig());
    setMounted(true);
  }, []);

  // Identity (cloud only): name + email + user id come straight from the
  // validated Supabase session the sign-in gate now guarantees.
  useEffect(() => {
    if (config?.mode !== 'cloud') return;
    const supabase = createClient();
    let cancelled = false;
    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (cancelled) return;
      const user = session?.user;
      setEmail(user?.email ?? null);
      setUserId(user?.id ?? null);
      const meta = user?.user_metadata as Record<string, unknown> | undefined;
      const metaName =
        (typeof meta?.full_name === 'string' && meta.full_name) ||
        (typeof meta?.name === 'string' && meta.name) ||
        '';
      setName(metaName || null);
    });
    return () => {
      cancelled = true;
    };
  }, [config?.mode]);

  const isCloud = config?.mode === 'cloud';

  // Activity (stat tiles + heatmap): the server aggregate, cached + synced
  // incrementally, with a comprehensive session-level fallback. Paint any
  // cached data instantly, then revalidate in the background.
  useEffect(() => {
    if (!mounted || !api) return;
    // Cloud needs the user id (cache key + server path); wait for it to resolve.
    if (isCloud && !userId) return;
    let cancelled = false;
    if (userId) {
      const cached = loadCache(userId);
      if (cached) setActivity(toProfileActivity(cached));
    }
    setActivityLoading(true);
    void loadProfileActivity(api, userId, new Date())
      .then((next) => {
        if (!cancelled) setActivity(next);
      })
      .catch(() => {
        /* keep whatever we already have (stale cache or nothing) */
      })
      .finally(() => {
        if (!cancelled) setActivityLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mounted, api, isCloud, userId]);

  const streaks = useMemo(
    () => computeStreaks(activity?.daily ?? new Map<string, number>(), new Date()),
    [activity],
  );

  if (!mounted) return null;

  const displayName = name || email || (isCloud ? 'Your profile' : 'Local session');
  // Show the email under the name, unless the name slot already shows it.
  const subEmail = email && email !== displayName ? email : null;
  const loading = activityLoading && !activity;
  // Message counts are null on the session-level fallback (no user/agent split);
  // render "—" until the server aggregate provides them.
  const messageValue = (value: number | null | undefined) =>
    loading || value == null ? '—' : formatCompact(value);

  return (
    <section className="flex flex-col items-center">
      {/* Identity */}
      <div className="flex h-20 w-20 items-center justify-center rounded-full bg-foreground/10 text-2xl font-light text-foreground/80">
        {initialsFrom(displayName, email)}
      </div>
      <h1 className="mt-4 text-2xl font-light tracking-tight text-foreground">{displayName}</h1>
      {subEmail && <p className="mt-1 text-sm text-muted-foreground">{subEmail}</p>}

      {/* Stat tiles */}
      <div className="mt-8 flex w-full divide-x divide-border/60 rounded-xl border border-border/60">
        <StatCell label="Sessions" value={loading ? '—' : formatCompact(activity?.totalSessions ?? 0)} />
        <StatCell label="Messages" value={messageValue(activity?.totalUserMessages)} />
        <StatCell label="Total messages" value={messageValue(activity?.totalMessages)} />
        <StatCell label="Current streak" value={loading ? '—' : formatDays(streaks.currentStreak)} />
        <StatCell label="Longest streak" value={loading ? '—' : formatDays(streaks.longestStreak)} />
      </div>

      {/* Activity heatmap */}
      <div className="mt-10 w-full">
        <h2 className="mb-3 text-sm text-foreground/90">Activity</h2>
        <ActivityHeatmap counts={activity?.daily ?? new Map<string, number>()} />
      </div>

      {/* Account (local mode only: prompt to connect) */}
      {!isCloud && (
        <div className="mt-10 w-full space-y-4 border-t border-border/50 pt-6">
          <p className="text-sm text-muted-foreground">
            You are in local mode. Connect your account to sync sessions to your phone.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => router.push('/desktop-signin')}
          >
            <LogIn className="h-3.5 w-3.5" />
            Connect account
          </Button>
        </div>
      )}
    </section>
  );
}

// --- Profile helpers -------------------------------------------------------

/** Up to two uppercase initials from a name, falling back to the email. */
function initialsFrom(name: string, email: string | null): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  const base = words[0] || email?.split('@')[0] || '';
  return base.slice(0, 2).toUpperCase() || '?';
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex-1 px-3 py-3 text-center">
      <div className="text-base text-foreground">{value}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

const AUTHORIZATION_LABELS: Record<NotificationAuthorizationStatus, string> = {
  authorized: 'Allowed',
  denied: 'Denied',
  'not-determined': 'Not requested yet',
  unknown: 'Unknown',
};

const AUTHORIZATION_COLORS: Record<NotificationAuthorizationStatus, string> = {
  authorized: 'text-success',
  denied: 'text-warning',
  'not-determined': 'text-muted-foreground',
  unknown: 'text-muted-foreground',
};

/** Grouped settings rows (title + description left, control right). */
function SettingsCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="divide-y divide-border/50 rounded-xl border border-border/60 bg-foreground/[0.03]">
      {children}
    </div>
  );
}

function SettingsRow({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 px-4 py-3.5">
      <div className="min-w-0 space-y-0.5">
        <div className="text-[13px] text-foreground">{title}</div>
        {description && <div className="text-xs text-muted-foreground">{description}</div>}
      </div>
      <div className="flex shrink-0 items-center gap-3">{children}</div>
    </div>
  );
}

const NOTIFICATION_MODE_LABELS: Record<NotificationMode, string> = {
  never: 'Never',
  unfocused: 'Only when unfocused',
  always: 'Always',
};

/** Appearance tab: theme selection (base modes + plugin themes). Its own tab so
 *  it has room to grow (e.g. accent tint, density) beyond the single Theme row. */
function AppearanceSection() {
  return (
    <section>
      <SectionTitle>Appearance</SectionTitle>
      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Theme</h2>
        <SettingsCard>
          <SettingsRow
            title="Theme"
            description="Base mode, or a theme installed from a plugin"
          >
            <ThemeSelect />
          </SettingsRow>
        </SettingsCard>
      </div>
    </section>
  );
}

function GeneralSection() {
  const [mounted, setMounted] = useState(false);
  const mobileHidden = useMobileSidebarHidden();
  const [mode, setMode] = useState<NotificationMode>('unfocused');
  const [authorization, setAuthorization] = useState<NotificationAuthorizationStatus | null>(null);
  const [isMac, setIsMac] = useState(false);
  // Phone-push mute is only meaningful when signed into the cloud (there's a
  // phone to push to); hidden in logged-out local mode.
  const [isCloud, setIsCloud] = useState(false);
  const [silencePhone, setSilencePhone] = useState(true);

  // The preferences are preload-injected and platform detection reads
  // `navigator`; read them post-mount so the SSR pass stays consistent (same
  // pattern as ProfileSection's config read).
  useEffect(() => {
    setMode(getDesktopNotificationsMode());
    setIsMac(isMacPlatform());
    setIsCloud(getDesktopConfig()?.mode === 'cloud');
    setSilencePhone(getSilencePhoneWhenFocused());
    setMounted(true);
  }, []);

  // Live macOS permission readout (bundled helper; null in dev). Refreshed on
  // window focus so returning from System Settings shows the new state.
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      void readNotificationAuthorization().then((status) => {
        if (!cancelled) setAuthorization(status);
      });
    };
    refresh();
    window.addEventListener('focus', refresh);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', refresh);
    };
  }, []);

  const changeMode = (value: string) => {
    const next = value as NotificationMode;
    setMode(next);
    setDesktopNotificationsMode(next);
  };

  const changeSilencePhone = (value: string) => {
    const next = value === 'silence';
    setSilencePhone(next);
    setSilencePhoneWhenFocused(next);
  };

  const sendTest = () => {
    // instanceId '' = focus-only click, no session routing.
    getDesktopNotificationsBridge()?.notify({
      instanceId: '',
      title: 'Vicoa',
      body: 'Notifications are working.',
    });
  };

  if (!mounted) return null;

  return (
    <section>
      <SectionTitle>General</SectionTitle>
      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Notifications</h2>
        <SettingsCard>
          <SettingsRow
            title="Show notifications"
            description="Alert when a session needs your input, completes, or fails"
          >
            <Select value={mode} onValueChange={changeMode}>
              <SelectTrigger
                aria-label="When to show notifications"
                className="h-7 w-auto gap-1.5 border-border/70 bg-foreground/[0.06] px-2.5 py-0 text-xs shadow-none focus:ring-0 focus:ring-offset-0"
              >
                <SelectValue>{NOTIFICATION_MODE_LABELS[mode]}</SelectValue>
              </SelectTrigger>
              {/* Match DropdownMenuContent (e.g. the chat page's ··· menu):
                  same --menu surface + foreground/10 hover instead of the
                  select's default popover/accent pair. */}
              <SelectContent align="end" className="bg-menu font-mono">
                {(Object.keys(NOTIFICATION_MODE_LABELS) as NotificationMode[]).map((value) => (
                  <SelectItem
                    key={value}
                    value={value}
                    className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground"
                  >
                    {NOTIFICATION_MODE_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingsRow>
          {isCloud && (
            <SettingsRow
              title="Phone notifications"
              description="Silence push on your phone while you're actively using the desktop app"
            >
              <Select value={silencePhone ? 'silence' : 'always'} onValueChange={changeSilencePhone}>
                <SelectTrigger
                  aria-label="Phone notifications while using the desktop app"
                  className="h-7 w-auto gap-1.5 border-border/70 bg-foreground/[0.06] px-2.5 py-0 text-xs shadow-none focus:ring-0 focus:ring-offset-0"
                >
                  <SelectValue>{silencePhone ? 'Silence while focused' : 'Always send'}</SelectValue>
                </SelectTrigger>
                <SelectContent align="end" className="bg-menu font-mono">
                  <SelectItem
                    value="silence"
                    className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground"
                  >
                    Silence while focused
                  </SelectItem>
                  <SelectItem
                    value="always"
                    className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground"
                  >
                    Always send
                  </SelectItem>
                </SelectContent>
              </Select>
            </SettingsRow>
          )}
          {isMac && (
            <SettingsRow
              title="macOS permission"
              description="Vicoa needs macOS permission to display banners"
            >
              {authorization !== null && (
                <span className={cn('text-xs', AUTHORIZATION_COLORS[authorization])}>
                  {AUTHORIZATION_LABELS[authorization]}
                </span>
              )}
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => void getDesktopNotificationsBridge()?.openNotificationSettings()}
              >
                System Settings…
              </Button>
            </SettingsRow>
          )}
          <SettingsRow
            title="Test notification"
            description="Send a sample banner to check delivery"
          >
            <Button variant="outline" size="sm" className="text-xs" onClick={sendTest}>
              Send test
            </Button>
          </SettingsRow>
        </SettingsCard>
      </div>
      <div className="mt-8">
        <h2 className="mb-3 text-sm text-foreground/90">Sidebar</h2>
        <SettingsCard>
          <SettingsRow
            title="Vicoa Mobile"
            description="Show the Vicoa Mobile page in the sidebar"
          >
            <Select
              value={mobileHidden ? 'hidden' : 'shown'}
              onValueChange={(v) => setMobileSidebarHidden(v === 'hidden')}
            >
              <SelectTrigger
                aria-label="Vicoa Mobile sidebar visibility"
                className="h-7 w-auto gap-1.5 border-border/70 bg-foreground/[0.06] px-2.5 py-0 text-xs shadow-none focus:ring-0 focus:ring-offset-0"
              >
                <SelectValue>{mobileHidden ? 'Hidden' : 'Shown'}</SelectValue>
              </SelectTrigger>
              <SelectContent align="end" className="bg-menu font-mono">
                <SelectItem value="shown" className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground">
                  Shown
                </SelectItem>
                <SelectItem value="hidden" className="cursor-pointer text-xs focus:bg-foreground/[0.06] dark:focus:bg-foreground/10 focus:text-foreground">
                  Hidden
                </SelectItem>
              </SelectContent>
            </Select>
          </SettingsRow>
        </SettingsCard>
      </div>
      <CliCommandCard />
      <UpdatesCard />
    </section>
  );
}

/**
 * Install the `vicoa` terminal command (the CLI the app already bundles) onto
 * the user's PATH. Hidden on plain web (no bridge). The result — including the
 * "add this to your PATH" hint when ~/.local/bin isn't on PATH — is shown inline
 * rather than in a native dialog (that dialog is what the app menu item uses).
 */
function CliCommandCard() {
  const [hasBridge, setHasBridge] = useState(false);
  const [status, setStatus] = useState<CliLinkStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CliInstallResult | null>(null);

  useEffect(() => {
    setHasBridge(getDesktopCliBridge() !== null);
    void getCliStatus().then(setStatus);
  }, []);

  if (!hasBridge) return null;

  const install = async () => {
    setBusy(true);
    const res = await installCli();
    setResult(res);
    setStatus(await getCliStatus());
    setBusy(false);
  };

  const disabled = busy || status?.foreign === true || (status !== null && !status.available);

  return (
    <div className="mt-8">
      <h2 className="mb-3 text-sm text-foreground/90">Command line</h2>
      <SettingsCard>
        <SettingsRow title="Terminal command" description={cliRowDescription(status)}>
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            disabled={disabled}
            onClick={() => void install()}
          >
            {cliButtonLabel(status, busy)}
          </Button>
        </SettingsRow>
        {result && (
          <div className="px-4 py-3 text-xs">
            <div className={result.ok ? 'text-success' : 'text-warning'}>{result.message}</div>
            {result.detail && (
              <div className="mt-1 whitespace-pre-wrap text-muted-foreground">{result.detail}</div>
            )}
          </div>
        )}
      </SettingsCard>
    </div>
  );
}

function updateStatusLabel(status: UpdateStatus): string {
  switch (status.state) {
    case 'checking':
      return 'Checking for updates…';
    case 'available':
      return `Version ${status.version} available`;
    case 'downloading':
      return `Downloading… ${status.percent}%`;
    case 'downloaded':
      return `Version ${status.version} ready — restart to install`;
    case 'not-available':
      return 'You’re on the latest version';
    case 'error':
      return 'Update check failed — try again';
    default:
      return 'Check for a newer version';
  }
}

/**
 * Version readout + updater controls. Hidden on plain web (no bridge). The
 * button follows the status: Check → Download → Restart to update; the same
 * flow the sidebar SidebarUpdateCallout offers, surfaced in Settings.
 */
function UpdatesCard() {
  const status = useDesktopUpdateStatus();
  const [version, setVersion] = useState<string | null>(null);
  const [hasBridge, setHasBridge] = useState(false);

  useEffect(() => {
    setHasBridge(getDesktopUpdatesBridge() !== null);
    void getAppVersion().then(setVersion);
  }, []);

  if (!hasBridge) return null;

  const checking = status.state === 'checking';

  return (
    <div className="mt-8">
      <h2 className="mb-3 text-sm text-foreground/90">About</h2>
      <SettingsCard>
        <SettingsRow title="Version" description="The version of Vicoa you’re running">
          <span className="text-xs text-muted-foreground">{version ?? '—'}</span>
        </SettingsRow>
        <SettingsRow title="Updates" description={updateStatusLabel(status)}>
          {status.state === 'available' ? (
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => void downloadUpdate()}
            >
              Download
            </Button>
          ) : status.state === 'downloaded' ? (
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => void quitAndInstallUpdate()}
            >
              Restart to update
            </Button>
          ) : status.state === 'downloading' ? (
            <span className="text-xs text-muted-foreground">{status.percent}%</span>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              disabled={checking}
              onClick={() => void checkForUpdates()}
            >
              {checking ? 'Checking…' : 'Check for updates'}
            </Button>
          )}
        </SettingsRow>
      </SettingsCard>
    </div>
  );
}

const SHORTCUT_SECTION_ORDER = ['General', 'Sessions', 'Chat', 'Code review', 'Files', 'Panel', 'Terminal'] as const;

function ShortcutsSection() {
  // Re-render on binding changes (recording saves, resets).
  const [, bump] = useReducer((n: number) => n + 1, 0);
  useEffect(() => subscribeShortcuts(bump), []);

  const [recordingId, setRecordingId] = useState<ShortcutId | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // While recording, capture the next non-modifier chord window-wide. The
  // settings page mounts neither the session sidebar nor the files/git panel,
  // so the live shortcut handlers can't fire mid-recording.
  useEffect(() => {
    if (recordingId === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (
        event.code === 'Escape' &&
        !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey
      ) {
        setRecordingId(null);
        setNotice(null);
        return;
      }
      if (isModifierCode(event.code)) return; // wait for the full chord
      const combo = {
        code: event.code,
        meta: event.metaKey || event.ctrlKey,
        shift: event.shiftKey,
        alt: event.altKey,
      };
      if (!combo.meta && !combo.alt) {
        setNotice(isMacPlatform() ? 'Include ⌘ or ⌥' : 'Include Ctrl or Alt');
        return;
      }
      const conflict = findShortcutConflict(recordingId, combo);
      if (conflict) {
        setNotice(`In use: ${conflict.label}`);
        return;
      }
      setShortcutOverride(recordingId, combo);
      setRecordingId(null);
      setNotice(null);
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [recordingId]);

  const startRecording = (id: ShortcutId) => {
    setRecordingId(id);
    setNotice(null);
  };

  const stopRecording = () => {
    setRecordingId(null);
    setNotice(null);
  };

  return (
    <section>
      <SectionTitle>Keyboard shortcuts</SectionTitle>
      <p className="mt-2 text-xs text-muted-foreground">
        Click a shortcut to record a new one. Esc cancels.
      </p>
      <div className="mt-1">
        {SHORTCUT_SECTION_ORDER.map((title) => (
          <div key={title}>
            <div className="pt-6 pb-1 text-xs text-muted-foreground">{title}</div>
            {/* The ⌘1–9 jump is a 9-key range, so it isn't rebindable. */}
            {title === 'Sessions' && (
              <ShortcutRow label="Go to the 1st–9th session">
                <span
                  className="flex items-center gap-1 px-1.5 py-1"
                  title="Not customizable"
                >
                  <Keycap>{primaryModifierLabel()}</Keycap>
                  <Keycap>1–9</Keycap>
                </span>
              </ShortcutRow>
            )}
            {/* Panel tab cycling is a fixed Ctrl+Tab combo (VSCode/browser
                convention) — not rebindable, since this shortcut model has no
                Control modifier. */}
            {title === 'Panel' && (
              <>
                <ShortcutRow label="Next panel tab (wraps)">
                  <span className="flex items-center gap-1 px-1.5 py-1" title="Not customizable">
                    <Keycap>⌃</Keycap>
                    <Keycap>⇥</Keycap>
                  </span>
                </ShortcutRow>
                <ShortcutRow label="Previous panel tab (wraps)">
                  <span className="flex items-center gap-1 px-1.5 py-1" title="Not customizable">
                    <Keycap>⌃</Keycap>
                    <Keycap>⇧</Keycap>
                    <Keycap>⇥</Keycap>
                  </span>
                </ShortcutRow>
              </>
            )}
            {SHORTCUT_DEFS.filter((def) => def.section === title).map((def) => {
              const recording = recordingId === def.id;
              const overridden = isShortcutOverridden(def.id);
              return (
                <ShortcutRow key={def.id} label={def.label}>
                  {overridden && !recording && (
                    <button
                      type="button"
                      title="Reset to default"
                      aria-label={`Reset ${def.label} to default`}
                      onClick={() => clearShortcutOverride(def.id)}
                      className="flex h-5 w-5 cursor-pointer items-center justify-center rounded text-muted-foreground/60 hover:bg-muted/60 hover:text-foreground"
                    >
                      <RotateCcw className="h-3 w-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    title={recording ? 'Press the new shortcut' : 'Click to change'}
                    onClick={() => (recording ? stopRecording() : startRecording(def.id))}
                    onBlur={() => {
                      if (recording) stopRecording();
                    }}
                    className={cn(
                      'flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-1 transition-colors',
                      recording
                        ? 'border border-foreground/40'
                        : 'border border-transparent hover:bg-muted/50',
                    )}
                  >
                    {recording ? (
                      <span
                        className={cn(
                          'px-1 text-[11px]',
                          notice ? 'text-amber-400' : 'text-foreground',
                        )}
                      >
                        {notice ?? 'Press keys'}
                      </span>
                    ) : (
                      comboKeycaps(getShortcutCombo(def.id)).map((key, index) => (
                        <Keycap key={`${key}-${index}`}>{key}</Keycap>
                      ))
                    )}
                  </button>
                </ShortcutRow>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

function ShortcutRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/40 py-2">
      <span className="text-[13px] text-foreground/90">{label}</span>
      <span className="flex shrink-0 items-center gap-1">{children}</span>
    </div>
  );
}

function Keycap({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="flex h-5 min-w-5 items-center justify-center rounded border border-border/70 bg-menu px-1 font-mono text-[10px] text-muted-foreground">
      {children}
    </kbd>
  );
}
