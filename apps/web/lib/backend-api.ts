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
  home_dir?: string | null;
  pinned_at?: string | null;
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
  /**
   * Server-derived liveness at fetch time. Prefer `useSessionLiveness`, which
   * recomputes this on a timer — see lib/session-liveness.ts for why a
   * transported value goes stale.
   */
  live_state?: LiveState;
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
  instance_metadata?: SessionInstanceMetadata | null;
  machine_id?: string | null;
  last_heartbeat_at?: string | null;
  /** See AgentInstanceResponse.worktree_name. */
  worktree_name?: string | null;
  /** See AgentInstanceResponse.live_state — prefer useSessionLiveness. */
  live_state?: LiveState;
}

export interface UserAgentResponse {
  id: string;
  name: string;
  webhook_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  instance_count: number;
  active_instance_count: number;
  waiting_instance_count: number;
  completed_instance_count: number;
  error_instance_count: number;
  has_webhook: boolean;
}

export interface CreateUserAgentRequest {
  name: string;
  webhook_url?: string | null;
  webhook_api_key?: string | null;
  is_active?: boolean;
}

export interface CreateAgentInstanceRequest {
  prompt: string;
  name?: string | null;
  worktree_name?: string | null;
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

export interface BillingSubscription {
  id: string;
  plan_type: string;
  agent_limit: number;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  provider: 'stripe' | 'apple' | 'google' | null;
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
  git_remote_url: string | null;
  color: string | null;
  icon: string | null;
  /**
   * Served URL for an uploaded/seeded image icon, or null. Rendered via the
   * same-origin proxy (see lib/project-icons.ts `projectIconSrc`) since an
   * <img> can't carry the backend bearer. Fallback chain when null: emoji
   * `icon` → generated initial-square.
   */
  icon_image_uri: string | null;
  /** Who set the image: 'user' (upload, wins) | 'git' (seeded) | null. */
  icon_source: string | null;
  /** The per-user "No project" bucket; not archivable or deletable. */
  is_inbox: boolean;
  is_archived: boolean;
  archived_at: string | null;
  directories: ProjectDirectory[];
  created_at: string;
  updated_at: string;
}

export interface TaskLabelResponse {
  id: string;
  name: string;
  /** Always #rrggbb — the backend pins the format (chips inline-style it). */
  color: string;
}

export interface TaskResponse {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  position: number;
  parent_task_id: string | null;
  labels: TaskLabelResponse[];
  start_date: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
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
}

export interface CreateTaskRequest {
  title: string;
  description?: string | null;
  /** Omitted → the user's Inbox ("No project"). */
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
}

export interface CreateTaskLabelRequest {
  name: string;
  color: string;
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
  machine_id: string;
  directory: string;
  worktree: AutomationWorktree | null;
  /** SessionConfig shape (agent / model / effort / permission-mode). */
  session_config: Record<string, unknown>;
  schedule_kind: AutomationScheduleKind;
  frequency: AutomationFrequency | null;
  timezone: string;
  next_run_at: string | null;
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: AutomationRunStatus | null;
  created_at: string;
  updated_at: string;
}

// --- Workspace search (cmd+K palette) ------------------------------------

export interface SearchSessionResult {
  id: string;
  name: string | null;
  agent_type_name: string | null;
  status: keyof AgentStatus;
  project: string | null;
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
  project_id: string;
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
  machine_id: string;
  directory: string;
  worktree?: AutomationWorktree | null;
  session_config: Record<string, unknown>;
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
      let errorMessage = `Backend API error: ${response.status} ${response.statusText}`;

      try {
        const errorBody = await response.json();
        if (typeof errorBody?.detail === 'string' && errorBody.detail.trim()) {
          errorMessage = errorBody.detail;
        }
      } catch {
        // Ignore JSON parse failures and fall back to the generic HTTP error.
      }

      // Carry the HTTP status so callers can tell "you are signed out" (401)
      // from "it broke, retry" — telling someone to try again after a 401 sends
      // them chasing the wrong problem, since retrying can never fix it.
      // `message` is unchanged, so existing callers are unaffected.
      throw Object.assign(new Error(errorMessage), { status: response.status });
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
      let errorMessage = `Backend API error: ${response.status} ${response.statusText}`;
      try {
        const errorBody = await response.json();
        if (typeof errorBody?.detail === 'string' && errorBody.detail.trim()) {
          errorMessage = errorBody.detail;
        }
      } catch {
        // Ignore JSON parse failures and fall back to the generic HTTP error.
      }
      throw Object.assign(new Error(errorMessage), { status: response.status });
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
    beforeMessageId?: string
  ) {
    const params = new URLSearchParams();
    if (limit) params.append('limit', limit.toString());
    if (beforeMessageId) params.append('before_message_id', beforeMessageId);
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

  // User Agents
  async listUserAgents(): Promise<UserAgentResponse[]> {
    return this.request<UserAgentResponse[]>('/api/v1/user-agents');
  }

  async createUserAgent(data: CreateUserAgentRequest): Promise<UserAgentResponse> {
    return this.request<UserAgentResponse>('/api/v1/user-agents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateUserAgent(agentId: string, data: CreateUserAgentRequest): Promise<UserAgentResponse> {
    return this.request<UserAgentResponse>(`/api/v1/user-agents/${agentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteUserAgent(agentId: string) {
    return this.request(`/api/v1/user-agents/${agentId}`, { method: 'DELETE' });
  }

  async getUserAgentInstances(agentId: string): Promise<AgentInstanceResponse[]> {
    return this.request<AgentInstanceResponse[]>(`/api/v1/user-agents/${agentId}/instances`);
  }

  async createAgentInstance(agentId: string, data: CreateAgentInstanceRequest) {
    return this.request(`/api/v1/user-agents/${agentId}/instances`, {
      method: 'POST',
      body: JSON.stringify(data),
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
  async getMachineAgentModels(
    machineId: string,
  ): Promise<Record<string, { id: string; label: string }[]>> {
    const resp = await this.request<{
      agent_models?: Record<string, { id: string; label: string }[]>;
    }>(`/api/v1/machines/${machineId}/agent-models`);
    return resp.agent_models ?? {};
  }

  async spawnRemoteSession(
    machineId: string,
    request: { directory: string; agent?: RemoteAgentType; prompt?: string; metadata?: Record<string, unknown> }
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
  async listProjects(includeArchived = false): Promise<ProjectResponse[]> {
    const params = new URLSearchParams();
    if (includeArchived) params.append('include_archived', 'true');
    const endpoint = `/api/v1/projects${params.toString() ? `?${params.toString()}` : ''}`;
    return this.request<ProjectResponse[]>(endpoint);
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

  async listTasks(options: { projectId?: string; status?: TaskStatus } = {}): Promise<TaskResponse[]> {
    const params = new URLSearchParams();
    if (options.projectId) params.append('project_id', options.projectId);
    if (options.status) params.append('status', options.status);
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

  async listAutomations(): Promise<AutomationResponse[]> {
    return this.request<AutomationResponse[]>('/api/v1/automations');
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
