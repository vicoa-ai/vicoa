// Backend API Client
// This client integrates with the backend API

import { getBrowserAccessToken } from '@/lib/auth/browser-token';
import { getCloudApiBase, getDesktopConfig } from '@/lib/runtime-config';
import type { LiveState } from '@/lib/session-liveness';

export interface BackendConfig {
  baseUrl: string;
  useSupabaseAuth?: boolean;
  accessToken?: string; // For server-side use with pre-obtained token
}

// Types based on the OpenAPI spec
export interface AgentStatus {
  STARTING: 'STARTING';
  ACTIVE: 'ACTIVE';
  AWAITING_INPUT: 'AWAITING_INPUT';
  REVIEWED: 'REVIEWED';
  PAUSED: 'PAUSED';
  STALE: 'STALE';
  COMPLETED: 'COMPLETED';
  FAILED: 'FAILED';
  KILLED: 'KILLED';
  DISCONNECTED: 'DISCONNECTED';
  DELETED: 'DELETED';
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  /** Served by us (/api/v1/users/{id}/avatar); render via `<PrincipalAvatar>`. */
  avatar_image_uri?: string | null;
  avatar_source?: string | null;
  /** Picked emoji, shown when there is no image (see lib/principals.ts). */
  avatar_emoji?: string | null;
  /** Cache-buster for the stable avatar URL (see lib/principals.ts). */
  updated_at?: string | null;
}

/**
 * A saved agent preset (collaboration P1): provider + model + config +
 * instructions, with a name and an avatar. `config` is the verbatim
 * `SessionConfig` shape, so it can be handed straight to `reconcileAgainst`.
 */
export interface AgentProfile {
  id: string;
  /** NULL ⇒ the caller's own; set ⇒ a team's agent, which every member of
   *  that team can run. */
  team_id?: string | null;
  /** Whether the caller may edit, archive or delete it: always for their
   *  own, only the team's owner and admins for a team's. Absent (older
   *  backends) means their own. */
  can_edit?: boolean;
  name: string;
  description: string | null;
  avatar_image_uri: string | null;
  avatar_source: string | null;
  color: string | null;
  emoji: string | null;
  agent: string;
  config: Record<string, unknown>;
  system_prompt: string | null;
  default_machine_id: string | null;
  default_project_id: string | null;
  position: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  /** Sessions this agent has started. Null from the agent-facing CLI mirror,
   *  which does not compute it. */
  session_count?: number | null;
  /** When any of those sessions was last active — `max(updated_at)`, not the
   *  newest start time, so a long session still being worked in reads as
   *  recent. Null when the agent has never run (or from the CLI mirror). */
  last_active_at?: string | null;
}

export interface AgentProfileInput {
  name?: string;
  agent?: string;
  description?: string | null;
  color?: string | null;
  emoji?: string | null;
  config?: Record<string, unknown>;
  system_prompt?: string | null;
  default_machine_id?: string | null;
  default_project_id?: string | null;
  position?: number;
  is_archived?: boolean;
  /** Create in (or move to) a team's list; `null` moves it back to yours. */
  team_id?: string | null;
}

/** The avatar endpoints' payload. Deliberately carries no email — an avatar is
 *  the one identity field a shared surface renders. */
export interface UserAvatar {
  id: string;
  display_name: string | null;
  avatar_image_uri: string | null;
  avatar_source: string | null;
  avatar_emoji: string | null;
  updated_at: string;
}

export interface APIKeyResponse {
  id: string;
  name: string;
  api_key: string;
  created_at: string;
  expires_at: string | null;
  is_active: boolean;
}

export interface AgentInstanceResponse {
  id: string;
  agent_type_id: string;
  agent_type_name: string | null;
  name: string | null;
  status: keyof AgentStatus;
  started_at: string;
  ended_at: string | null;
  latest_message: string | null;
  latest_message_at: string | null;
  chat_length: number;
  project?: string | null;
  /**
   * Formal projects-entity id, auto-matched server-side from the session's
   * (machine, working-dir) — and, for a linked worktree, its source repo
   * root/remote. Drives the sidebar's top-level project grouping; null when no
   * project is set up for that checkout (grouping then falls back to the
   * `project` path basename). See session-grouping.ts `projectGroupKey`.
   */
  project_id?: string | null;
  /**
   * The task this run works on. Read-only on this DTO — it is written by
   * `updateAgentInstance(id, { task_id })`. The composer's `#` reference reads
   * it to tell a new link from a session that already belongs to a task.
   */
  task_id?: string | null;
  home_dir?: string | null;
  pinned_at?: string | null;
  /**
   * Which agent profile started this session (collab P1) — provenance only, so
   * the row can show that agent's name and avatar rather than a generic
   * provider mark. Resolved client-side against the profile list the picker
   * already holds; see lib/use-agent-profiles.ts.
   */
  agent_profile_id?: string | null;
  /** Host this session runs on. Null for legacy TUI-registered sessions. */
  machine_id?: string | null;
  last_heartbeat_at?: string | null;
  /**
   * Linked git worktree this session runs in, probed from its cwd at
   * registration. Null for a repo's main checkout, for non-git directories,
   * and for sessions that predate the field — all of which render directly
   * under their project rather than in a synthetic "main" bucket.
   */
  worktree_name?: string | null;
  /** Registration-time stamps (`source`, `repo_root`, usage…); see the type. */
  instance_metadata?: SessionInstanceMetadata | null;
  /**
   * Server-derived liveness at fetch time. Prefer `useSessionLiveness`, which
   * recomputes this on a timer — see lib/session-liveness.ts for why a
   * transported value goes stale.
   */
  live_state?: LiveState;
  /**
   * Set only on a session someone else owns (scope=shared|all): its owner and
   * the caller's standing. Such a row also arrives with no `machine_id`,
   * `home_dir` or absolute paths, so nothing can aim a daemon RPC at it.
   */
  owner?: PrincipalResponse | null;
  viewer_role?: ProjectRole | null;
  /**
   * See AgentInstanceDetail.participants. On a list row it is set only once
   * someone besides the owner has written in the session; a solo row carries
   * an empty list, so it renders exactly as it always has.
   */
  participants?: PrincipalResponse[];
}

export type AgentInstanceScope = 'me' | 'shared' | 'all';

export interface PaginatedAgentInstanceResponse {
  items: AgentInstanceResponse[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ListAgentInstancesOptions {
  limit?: number;
  offset?: number;
  scope?: AgentInstanceScope;
  activeOnly?: boolean;
}

export interface AgentInstancesPage {
  items: AgentInstanceResponse[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  isPaginated: boolean;
}

/**
 * Server-aggregated activity for the profile page. `daily` maps a local-ish
 * `YYYY-MM-DD` day to the number of user-sent messages that day (drives the
 * heatmap + streak). Totals are all-time. With `?since=<day>` the server may
 * return only days >= since (the client overwrites those in its cache).
 * See docs/superpowers/specs for the endpoint contract.
 */
export interface ActivityResponse {
  daily: Record<string, number>;
  total_sessions: number;
  /** All-time count of the user's own (user-sent) messages. */
  total_user_messages: number;
  /** All-time count of all messages (user + agent) in the user's sessions. */
  total_messages: number;
  as_of: string;
}

export interface AgentTypeOverview {
  id: string;
  name: string;
  created_at: string;
  recent_instances: AgentInstanceResponse[];
  total_instances: number;
  active_instances: number;
}

export interface MessageResponse {
  id: string;
  content: string;
  sender_type: string;
  /**
   * Who wrote a user message; null for one typed into the owner's terminal.
   * Read against the session's `participants` to name its author.
   */
  sender_user_id?: string | null;
  sender_user_display_name?: string | null;
  created_at: string;
  requires_user_input: boolean;
  message_metadata?: Record<string, unknown> | null;
}

/** One session/weekly rate-limit window in the usage blob. */
export interface SessionUsageWindow {
  id: string;
  label: string;
  used_pct: number;
  resets_at?: string | null;
}

/** GET /machines/{id}/agent-models — see `getMachineAgentModels`. */
export interface MachineAgentModelsCache {
  models: Record<string, { id: string; label: string }[]>;
  modes: Record<string, { id: string; label: string }[]>;
}

/**
 * Live usage stamped by the headless runner onto `instance_metadata.usage`
 * (Claude + Codex). `context` is the per-conversation token fill; `limits` is
 * the account's session/weekly rate limits plus an optional credit balance.
 */
export interface SessionUsage {
  context?: {
    used_tokens: number;
    max_tokens: number | null;
    cost_usd: number | null;
  } | null;
  limits?: {
    windows: SessionUsageWindow[];
    credits?: { unit: string; remaining: number } | null;
  } | null;
  updated_at?: string;
}

export interface SessionInstanceMetadata {
  usage?: SessionUsage | null;
  /**
   * Where the session was launched from, stamped once at registration:
   * `"app"` for the headless runners the machine daemon spawns, `"terminal"`
   * for the interactive CLI wrapper. Absent on pre-stamping sessions.
   */
  source?: string | null;
  /**
   * The repo's MAIN checkout (home-collapsed), stamped at registration. For a
   * session in a linked worktree this differs from its own `project` — it is
   * where worktree-level git RPCs must run, since the worktree folder itself
   * may be gone by the time the sidebar acts on it. Absent on non-git dirs and
   * pre-stamping sessions.
   */
  repo_root?: string | null;
  [key: string]: unknown;
}

export interface AgentInstanceDetail {
  id: string;
  agent_type_id: string;
  agent_type_name: string;
  name: string | null;
  status: keyof AgentStatus;
  started_at: string;
  ended_at: string | null;
  git_diff: string | null;
  messages: MessageResponse[];
  last_read_message_id: string | null;
  project?: string | null;
  home_dir?: string | null;
  pinned_at?: string | null;
  session_config?: Record<string, unknown> | null;
  /**
   * Which agent profile started this session (collab P1). PROVENANCE ONLY —
   * `session_config` is what it's actually running, and the two legitimately
   * diverge the moment the user switches model mid-session. Resolve the name
   * and avatar from the profile list the picker already holds.
   */
  agent_profile_id?: string | null;
  /** See AgentInstanceResponse.project_id. */
  project_id?: string | null;
  /** See AgentInstanceResponse.task_id. */
  task_id?: string | null;
  instance_metadata?: SessionInstanceMetadata | null;
  machine_id?: string | null;
  last_heartbeat_at?: string | null;
  /** See AgentInstanceResponse.worktree_name. */
  worktree_name?: string | null;
  /** See AgentInstanceResponse.live_state — prefer useSessionLiveness. */
  live_state?: LiveState;
  /** Whether the caller owns the session (vs. reaching it through a share). */
  is_owner?: boolean;
  access_level?: 'READ' | 'WRITE';
  /** See AgentInstanceResponse.owner / viewer_role. */
  owner?: PrincipalResponse | null;
  viewer_role?: ProjectRole | null;
  /**
   * Everyone who has written in the session: the owner first, then each
   * other sender in order of their first message. The avatar stack and the
   * author headers show only when there is more than one (collaboration §8.2).
   */
  participants?: PrincipalResponse[];
  /**
   * The automation whose run started this session, when the caller may see
   * that automation. Null for a session someone started by hand.
   */
  automation?: AutomationRef | null;
}

/** Just enough of an automation to name it and link to it. */
export interface AutomationRef {
  id: string;
  title: string;
  /** True when the automation runs in this session rather than started it. */
  runs_here?: boolean;
}

export interface UserMessageRequest {
  content: string;
  /** Ids of images eagerly uploaded via /api/attachments; ride the message. */
  attachment_ids?: string[];
}

export interface MachineSummary {
  machine_id: string;
  display_name?: string | null;
  hostname?: string | null;
  platform?: string | null;
  home_dir?: string | null;
  last_heartbeat_at?: string | null;
  metadata?: Record<string, unknown> | null;
  recent_directories: string[];
}

export interface MachineListResponse {
  machines: MachineSummary[];
}

export type RemoteAgentType =
  | 'claude'
  | 'codex'
  | 'opencode'
  | 'cursor'
  | 'gemini'
  | 'copilot'
  | 'kimi'
  | 'hermes';

export interface SpawnRemoteSessionResponse {
  request_id: string;
  agent_instance_id: string;
}

export interface SpawnRequestStatus {
  request_id: string;
  machine_id: string;
  directory: string;
  agent: string;
  status: 'pending' | 'claimed' | 'started' | 'success' | 'error';
  message: string | null;
  agent_instance_id: string | null;
  created_at: string;
  claimed_at: string | null;
  completed_at: string | null;
  metadata: Record<string, any> | null;
}

export interface SlashCommandItem {
  name: string;
  description: string;
  /** 'command' or 'skill'. Absent on rows synced before the field existed. */
  kind?: 'command' | 'skill';
  /** Composer text to insert on selection when it differs from /name (Codex skills use $name). */
  insert?: string | null;
}

export interface SlashCommandsResponse {
  agent_type: string;
  commands: SlashCommandItem[];
}

export interface FileMentionsResponse {
  project_path: string;
  files: string[];
  file_count: number;
}

export interface FileMention {
  path: string;
}

export type BillingTier = 'pro' | 'team';

/** A Team seat someone else pays for: "your seat comes from <name>". */
export interface SeatCoverage {
  name: string;
  /** The team the seat comes through; null for an outside editor. */
  team_id: string | null;
}

/**
 * The caller's subscription and entitlement. `plan_type` is what every client
 * gates on: 'pro' for their own Pro or Team, and also for a member whose Team
 * seat someone else pays for (`covered_by`). `tier` tells Pro from Team.
 */
export interface BillingSubscription {
  id: string;
  plan_type: string;
  agent_limit: number;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  provider: 'stripe' | 'apple' | 'google' | null;
  /** Seats bought on Vicoa Team; null on every other plan. */
  seat_quantity?: number | null;
  tier?: BillingTier | null;
  covered_by?: SeatCoverage | null;
}

/** One per-seat price as Stripe has it (minor units). */
export interface SeatPrice {
  unit_amount: number;
  currency: string;
}

/**
 * The caller's seats as a payer (collaboration §6): everyone their
 * subscription covers, themselves, the editing members of teams they own and
 * outside editors on their work, minus anyone with their own Pro (`own_pro`).
 * `over` = more in use than the plan includes: nobody loses access, but nobody
 * new can be added until seats are bought.
 * Only the hosted build serves this; elsewhere the call 404s.
 */
export interface BillingSeats {
  used: number;
  /** null ⇒ unlimited. */
  included: number | null;
  over: boolean;
  /** People on the caller's work who bring their own Pro: no seat taken. */
  own_pro: number;
  plan_type: string;
  tier: BillingTier | null;
  provider: 'stripe' | 'apple' | 'google' | null;
  /** Seats bought on Vicoa Team; null otherwise. */
  purchased: number | null;
  /** The fewest seats Vicoa Team sells. */
  min_quantity: number;
  /** An owner always sees the Team card on Billing. */
  owns_team: boolean;
  /** What buying or changing seats does from here: change the Stripe
   *  subscription in place (prorated, so confirm first) or open Checkout. */
  change_mode: 'checkout' | 'in_place';
  /** The interval a live Stripe subscription (per seat or Pro) is billed at;
   *  null without one. */
  billing_interval: BillingInterval | null;
  per_seat_available: boolean;
  prices: { monthly: SeatPrice | null; annual: SeatPrice | null } | null;
}

export interface ChangeBillingSeatsResponse {
  status: 'checkout' | 'updated';
  checkout_url: string | null;
  seats: BillingSeats | null;
}

export interface BillingUsage {
  total_agents: number;
  agent_limit: number;
  period_start: string;
  period_end: string;
}

// Projects & Tasks (human task tracker — plans/todos/tasks-and-projects-feature.md)
export type TaskStatus =
  | 'backlog'
  | 'todo'
  | 'in_progress'
  | 'in_review'
  | 'done'
  | 'blocked'
  | 'cancelled';

export type TaskPriority = 'urgent' | 'high' | 'medium' | 'low' | 'none';

/** Where a project is checked out on one machine; at most one per machine. */
export interface ProjectDirectory {
  machine_id: string;
  machine_name: string | null;
  local_path: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  /**
   * Task-identifier prefix — "VIC" makes this project's tasks read "VIC-42".
   * Auto-derived on the project's first task, so it is null for a project that
   * has never held one. Editable in project settings; unique within the owner,
   * never globally.
   */
  key: string | null;
  git_remote_url: string | null;
  color: string | null;
  icon: string | null;
  /**
   * Served URL for an uploaded/seeded image icon, or null. Rendered via the
   * same-origin proxy (see lib/project-icons.ts `projectIconSrc`) since an
   * <img> can't carry the backend bearer. Fallback chain when null: emoji
   * `icon` → Folder glyph.
   */
  icon_image_uri: string | null;
  /** Who set the image: 'user' (upload, wins) | 'git' (seeded) | null. */
  icon_source: string | null;
  /**
   * DEPRECATED, always false. "No project" is a null `project_id` on the task
   * or session, not a project row. Kept one release for old clients.
   */
  is_inbox: boolean;
  is_archived: boolean;
  archived_at: string | null;
  /**
   * Newest session start in this project, for recency ordering. Only the list
   * endpoint knows it; single-project responses leave it null.
   */
  last_activity_at?: string | null;
  /**
   * The caller's manual rank (0-based) from `setProjectOrder`, null when they
   * never dragged this project into place. The list already comes back in
   * rank order (ranked first, then recency), so this only answers "does the
   * user have a custom order at all?". Only the list endpoint sets it.
   */
  position?: number | null;
  directories: ProjectDirectory[];
  created_at: string;
  updated_at: string;
  /** NULL ⇒ personal; set ⇒ team-owned (collaboration §2). */
  team_id?: string | null;
  /**
   * The caller's standing on this project and which areas it covers
   * (collaboration §4). Defaults server-side to the least privilege, so a
   * missing field must be read as "viewer", never as "owner".
   */
  role?: ProjectRole;
  scopes?: GrantScope[];
  /**
   * Who owns a project the caller does not (the user, or the team for a
   * team-owned one). Null/absent on the caller's own projects. Never carries
   * an email.
   */
  owner?: PrincipalResponse | null;
  /**
   * Whether it is in the caller's own project list: always for one they own;
   * for one shared with them, once they follow it — until then it sits under
   * "Shared with me" only. Absent from an older backend: read as not followed.
   */
  followed?: boolean;
  /**
   * The caller is on the team that owns this project: it is their team's
   * work, always in their own list, reached through the team. Not a share
   * they can stop following or leave. Absent from an older backend: false.
   */
  is_team_member?: boolean;
}

/** Echo of `setProjectOrder`: the ids actually stored, in order. */
export interface ProjectOrderResponse {
  project_ids: string[];
}

/** Echo of `setAutomationOrder`: the ids actually stored, in order. */
export interface AutomationOrderResponse {
  automation_ids: string[];
}

/** What deleting the project would file under No project — for the confirm dialog. */
export interface ProjectSummaryResponse {
  task_count: number;
  session_count: number;
  active_session_count: number;
}

export type ProjectRole = 'viewer' | 'commenter' | 'editor' | 'admin' | 'owner';
/** What a grant covers. `automations` came later: older grants hold only the
 *  first two, and owners and team members cover all three. */
export type GrantScope = 'tasks' | 'sessions' | 'automations';

const PROJECT_ROLE_RANK: Record<ProjectRole, number> = {
  viewer: 1,
  commenter: 2,
  editor: 3,
  admin: 4,
  owner: 5,
};

/** Whether `role` reaches `minimum` on the ladder; an absent role is a viewer. */
export function projectRoleAtLeast(role: ProjectRole | undefined, minimum: ProjectRole): boolean {
  return PROJECT_ROLE_RANK[role ?? 'viewer'] >= PROJECT_ROLE_RANK[minimum];
}

export interface TaskLabelResponse {
  id: string;
  name: string;
  /** Always #rrggbb — the backend pins the format (chips inline-style it). */
  color: string;
  /** NULL ⇒ the caller's own vocabulary; set ⇒ that team's. */
  team_id?: string | null;
}

/** A user, a team or an agent, in the one shape `<PrincipalAvatar>` renders. */
export interface PrincipalResponse {
  type: 'user' | 'team' | 'agent' | 'system';
  id: string | null;
  name: string | null;
  avatar_image_uri: string | null;
  emoji: string | null;
  updated_at: string | null;
}

// --- Teams & people (collaboration §3.2, §3.3, §8.4) -------------------------

/** `viewer` is the free role: sees and comments, cannot edit or prompt. */
export type TeamRole = 'owner' | 'admin' | 'member' | 'viewer';
export type GrantRole = Exclude<ProjectRole, 'owner'>;

export interface TeamSummary {
  id: string;
  name: string;
  /** Reserved, not routable (D-D): shown read-only, never an input. */
  slug: string;
  avatar_image_uri: string | null;
  role: TeamRole;
  /** Active + invited: everyone holding a seat. */
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface TeamMember {
  id: string;
  user_id: string | null;
  /** Only owners/admins receive addresses; plain members see names only. */
  email: string | null;
  display_name: string | null;
  avatar_image_uri: string | null;
  role: TeamRole;
  status: 'invited' | 'active';
  /** Set while a viewer only because the seat paying for them lapsed (the
   *  owner's Team subscription ended): the role that comes back with seats. */
  lapsed_role?: 'admin' | 'member' | null;
  joined_at: string | null;
  created_at: string;
}

export interface TeamDetail extends TeamSummary {
  members: TeamMember[];
}

export interface TeamMemberInvite extends TeamMember {
  /** False when this server has no mail transport; pass `join_url` on by hand. */
  email_sent: boolean;
  join_url: string;
}

export interface TeamInviteLink {
  id: string;
  token: string;
  role: TeamRole;
  expires_at: string | null;
  max_uses: number | null;
  uses: number;
  created_at: string;
}

export interface TeamInvitePreview {
  team_id: string;
  name: string;
  avatar_image_uri: string | null;
  role: TeamRole;
  member_count: number;
}

/** A pending email invite addressed to the signed-in user. */
export interface TeamInvitation {
  team_id: string;
  name: string;
  slug: string;
  avatar_image_uri: string | null;
  role: TeamRole;
  invited_by_display_name: string | null;
  created_at: string;
}

/** One row of a project's People list: the owner, or a grant. */
export interface ProjectPerson {
  /** null on the owner row — ownership is a column, not a grant. */
  id: string | null;
  principal: PrincipalResponse;
  /** Beside the principal, never inside it; only project admins can list. */
  email: string | null;
  /** An email grant waiting for that address to sign up. */
  pending: boolean;
  role: ProjectRole;
  scopes: GrantScope[];
  member_count: number | null;
  /** Set while a grant reads commenter because the seat paying for it
   *  lapsed: the role that comes back with seats. */
  lapsed_role?: 'editor' | 'admin' | null;
  is_owner: boolean;
  is_self: boolean;
  created_at: string | null;
}

export interface ProjectGrantCreated extends ProjectPerson {
  email_sent: boolean;
}

export type CreateProjectGrantRequest =
  | { email: string; team_id?: never; role: GrantRole; scopes: GrantScope[] }
  | { team_id: string; email?: never; role: GrantRole; scopes: GrantScope[] };

/** One row of a session's own shares (the owner, a person, or a team). */
export interface SessionShare {
  id: string;
  principal_type: 'user' | 'team';
  email: string | null;
  access: 'READ' | 'WRITE';
  user_id: string | null;
  team_id: string | null;
  display_name: string | null;
  avatar_image_uri: string | null;
  member_count: number | null;
  invited: boolean;
  is_owner: boolean;
  /** A WRITE share reading READ because the seat paying for it lapsed. */
  lapsed?: boolean;
  created_at: string;
  updated_at: string;
}

export type CreateSessionShareRequest =
  | { email: string; team_id?: never; access: 'READ' | 'WRITE' }
  | { team_id: string; email?: never; access: 'READ' | 'WRITE' };

export interface TaskResponse {
  id: string;
  /** null = "No project" (unfiled) — the same convention as a session's `project_id`. */
  project_id: string | null;
  /** Per-project sequential number; null for an unfiled task or one that predates the backfill. */
  number: number | null;
  /** "VIC-42" — null for an unfiled task, or when the project has no key / the task no number. */
  identifier: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  position: number;
  parent_task_id: string | null;
  /** Denormalized so a sub-task can say "Part of: <title>" without a refetch. */
  parent_title: string | null;
  assignee_type: 'user' | 'agent' | null;
  assignee_id: string | null;
  assignee: PrincipalResponse | null;
  labels: TaskLabelResponse[];
  start_date: string | null;
  due_date: string | null;
  /**
   * The session the task was created in (`vicoa task create` run inside one).
   * Only an id: the timeline's `sessions` names it when the viewer may open it.
   */
  created_in_instance_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskReactionSummary {
  emoji: string;
  count: number;
  /** Whether the signed-in user is one of them — drives the pill's filled state. */
  reacted: boolean;
  /**
   * Who reacted, oldest first, capped server-side. `count` is the true total,
   * so "and N others" is the difference.
   */
  reactors: PrincipalResponse[];
}

export interface TaskCommentResponse {
  id: string;
  task_id: string;
  /**
   * The root this comment answers, or null when it is one. Threads are one
   * level deep, so this always names a root — never another reply. The list
   * arrives in thread order: each root immediately followed by its replies.
   */
  parent_comment_id: string | null;
  author: PrincipalResponse;
  /** The session it was posted from, if any — "via <session>". */
  agent_instance_id: string | null;
  /** null once soft-deleted; render a tombstone, not an empty comment. */
  body: string | null;
  kind: 'comment' | 'system';
  reactions: TaskReactionSummary[];
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
}

export interface TaskActivityResponse {
  id: string;
  /** null when the change had no request context (a background sweep). */
  actor: PrincipalResponse | null;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
}

/** A session the timeline mentions ("Created in", "via"), by name. */
export interface TaskSessionRef {
  id: string;
  name: string | null;
  agent_type_name: string | null;
}

export interface TaskTimelineResponse {
  comments: TaskCommentResponse[];
  activity: TaskActivityResponse[];
  /** Reactions on the task itself, not on any comment. */
  reactions: TaskReactionSummary[];
  /**
   * The sessions the task or its rows came from that the viewer may open. A
   * session id with no entry here is one they can't: show no link or title.
   */
  sessions: TaskSessionRef[];
}

export interface CreateProjectRequest {
  name: string;
  color?: string | null;
  icon?: string | null;
  git_remote_url?: string | null;
}

export interface UpdateProjectRequest {
  name?: string;
  color?: string | null;
  icon?: string | null;
  git_remote_url?: string | null;
  is_archived?: boolean;
  /**
   * Task-identifier prefix ("VIC" → "VIC-42"): 2–8 letters/digits, starting
   * with a letter; the backend uppercases it. Unique within the owner — a
   * clash comes back as 409.
   */
  key?: string;
}

export interface CreateTaskRequest {
  title: string;
  description?: string | null;
  /** Omitted → No project (unfiled: no identifier). */
  project_id?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  position?: number;
  parent_task_id?: string | null;
  label_ids?: string[];
  start_date?: string | null;
  due_date?: string | null;
}

export interface UpdateTaskRequest {
  title?: string;
  description?: string | null;
  project_id?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  position?: number;
  parent_task_id?: string | null;
  label_ids?: string[];
  start_date?: string | null;
  due_date?: string | null;
  /** The pair moves together — the backend rejects one without the other. */
  assignee_type?: 'user' | 'agent' | null;
  assignee_id?: string | null;
}

export interface CreateTaskLabelRequest {
  name: string;
  color: string;
  /** Create in a team's vocabulary (needs membership) instead of your own. */
  team_id?: string | null;
}

// --- Automations (scheduled agent runs) -----------------------------------

export type AutomationScheduleKind = 'once' | 'recurring';
export type AutomationRunStatus =
  | 'fired'
  | 'missed_offline'
  | 'failed'
  | 'skipped';

/** A time-of-day span (local to the automation's timezone) that confines a
 *  sub-daily interval schedule. `end` is inclusive and must be after `start`
 *  (overnight spans are not supported). */
export interface AutomationTimeWindow {
  start: string; // 'HH:MM'
  end: string; // 'HH:MM'
}

/** Weekday convention: 0=Sunday … 6=Saturday. */
export type AutomationFrequency =
  | { kind: 'hourly'; minute: number }
  | { kind: 'daily'; time: string }
  | { kind: 'weekdays'; time: string }
  | { kind: 'weekly'; weekdays: number[]; time: string }
  | {
      kind: 'custom';
      unit: 'minutely';
      interval: number;
      window?: AutomationTimeWindow | null;
    }
  | {
      kind: 'custom';
      unit: 'hourly';
      interval: number;
      minute: number;
      window?: AutomationTimeWindow | null;
    }
  | { kind: 'custom'; unit: 'daily'; interval: number; time: string }
  | { kind: 'custom'; unit: 'weekly'; interval: number; weekdays: number[]; time: string }
  | { kind: 'custom'; unit: 'monthly'; interval: number; monthdays: number[]; time: string };

export interface AutomationWorktree {
  mode: 'none' | 'new' | 'existing';
  path?: string | null;
}

export interface AutomationResponse {
  id: string;
  title: string;
  prompt: string;
  /** Null only on someone else's automation (see `owner`). */
  machine_id: string | null;
  /** On someone else's automation, the folder's name without its path. */
  directory: string;
  worktree: AutomationWorktree | null;
  /** SessionConfig shape (agent / model / effort / permission-mode). */
  session_config: Record<string, unknown>;
  /** Live reference to a saved agent. When set, the scheduler resolves it at
   *  dispatch and `session_config` above is only the fallback snapshot. */
  agent_profile_id?: string | null;
  /** Set when every run continues this session instead of starting a new
   *  one; `machine_id`, `directory` and `session_config` are then its
   *  snapshot. Null on someone else's automation. */
  agent_instance_id?: string | null;
  /** That session's name, when it has one. */
  agent_instance_name?: string | null;
  schedule_kind: AutomationScheduleKind;
  frequency: AutomationFrequency | null;
  timezone: string;
  next_run_at: string | null;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: AutomationRunStatus | null;
  created_at: string;
  updated_at: string;
  /**
   * Set only on an automation someone else wrote, which reaches you through a
   * project shared with you: its author and your standing (never `owner`).
   * Such a row is read-only to you and carries nothing that locates the
   * author's machine.
   */
  owner?: PrincipalResponse | null;
  viewer_role?: ProjectRole | null;
  /** The project the automation's folder files it under; null when none. */
  project_id?: string | null;
}

// --- Workspace search (cmd+K palette) ------------------------------------

export interface SearchSessionResult {
  id: string;
  name: string | null;
  agent_type_name: string | null;
  status: keyof AgentStatus;
  project: string | null;
  /** Null for a terminal session with no computer linked. */
  machine_id?: string | null;
  started_at: string;
  latest_message: string | null;
  latest_message_at: string | null;
  match_source: 'name' | 'project' | 'message';
  /** Context window around the hit; only set for message matches. */
  snippet: string | null;
}

export interface SearchTaskResult {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  /** null = "No project" (unfiled), as on TaskResponse. */
  project_id: string | null;
  updated_at: string;
  match_source: 'title' | 'description';
  snippet: string | null;
}

export interface SearchAutomationResult {
  id: string;
  title: string;
  enabled: boolean;
  schedule_kind: AutomationScheduleKind;
  next_run_at: string | null;
  match_source: 'title' | 'prompt';
  snippet: string | null;
}

export interface WorkspaceSearchResponse {
  query: string;
  sessions: SearchSessionResult[];
  tasks: SearchTaskResult[];
  automations: SearchAutomationResult[];
}

// --- `#` composer references ------------------------------------------------
// Deliberately not the search DTOs above: the palette navigates (so it ranks
// message bodies and carries snippets), `#` attaches — every kind collapses to
// the same row the panel draws plus the one token the message carries.

export type ReferenceKind = 'session' | 'task' | 'automation';

/** Just enough of a project to draw its icon — the fields `ProjectIcon` reads. */
export interface ReferenceProject {
  id: string;
  name: string;
  icon: string | null;
  icon_image_uri: string | null;
  updated_at: string | null;
}

export interface ReferenceCandidate {
  kind: ReferenceKind;
  id: string;
  /** What the panel row reads. */
  label: string;
  /** What follows "#" in the composer — a slug, or "VIC-42" for a task with
   * an identifier. Never contains whitespace. */
  token: string;
  /** Trailing text on the row's single line: the project's name when the item
   * is filed under one, otherwise the folder it runs in (and nothing at all
   * for an unfiled task). */
  meta: string | null;
  /** The project behind `meta`, when there is one. Present only so the row can
   * draw its icon — `meta` already carries the name. */
  project: ReferenceProject | null;
  /** Tasks only, and only when the task really has a key; rendered after
   * `meta` so a filed task reads "Vicoa  VIC-42". */
  identifier: string | null;
  status: string | null;
}

export interface ReferenceCandidatesResponse {
  query: string;
  /** Kind-ordered (sessions → tasks → automations) so the panel can draw a
   * group header wherever `kind` changes and still run one keyboard list. */
  items: ReferenceCandidate[];
}

export interface ReferenceDetail {
  kind: ReferenceKind;
  id: string;
  label: string;
  token: string;
  /** The block appended to the outgoing message. Fetched at pick time so
   * sending never waits on the network. */
  context: string;
}

// --- Share links (collaboration §3.4, P4) -----------------------------------

export type ShareKind = 'session' | 'project';
/** Which parts of a project a link carries — the words a grant already uses. */
export type ShareScope = 'tasks' | 'sessions' | 'automations';
export type ShareAudience = 'public' | 'authenticated';

/** The `tasks` half of a project link's filters. Every list is optional and ANDed. */
export interface ShareBoardFilters {
  label_ids?: string[];
  statuses?: TaskStatus[];
  assignee_ids?: string[];
}

/**
 * The `sessions` half. `statuses`, when given, replaces the default
 * (everything but archived); DELETED is never visible.
 */
export interface ShareSessionsFilters {
  date_from?: string;
  date_to?: string;
  machine_ids?: string[];
  agent_types?: string[];
  statuses?: (keyof AgentStatus)[];
}

/** A project link's filters, one entry per scope it carries. */
export interface ShareProjectFilters {
  sessions?: ShareSessionsFilters;
  tasks?: ShareBoardFilters;
}

export interface CreateShareLinkRequest {
  kind: ShareKind;
  agent_instance_id?: string;
  project_id?: string;
  /** A project link carries at least one; a session link carries none. */
  scopes?: ShareScope[];
  audience?: ShareAudience;
  filters?: ShareProjectFilters | null;
  /** The one write a link can carry; needs a link that carries `tasks`. */
  allow_comments?: boolean;
  /** Show the owner's name/avatar on the page. Off by default. */
  show_owner?: boolean;
  /** Show worktree/branch names on the page. Off by default. */
  show_branch?: boolean;
  expires_in_days?: number | null;
}

/**
 * Edit a live link in place. Every field is optional and absent means "leave
 * it alone"; the token, kind and target are not editable at all — a link is
 * only worth editing because its URL is already out there.
 *
 * `null` is meaningful on two of them (no expiry / no filters), so the caller
 * must omit a key rather than pass `undefined` for "unchanged" — `undefined`
 * disappears in `JSON.stringify`, which happens to be the same thing, but the
 * intent is worth stating.
 */
export interface UpdateShareLinkRequest {
  scopes?: ShareScope[];
  audience?: ShareAudience;
  filters?: ShareProjectFilters | null;
  allow_comments?: boolean;
  show_owner?: boolean;
  show_branch?: boolean;
  /** `null` = never expires. A new window always runs from now. */
  expires_in_days?: number | null;
}

export interface ShareLinkResponse {
  id: string;
  /** The capability itself — the URL is `/share/<token>`. */
  token: string;
  kind: ShareKind;
  agent_instance_id: string | null;
  project_id: string | null;
  scopes: ShareScope[];
  audience: ShareAudience;
  filters: ShareProjectFilters | null;
  allow_comments: boolean;
  show_owner: boolean;
  show_branch: boolean;
  expires_at: string | null;
  revoked_at: string | null;
  last_accessed_at: string | null;
  view_count: number;
  created_at: string;
  created_by: PrincipalResponse | null;
}

/** A session as a link viewer sees it — no `home_dir`, machine or raw metadata. */
export interface PublicSessionSummary {
  id: string;
  name: string | null;
  agent_type_name: string;
  agent_profile: PrincipalResponse | null;
  status: keyof AgentStatus;
  live_state: LiveState;
  started_at: string;
  ended_at: string | null;
  updated_at: string | null;
  worktree_name: string | null;
  /** Display keys only: agent, model, effort, permission/mode. */
  session_config: Record<string, unknown> | null;
  message_count: number;
  latest_message_at: string | null;
}

/** `MessageResponse` plus the sender's display name (never an email). */
export interface PublicMessage extends MessageResponse {
  sender_user_display_name: string | null;
}

export interface PublicMessagesPage {
  messages: PublicMessage[];
  /** More rows in the direction asked for (older for before/initial, newer for after). */
  has_more: boolean;
}

export interface PublicProjectSummary {
  id: string;
  name: string;
  key: string | null;
  color: string | null;
  icon: string | null;
}

export interface PublicShareResponse {
  id: string;
  kind: ShareKind;
  /** What this link carries; empty for a session link. The viewer draws its sidebar from it. */
  scopes: ShareScope[];
  audience: ShareAudience;
  /** Whether THIS visitor may comment (link allows it and they are signed in). */
  allow_comments: boolean;
  /** The link allows comments at all — the sign-in prompt for an anonymous visitor. */
  comments_available: boolean;
  filters: ShareProjectFilters | null;
  created_at: string;
  expires_at: string | null;
  /** Only when the link opted in (`show_owner`). */
  owner: PrincipalResponse | null;
  viewer: PrincipalResponse | null;
  /** The signed-in visitor created this link — the page may deep-link into their dashboard. */
  viewer_is_owner: boolean;
  session: PublicSessionSummary | null;
  project: PublicProjectSummary | null;
}

/** The share page's sidebar status filter (`?status=` on the public sessions
 * list): the dashboard sidebar's options, under their URL names. */
export type PublicSessionStatusFilter = 'active' | 'in_progress' | 'in_review' | 'done' | 'archived';

export interface PublicSessionsPage {
  items: PublicSessionSummary[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface PublicBoardResponse {
  project: PublicProjectSummary;
  tasks: TaskResponse[];
  labels: TaskLabelResponse[];
}

export interface AutomationRunResponse {
  id: string;
  automation_id: string;
  agent_instance_id: string | null;
  planned_at: string | null;
  fired_at: string;
  status: AutomationRunStatus;
  detail: string | null;
  created_at: string;
}

export interface CreateAutomationRequest {
  title: string;
  prompt: string;
  /** Run every fire in this session. It then supplies machine, folder and
   *  agent, so those may be left out; without it they are required. */
  agent_instance_id?: string | null;
  machine_id?: string;
  directory?: string;
  worktree?: AutomationWorktree | null;
  session_config?: Record<string, unknown>;
  agent_profile_id?: string | null;
  schedule_kind: AutomationScheduleKind;
  /** One-time: absolute ISO instant (UTC-anchored). */
  run_at?: string | null;
  /** Recurring: structured frequency. */
  frequency?: AutomationFrequency | null;
  timezone?: string;
  enabled?: boolean;
}

export interface UpdateAutomationRequest {
  title?: string;
  prompt?: string;
  machine_id?: string;
  directory?: string;
  worktree?: AutomationWorktree | null;
  session_config?: Record<string, unknown>;
  agent_profile_id?: string | null;
  /** A session id to run every fire in it, or null for a new session per run. */
  agent_instance_id?: string | null;
  schedule_kind?: AutomationScheduleKind;
  run_at?: string | null;
  frequency?: AutomationFrequency | null;
  timezone?: string;
  enabled?: boolean;
}

export interface RecordAutomationRunRequest {
  status: AutomationRunStatus;
  agent_instance_id?: string | null;
  detail?: string | null;
}

export interface BillingCheckoutSessionResponse {
  checkout_url: string;
  session_id: string;
}

export type BillingInterval = 'monthly' | 'annual';

export interface BillingPortalSessionResponse {
  url: string;
}

/**
 * A failed backend call. `message` is the backend's `detail` when it sent a
 * string one, so existing callers that only read `.message` are unaffected.
 *
 * `status` lets a caller tell "you are signed out" (401) from "it broke, retry"
 * — telling someone to try again after a 401 sends them chasing the wrong
 * problem, since retrying can never fix it. `capability` is set on a 402: the
 * action exists and the caller may ask for it, but it is metered
 * (`collab.team_seat` | `collab.grant_write` | `collab.team_own`); see
 * `seatLimitFromError`.
 */
export interface BackendApiError extends Error {
  status: number;
  capability?: string;
  requiredRole?: string;
  /** A machine-readable reason some 4xx answers carry (e.g.
   *  `project_key_taken` on a project move). */
  code?: string;
  /** With `code: 'project_key_taken'`: a key that is free at the destination. */
  suggestedKey?: string;
}

async function backendApiError(response: Response): Promise<BackendApiError> {
  let errorMessage = `Backend API error: ${response.status} ${response.statusText}`;
  let capability: string | undefined;
  let requiredRole: string | undefined;
  let code: string | undefined;
  let suggestedKey: string | undefined;
  try {
    const errorBody = await response.json();
    if (typeof errorBody?.detail === 'string' && errorBody.detail.trim()) {
      errorMessage = errorBody.detail;
    }
    if (typeof errorBody?.capability === 'string') capability = errorBody.capability;
    if (typeof errorBody?.required_role === 'string') requiredRole = errorBody.required_role;
    if (typeof errorBody?.code === 'string') code = errorBody.code;
    if (typeof errorBody?.suggested_key === 'string') suggestedKey = errorBody.suggested_key;
  } catch {
    // Ignore JSON parse failures and fall back to the generic HTTP error.
  }
  return Object.assign(new Error(errorMessage), {
    status: response.status,
    capability,
    requiredRole,
    code,
    suggestedKey,
  });
}

/**
 * The capability a 402 names, or null for any other error. The open /
 * self-hosted build never answers 402 (its capability registry is empty), so
 * a caller can branch on this unconditionally.
 */
export function seatLimitFromError(err: unknown): { capability: string; detail: string } | null {
  if (!(err instanceof Error)) return null;
  const { status, capability } = err as Partial<BackendApiError>;
  if (status !== 402) return null;
  return { capability: capability ?? '', detail: err.message };
}

class BackendAPI {
  private config: BackendConfig;

  constructor(config: BackendConfig) {
    this.config = config;
  }

  private async getHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Tag every backend request with the build version so the server can
    // compute the Wave A retirement gate (websocket-migration §4 item 6).
    // When unset the request carries no version header and the server counts
    // it as a pre-telemetry / old client, which is the correct default.
    const appVersion = process.env.NEXT_PUBLIC_APP_VERSION;
    if (appVersion) {
      headers['X-Client-Version'] = appVersion;
    }

    // Use pre-provided access token (for server-side calls)
    if (this.config.accessToken) {
      headers['Authorization'] = `Bearer ${this.config.accessToken}`;
    } 
    // Otherwise use the browser session from whichever auth provider is active
    else if (this.config.useSupabaseAuth) {
      const token = await getBrowserAccessToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    return headers;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.config.baseUrl}${endpoint}`;
    const headers = await this.getHeaders();

    const response = await fetch(url, {
      ...options,
      headers: {
        ...headers,
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw await backendApiError(response);
    }

    return response.json();
  }

  /** Like request(), for endpoints that return 204 No Content. */
  private async requestVoid(endpoint: string, options: RequestInit = {}): Promise<void> {
    const url = `${this.config.baseUrl}${endpoint}`;
    const headers = await this.getHeaders();

    const response = await fetch(url, {
      ...options,
      headers: {
        ...headers,
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw await backendApiError(response);
    }
  }

  // Authentication endpoints
  async syncUser(data: { id: string; email: string; display_name: string | null }) {
    return this.request('/api/v1/auth/sync-user', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getSession() {
    return this.request('/api/v1/auth/session');
  }

  async getCurrentUserProfile(): Promise<UserProfile> {
    return this.request<UserProfile>('/api/v1/auth/me');
  }

  async updateUserProfile(data: { display_name: string | null }): Promise<UserProfile> {
    return this.request<UserProfile>('/api/v1/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteUserAccount() {
    return this.request('/api/v1/auth/me', { method: 'DELETE' });
  }

  /** Set the caller's avatar. 'user' wins over any later OAuth re-seed. */
  async uploadMyAvatar(file: File | Blob): Promise<UserAvatar> {
    const headers = await this.getHeaders();
    // Let the browser set the multipart boundary; a fixed JSON type breaks it.
    delete headers['Content-Type'];
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${this.config.baseUrl}/api/v1/me/avatar`, {
      method: 'PUT',
      headers,
      body: form,
    });
    if (!response.ok) {
      let message = `Backend API error: ${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === 'string' && body.detail.trim()) message = body.detail;
      } catch {
        // fall back to the generic HTTP error
      }
      throw Object.assign(new Error(message), { status: response.status });
    }
    return response.json();
  }

  /** Drop the caller's avatar image → generated initials. */
  async deleteMyAvatar(): Promise<UserAvatar> {
    return this.request<UserAvatar>('/api/v1/me/avatar', { method: 'DELETE' });
  }

  /** Pick (or clear, with `null`) the emoji shown when there is no image. */
  async updateMyAvatarEmoji(emoji: string | null): Promise<UserAvatar> {
    return this.request<UserAvatar>('/api/v1/me/avatar-emoji', {
      method: 'PUT',
      body: JSON.stringify({ emoji }),
    });
  }

  // Agent profiles — the "Agents" the UI shows (collaboration P1). Not to be
  // confused with agent *types* (`/api/v1/user-agents`), which mean "claude
  // code" / "codex" and are auto-created per session.

  async listAgentProfiles(includeArchived = false): Promise<AgentProfile[]> {
    const query = includeArchived ? '?include_archived=true' : '';
    return this.request<AgentProfile[]>(`/api/v1/agents${query}`);
  }

  async createAgentProfile(input: AgentProfileInput): Promise<AgentProfile> {
    return this.request<AgentProfile>('/api/v1/agents', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  async updateAgentProfile(id: string, input: AgentProfileInput): Promise<AgentProfile> {
    return this.request<AgentProfile>(`/api/v1/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    });
  }

  /** Hard delete. Returns how many automations referenced it — they keep running
   *  off their fallback snapshot, so this is a warning, never a blocker. */
  async deleteAgentProfile(id: string): Promise<{ id: string; automations_affected: number }> {
    return this.request<{ id: string; automations_affected: number }>(
      `/api/v1/agents/${id}`,
      { method: 'DELETE' },
    );
  }

  async uploadAgentProfileAvatar(id: string, file: File | Blob): Promise<AgentProfile> {
    const headers = await this.getHeaders();
    // Let the browser set the multipart boundary; a fixed JSON type breaks it.
    delete headers['Content-Type'];
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${this.config.baseUrl}/api/v1/agents/${id}/avatar`, {
      method: 'PUT',
      headers,
      body: form,
    });
    if (!response.ok) {
      let message = `Backend API error: ${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === 'string' && body.detail.trim()) message = body.detail;
      } catch {
        // fall back to the generic HTTP error
      }
      throw Object.assign(new Error(message), { status: response.status });
    }
    return response.json();
  }

  async deleteAgentProfileAvatar(id: string): Promise<AgentProfile> {
    return this.request<AgentProfile>(`/api/v1/agents/${id}/avatar`, { method: 'DELETE' });
  }

  /** This agent's run history: the sessions it started, newest first. Stamped at
   *  spawn, so editing the agent never rewrites what already ran. */
  async listAgentProfileSessions(id: string, limit = 50): Promise<AgentInstanceResponse[]> {
    return this.request<AgentInstanceResponse[]>(
      `/api/v1/agents/${id}/sessions?limit=${limit}`,
    );
  }

  // API Key management
  async listApiKeys(): Promise<APIKeyResponse[]> {
    return this.request<APIKeyResponse[]>('/api/v1/auth/api-keys');
  }

  async createApiKey(data: { name: string; expires_in_days?: number | null }): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>('/api/v1/auth/api-keys', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async revokeApiKey(keyId: string) {
    return this.request(`/api/v1/auth/api-keys/${keyId}`, { method: 'DELETE' });
  }

  async createCliKey(): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>('/api/v1/auth/cli-key', { method: 'POST' });
  }

  // Agent Types and Instances
  async listAgentTypes(): Promise<AgentTypeOverview[]> {
    return this.request<AgentTypeOverview[]>('/api/v1/agent-types');
  }

  async listAllAgentInstancesPage(options: ListAgentInstancesOptions = {}): Promise<AgentInstancesPage> {
    const params = new URLSearchParams();
    if (options.limit) params.append('limit', options.limit.toString());
    if (options.offset) params.append('offset', options.offset.toString());
    if (options.scope) params.append('scope', options.scope);
    if (options.activeOnly) params.append('active_only', 'true');
    const endpoint = `/api/v1/agent-instances${params.toString() ? `?${params.toString()}` : ''}`;
    const response = await this.request<AgentInstanceResponse[] | PaginatedAgentInstanceResponse>(endpoint);

    if (Array.isArray(response)) {
      return {
        items: response,
        total: response.length,
        limit: options.limit ?? response.length,
        offset: options.offset ?? 0,
        hasMore: false,
        isPaginated: false,
      };
    }

    return {
      items: response.items,
      total: response.total,
      limit: response.limit,
      offset: response.offset ?? options.offset ?? 0,
      hasMore: response.has_more,
      isPaginated: true,
    };
  }

  async listAllAgentInstances(limitOrOptions?: number | ListAgentInstancesOptions): Promise<AgentInstanceResponse[]> {
    const options = typeof limitOrOptions === 'number'
      ? { limit: limitOrOptions }
      : (limitOrOptions ?? {});

    const page = await this.listAllAgentInstancesPage(options);
    return page.items;
  }

  async getAgentSummary() {
    return this.request('/api/v1/agent-summary');
  }

  /**
   * Server-aggregated profile activity (daily user-message counts + totals).
   * `since` (a `YYYY-MM-DD` day) asks for only that day onward so the client
   * can sync incrementally. Throws if the endpoint isn't deployed yet — the
   * caller falls back to deriving stats from the session list.
   */
  async getActivity(since?: string): Promise<ActivityResponse> {
    const params = new URLSearchParams();
    if (since) params.append('since', since);
    const qs = params.toString();
    return this.request<ActivityResponse>(`/api/v1/activity${qs ? `?${qs}` : ''}`);
  }

  async getTypeInstances(typeId: string): Promise<AgentInstanceResponse[]> {
    return this.request<AgentInstanceResponse[]>(`/api/v1/agent-types/${typeId}/instances`);
  }

  async getInstanceDetail(
    instanceId: string,
    messageLimit?: number,
    beforeMessageId?: string
  ): Promise<AgentInstanceDetail> {
    const params = new URLSearchParams();
    if (messageLimit) params.append('message_limit', messageLimit.toString());
    if (beforeMessageId) params.append('before_message_id', beforeMessageId);
    const endpoint = `/api/v1/agent-instances/${instanceId}${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<AgentInstanceDetail>(endpoint);
  }

  async deleteAgentInstance(instanceId: string) {
    return this.request(`/api/v1/agent-instances/${instanceId}`, { method: 'DELETE' });
  }

  async updateAgentInstance(instanceId: string, data: any): Promise<AgentInstanceResponse> {
    return this.request<AgentInstanceResponse>(`/api/v1/agent-instances/${instanceId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // Messages
  async getInstanceMessagesPaginated(
    instanceId: string,
    limit?: number,
    beforeMessageId?: string,
    afterMessageId?: string,
  ) {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (beforeMessageId) params.append('before_message_id', beforeMessageId);
    // The poll watermark: messages newer than this one, oldest first.
    if (afterMessageId) params.append('after_message_id', afterMessageId);
    const endpoint = `/api/v1/agent-instances/${instanceId}/messages${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request(endpoint);
  }

  async createUserMessage(instanceId: string, data: UserMessageRequest): Promise<MessageResponse> {
    return this.request<MessageResponse>(`/api/v1/agent-instances/${instanceId}/messages`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * Cancel a still-queued user message (one sent while the agent was busy —
   * `message_metadata.queue.status === 'queued'`). Returns `cancelled: false`
   * if the message was already consumed/cancelled by the time this landed.
   */
  async cancelQueuedMessage(instanceId: string, messageId: string): Promise<{ cancelled: boolean }> {
    return this.request<{ cancelled: boolean }>(
      `/api/v1/agent-instances/${instanceId}/messages/${messageId}/cancel`,
      { method: 'POST' },
    );
  }

  /**
   * Ask for a still-queued user message to be steered into the agent's
   * running turn instead of waiting for it to end. Only flips the row to
   * `queue.status = 'steer'`; the daemon delivers it and settles the row to
   * `consumed` (with `steered: true`) or back to `queued`. Resolves to
   * `{ steered: false }` if the message was no longer plainly queued.
   */
  async steerQueuedMessage(instanceId: string, messageId: string): Promise<{ steered: boolean }> {
    return this.request<{ steered: boolean }>(
      `/api/v1/agent-instances/${instanceId}/messages/${messageId}/steer`,
      { method: 'POST' },
    );
  }

  // Stream messages (for real-time updates). Legacy SSE — superseded by the
  // WebSocket client (ws-client.ts); kept until the Wave A SSE retirement.
  async getMessageStreamUrl(instanceId: string): Promise<string> {
    const params = new URLSearchParams();

    if (this.config.useSupabaseAuth) {
      const token = await getBrowserAccessToken();
      if (token) {
        params.append('token', token);
      }
    }

    return `${this.config.baseUrl}/api/v1/agent-instances/${instanceId}/messages/stream${params.toString() ? `?${params.toString()}` : ''}`;
  }

  async getInstanceStreamUrl(): Promise<string> {
    const params = new URLSearchParams();

    if (this.config.useSupabaseAuth) {
      const token = await getBrowserAccessToken();
      if (token) {
        params.append('token', token);
      }
    }

    return `${this.config.baseUrl}/api/v1/agent-instances/stream${params.toString() ? `?${params.toString()}` : ''}`;
  }

  async updateAgentStatus(instanceId: string, statusUpdate: any): Promise<AgentInstanceResponse> {
    return this.request<AgentInstanceResponse>(`/api/v1/agent-instances/${instanceId}/status`, {
      method: 'PUT',
      body: JSON.stringify(statusUpdate),
    });
  }

  // Push Notifications
  async registerPushToken(data: { token: string; platform: string }) {
    return this.request('/api/v1/push/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deactivatePushToken(token: string) {
    return this.request(`/api/v1/push/deactivate/${token}`, { method: 'DELETE' });
  }

  async getMyPushTokens() {
    return this.request('/api/v1/push/tokens');
  }

  // User Settings
  async getNotificationSettings() {
    return this.request('/api/v1/user/notification-settings');
  }

  async updateNotificationSettings(data: any) {
    return this.request('/api/v1/user/notification-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async testNotification(notificationType: string = 'all') {
    const params = new URLSearchParams({ notification_type: notificationType });
    return this.request(`/api/v1/user/test-notification?${params.toString()}`, { method: 'POST' });
  }

  // Machines & remote sessions
  async listMachines(): Promise<MachineSummary[]> {
    const response = await this.request<MachineListResponse>('/api/v1/machines');
    return response.machines || [];
  }

  /**
   * Forget a machine. Hard delete server-side: its sessions survive with
   * `machine_id` cleared, and the machine reappears only if its daemon
   * re-registers.
   */
  async deleteMachine(machineId: string): Promise<void> {
    return this.requestVoid(`/api/v1/machines/${machineId}`, { method: 'DELETE' });
  }

  /**
   * Fetch the per-agent catalog (plan §5.2). Returns the full payload; the
   * caller is responsible for falling back to AGENT_CATALOG_FALLBACK on
   * failure. ETag/304 short-circuiting is left to a follow-up — the catalog
   * is small (~3 KB) and only loaded once per page open.
   */
  async getAgentCatalog(): Promise<import('./agent-catalog').AgentCatalog> {
    return this.request<import('./agent-catalog').AgentCatalog>('/api/v1/agent-catalog');
  }

  /**
   * A machine's cached real per-agent model lists (`{agentId: [{id,label}]}`),
   * populated once an ACP agent has run there. Lets the new-session picker show
   * real models before a session starts; empty until something is cached.
   */
  /**
   * The machine's cached per-agent model lists (and, for ACP agents whose
   * source reported them, session modes), keyed by catalog agent id. Filled
   * by the wrappers' session/new report and by daemon provider probes.
   */
  async getMachineAgentModels(machineId: string): Promise<MachineAgentModelsCache> {
    const resp = await this.request<{
      agent_models?: Record<string, { id: string; label: string }[]>;
      agent_modes?: Record<string, { id: string; label: string }[]>;
    }>(`/api/v1/machines/${machineId}/agent-models`);
    return { models: resp.agent_models ?? {}, modes: resp.agent_modes ?? {} };
  }

  async spawnRemoteSession(
    machineId: string,
    request: {
      directory: string;
      agent?: RemoteAgentType;
      prompt?: string;
      metadata?: Record<string, unknown>;
      /** Records provenance on the session AND is what the server reads the
       *  profile's instructions from — they are never sent in `metadata`. */
      agent_profile_id?: string | null;
    }
  ): Promise<SpawnRemoteSessionResponse> {
    const { metadata, ...rest } = request;
    return this.request<SpawnRemoteSessionResponse>(
      `/api/v1/machines/${machineId}/spawn-requests`,
      {
        method: 'POST',
        body: JSON.stringify({
          agent: 'claude',
          ...rest,
          metadata: { enable_thinking: true, ...metadata },
        }),
      },
    );
  }

  async getSpawnRequestStatus(
    machineId: string,
    requestId: string
  ): Promise<SpawnRequestStatus> {
    return this.request<SpawnRequestStatus>(
      `/api/v1/machines/${machineId}/spawn-requests/${requestId}`
    );
  }

  // Mobile Billing
  async getMobileSubscriptionStatus() {
    return this.request('/api/v1/billing/mobile/status');
  }

  // Web Billing
  async getBillingSubscription(): Promise<BillingSubscription> {
    return this.request<BillingSubscription>('/api/v1/billing/subscription');
  }

  async getBillingUsage(): Promise<BillingUsage> {
    return this.request<BillingUsage>('/api/v1/billing/usage');
  }

  async createBillingCheckoutSession(data: {
    plan_type: 'pro';
    billing_interval?: BillingInterval;
    success_url: string;
    cancel_url: string;
    promo_code?: string;
  }): Promise<BillingCheckoutSessionResponse> {
    return this.request<BillingCheckoutSessionResponse>('/api/v1/billing/checkout', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async createBillingPortalSession(data: {
    return_url: string;
  }): Promise<BillingPortalSessionResponse> {
    return this.request<BillingPortalSessionResponse>('/api/v1/billing/portal', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async cancelBillingSubscription() {
    return this.request('/api/v1/billing/cancel', {
      method: 'POST',
    });
  }

  /** The caller's seats as a payer. Hosted build only — 404 elsewhere. */
  async getBillingSeats(): Promise<BillingSeats> {
    return this.request<BillingSeats>('/api/v1/billing/seats');
  }

  /** Start per-seat billing (returns a Checkout URL) or change the seats on
   *  the Stripe subscription already in place (prorated, `status: updated`). */
  async changeBillingSeats(data: {
    quantity: number;
    billing_interval: BillingInterval;
    success_url: string;
    cancel_url: string;
  }): Promise<ChangeBillingSeatsResponse> {
    return this.request<ChangeBillingSeatsResponse>('/api/v1/billing/seats', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Support
  async reportIssue(data: { message: string }): Promise<{ status: string }> {
    return this.request<{ status: string }>('/api/v1/support/report-issue', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ConvertKit
  async subscribeToConvertKit(data: { email: string; name?: string }) {
    return this.request('/api/v1/convertkit/subscribe', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Slash Commands
  async getSlashCommands(agentType?: string): Promise<SlashCommandsResponse[]> {
    const params = new URLSearchParams();
    if (agentType) params.append('agent_type', agentType);
    const endpoint = `/api/v1/commands${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<SlashCommandsResponse[]>(endpoint);
  }

  async getSlashCommandsByAgentType(agentType: string): Promise<SlashCommandsResponse> {
    return this.request<SlashCommandsResponse>(`/api/v1/commands/${agentType}`);
  }

  async getFileMentions(projectPath?: string): Promise<FileMentionsResponse> {
    const params = new URLSearchParams();
    if (projectPath) params.append('project_path', projectPath);
    const endpoint = `/api/v1/files${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<FileMentionsResponse>(endpoint);
  }

  // Projects & Tasks (human task tracker)
  /**
   * The caller's projects, most recent activity first. `machineId` narrows to
   * projects linked to a folder on that machine — what the new-session picker
   * lists.
   */
  async listProjects(
    includeArchived = false,
    options: { machineId?: string } = {},
  ): Promise<ProjectResponse[]> {
    const params = new URLSearchParams();
    if (includeArchived) params.append('include_archived', 'true');
    if (options.machineId) params.append('machine_id', options.machineId);
    const endpoint = `/api/v1/projects${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<ProjectResponse[]>(endpoint);
  }

  /**
   * Replace the caller's manual project order (sidebar drag-and-drop), first
   * to last. Per viewer, so ranking a shared project never moves it for anyone
   * else. Ids the caller cannot see are dropped; the echo is what got stored.
   */
  async setProjectOrder(projectIds: string[]): Promise<ProjectOrderResponse> {
    return this.request<ProjectOrderResponse>('/api/v1/projects/order', {
      method: 'PUT',
      body: JSON.stringify({ project_ids: projectIds }),
    });
  }

  /** What deleting the project would file under No project — for the confirm dialog. */
  async getProjectSummary(projectId: string): Promise<ProjectSummaryResponse> {
    return this.request<ProjectSummaryResponse>(`/api/v1/projects/${projectId}/summary`);
  }

  async createProject(data: CreateProjectRequest): Promise<ProjectResponse> {
    return this.request<ProjectResponse>('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProject(projectId: string, data: UpdateProjectRequest): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(`/api/v1/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  /**
   * Move a project into a team (`team_id`), or out of one into the caller's
   * personal space (`team_id: null`). Owner only. A 409 with
   * `code === 'project_key_taken'` means its task key is already used there;
   * resend with `key` (the error's `suggestedKey` is a free one).
   */
  async transferProject(
    projectId: string,
    data: { team_id: string | null; key?: string },
  ): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(`/api/v1/projects/${projectId}/transfer`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /** Upload a project's image icon (multipart). Sets icon_source='user'. */
  async uploadProjectIcon(projectId: string, file: File | Blob): Promise<ProjectResponse> {
    const headers = await this.getHeaders();
    // Let the browser set the multipart boundary; a fixed JSON type breaks it.
    delete headers['Content-Type'];
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(
      `${this.config.baseUrl}/api/v1/projects/${projectId}/icon`,
      { method: 'PUT', headers, body: form },
    );
    if (!response.ok) {
      let message = `Backend API error: ${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (typeof body?.detail === 'string' && body.detail.trim()) message = body.detail;
      } catch {
        // fall back to the generic HTTP error
      }
      throw Object.assign(new Error(message), { status: response.status });
    }
    return response.json();
  }

  /** Reset a project's icon to the generated default: clears the image AND emoji
   *  and pins it so the git seed won't re-add an image. */
  async deleteProjectIcon(projectId: string): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(`/api/v1/projects/${projectId}/icon`, {
      method: 'DELETE',
    });
  }

  /** Link (or relink) a project to a path on one machine. Upserts per machine. */
  async setProjectDirectory(
    projectId: string,
    data: { machine_id: string; local_path: string },
  ): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(`/api/v1/projects/${projectId}/directories`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteProjectDirectory(projectId: string, machineId: string): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(
      `/api/v1/projects/${projectId}/directories/${machineId}`,
      { method: 'DELETE' },
    );
  }

  async deleteProject(projectId: string): Promise<void> {
    await this.requestVoid(`/api/v1/projects/${projectId}`, { method: 'DELETE' });
  }

  async listTasks(
    options: { projectId?: string; status?: TaskStatus; createdInInstanceId?: string } = {},
  ): Promise<TaskResponse[]> {
    const params = new URLSearchParams();
    if (options.projectId) params.append('project_id', options.projectId);
    if (options.status) params.append('status', options.status);
    if (options.createdInInstanceId) params.append('created_in_instance_id', options.createdInInstanceId);
    const endpoint = `/api/v1/tasks${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<TaskResponse[]>(endpoint);
  }

  async createTask(data: CreateTaskRequest): Promise<TaskResponse> {
    return this.request<TaskResponse>('/api/v1/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getTask(taskId: string): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/api/v1/tasks/${taskId}`);
  }

  /** Agent sessions started from this task, most recent first. */
  async listTaskSessions(taskId: string): Promise<AgentInstanceResponse[]> {
    return this.request<AgentInstanceResponse[]>(`/api/v1/tasks/${taskId}/sessions`);
  }

  /** Comments + activity in one round trip (no WS channel for tasks). */
  async getTaskTimeline(taskId: string): Promise<TaskTimelineResponse> {
    return this.request<TaskTimelineResponse>(`/api/v1/tasks/${taskId}/timeline`);
  }

  // Every mutation below answers with the whole timeline: the caller was going
  // to revalidate anyway, and it closes the window where an optimistic append
  // and a background poll disagree about ordering.
  async createTaskComment(
    taskId: string,
    body: string,
    /** Reply into this comment's thread. Replying to a reply lands in the same thread. */
    parentCommentId?: string,
  ): Promise<TaskTimelineResponse> {
    return this.request<TaskTimelineResponse>(`/api/v1/tasks/${taskId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body, parent_comment_id: parentCommentId ?? null }),
    });
  }

  async updateTaskComment(
    taskId: string,
    commentId: string,
    body: string,
  ): Promise<TaskTimelineResponse> {
    return this.request<TaskTimelineResponse>(
      `/api/v1/tasks/${taskId}/comments/${commentId}`,
      { method: 'PATCH', body: JSON.stringify({ body }) },
    );
  }

  async deleteTaskComment(taskId: string, commentId: string): Promise<TaskTimelineResponse> {
    return this.request<TaskTimelineResponse>(
      `/api/v1/tasks/${taskId}/comments/${commentId}`,
      { method: 'DELETE' },
    );
  }

  async toggleTaskReaction(
    taskId: string,
    target: { targetType: 'task' | 'comment'; targetId: string; emoji: string },
  ): Promise<TaskTimelineResponse> {
    return this.request<TaskTimelineResponse>(`/api/v1/tasks/${taskId}/reactions`, {
      method: 'PUT',
      body: JSON.stringify({
        target_type: target.targetType,
        target_id: target.targetId,
        emoji: target.emoji,
      }),
    });
  }

  async updateTask(taskId: string, data: UpdateTaskRequest): Promise<TaskResponse> {
    return this.request<TaskResponse>(`/api/v1/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteTask(taskId: string): Promise<void> {
    await this.requestVoid(`/api/v1/tasks/${taskId}`, { method: 'DELETE' });
  }

  async listTaskLabels(): Promise<TaskLabelResponse[]> {
    return this.request<TaskLabelResponse[]>('/api/v1/task-labels');
  }

  async createTaskLabel(data: CreateTaskLabelRequest): Promise<TaskLabelResponse> {
    return this.request<TaskLabelResponse>('/api/v1/task-labels', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTaskLabel(
    labelId: string,
    data: Partial<CreateTaskLabelRequest>,
  ): Promise<TaskLabelResponse> {
    return this.request<TaskLabelResponse>(`/api/v1/task-labels/${labelId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteTaskLabel(labelId: string): Promise<void> {
    await this.requestVoid(`/api/v1/task-labels/${labelId}`, { method: 'DELETE' });
  }

  // --- Automations --------------------------------------------------------

  /**
   * Default: your own automations, in every project. `scope: 'all'` adds
   * collaborators' automations in projects shared with you; `projectId` lists
   * one project's. Collaborators' rows are read-only, with `owner` set: edit,
   * run and delete stay with their author. Every list comes back in your own
   * order (`setAutomationOrder`): unranked ones first, newest first.
   */
  async listAutomations(
    options: { scope?: 'me' | 'all'; projectId?: string | null } = {},
  ): Promise<AutomationResponse[]> {
    const params = new URLSearchParams();
    if (options.projectId) params.set('project_id', options.projectId);
    else if (options.scope === 'all') params.set('scope', 'all');
    const query = params.toString();
    return this.request<AutomationResponse[]>(`/api/v1/automations${query ? `?${query}` : ''}`);
  }

  /**
   * Replace the caller's manual automation order (drag-and-drop), first to
   * last, over everything they can see. Per viewer, so ranking a
   * collaborator's automation never moves it for anyone else. Ids the caller
   * cannot see are dropped; the echo is what got stored.
   */
  async setAutomationOrder(automationIds: string[]): Promise<AutomationOrderResponse> {
    return this.request<AutomationOrderResponse>('/api/v1/automations/order', {
      method: 'PUT',
      body: JSON.stringify({ automation_ids: automationIds }),
    });
  }

  async getAutomation(id: string): Promise<AutomationResponse> {
    return this.request<AutomationResponse>(`/api/v1/automations/${id}`);
  }

  async createAutomation(
    data: CreateAutomationRequest,
  ): Promise<AutomationResponse> {
    return this.request<AutomationResponse>('/api/v1/automations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateAutomation(
    id: string,
    data: UpdateAutomationRequest,
  ): Promise<AutomationResponse> {
    return this.request<AutomationResponse>(`/api/v1/automations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteAutomation(id: string): Promise<void> {
    await this.requestVoid(`/api/v1/automations/${id}`, { method: 'DELETE' });
  }

  async listAutomationRuns(id: string): Promise<AutomationRunResponse[]> {
    return this.request<AutomationRunResponse[]>(
      `/api/v1/automations/${id}/runs`,
    );
  }

  /** Record the outcome of a client-side "run now" dispatch. */
  async recordAutomationRun(
    id: string,
    data: RecordAutomationRunRequest,
  ): Promise<AutomationRunResponse> {
    return this.request<AutomationRunResponse>(
      `/api/v1/automations/${id}/run`,
      { method: 'POST', body: JSON.stringify(data) },
    );
  }

  // --- Share links (collaboration §3.4, P4) --------------------------------

  async createShareLink(data: CreateShareLinkRequest): Promise<ShareLinkResponse> {
    return this.request<ShareLinkResponse>('/api/v1/shares', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /** Live links on one target — pass exactly one of the two ids. */
  async listShareLinks(
    target: { agent_instance_id: string } | { project_id: string },
  ): Promise<ShareLinkResponse[]> {
    const params = new URLSearchParams(target);
    return this.request<ShareLinkResponse[]>(`/api/v1/shares?${params.toString()}`);
  }

  /** Edit an existing link's settings, keeping its token. */
  async updateShareLink(
    linkId: string,
    data: UpdateShareLinkRequest,
  ): Promise<ShareLinkResponse> {
    return this.request<ShareLinkResponse>(`/api/v1/shares/${linkId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async revokeShareLink(linkId: string): Promise<void> {
    return this.requestVoid(`/api/v1/shares/${linkId}`, { method: 'DELETE' });
  }

  // --- People: project grants and per-session shares (P5) -------------------

  /** Owner row + every grant. Admin on tasks and sessions; 403 otherwise. */
  async listProjectPeople(projectId: string): Promise<ProjectPerson[]> {
    return this.request<ProjectPerson[]>(`/api/v1/projects/${projectId}/grants`);
  }

  async createProjectGrant(
    projectId: string,
    data: CreateProjectGrantRequest,
  ): Promise<ProjectGrantCreated> {
    return this.request<ProjectGrantCreated>(`/api/v1/projects/${projectId}/grants`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateProjectGrant(
    projectId: string,
    grantId: string,
    data: { role?: GrantRole; scopes?: GrantScope[] },
  ): Promise<ProjectPerson> {
    return this.request<ProjectPerson>(`/api/v1/projects/${projectId}/grants/${grantId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteProjectGrant(projectId: string, grantId: string): Promise<void> {
    return this.requestVoid(`/api/v1/projects/${projectId}/grants/${grantId}`, {
      method: 'DELETE',
    });
  }

  /** Drop your own grant on a project shared with you. 409 when the access
   *  comes from a team, or you own it. */
  async leaveProject(projectId: string): Promise<void> {
    return this.requestVoid(`/api/v1/projects/${projectId}/leave`, { method: 'POST' });
  }

  /**
   * Follow a project shared with you into your own list (or unfollow it). Your
   * view only — the project and your access are unchanged.
   */
  async setProjectFollowed(projectId: string, followed: boolean): Promise<ProjectResponse> {
    return this.request<ProjectResponse>(`/api/v1/projects/${projectId}/follow`, {
      method: followed ? 'PUT' : 'DELETE',
    });
  }

  /** The owner row, per-person shares, then team shares of one session. */
  async listSessionShares(instanceId: string): Promise<SessionShare[]> {
    return this.request<SessionShare[]>(`/api/v1/agent-instances/${instanceId}/access`);
  }

  async createSessionShare(
    instanceId: string,
    data: CreateSessionShareRequest,
  ): Promise<SessionShare> {
    return this.request<SessionShare>(`/api/v1/agent-instances/${instanceId}/access`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSessionShare(
    instanceId: string,
    shareId: string,
    access: 'READ' | 'WRITE',
  ): Promise<SessionShare> {
    return this.request<SessionShare>(
      `/api/v1/agent-instances/${instanceId}/access/${shareId}`,
      { method: 'PATCH', body: JSON.stringify({ access }) },
    );
  }

  async deleteSessionShare(instanceId: string, shareId: string): Promise<void> {
    await this.request<{ status: string }>(
      `/api/v1/agent-instances/${instanceId}/access/${shareId}`,
      { method: 'DELETE' },
    );
  }

  // --- Teams (collaboration §3.2) -------------------------------------------

  async listTeams(): Promise<TeamSummary[]> {
    return this.request<TeamSummary[]>('/api/v1/teams');
  }

  async createTeam(name: string): Promise<TeamDetail> {
    return this.request<TeamDetail>('/api/v1/teams', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async getTeam(teamId: string): Promise<TeamDetail> {
    return this.request<TeamDetail>(`/api/v1/teams/${teamId}`);
  }

  async renameTeam(teamId: string, name: string): Promise<TeamSummary> {
    return this.request<TeamSummary>(`/api/v1/teams/${teamId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
  }

  async deleteTeam(teamId: string): Promise<void> {
    return this.requestVoid(`/api/v1/teams/${teamId}`, { method: 'DELETE' });
  }

  /** Set the team's picture (owner/admin; multipart). */
  async uploadTeamAvatar(teamId: string, file: File | Blob): Promise<TeamSummary> {
    const headers = await this.getHeaders();
    // Let the browser set the multipart boundary; a fixed JSON type breaks it.
    delete headers['Content-Type'];
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${this.config.baseUrl}/api/v1/teams/${teamId}/avatar`, {
      method: 'PUT',
      headers,
      body: form,
    });
    if (!response.ok) throw await backendApiError(response);
    return response.json();
  }

  async deleteTeamAvatar(teamId: string): Promise<TeamSummary> {
    return this.request<TeamSummary>(`/api/v1/teams/${teamId}/avatar`, { method: 'DELETE' });
  }

  /** Hand the team to another active member (owner only); you stay on as
   *  an admin. The new owner pays for its seats, so this can 402. */
  async transferTeamOwnership(teamId: string, memberId: string): Promise<TeamDetail> {
    return this.request<TeamDetail>(`/api/v1/teams/${teamId}/transfer`, {
      method: 'POST',
      body: JSON.stringify({ member_id: memberId }),
    });
  }

  /** Email invites waiting on the caller. Also attaches any project grants
   *  and session shares sent to the caller's address before they signed up. */
  async listTeamInvitations(): Promise<TeamInvitation[]> {
    return this.request<TeamInvitation[]>('/api/v1/teams/invitations');
  }

  async acceptTeamInvitation(teamId: string): Promise<TeamSummary> {
    return this.request<TeamSummary>(`/api/v1/teams/${teamId}/members/accept`, {
      method: 'POST',
    });
  }

  async declineTeamInvitation(teamId: string): Promise<void> {
    return this.requestVoid(`/api/v1/teams/${teamId}/members/decline`, { method: 'POST' });
  }

  async inviteTeamMember(
    teamId: string,
    email: string,
    role: Exclude<TeamRole, 'owner'>,
  ): Promise<TeamMemberInvite> {
    return this.request<TeamMemberInvite>(`/api/v1/teams/${teamId}/members`, {
      method: 'POST',
      body: JSON.stringify({ email, role }),
    });
  }

  async updateTeamMemberRole(
    teamId: string,
    memberId: string,
    role: Exclude<TeamRole, 'owner'>,
  ): Promise<TeamMember> {
    return this.request<TeamMember>(`/api/v1/teams/${teamId}/members/${memberId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    });
  }

  /** Remove a member, or yourself (leaving the team). */
  async removeTeamMember(teamId: string, memberId: string): Promise<void> {
    return this.requestVoid(`/api/v1/teams/${teamId}/members/${memberId}`, {
      method: 'DELETE',
    });
  }

  async listTeamInviteLinks(teamId: string): Promise<TeamInviteLink[]> {
    return this.request<TeamInviteLink[]>(`/api/v1/teams/${teamId}/invites`);
  }

  async createTeamInviteLink(
    teamId: string,
    data: {
      role: Exclude<TeamRole, 'owner'>;
      expires_in_days: number | null;
      max_uses: number | null;
    },
  ): Promise<TeamInviteLink> {
    return this.request<TeamInviteLink>(`/api/v1/teams/${teamId}/invites`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async revokeTeamInviteLink(teamId: string, inviteId: string): Promise<void> {
    return this.requestVoid(`/api/v1/teams/${teamId}/invites/${inviteId}`, {
      method: 'DELETE',
    });
  }

  /** What the join page shows. Uniform 404 for unknown / revoked / expired /
   *  used-up tokens — callers must not try to tell them apart. */
  async previewTeamInviteLink(token: string): Promise<TeamInvitePreview> {
    return this.request<TeamInvitePreview>(`/api/v1/team-invites/${encodeURIComponent(token)}`);
  }

  async acceptTeamInviteLink(token: string): Promise<TeamSummary> {
    return this.request<TeamSummary>(
      `/api/v1/team-invites/${encodeURIComponent(token)}/accept`,
      { method: 'POST' },
    );
  }

  // --- Workspace search (cmd+K palette) -----------------------------------

  async search(
    query: string,
    options: { limit?: number; signal?: AbortSignal } = {},
  ): Promise<WorkspaceSearchResponse> {
    const params = new URLSearchParams({ q: query });
    if (options.limit) params.set('limit', String(options.limit));
    return this.request<WorkspaceSearchResponse>(
      `/api/v1/search?${params.toString()}`,
      { signal: options.signal },
    );
  }

  // --- `#` composer references ----------------------------------------------

  /** Candidates for the composer's `#` panel. An empty `q` is legal and means
   * "what's live and recent", so `#` on its own opens a useful list. */
  async listReferences(
    query: string,
    options: {
      limit?: number;
      /** The session doing the referencing; dropped from the results. */
      excludeSessionId?: string | null;
      signal?: AbortSignal;
    } = {},
  ): Promise<ReferenceCandidatesResponse> {
    const params = new URLSearchParams({ q: query });
    if (options.limit) params.set('limit', String(options.limit));
    if (options.excludeSessionId) {
      params.set('exclude_session_id', options.excludeSessionId);
    }
    return this.request<ReferenceCandidatesResponse>(
      `/api/v1/references?${params.toString()}`,
      { signal: options.signal },
    );
  }

  /** One pick, expanded into the text block the agent reads. */
  async getReference(kind: ReferenceKind, id: string): Promise<ReferenceDetail> {
    return this.request<ReferenceDetail>(`/api/v1/references/${kind}/${id}`);
  }
}

// Singleton instance with default configuration
let backendAPI: BackendAPI | null = null;

export function getBackendAPI(useSupabaseAuth = true, accessToken?: string): BackendAPI {
  // Desktop local (logged-out) mode: talk to the daemon's local server with
  // the preload-injected nonce — there is no Supabase session to read, and
  // attempting to would just log errors. `getDesktopConfig()` is null on
  // plain web and during SSR, so every other caller is unaffected.
  const desktop = getDesktopConfig();
  if (desktop && desktop.mode === 'local') {
    return new BackendAPI({
      baseUrl: desktop.apiBase,
      accessToken: desktop.token,
    });
  }

  // Always create a new instance to ensure config changes are applied
  backendAPI = new BackendAPI({
    baseUrl: getCloudApiBase(),
    useSupabaseAuth,
    accessToken,
  });

  return backendAPI;
}

export default BackendAPI;
