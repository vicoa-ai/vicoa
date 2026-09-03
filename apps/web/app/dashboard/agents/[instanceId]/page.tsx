'use client';

import { useState, useEffect, useRef, useCallback, useMemo, useSyncExternalStore } from 'react';
import { useParams } from 'next/navigation';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { Button } from '@/components/ui/button';
import { X, ArrowDown, Pin, Loader2, Menu, PanelLeft, Folder, FolderPlus, MessageCircle, FileCode } from 'lucide-react';
import { useDesktopChrome } from '@/components/dashboard/desktop-chrome-context';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import { DesktopTitlebarLead, DesktopWindowControlsSpacer, useDesktopWindows } from '@/components/desktop/window-chrome';
import { getDesktopConfig } from '@/lib/runtime-config';
import { trackFirstMessageSent } from '@/lib/desktop-telemetry';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { useDashboardNavigation } from '@/lib/contexts/dashboard-navigation-context';
import { AgentInstanceDetail, MessageResponse, SessionInstanceMetadata } from '@/lib/backend-api';
import { getInstanceDetail, postInstanceMessage } from '@/lib/agent-instance-api';
import { getMessageStore } from '@/lib/message-store';
import { useMessageStream } from '@/lib/hooks/use-ws-stream';
import { extractMessageOptions, formatTaskNotifications } from '@/components/ui/message-markdown-utils';
import { GitBranchBadge } from '@/components/dashboard/git-branch-badge';
import { ToolUseGroup, parseToolUse } from '@/components/dashboard/tool-use-display';
import { SubagentGroup } from '@/components/dashboard/subagent-group';
import { MessageItem, resolveAgentType, DateSeparator, ThinkingIndicator, vibingMessages, getMessageVisibleText } from '@/components/dashboard/chat-message-item';
import { ChatFindBar } from '@/components/dashboard/chat-find-bar';
import { FindHighlightProvider } from '@/components/dashboard/chat-find-context';
import { groupSubagents } from '@/components/dashboard/subagent-grouping';
import { parseThinkingPayload } from '@/components/dashboard/thinking-card';
import { FilesGitPanel, FilesGitPanelToggle, usePanelState, type PanelPendingAction } from '@/components/files-git-panel';
import { ChatInput, PermissionModeValue, OpencodeAgentModeValue, type ChatUploadedAttachment, type ChatInputHandle } from '@/components/chat-input';
import { collectComposerDrop } from '@/lib/chat-drop';
import { matchesShortcut, getShortcutCombo } from '@/lib/desktop-shortcuts';
import { extractChatAttachments } from '@/components/chat-attachments';
import { SessionEmptyState } from '@/components/dashboard/session-empty-state';
import { SessionActionsMenu } from '@/components/dashboard/session-actions-menu';
import { FileSearchPalette } from '@/components/dashboard/file-search-palette';
import { toAbsolutePath } from '@/lib/utils';
import { RenameSessionDialog, DeleteSessionDialog, CompleteSessionDialog } from '@/components/dashboard/session-dialogs';
import { useSessionOperations, useCopyToClipboard } from '@/lib/hooks/use-session-operations';
import { useNow, useSessionLiveness } from '@/lib/hooks/use-session-liveness';
import { blocksSending, isClosedByDesign, liveStateHint } from '@/lib/session-liveness';
import {
  canResumeSession,
  isWithinResumeGrace,
  resumeBlockedMessage,
  resumeBlockedShortLabel,
  resumeBlockedReason,
  resumeSession,
} from '@/lib/session-resume';
import { AskUserQuestionSubmitPayload, buildAskUserQuestionCancelPersistMessage, buildAskUserQuestionControlMessage, buildAskUserQuestionSummaryMessage, parseAskUserQuestionPayload } from '@/components/dashboard/ask-user-question-panel';
import { parseQueuePayload, type QueuedMessageItem } from '@/components/dashboard/queue-status';
import {
  isControlEnvelope,
  isInterruptControlMessage,
} from '@/lib/control-messages';
import {
  shouldHideControlMessage,
  extractControlSettingValue,
  getPermissionModeLabel,
  buildPermissionModeRequestMessage,
  buildAgentTypeControlMessage,
  buildThinkingControlMessage,
  buildInterruptControlMessage,
  stripPermissionModeCommandTokens,
  extractPermissionModeFromMessage,
  findLatestPermissionMode,
  findInitialPermissionMode,
  extractAgentModeFromMessage,
  findLatestAgentMode,
  extractThinkingSettingFromMessage,
  findLatestThinkingSetting,
  findLatestModel,
  findLatestEffort,
} from '@/lib/session-control-messages';
import { messageSortKey, groupMessagesByDate } from '@/lib/message-grouping';
import { AGENT_CATALOG_FALLBACK, agentById } from '@/lib/agent-catalog';
import { buildModelControlMessage, buildEffortControlMessage, extractSessionConfigFromInstance, extractAcpControlsFromInstance } from '@/lib/session-config-utils';

// Git diff functionality moved to separate component

// Function to parse git diff and get total changes count
function getGitDiffStats(diffText: string): { additions: number; deletions: number; files: number } {
  const lines = diffText.split('\n');
  let additions = 0;
  let deletions = 0;
  let files = 0;
  let currentFile = false;
  
  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      if (currentFile) files++;
      currentFile = true;
    } else if (line.startsWith('+') && !line.startsWith('+++') && currentFile) {
      additions++;
    } else if (line.startsWith('-') && !line.startsWith('---') && currentFile) {
      deletions++;
    }
  }
  
  if (currentFile) files++;
  
  return { additions, deletions, files };
}

/**
 * True for sessions the machine daemon spawned (the headless runners register
 * with `source: "app"`; the interactive CLI wrapper registers `"terminal"`).
 * Matters because the two drive Claude's permission mode differently — see
 * `sessionPermissionModes`.
 */
function isHeadlessSpawnedSession(instance: { instance_metadata?: SessionInstanceMetadata | null } | null): boolean {
  return instance?.instance_metadata?.source === 'app';
}

/** Legacy remote-session marker: headless spawns used to open with a
 *  "You are starting a coding session" prompt. Dropped June 2026, so this only
 *  still identifies sessions started before then. */
function hasRemoteSessionStartMessage(messages: MessageResponse[]): boolean {
  const scanLimit = 10;
  return messages.slice(0, scanLimit).some((message) => {
    const senderType = message.sender_type?.toLowerCase() ?? '';
    const isUser = senderType === 'user' || senderType === 'human';
    if (!isUser) {
      return false;
    }
    return message.content.toLowerCase().includes('you are starting a coding session');
  });
}

/** Build the `message_metadata` for an optimistic user row, mirroring the
 *  server's shape so the row derives identically before and after the
 *  round-trip: `attachments` for the bubble, and — when the message is (or
 *  turns out to be) queued — the same `queue.status: 'queued'` stamp the echo
 *  carries, so it lands in the queued-messages bar instead of the transcript.
 *  Used both for the initial optimistic append and for the POST-response
 *  correction, so both agree on the exact shape. */
function buildOptimisticUserMetadata(
  attachments: ChatUploadedAttachment[],
  queued: boolean,
): Record<string, unknown> | null {
  if (attachments.length === 0 && !queued) return null;
  return {
    ...(attachments.length > 0 ? { attachments } : {}),
    ...(queued ? { queue: { status: 'queued' as const } } : {}),
  };
}

type ChatItem =
  | { type: 'separator'; date: string; key: string }
  | { type: 'message'; message: MessageResponse; key: string }
  | { type: 'tool-group'; messages: MessageResponse[]; key: string }
  | {
      type: 'subagent-group';
      messages: MessageResponse[];
      subagentType: string;
      description: string;
      key: string;
    }
  | { type: 'thinking'; key: string };

const USER_SENDER_TYPES = new Set(['user', 'human', 'USER', 'HUMAN']);

// Within this many px of the bottom we consider the user "back at the bottom"
// and re-arm follow. Strict so re-following only resumes at the very tail.
const REATTACH_PX = 8;

// Don't re-stick for drift smaller than this. Virtuoso's total height flutters
// by a few dozen px as boundary rows toggle between estimated and measured
// heights; re-scrolling for each flutter shifts the rendered range, forces a
// re-measure, and fires another height change — the open-time "shake". Staying
// put for sub-threshold gaps breaks that loop. The residual gap is < this and
// well inside atBottomThreshold, so the ↓ button stays hidden / it reads as
// "at the bottom". Genuine new content (a streamed message) exceeds this and is
// still followed.
const STICK_TOLERANCE_PX = 72;

function AgentInstanceContent() {
  const params = useParams();
  const instanceId = params.instanceId as string;
  const dashboardContext = useAgentDashboard();
  const { refreshData, updateInstanceStatus } = dashboardContext;
  const { openSidebar } = useDashboardNavigation();

  // The message store (lib/message-store.ts) owns this session's messages +
  // instance metadata; the page paints whatever the store already has. A
  // session visited before renders synchronously from cache (no skeleton)
  // while the mount effect revalidates in the background.
  const storeEntry = useSyncExternalStore(
    useCallback(
      (onStoreChange: () => void) => getMessageStore().subscribe(instanceId, onStoreChange),
      [instanceId],
    ),
    () => getMessageStore().getSnapshot(instanceId),
    () => null,
  );
  const instance = useMemo<AgentInstanceDetail | null>(
    () => (storeEntry?.instance ? { ...storeEntry.instance, messages: storeEntry.messages } : null),
    [storeEntry],
  );
  const hasOlderMessages = storeEntry?.hasOlder ?? false;
  const [error, setError] = useState<string | null>(null);
  // Loading = nothing to paint yet and no failure to report. Derived, not
  // state: a cached session is never "loading", even before its revalidate.
  const isLoading = !instance && !error;
  const [isSending, setIsSending] = useState(false);
  const [streamEnabled, setStreamEnabled] = useState(true);
  const [isAgentThinking, setIsAgentThinking] = useState(false);
  // The vibing row's *visibility*, debounced. `isAgentThinking` gets toggled
  // off→on by separate stream events (every agent message clears it; mode/status
  // pings clear it with nothing re-arming until the next content message), which
  // made the row blink and the list jitter. Showing is immediate; hiding waits a
  // grace window so those sub-second off-blips never remove the row — it only
  // disappears once the agent is genuinely idle.
  const [showThinking, setShowThinking] = useState(false);
  const hideThinkingTimerRef = useRef<number | null>(null);
  const [renameDialog, setRenameDialog] = useState<{
    open: boolean;
    sessionId: string;
    currentName: string;
  }>({ open: false, sessionId: '', currentName: '' });

  const [deleteDialog, setDeleteDialog] = useState<{
    open: boolean;
    sessionId: string;
    sessionName: string;
  }>({ open: false, sessionId: '', sessionName: '' });

  const [completeDialog, setCompleteDialog] = useState<{
    open: boolean;
    sessionId: string;
    sessionName: string;
  }>({ open: false, sessionId: '', sessionName: '' });
  const panel = usePanelState(instanceId);
  const isWindows = useDesktopWindows();
  // Handed to FilesGitPanel so a ⌘T pressed while the panel is closed can still
  // open a fresh terminal tab (see the keydown effect below).
  const pendingPanelActionRef = useRef<PanelPendingAction | null>(null);
  // ⌘P file finder (see the keydown effect below). Opening a picked file goes
  // through `openFileRequest`, whose bumped nonce makes the panel open it even
  // when it's already mounted / already showing another file.
  const [fileSearchOpen, setFileSearchOpen] = useState(false);
  const [openFileRequest, setOpenFileRequest] = useState<{ path: string; nonce: number } | null>(
    null,
  );
  // Focus-mode chat peek (design A): temporarily reveal the chat beneath the
  // maximized file layer. `sticky` toggles from the header button; `hold` is the
  // spring-loaded key (peek while held). Either one reveals the chat.
  const [peekSticky, setPeekSticky] = useState(false);
  const [peekHold, setPeekHold] = useState(false);
  const desktopChrome = useDesktopChrome();
  const [permissionMode, setPermissionMode] = useState<PermissionModeValue | null>(null);
  const [pendingPermissionMode, setPendingPermissionMode] = useState<PermissionModeValue | null>(null);
  const [permissionModeError, setPermissionModeError] = useState<string | null>(null);
  const [initialPermissionMode, setInitialPermissionMode] = useState<PermissionModeValue | null>(null);
  const [opencodeAgentMode, setOpencodeAgentMode] = useState<OpencodeAgentModeValue | null>(null);
  const [pendingOpencodeAgentMode, setPendingOpencodeAgentMode] = useState<OpencodeAgentModeValue | null>(null);
  const [thinkingSettingEnabled, setThinkingSettingEnabled] = useState<boolean | null>(null);
  const [confirmedModel, setConfirmedModel] = useState<string | null>(null);
  const [pendingModel, setPendingModel] = useState<string | null>(null);
  const [confirmedEffort, setConfirmedEffort] = useState<string | null>(null);
  const [pendingEffort, setPendingEffort] = useState<string | null>(null);
  // Optimistic gear selection for ACP agents (cursor/gemini/copilot/kimi/hermes).
  // Their raw model/mode ids aren't recognised by the claude/codex echo parsers,
  // so we apply changes optimistically here instead of waiting for an echo.
  const [acpModel, setAcpModel] = useState<string | null>(null);
  const [acpMode, setAcpMode] = useState<string | null>(null);
  // Whether this session was started with an initial prompt (set by the
  // new-session flow via sessionStorage). true → show the "Starting your
  // session" loader while empty; false/unknown → the idle "Session ready" card.
  const [initialPromptHint, setInitialPromptHint] = useState<boolean | null>(null);
  const pendingPermissionTimer = useRef<NodeJS.Timeout | null>(null);
  const optimisticIdsRef = useRef<string[]>([]);
  // Live mirror of the instance status for `sendMessage`'s queue prediction.
  // Kept in a ref (assigned every render) so reading it doesn't pull
  // `instance.status` into sendMessage's dep array — which would re-identity
  // the callback and re-render the memoized composer on every status flip.
  const statusRef = useRef<string | null>(null);
  statusRef.current = instance?.status ?? null;
  // The session currently on screen. Fetches capture `instanceId` and compare
  // against this before touching transient UI state, so a slow response for a
  // previously viewed session can still warm that session's cache entry
  // without bleeding into the one now displayed.
  const currentInstanceIdRef = useRef(instanceId);
  currentInstanceIdRef.current = instanceId;
  const { copied: copiedSessionId, copy: copySessionId } = useCopyToClipboard();
  const { renameSession, deleteSession, markAsComplete: markComplete, markAsUnread, togglePin } = useSessionOperations(instanceId);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  // `isNearBottom === true` hides the floating ↓ button; it mirrors our intent
  // to follow the bottom, NOT Virtuoso's raw "is the scroller at the geometric
  // bottom" reading. `followBottomRef` is the synchronous source of truth read
  // by `followOutput` and the scroller listeners (which run outside React's
  // render cycle, so they can't read state). They're kept in sync via
  // `setFollowBottom`. We only detach (show the button) when the user
  // deliberately scrolls up — never because appended/measured content grew the
  // list out from under a still-following view. See scroller listeners below.
  const followBottomRef = useRef(true);
  // Scroller element + the signals used to tell a user-driven upward scroll
  // apart from Virtuoso's own measurement-driven scrollTop adjustments. A
  // programmatic stick-to-bottom only ever *increases* scrollTop, so a decrease
  // paired with a real wheel/touch/scrollbar gesture is the user leaving.
  const scrollerElRef = useRef<HTMLElement | null>(null);
  const lastScrollTopRef = useRef(0);
  const userScrollUpIntentRef = useRef(false);
  const pointerScrollActiveRef = useRef(false);
  const lastTouchYRef = useRef<number | null>(null);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const isLoadingOlderRef = useRef(false);
  // Virtuoso renders incrementally and measures item heights as it goes — for a
  // long history this produces a visible "scroll down in segments" artifact on
  // first paint. Hide the list under a background overlay until either Virtuoso
  // confirms the last index is in range, or a max-wait timer trips. Once we
  // reveal, we never go back: prepending older history must stay seamless.
  const [isViewReady, setIsViewReady] = useState(false);
  const viewReadyRef = useRef(false);
  const chatInputRef = useRef<ChatInputHandle>(null);
  // Drag-drop onto the middle panel: dropped files/images upload; a dropped
  // folder is referenced by path on desktop, or its files upload on web (see
  // `collectComposerDrop`). `dragDepthRef` counts enter/leave across nested
  // children so the overlay doesn't flicker as the cursor crosses them.
  const [isDropTarget, setIsDropTarget] = useState(false);
  const dragDepthRef = useRef(0);
  // Safety net: a drag that ends outside the panel (Escape, dropped elsewhere,
  // or dragged back to the file explorer) never fires our own leave/drop, so
  // clear the overlay on any window-level end. `dragend`/`drop` cover a drop
  // somewhere in the window, but an OS file drag that leaves WITHOUT dropping
  // fires neither — `dragend` targets the drag's source node, which lives
  // outside our document. The one event that does fire when the pointer exits
  // the viewport is a window-level `dragleave` whose `relatedTarget` is null
  // (an internal element-to-element move always carries the entered element).
  useEffect(() => {
    if (!isDropTarget) return;
    const reset = () => {
      dragDepthRef.current = 0;
      setIsDropTarget(false);
    };
    const onWindowDragLeave = (e: DragEvent) => {
      if (!e.relatedTarget) reset();
    };
    window.addEventListener('drop', reset);
    window.addEventListener('dragend', reset);
    window.addEventListener('dragleave', onWindowDragLeave);
    return () => {
      window.removeEventListener('drop', reset);
      window.removeEventListener('dragend', reset);
      window.removeEventListener('dragleave', onWindowDragLeave);
    };
  }, [isDropTarget]);

  // Initial page size — covers most sessions in one round-trip and lets the
  // viewport paint fast. Older messages lazy-load when the user scrolls up.
  const INITIAL_MESSAGE_PAGE_SIZE = 200;
  const OLDER_MESSAGE_PAGE_SIZE = 200;

  // Generate a random vibing message (regenerates when messages change)
  const vibingMessage = useMemo(() => {
    const message = vibingMessages[Math.floor(Math.random() * vibingMessages.length)];
    // Capitalize first letter only
    return message.charAt(0).toUpperCase() + message.slice(1).toLowerCase() + '…';
  }, [instance?.messages.length]);

  // Debounce the vibing row's hide so brief isAgentThinking off-blips (mode/
  // status pings between content messages) don't flicker the row in and out.
  useEffect(() => {
    if (isAgentThinking) {
      if (hideThinkingTimerRef.current !== null) {
        window.clearTimeout(hideThinkingTimerRef.current);
        hideThinkingTimerRef.current = null;
      }
      setShowThinking(true);
      return;
    }
    if (hideThinkingTimerRef.current !== null) window.clearTimeout(hideThinkingTimerRef.current);
    hideThinkingTimerRef.current = window.setTimeout(() => {
      hideThinkingTimerRef.current = null;
      setShowThinking(false);
    }, 600);
  }, [isAgentThinking]);

  useEffect(() => () => {
    if (hideThinkingTimerRef.current !== null) window.clearTimeout(hideThinkingTimerRef.current);
  }, []);

  // Handle new messages from stream
  const handleNewMessage = useCallback((newMessage: MessageResponse) => {
    const store = getMessageStore();
    // Already known (REST hydrate and WS catch-up overlap by design): skip the
    // append AND the side effects, matching the old seenMessageIdsRef gate.
    if (store.hasMessage(instanceId, newMessage.id)) return;

    const isAgentMessage = newMessage.sender_type !== 'user' && newMessage.sender_type !== 'human';
    const derivedMode = extractPermissionModeFromMessage(newMessage.content);
    // Raw permission_mode value (covers ACP agents whose mode ids the claude/
    // codex validator above rejects) — used only to keep these control echoes
    // from being treated as real, status-affecting chat messages.
    const derivedRawPermission = extractControlSettingValue(newMessage.content, 'permission_mode');
    const derivedAgentMode = extractAgentModeFromMessage(newMessage.content);
    const derivedThinking = extractThinkingSettingFromMessage(newMessage.content);
    const derivedModel = extractControlSettingValue(newMessage.content, 'model');
    const derivedEffort = extractControlSettingValue(newMessage.content, 'effort');
    const shouldAffectStatus = !derivedMode && !derivedRawPermission && !derivedAgentMode && derivedThinking === null && !derivedModel && !derivedEffort;

    if (isAgentMessage) {
      setIsAgentThinking(false);
    }

    // When real user message arrives, swap out the oldest pending optimistic message
    let optimisticIdToRemove: string | null = null;
    if (!isAgentMessage && optimisticIdsRef.current.length > 0) {
      optimisticIdToRemove = optimisticIdsRef.current[0];
      optimisticIdsRef.current = optimisticIdsRef.current.slice(1);
    }

    if (optimisticIdToRemove) {
      store.removeMessage(instanceId, optimisticIdToRemove);
    }
    store.appendOrMerge(instanceId, [newMessage]);
    // Update status based on message, unless it's just a permission mode ping
    if (shouldAffectStatus) {
      store.patchInstance(instanceId, {
        status: newMessage.requires_user_input ? 'AWAITING_INPUT' : 'ACTIVE',
      });
    }

    if (shouldAffectStatus && isAgentMessage && !newMessage.requires_user_input) {
      // Agent is still working
      setIsAgentThinking(true);
    }

    // Update sidebar with latest message when status is affected
    if (shouldAffectStatus) {
      const newStatus = newMessage.requires_user_input ? 'AWAITING_INPUT' : 'ACTIVE';
      // Truncate message preview to ~50 chars for sidebar display
      const messagePreview = newMessage.content.slice(0, 50);
      updateInstanceStatus(instanceId, newStatus, messagePreview);
    }

    if (derivedMode) {
      setPermissionMode(derivedMode);
      setPendingPermissionMode(prev => (prev === derivedMode ? null : prev));
    }

    if (derivedAgentMode) {
      setOpencodeAgentMode(derivedAgentMode);
      setPendingOpencodeAgentMode(prev => (prev === derivedAgentMode ? null : prev));
    }

    if (derivedThinking !== null) {
      setThinkingSettingEnabled(prev => (prev === derivedThinking ? prev : derivedThinking));
    }

    if (derivedModel) {
      setConfirmedModel(derivedModel);
      setPendingModel(prev => (prev === derivedModel ? null : prev));
    }

    if (derivedEffort) {
      setConfirmedEffort(derivedEffort);
      setPendingEffort(prev => (prev === derivedEffort ? null : prev));
    }
  }, [instanceId, updateInstanceStatus]);
  
  // Handle status updates from stream
  const handleStatusUpdate = useCallback((status: string) => {
    // Handle thinking state based on status
    if (status === 'AWAITING_INPUT' || status === 'COMPLETED' || status === 'FAILED') {
      setIsAgentThinking(false);
    } else if (status === 'ACTIVE' || status === 'STARTING') {
      setIsAgentThinking(true);
    }

    getMessageStore().patchInstance(instanceId, {
      status: status as AgentInstanceDetail['status'],
    });

    // Update sidebar in real-time via SSE
    updateInstanceStatus(instanceId, status);
  }, [instanceId, updateInstanceStatus]);

  // Auto-mark REVIEWED when the user switches away from a session they were
  // viewing. The sidebar only marks a session reviewed on *open*, so a session
  // that flips to AWAITING_INPUT *while it's already on screen* (agent finished
  // its turn as you watched) keeps its blue dot until you re-open it. Since you
  // were looking at it, leaving = you've seen the last message — so clear it.
  // Skipped when the last message is a real question (ask-user-question /
  // options block): those genuinely still need your input, so the dot stays.
  const markReviewedOnLeave = useCallback((leavingId: string) => {
    const snapshot = getMessageStore().getSnapshot(leavingId);
    if (snapshot?.instance?.status !== 'AWAITING_INPUT') return;
    const messages = snapshot?.messages ?? [];
    const lastMessage = messages[messages.length - 1];
    if (lastMessage) {
      const hasAskUserQuestion = Boolean(parseAskUserQuestionPayload(lastMessage));
      const hasOptions = extractMessageOptions(lastMessage.content || '').options.length > 0;
      if (hasAskUserQuestion || hasOptions) return;
    }
    // Optimistic local flip (sidebar row + cached message-store snapshot), then
    // persist. Fire-and-forget: the page is unmounting, nothing awaits it.
    updateInstanceStatus(leavingId, 'REVIEWED');
    getMessageStore().patchInstance(leavingId, { status: 'REVIEWED' });
    if (dashboardContext.api) {
      void dashboardContext.api
        .updateAgentStatus(leavingId, { status: 'REVIEWED' })
        .catch((err) => console.error('Failed to auto-mark session reviewed on leave:', err));
    }
  }, [dashboardContext, updateInstanceStatus]);
  // Read the latest callback through a ref so the leave effect can depend on
  // instanceId alone — otherwise a new `api`/callback identity would re-run the
  // effect and fire its cleanup while the session is still on screen.
  const markReviewedOnLeaveRef = useRef(markReviewedOnLeave);
  markReviewedOnLeaveRef.current = markReviewedOnLeave;
  useEffect(() => () => {
    markReviewedOnLeaveRef.current(instanceId);
  }, [instanceId]);

  // Live usage (context window + rate limits) rides instance_metadata on every
  // instance-update; merge it into the store so the composer meter repaints.
  const handleInstanceMetadata = useCallback((metadata: Record<string, unknown> | null) => {
    getMessageStore().patchInstance(instanceId, {
      instance_metadata: metadata as AgentInstanceDetail['instance_metadata'],
    });
  }, [instanceId]);

  const handleTogglePin = useCallback(async () => {
    const wasPinned = !!instance?.pinned_at;
    const optimisticNext = wasPinned ? null : new Date().toISOString();
    getMessageStore().patchInstance(instanceId, { pinned_at: optimisticNext });
    dashboardContext.updateInstance(instanceId, { pinned_at: optimisticNext });

    const ok = await togglePin(instanceId, !wasPinned);
    if (!ok) {
      const original = instance?.pinned_at ?? null;
      getMessageStore().patchInstance(instanceId, { pinned_at: original });
      dashboardContext.updateInstance(instanceId, { pinned_at: original });
      alert(wasPinned ? "Couldn't unpin session" : "Couldn't pin session");
    }
  }, [instance?.pinned_at, instanceId, togglePin, dashboardContext]);
  
  // Handle streaming connection
  const {
    isConnected: isStreamConnected,
    error: streamError,
  } = useMessageStream({
    instanceId,
    enabled: streamEnabled && !!instance,
    // Catch-up starts after the store's newest non-optimistic message, so
    // revisiting a cached session fetches a delta rather than the full page.
    initialWatermark: storeEntry?.watermark ?? null,
    onMessage: handleNewMessage,
    onStatusUpdate: handleStatusUpdate,
    onInstanceMetadata: handleInstanceMetadata,
    onError: (err) => {
      console.error('Stream error:', err);
    },
  });

  // Single source of truth for "are we following the bottom". Keeps the
  // synchronous ref (read by followOutput + scroller listeners) and the React
  // state (drives the ↓ button) in lockstep.
  const setFollowBottom = useCallback((following: boolean) => {
    followBottomRef.current = following;
    if (following) userScrollUpIntentRef.current = false;
    setIsNearBottom(following);
  }, []);

  // Scroll the real DOM scroller to its LIVE scrollHeight rather than using
  // Virtuoso's `scrollToIndex({index:'LAST'})`, which targets an offset computed
  // from the 120px height estimate and parks a few hundred px ABOVE the true
  // bottom. Skips the correction when already within the tolerance so we don't
  // chase the measurement flutter (the source of the open-time shake). The rAF
  // re-apply covers the race where totalListHeightChanged fires before React has
  // committed the taller sizer, so the first scroll clamps to a stale height.
  const stickToBottomNow = useCallback((behavior: 'auto' | 'smooth' = 'auto') => {
    const apply = () => {
      const el = scrollerElRef.current;
      if (!el) {
        virtuosoRef.current?.scrollTo({ top: Number.MAX_SAFE_INTEGER, behavior });
        return;
      }
      const distance = el.scrollHeight - el.clientHeight - el.scrollTop;
      if (distance <= STICK_TOLERANCE_PX) return;
      el.scrollTo({ top: el.scrollHeight, behavior });
    };
    apply();
    if (behavior === 'auto') {
      requestAnimationFrame(() => {
        if (followBottomRef.current) apply();
      });
    }
  }, []);

  const snapToBottomAnchor = useCallback((behavior: 'auto' | 'smooth' = 'auto') => {
    stickToBottomNow(behavior);
    setFollowBottom(true);
  }, [stickToBottomNow, setFollowBottom]);

  const scheduleBottomAnchorSnaps = useCallback((attempts = 1, intervalMs = 50) => {
    let attempt = 0;
    const tick = () => {
      snapToBottomAnchor('auto');
      attempt += 1;
      if (attempt < attempts) {
        window.setTimeout(tick, intervalMs);
      }
    };
    tick();
  }, [snapToBottomAnchor]);

  // ↓ button: re-arm follow intent, then scroll the DOM scroller to its true
  // bottom (NOT scrollToIndex, which lands short — see stickToBottomNow).
  const scrollToBottom = useCallback(() => {
    setFollowBottom(true);
    stickToBottomNow('smooth');
  }, [setFollowBottom, stickToBottomNow]);

  // Re-attach the moment the view is essentially back at the bottom; detach
  // only when the user themselves drives the scroller upward off the bottom.
  const handleScrollerScroll = useCallback(() => {
    const el = scrollerElRef.current;
    if (!el) return;
    const top = el.scrollTop;
    const previousTop = lastScrollTopRef.current;
    lastScrollTopRef.current = top;
    const distanceFromBottom = el.scrollHeight - el.clientHeight - top;

    if (distanceFromBottom <= REATTACH_PX) {
      if (!followBottomRef.current) setFollowBottom(true);
      userScrollUpIntentRef.current = false;
      return;
    }

    // A decrease in scrollTop that the user actually caused (wheel up, touch
    // drag down, or a scrollbar drag) means they want to leave the bottom.
    // Virtuoso's own post-measurement corrections also decrease scrollTop but
    // carry no such gesture, so they slip past this guard and we stay stuck.
    const scrolledUp = top < previousTop - 1;
    const userDriven = userScrollUpIntentRef.current || pointerScrollActiveRef.current;
    if (scrolledUp && userDriven && followBottomRef.current) {
      setFollowBottom(false);
    }
    userScrollUpIntentRef.current = false;
  }, [setFollowBottom]);

  const handleScrollerWheel = useCallback((event: WheelEvent) => {
    if (event.deltaY < 0) userScrollUpIntentRef.current = true;
  }, []);
  const handleScrollerTouchStart = useCallback((event: TouchEvent) => {
    lastTouchYRef.current = event.touches[0]?.clientY ?? null;
  }, []);
  const handleScrollerTouchMove = useCallback((event: TouchEvent) => {
    const y = event.touches[0]?.clientY;
    const previousY = lastTouchYRef.current;
    if (y != null && previousY != null && y > previousY + 1) {
      userScrollUpIntentRef.current = true;
    }
    if (y != null) lastTouchYRef.current = y;
  }, []);
  const handleScrollerPointerDown = useCallback(() => {
    pointerScrollActiveRef.current = true;
  }, []);
  const handleScrollerPointerUp = useCallback(() => {
    pointerScrollActiveRef.current = false;
  }, []);

  // Virtuoso owns the scroller DOM node; capture it here so we can listen for
  // raw user gestures (Virtuoso surfaces no onScroll/onWheel prop). Re-runs per
  // session because <Virtuoso key={instanceId}> remounts.
  const handleScrollerRef = useCallback((node: HTMLElement | Window | null) => {
    const previous = scrollerElRef.current;
    if (previous) {
      previous.removeEventListener('scroll', handleScrollerScroll);
      previous.removeEventListener('wheel', handleScrollerWheel);
      previous.removeEventListener('touchstart', handleScrollerTouchStart);
      previous.removeEventListener('touchmove', handleScrollerTouchMove);
      previous.removeEventListener('pointerdown', handleScrollerPointerDown);
      previous.removeEventListener('pointerup', handleScrollerPointerUp);
      previous.removeEventListener('pointercancel', handleScrollerPointerUp);
    }
    const element = node instanceof HTMLElement ? node : null;
    scrollerElRef.current = element;
    if (element) {
      // Guarantee it lands on the actual scroller (not just via className) so
      // scrolling past the last message can't rubber-band or chain to the window.
      element.style.overscrollBehavior = 'none';
      lastScrollTopRef.current = element.scrollTop;
      element.addEventListener('scroll', handleScrollerScroll, { passive: true });
      element.addEventListener('wheel', handleScrollerWheel, { passive: true });
      element.addEventListener('touchstart', handleScrollerTouchStart, { passive: true });
      element.addEventListener('touchmove', handleScrollerTouchMove, { passive: true });
      element.addEventListener('pointerdown', handleScrollerPointerDown, { passive: true });
      element.addEventListener('pointerup', handleScrollerPointerUp, { passive: true });
      element.addEventListener('pointercancel', handleScrollerPointerUp, { passive: true });
    }
  }, [
    handleScrollerScroll,
    handleScrollerWheel,
    handleScrollerTouchStart,
    handleScrollerTouchMove,
    handleScrollerPointerDown,
    handleScrollerPointerUp,
  ]);

  const fetchInstanceDetail = useCallback(async () => {
    // Capture the target: the store write below stays keyed to it, so a
    // response landing after a session switch warms that session's cache
    // instead of bleeding into the one now on screen.
    const targetId = instanceId;
    try {
      setError(null);
      const detail = await getInstanceDetail(targetId, {
        messageLimit: INITIAL_MESSAGE_PAGE_SIZE,
      });

      const messages: MessageResponse[] = detail.messages ?? [];
      // Authoritative hydrate: backend wins on id conflicts; optimistic rows,
      // paginated older history, and newer live rows survive (store rules).
      // If we got a full page, there's almost certainly more older history —
      // backend orders DESC + LIMIT then reverses, so a full page === N most recent.
      getMessageStore().hydrateFromDetail(targetId, detail, {
        hasOlder: messages.length >= INITIAL_MESSAGE_PAGE_SIZE,
      });
      if (currentInstanceIdRef.current !== targetId) return;
      if (detail.status === 'STARTING' || detail.status === 'ACTIVE') {
        setIsAgentThinking(true);
      }
    } catch (err) {
      if (currentInstanceIdRef.current !== targetId) return;
      console.error('Failed to fetch instance:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch instance');
    }
  }, [instanceId]);

  const loadOlderMessages = useCallback(async () => {
    if (isLoadingOlderRef.current) return;
    const store = getMessageStore();
    const entry = store.getSnapshot(instanceId);
    if (!entry?.hasOlder) return;
    const oldest = entry.messages[0];
    if (!oldest || oldest.id.startsWith('optimistic-')) return;

    isLoadingOlderRef.current = true;
    setIsLoadingOlder(true);
    try {
      const detail = await getInstanceDetail(instanceId, {
        messageLimit: OLDER_MESSAGE_PAGE_SIZE,
        beforeMessageId: oldest.id,
      });

      const older: MessageResponse[] = detail.messages ?? [];
      // The store dedupes by id; a fully-duplicate page clears hasOlder even
      // when the size heuristic (full page ⇒ assume more remain) says otherwise.
      store.prependOlder(instanceId, older, older.length >= OLDER_MESSAGE_PAGE_SIZE);
    } catch (err) {
      console.error('Failed to load older messages:', err);
    } finally {
      isLoadingOlderRef.current = false;
      setIsLoadingOlder(false);
    }
  }, [instanceId]);

  const postMessageToInstance = useCallback(async (messageContent: string, attachmentIds: string[] = []) => {
    const echo = await postInstanceMessage(instanceId, messageContent, attachmentIds);

    if (!isStreamConnected) {
      await fetchInstanceDetail();
    }
    return echo;
  }, [instanceId, isStreamConnected, fetchInstanceDetail]);

  // Re-arm follow intent and nudge the just-committed row into view. A direct
  // send expects to watch its message land and the reply stream in, regardless
  // of where the user was scrolled. The double rAF waits for the store-write
  // commit + Virtuoso's first re-measure before scrolling — covers the
  // send-from-up-the-scroll case where there was nothing to follow.
  const followOwnSend = useCallback(() => {
    setFollowBottom(true);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (followBottomRef.current) stickToBottomNow('auto');
      });
    });
  }, [setFollowBottom, stickToBottomNow]);

  const addOptimisticUserMessage = useCallback((content: string, attachments: ChatUploadedAttachment[] = [], queued = false): string => {
    const optimisticId = `optimistic-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const optimisticMessage: MessageResponse = {
      id: optimisticId,
      content,
      sender_type: 'user',
      created_at: new Date().toISOString(),
      requires_user_input: false,
      message_metadata: buildOptimisticUserMetadata(attachments, queued),
    };
    optimisticIdsRef.current = [...optimisticIdsRef.current, optimisticId];
    // Flagged optimistic in the store: a background hydrate preserves it and
    // the WS watermark ignores its client-clock timestamp. It leaves when the
    // real echo arrives (handleNewMessage swaps it out) or the send fails.
    getMessageStore().appendOptimistic(instanceId, optimisticMessage);
    // A queued row lands in the composer's queue bar, not the transcript, so
    // there's no new bottom row to follow — don't yank a user reading history
    // down to the bottom.
    if (!queued) followOwnSend();
    return optimisticId;
  }, [instanceId, followOwnSend]);

  const removeOptimisticMessage = useCallback((id: string) => {
    optimisticIdsRef.current = optimisticIdsRef.current.filter(oid => oid !== id);
    getMessageStore().removeMessage(instanceId, id);
  }, [instanceId]);

  const sendMessage = useCallback(async (messageContent: string, attachments: ChatUploadedAttachment[] = []) => {
    if ((!messageContent && attachments.length === 0) || isSending) return;

    // Guess where the optimistic row goes for the instant render: the backend
    // stamps a user message `queued` iff the instance was ACTIVE when it arrived
    // (agents.py), so mirror that with the status we last saw. It's only a guess
    // — local status is an async WS mirror that can lag the agent's real
    // ACTIVE⇄idle flip by a round-trip — but the POST response below corrects
    // any miss authoritatively, so this just minimizes the visible correction.
    const willQueue = statusRef.current === 'ACTIVE';

    setIsSending(true);
    setIsAgentThinking(true);

    const optimisticId = addOptimisticUserMessage(messageContent, attachments, willQueue);

    try {
      const echo = await postMessageToInstance(messageContent, attachments.map(a => a.id));
      // The POST response carries the backend's real queue decision for THIS
      // message. If the guess above missed — the agent flipped ACTIVE/idle in
      // the round-trip before its status echo landed — restamp the optimistic
      // row now, off the response, so it jumps to the right place immediately
      // instead of waiting for the slower WS message echo (that lag is the
      // visible bounce). Skip if the WS echo already reconciled the row
      // (handleNewMessage swapped it out), so we don't stash a stale patch.
      const actuallyQueued = parseQueuePayload(echo)?.status === 'queued';
      if (actuallyQueued !== willQueue && getMessageStore().hasMessage(instanceId, optimisticId)) {
        getMessageStore().patchMetadata(
          instanceId,
          optimisticId,
          buildOptimisticUserMetadata(attachments, actuallyQueued),
        );
        // Corrected down into the transcript — re-arm follow so it lands in view
        // like a direct send would (the queued branch had skipped the scroll).
        if (!actuallyQueued) followOwnSend();
      }
      // Picks first_web_message_sent / first_desktop_message_sent from the
      // surface and owns its own guard. It also swallows its own storage
      // errors, which this try-block could not: an unreadable localStorage used
      // to land in the catch below and roll back a message that had in fact
      // been delivered.
      trackFirstMessageSent();
    } catch (err) {
      console.error('Failed to send message:', err);
      removeOptimisticMessage(optimisticId);
      alert('Failed to send message');
      setIsAgentThinking(false);
    } finally {
      setIsSending(false);
    }
  }, [isSending, instanceId, postMessageToInstance, addOptimisticUserMessage, removeOptimisticMessage, followOwnSend]);

  const handleOptionClick = (option: string) => {
    sendMessage(option);
  };

  const handleAskUserQuestionSubmit = useCallback((payload: AskUserQuestionSubmitPayload) => {
    console.debug('[AskUserQuestion] Submit payload', {
      messageId: payload.message_id,
      answers: payload.answers,
      displayAnswers: payload.display_answers,
    });
    const summaryMessage = buildAskUserQuestionSummaryMessage(payload);
    const optimisticId = summaryMessage ? addOptimisticUserMessage(summaryMessage) : null;
    (async () => {
      try {
        if (summaryMessage) {
          await postMessageToInstance(summaryMessage);
        }
        await postMessageToInstance(buildAskUserQuestionControlMessage('submit', payload));
      } catch (err) {
        if (optimisticId) removeOptimisticMessage(optimisticId);
        console.error('Failed to submit AskUserQuestion answers:', err);
        alert('Failed to submit AskUserQuestion answers');
      }
    })();
  }, [postMessageToInstance, addOptimisticUserMessage, removeOptimisticMessage]);

  const handleAskUserQuestionCancel = useCallback((_messageId: string) => {
    const persistMessage = buildAskUserQuestionCancelPersistMessage();
    const optimisticId = addOptimisticUserMessage(persistMessage);
    (async () => {
      try {
        await postMessageToInstance(persistMessage);
        await postMessageToInstance(buildAskUserQuestionControlMessage('cancel'));
      } catch (err) {
        removeOptimisticMessage(optimisticId);
        console.error('Failed to cancel AskUserQuestion:', err);
        alert('Failed to cancel AskUserQuestion');
      }
    })();
  }, [postMessageToInstance, addOptimisticUserMessage, removeOptimisticMessage]);

  const handlePermissionModeSelect = useCallback((mode: PermissionModeValue) => {
    if (pendingPermissionMode === mode) {
      return;
    }
    if (!pendingPermissionMode && permissionMode === mode) {
      return;
    }

    setPermissionModeError(null);
    setPendingPermissionMode(mode);
    postMessageToInstance(buildPermissionModeRequestMessage(mode)).catch(err => {
      console.error('Failed to update permission mode:', err);
      setPendingPermissionMode(prev => (prev === mode ? null : prev));
      setPermissionModeError("Couldn't update permission mode. Please try again.");
    });
  }, [pendingPermissionMode, permissionMode, postMessageToInstance]);

  const handleOpencodeAgentModeSelect = useCallback((mode: OpencodeAgentModeValue) => {
    if (pendingOpencodeAgentMode === mode) {
      return;
    }
    if (!pendingOpencodeAgentMode && opencodeAgentMode === mode) {
      return;
    }

    setPendingOpencodeAgentMode(mode);
    setOpencodeAgentMode(mode);
    postMessageToInstance(buildAgentTypeControlMessage(mode))
      .then(() => {
        setPendingOpencodeAgentMode(prev => (prev === mode ? null : prev));
      })
      .catch(err => {
        console.error('Failed to update agent mode:', err);
        setPendingOpencodeAgentMode(prev => (prev === mode ? null : prev));
      });
  }, [pendingOpencodeAgentMode, opencodeAgentMode, postMessageToInstance]);

  const handleThinkingToggle = useCallback((enabled: boolean) => {
    if (thinkingSettingEnabled === enabled) {
      return;
    }

    const previousState = thinkingSettingEnabled;
    setThinkingSettingEnabled(enabled);
    postMessageToInstance(buildThinkingControlMessage(enabled)).catch(err => {
      console.error('Failed to update thinking setting:', err);
      setThinkingSettingEnabled(previousState);
    });
  }, [thinkingSettingEnabled, postMessageToInstance]);

  const handleModelChange = useCallback((modelId: string) => {
    const prev = pendingModel;
    setPendingModel(modelId);
    postMessageToInstance(buildModelControlMessage(modelId)).catch((err) => {
      console.error('Failed to update model:', err);
      setPendingModel(prev);
    });
  }, [pendingModel, postMessageToInstance]);

  const handleEffortChange = useCallback((effortId: string) => {
    const prev = pendingEffort;
    setPendingEffort(effortId);
    postMessageToInstance(buildEffortControlMessage(effortId)).catch((err) => {
      console.error('Failed to update effort:', err);
      setPendingEffort(prev);
    });
  }, [pendingEffort, postMessageToInstance]);

  // ACP model/mode changes (cursor/gemini/copilot/kimi/hermes). The shared
  // claude/codex handlers clear their pending spinner off an echo the ACP raw
  // ids never produce, so they'd hang until the 20s timeout with the radio
  // stuck on the old value. Apply optimistically: move the selection
  // immediately, send the control message, revert only on failure.
  const handleAcpModelChange = useCallback((modelId: string) => {
    setAcpModel(modelId);
    postMessageToInstance(buildModelControlMessage(modelId)).catch((err) => {
      console.error('Failed to update model:', err);
      setAcpModel(null);
    });
  }, [postMessageToInstance]);

  const handleAcpModeChange = useCallback((modeId: string) => {
    setAcpMode(modeId);
    postMessageToInstance(buildPermissionModeRequestMessage(modeId as PermissionModeValue)).catch((err) => {
      console.error('Failed to update mode:', err);
      setAcpMode(null);
    });
  }, [postMessageToInstance]);

  const handleInterrupt = useCallback(() => {
    // Optimistic row first, same as a normal send: the Stop should land in
    // the transcript the moment it's pressed, ahead of the POST round-trip,
    // so the order the user sees matches the order things happened —
    // "Stop current task." and then the agent's "Interrupted" reply.
    const content = buildInterruptControlMessage();
    const optimisticId = addOptimisticUserMessage(content);
    postMessageToInstance(content).catch(err => {
      console.error('Failed to send interrupt:', err);
      // Nothing was delivered, so leaving the row would claim a stop that
      // never happened.
      removeOptimisticMessage(optimisticId);
    });
  }, [addOptimisticUserMessage, postMessageToInstance, removeOptimisticMessage]);

  const handleCopySessionId = useCallback(async () => {
    await copySessionId(instance?.id || instanceId);
  }, [instance?.id, instanceId, copySessionId]);

  const handleRenameSession = useCallback((sessionId: string, currentName: string) => {
    setRenameDialog({ open: true, sessionId, currentName });
  }, []);

  const handleDeleteSession = useCallback((sessionId: string, sessionName: string) => {
    setDeleteDialog({ open: true, sessionId, sessionName });
  }, []);

  const handleMarkSessionComplete = useCallback((sessionId: string, sessionName: string) => {
    setCompleteDialog({ open: true, sessionId, sessionName });
  }, []);

  const performRename = useCallback(async (sessionId: string, newName: string) => {
    await renameSession(sessionId, newName);
    await fetchInstanceDetail();
  }, [renameSession, fetchInstanceDetail]);

  const performDelete = useCallback(async (sessionId: string) => {
    await deleteSession(sessionId, true);
  }, [deleteSession]);

  const performComplete = useCallback(async (sessionId: string) => {
    await markComplete(sessionId);
    updateInstanceStatus(sessionId, 'COMPLETED');
    await fetchInstanceDetail();
  }, [markComplete, updateInstanceStatus, fetchInstanceDetail]);

  const handleMarkSessionUnread = useCallback(async (sessionId: string) => {
    updateInstanceStatus(sessionId, 'AWAITING_INPUT');
    await markAsUnread(sessionId);
    await fetchInstanceDetail();
  }, [markAsUnread, updateInstanceStatus, fetchInstanceDetail]);

  const handleOpenRenameDialog = useCallback(() => {
    if (!instance) return;

    // Helper function to extract last part of path
    const getLastPathPart = (path: string) => {
      const cleanPath = path.replace(/\/+$/, '');
      const parts = cleanPath.split('/');
      return parts[parts.length - 1] || path;
    };

    // Set initial value based on current name or project
    let currentName = '';
    if (instance.name) {
      currentName = instance.name;
    } else if (instance.project) {
      currentName = getLastPathPart(instance.project);
    }

    handleRenameSession(instanceId, currentName);
  }, [instance, instanceId, handleRenameSession]);


  // Memoize expensive computations to prevent unnecessary re-renders
  // Derived liveness for the composer. Recomputed on a timer so a session that
  // dies while the user is typing stops claiming to be reachable.
  // Liveness only speaks for sessions that still claim to be usable. A closed
  // or archived session has no agent by design and already has its own
  // placeholder and disabled state — don't override either.
  const livenessNow = useNow();
  const chatLiveState = useSessionLiveness(instance);
  const chatSessionClosed = isClosedByDesign(instance?.status);
  const canResume = canResumeSession(instance, chatLiveState);
  const resumeBlocked = resumeBlockedReason(instance, chatLiveState);
  const [isResuming, setIsResuming] = useState(false);
  // A resumed session has a stale heartbeat until its relaunched agent beats
  // (up to ~30s), and liveness would keep the composer locked for that whole
  // window. Read from the shared registry rather than local state: Resume is
  // also triggered from the sidebar, where this page isn't mounted yet.
  // `livenessNow` ticks so the grace expires without needing another event.
  const withinResumeGrace = isWithinResumeGrace(instanceId, livenessNow);

  const handleResumeSession = useCallback(async () => {
    if (!instance || isResuming) return;
    setIsResuming(true);
    try {
      await resumeSession(instance);
      await fetchInstanceDetail();
    } catch (error) {
      setPermissionModeError(
        error instanceof Error ? error.message : 'Failed to resume session'
      );
    } finally {
      setIsResuming(false);
    }
  }, [instance, isResuming, fetchInstanceDetail]);
  const chatLiveStateHint =
    chatSessionClosed || withinResumeGrace ? null : liveStateHint(chatLiveState);
  const livenessBlocksSending =
    !chatSessionClosed && !withinResumeGrace && blocksSending(chatLiveState);

  const { requiresUserAction, canSendMessage } = useMemo(() => {
    if (!instance) {
      return {
        requiresUserAction: false,
        canSendMessage: false
      };
    }

    const lastMsg = instance.messages[instance.messages.length - 1];
    const requiresAction = lastMsg?.requires_user_input || false;
    const canSend = (requiresAction || instance.status === 'ACTIVE' || instance.status === 'AWAITING_INPUT' || instance.status === 'REVIEWED')
      && !['COMPLETED', 'FAILED', 'KILLED', 'DELETED'].includes(instance.status)
      // Nothing is listening: refuse input the same way an archived session
      // does, rather than accepting a message that will never be read.
      && !livenessBlocksSending;

    return {
      requiresUserAction: requiresAction,
      canSendMessage: canSend
    };
  }, [instance, livenessBlocksSending]);

  // Drives the composer's Send→Stop swap. `isAgentThinking` is the optimistic
  // local mirror — it flips true the instant a message is sent, so Stop shows
  // without waiting for the server's ACTIVE write; the status check covers a
  // turn that was already running when the page loaded.
  const agentIsWorking =
    isAgentThinking || instance?.status === 'ACTIVE' || instance?.status === 'STARTING';

  const allMessages = useMemo(() => {
    const messages = instance?.messages ?? [];
    // If both an optimistic and a real user message have the same content (race condition between
    // state commit and SSE delivery), hide the optimistic since the real one has arrived.
    // Attachment ids are part of the key so image-only messages (empty content)
    // only collide with their own echo, not with every other image-only send.
    const dedupeKey = (m: MessageResponse) =>
      `${m.content}\u0000${extractChatAttachments(m.message_metadata).map(a => a.id).join(',')}`;
    const realUserContents = new Set(
      messages
        .filter(m => !m.id.startsWith('optimistic-') && (m.sender_type === 'user' || m.sender_type === 'human' || m.sender_type === 'USER' || m.sender_type === 'HUMAN'))
        .map(dedupeKey)
    );
    return messages.filter(m =>
      !m.id.startsWith('optimistic-') || !realUserContents.has(dedupeKey(m))
    );
    // Depend on the messages array only — `instance` is a fresh reference on
    // every status/metadata patch, but reordering allMessages only matters when
    // the message list itself actually changes.
  }, [instance?.messages]);

  // FIFO self-heal for stuck `queued` rows. The queue is consumed in order, so
  // if a *later* user message is already `consumed`, every user message queued
  // *before* it was necessarily consumed too. `queueProgressAt` is the newest
  // such "known-drained" timestamp — used to recover messages left stuck at
  // `queued` when their consumed WS patch is dropped (a full refetch confirms
  // them, but the live `message-update` can be lost around a disconnect).
  //
  // Only `consumed` counts. A `none` (unqueued) message is NOT proof of drain:
  // when the agent pauses mid-turn on an AskUserQuestion it sits in
  // AWAITING_INPUT, and messages sent then — including the answer itself — are
  // unqueued while real queued messages still wait behind the paused turn.
  // Counting `none` there would wrongly evict a still-pending queued message.
  const queueProgressAt = useMemo(() => {
    let max: string | null = null;
    for (const m of allMessages) {
      if (!USER_SENDER_TYPES.has(m.sender_type)) continue;
      if (parseQueuePayload(m)?.status === 'consumed') {
        if (m.created_at && (max === null || m.created_at > max)) max = m.created_at;
      }
    }
    return max;
  }, [allMessages]);

  // True for a `queued` message the agent has demonstrably moved past — its
  // live status is stale and it belongs in the transcript, not the bar.
  const isDrainedQueued = useCallback(
    (m: MessageResponse) =>
      parseQueuePayload(m)?.status === 'queued' &&
      queueProgressAt !== null &&
      !!m.created_at &&
      m.created_at < queueProgressAt,
    [queueProgressAt],
  );

  // Queued (not-yet-sent) user messages are lifted out of the transcript and
  // shown in a stack attached to the top of the chat input, oldest → newest.
  // Any message sent mid-turn is stamped `queued`, including control/artifact
  // messages (permission-mode, model, thinking, "Submit AskUserQuestion
  // answers.", persist_only summaries). The agent swallows those without ever
  // consuming them, so they'd sit in the bar forever — they aren't real
  // pending input. Also drop rows the agent has already drained (stale
  // `queued`), the "Waiting for your input..." placeholder, and control tokens.
  const queuedItems = useMemo<QueuedMessageItem[]>(() => {
    return allMessages
      .filter((m) => {
        if (!USER_SENDER_TYPES.has(m.sender_type)) return false;
        if (parseQueuePayload(m)?.status !== 'queued') return false;
        if (isDrainedQueued(m)) return false;
        const raw = m.content || '';
        if (raw.trim() === 'Waiting for your input...') return false;
        // Drop only genuine control directives; a prose message that merely
        // quotes control JSON is real pending input (the agent now consumes it).
        if (isControlEnvelope(raw)) return false;
        return true;
      })
      .map((m) => {
        const { content } = extractMessageOptions(m.content);
        const text = formatTaskNotifications(stripPermissionModeCommandTokens(content) || content) || m.content;
        // Optimistic rows have no backend id yet, so cancel/retrieve can't reach
        // the server until the echo swaps in the real id — flagged so the row's
        // actions stay disabled for that sub-second round-trip.
        return { id: m.id, text, pending: m.id.startsWith('optimistic-') };
      });
  }, [allMessages, isDrainedQueued]);

  // The transcript hides messages still living in the queue: genuinely pending
  // `queued` ones (shown in the stack above) and `cancelled` ones (removing
  // from the queue means "unsend"). `consumed`/`none` fall through — as does a
  // stale `queued` row the agent already drained (see `isDrainedQueued`).
  const visibleMessages = useMemo(() => {
    return allMessages.filter((m) => {
      if (!USER_SENDER_TYPES.has(m.sender_type)) return true;
      const status = parseQueuePayload(m)?.status;
      if (status === 'cancelled') return false;
      // An interrupt is an action the user already took, not pending input.
      // It's stamped `queued` purely because it lands mid-turn, but it is
      // never surfaced in the queued-messages bar either (that drops every
      // control token), so honouring the stamp here hid the Stop entirely —
      // it only appeared once the *next* message drained the queue, reading
      // as though it had been sent then.
      if (isInterruptControlMessage(m.content || '')) return true;
      if (status === 'queued') return isDrainedQueued(m);
      return true;
    });
  }, [allMessages, isDrainedQueued]);

  // Backstop for the FIFO self-heal above (which needs a *later* consumed
  // message to recover a stuck row). When the agent settles after working
  // (ACTIVE/STARTING → awaiting/done) while messages are still showing as
  // `queued`, their `consumed` WS patch was likely lost. A full refetch
  // reconciles authoritative statuses: a row the agent actually consumed moves
  // into the transcript, while a genuinely-pending row (e.g. queued behind an
  // AskUserQuestion pause) stays `queued`. Only fires when the bar is non-empty,
  // so the common (patch-arrived) path never refetches.
  const prevStatusRef = useRef<string | null>(null);
  useEffect(() => {
    const status = instance?.status ?? null;
    const prev = prevStatusRef.current;
    prevStatusRef.current = status;
    if (!status) return;
    const wasWorking = prev === 'ACTIVE' || prev === 'STARTING';
    const settled =
      status === 'AWAITING_INPUT' ||
      status === 'COMPLETED' ||
      status === 'FAILED' ||
      status === 'REVIEWED';
    if (wasWorking && settled && queuedItems.length > 0) {
      fetchInstanceDetail();
    }
  }, [instance?.status, queuedItems.length, fetchInstanceDetail]);

  // Reorder consumed-queued messages to their consumption point (see
  // messageSortKey). Stable sort keeps everything else in created_at order, so
  // only a message the agent picked up mid-turn actually moves.
  const orderedVisibleMessages = useMemo(() => {
    return [...visibleMessages].sort((a, b) => {
      const ka = messageSortKey(a);
      const kb = messageSortKey(b);
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }, [visibleMessages]);

  // Memoize grouped messages to avoid re-grouping on every render
  const groupedMessages = useMemo(() => groupMessagesByDate(orderedVisibleMessages), [orderedVisibleMessages]);

  // Focus mode: the files/git panel covers the transcript as a full-width layer
  // between the header and composer (see the render below). Derived from the
  // shared panel state, so it's stable regardless of which session is on screen.
  const fileOverlay = panel.open && panel.maximized && !panel.isOverlay;
  // Peek reveals the chat beneath the file layer (sticky button or held key).
  const peeking = peekSticky || peekHold;

  // Flatten groups + thinking indicator into a single list of items for Virtuoso.
  // `key` is stable per item (separator uses date, messages use id) so Virtuoso
  // can correctly preserve scroll position when older history is prepended.
  const chatItems = useMemo<ChatItem[]>(() => {
    const itemsAgentType = resolveAgentType(instance?.agent_type_name || undefined);
    const items: ChatItem[] = [];
    for (const group of groupedMessages) {
      const filtered = group.messages.filter(
        (msg) => msg.content.trim() !== 'Waiting for your input...' && !shouldHideControlMessage(msg),
      );
      if (filtered.length === 0) continue;
      const firstId = filtered[0].id;
      items.push({ type: 'separator', date: group.date, key: `sep-${group.date}-${firstId}` });
      // Sub-agent (Task tool) child messages are bucketed by tool_use_id,
      // anchored at each group's first occurrence, BEFORE tool-run collapsing
      // runs below — so interleaved parallel sub-agents form separate groups
      // instead of their messages getting folded into the flat tool-group
      // stream. Non-subagent messages pass through untouched, in place.
      const subagentBucketed = groupSubagents(filtered);

      // Consecutive agent tool-use messages collapse into one 'tool-group'
      // item ("N tool uses"); a run of one renders as a single tool line.
      // The key is the run's first message id, so a run that grows while
      // streaming keeps its identity (and expansion state).
      let toolRun: MessageResponse[] = [];
      const flushToolRun = () => {
        if (toolRun.length === 0) return;
        items.push({ type: 'tool-group', messages: toolRun, key: `tools-${toolRun[0].id}` });
        toolRun = [];
      };
      for (const bucketed of subagentBucketed) {
        // A subagent-group is an opaque boundary for tool-run collapsing —
        // like an interactive message, it flushes whatever run preceded it
        // and is pushed as-is (its own children aren't re-collapsed here;
        // they render as full messages inside the group, per the brief).
        if (bucketed.type === 'subagent-group') {
          flushToolRun();
          items.push(bucketed);
          continue;
        }
        const msg = bucketed.message;
        // Interactive messages (AskUserQuestion, permission prompts) look like
        // tool uses but must render through MessageItem so their panels /
        // option buttons show — never fold them into a tool group.
        // Reasoning rows render as their own collapsed "Thinking" card via
        // MessageItem — never fold them into a tool-group (which would bypass
        // that card and render them as a tool line).
        const isInteractive =
          msg.requires_user_input ||
          parseAskUserQuestionPayload(msg) !== null ||
          parseThinkingPayload(msg) !== null;
        const isToolUse =
          !isInteractive &&
          !USER_SENDER_TYPES.has(msg.sender_type) &&
          parseToolUse(msg.content, itemsAgentType) !== null;
        if (isToolUse) {
          toolRun.push(msg);
        } else {
          flushToolRun();
          items.push({ type: 'message', message: msg, key: msg.id });
        }
      }
      flushToolRun();
    }
    if (showThinking && thinkingSettingEnabled !== false) {
      items.push({ type: 'thinking', key: 'thinking' });
    }
    return items;
  }, [groupedMessages, showThinking, thinkingSettingEnabled, instance?.agent_type_name]);

  // Whether the list has any real message rows. A lone "thinking" item doesn't
  // count — we render the SessionEmptyState (not the virtual list) until a real
  // message arrives, so the Virtuoso-tied overlays/buttons gate on this too.
  const hasMessageItems = chatItems.some(
    (it) => it.type === 'message' || it.type === 'tool-group' || it.type === 'subagent-group',
  );

  // Expanded tool rows/groups (and subagent-groups — same key-space, no
  // collision since their keys are prefixed distinctly: 'tools-'/message id
  // vs 'subagent-'), keyed by chat-item key. Held here rather than in the row
  // components because Virtuoso recycles offscreen rows.
  const [expandedToolItems, setExpandedToolItems] = useState<Set<string>>(new Set());
  const toggleToolItem = useCallback((key: string) => {
    setExpandedToolItems((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // --- Find in conversation -------------------------------------------------
  // Client-side find over the LOADED transcript. Native ⌘F / findInPage only
  // sees Virtuoso's rendered rows; this searches the in-memory message array
  // and uses scrollToIndex to reach off-screen hits. Matches are message-level
  // (one per matching text message) so they map 1:1 onto chatItems indices.
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState('');
  const [findActive, setFindActive] = useState(0);

  const findMatches = useMemo(() => {
    const needle = findQuery.trim().toLowerCase();
    if (!findOpen || !needle) return [] as number[];
    const hits: number[] = [];
    chatItems.forEach((item, index) => {
      if (item.type === 'message' && getMessageVisibleText(item.message).toLowerCase().includes(needle)) {
        hits.push(index);
      }
    });
    return hits;
  }, [chatItems, findQuery, findOpen]);

  // Chat-item key (== message id) of the focused match, for the active-row glow.
  const findActiveKey =
    findMatches.length > 0
      ? chatItems[findMatches[Math.min(findActive, findMatches.length - 1)]]?.key ?? null
      : null;

  const scrollToMatch = useCallback(
    (matchIndex: number) => {
      const target = findMatches[matchIndex];
      if (target === undefined) return;
      // Detach from the bottom BEFORE scrolling so the measurement-driven
      // atBottomStateChange doesn't yank us back down (it re-sticks only while
      // followBottomRef is still true).
      setFollowBottom(false);
      virtuosoRef.current?.scrollToIndex({ index: target, align: 'center', behavior: 'smooth' });
    },
    [findMatches, setFollowBottom],
  );

  const gotoRelativeMatch = useCallback(
    (delta: number) => {
      if (findMatches.length === 0) return;
      const next = (((findActive + delta) % findMatches.length) + findMatches.length) % findMatches.length;
      setFindActive(next);
      scrollToMatch(next);
    },
    [findMatches.length, findActive, scrollToMatch],
  );

  const openFind = useCallback(() => {
    const selection = typeof window !== 'undefined' ? window.getSelection?.()?.toString().trim() ?? '' : '';
    if (selection) setFindQuery(selection.slice(0, 200));
    setFindOpen(true);
  }, []);

  const closeFind = useCallback(() => setFindOpen(false), []);

  // Clamp the active index when the match set shrinks (query narrowed).
  useEffect(() => {
    if (findActive > 0 && findActive > findMatches.length - 1) {
      setFindActive(Math.max(0, findMatches.length - 1));
    }
  }, [findMatches.length, findActive]);

  // Incremental find: jump to the first match whenever the query TEXT changes
  // (guarded so streamed messages mutating findMatches don't re-trigger it).
  const prevFindQueryRef = useRef('');
  useEffect(() => {
    if (!findOpen) {
      prevFindQueryRef.current = '';
      return;
    }
    if (findQuery === prevFindQueryRef.current) return;
    prevFindQueryRef.current = findQuery;
    setFindActive(0);
    if (findMatches.length > 0) {
      setFollowBottom(false);
      virtuosoRef.current?.scrollToIndex({ index: findMatches[0], align: 'center' });
    }
  }, [findQuery, findOpen, findMatches, setFollowBottom]);

  // ⌘F / Ctrl+F opens the bar and preempts the browser's native find (which is
  // defeated by virtualization). Capture phase + preventDefault suppresses it.
  // The files panel owns ⌘F for its own surfaces (file body, git diff,
  // CodeMirror editors), so yield when it's the target: the maximized file
  // overlay is up, or focus sits inside the panel.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat) return;
      if (matchesShortcut(e, 'find-in-page')) {
        const inFilesPanel =
          fileOverlay ||
          !!(document.activeElement as HTMLElement | null)?.closest('[data-files-panel]');
        if (inFilesPanel) return;
        e.preventDefault();
        openFind();
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [openFind, fileOverlay]);

  // ⌘T / ⌘⇧T open a fresh terminal tab even when the panel is closed. While the
  // panel is open FilesGitPanel owns these shortcuts, but it unmounts when the
  // panel closes — so its window listener is gone. Cover that gap here: open the
  // panel and flag a one-shot intent the panel runs on mount (it spawns the tab
  // and clears any reopened file so the terminal shows). Desktop-only, matching
  // FilesGitPanel — ⌘T collides with the browser's own new-tab in plain web.
  useEffect(() => {
    if (getDesktopConfig() === null || isWindows) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || panel.open) return; // panel open → FilesGitPanel handles it
      if (!matchesShortcut(e, 'terminal-new') && !matchesShortcut(e, 'terminal-new-focused')) {
        return;
      }
      e.preventDefault();
      pendingPanelActionRef.current = 'new-terminal';
      panel.setOpen(true);
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [isWindows, panel.open, panel.setOpen]);

  // Open a file picked in the ⌘P finder: reveal the panel and hand it the path.
  // The bumped nonce makes the panel open it whether it was closed (opens on
  // mount) or already showing something else.
  const handleOpenSearchedFile = useCallback((path: string) => {
    panel.setOpen(true);
    setOpenFileRequest((prev) => ({ path, nonce: (prev?.nonce ?? 0) + 1 }));
  }, [panel]);

  // ⌘P opens the file finder. Session-scoped and gated on a reachable machine —
  // the finder reads the live project index off the daemon, and picking a file
  // opens it in the files panel (both need the box online). Capture phase +
  // preventDefault also suppresses the browser's native ⌘P print in-session.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || !matchesShortcut(e, 'open-file-search')) return;
      e.preventDefault();
      if (!instance?.machine_id || chatLiveState === 'machine_offline') return;
      setFileSearchOpen((v) => !v);
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [instance?.machine_id, chatLiveState]);

  // Shift+⌘A archives the session in view — the same action (and confirm
  // dialog) as the header's Archive control, so a stray keystroke can't discard
  // a session outright. No-op once it's already archived.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || !matchesShortcut(e, 'session-archive')) return;
      if (!instance || instance.status === 'COMPLETED') return;
      e.preventDefault();
      handleMarkSessionComplete(instanceId, instance.name || '');
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [instance, instanceId, handleMarkSessionComplete]);

  // Kill the window/document elastic bounce while the chat is open. The inner
  // scroller already sets overscroll-behavior:none, but Safari ignores that on
  // inner elements and bounces the window via scroll-chaining — so we also pin
  // it on <html>/<body>, scoped to this page (restored on unmount).
  useEffect(() => {
    const html = document.documentElement;
    const { body } = document;
    const prevHtml = html.style.overscrollBehavior;
    const prevBody = body.style.overscrollBehavior;
    html.style.overscrollBehavior = 'none';
    body.style.overscrollBehavior = 'none';
    return () => {
      html.style.overscrollBehavior = prevHtml;
      body.style.overscrollBehavior = prevBody;
    };
  }, []);

  useEffect(() => {
    // Cold session: this fetch fills the store before first paint (skeleton
    // meanwhile). Cached session: the store already painted synchronously and
    // this same fetch is the background revalidation (stale-while-revalidate).
    fetchInstanceDetail();
  }, [fetchInstanceDetail]);

  // Auto-focus chat input once per session. Depending on the whole `instance`
  // object would re-fire this effect on every WS-driven store write (i.e.
  // every streamed message), which cancels and re-arms the 100ms timer and
  // also steals focus while the user is typing.
  useEffect(() => {
    if (isLoading) return;
    const timer = setTimeout(() => {
      chatInputRef.current?.focus({ preventScroll: true });
    }, 100);
    return () => clearTimeout(timer);
  }, [isLoading, instanceId]);

  // Stabilization-based reveal: keep the overlay up until the list height has
  // gone N ms without changing. Virtuoso measures item heights lazily, and each
  // measurement resizes the scrollable area and bumps the scroll position to
  // keep the tail anchored — that's what produces the visible "scroll → render
  // → scroll" chunks. Waiting for height changes to stop is a tight signal for
  // "all the items in/around the viewport have been measured".
  const stabilizeTimerRef = useRef<NodeJS.Timeout | null>(null);
  const fallbackRevealTimerRef = useRef<NodeJS.Timeout | null>(null);
  const armStabilize = useCallback(() => {
    if (viewReadyRef.current) return;
    if (stabilizeTimerRef.current) clearTimeout(stabilizeTimerRef.current);
    stabilizeTimerRef.current = setTimeout(() => {
      stabilizeTimerRef.current = null;
      if (viewReadyRef.current) return;
      scheduleBottomAnchorSnaps(6);
      viewReadyRef.current = true;
      setIsViewReady(true);
    }, 220);
  }, [scheduleBottomAnchorSnaps]);

  // Virtuoso bumps total height once per item it (re)measures. The optimistic
  // row + thinking indicator measure asynchronously over several frames after a
  // send, and streamed markdown/code blocks keep resizing after they mount — so
  // a one-shot scroll on append drifts (see investigation log). Re-sticking on
  // every height change while following converges against the latest geometry;
  // it reads followBottomRef (never writes follow state) so a user scroll-up
  // that lands between two measurements still detaches cleanly.
  const handleListHeightChanged = useCallback(() => {
    armStabilize();
    if (followBottomRef.current) stickToBottomNow('auto');
  }, [armStabilize, stickToBottomNow]);

  useEffect(() => {
    // Gate on real messages: the virtual list only mounts once there's a
    // message row (until then SessionEmptyState renders), so arming earlier
    // would mark the view ready while Virtuoso is absent and skip the
    // first-paint holdback when the first message finally lands.
    if (!hasMessageItems || viewReadyRef.current) return;
    armStabilize();
  }, [chatItems.length, hasMessageItems, armStabilize]);

  useEffect(() => {
    setFollowBottom(true);
    lastScrollTopRef.current = 0;
    userScrollUpIntentRef.current = false;
    pointerScrollActiveRef.current = false;
    // Message identity/pagination state now lives in the store, keyed by
    // instanceId — nothing to reset here when switching sessions.
    // Re-hide the list while the new session's messages settle. We trigger a
    // first armStabilize() on mount so an instance with all items already
    // measured (e.g. a very short chat) still reveals without needing a height
    // change to fire. The fallback timer guarantees we reveal even if neither
    // signal lands (defensive — keeps a slow load from looking broken).
    if (stabilizeTimerRef.current) {
      clearTimeout(stabilizeTimerRef.current);
      stabilizeTimerRef.current = null;
    }
    if (fallbackRevealTimerRef.current) clearTimeout(fallbackRevealTimerRef.current);
    viewReadyRef.current = false;
    setIsViewReady(false);
    fallbackRevealTimerRef.current = setTimeout(() => {
      fallbackRevealTimerRef.current = null;
      if (viewReadyRef.current) return;
      scheduleBottomAnchorSnaps(6);
      viewReadyRef.current = true;
      setIsViewReady(true);
    }, 1000);
    return () => {
      if (fallbackRevealTimerRef.current) clearTimeout(fallbackRevealTimerRef.current);
    };
  }, [instanceId, scheduleBottomAnchorSnaps, setFollowBottom]);


  useEffect(() => {
    setInitialPermissionMode(null);
    setAcpModel(null);
    setAcpMode(null);
    // Read the new-session hint (kept, not consumed, so a refresh while still
    // empty stays consistent). Absent → null → idle "Session ready".
    try {
      const v = sessionStorage.getItem(`vicoa.session.${instanceId}.hasPrompt`);
      setInitialPromptHint(v === '1' ? true : v === '0' ? false : null);
    } catch {
      setInitialPromptHint(null);
    }
  }, [instanceId]);

  // Full backwards scan of every message — kept on a deliberately narrow dep
  // set so a streaming burst (instance.messages identity flips per WS frame)
  // doesn't re-walk N messages × 4 scans on every tick. `handleNewMessage`
  // already updates permission/agent/thinking incrementally for live arrivals;
  // this effect just covers (a) the initial REST load and (b) older messages
  // being prepended by `loadOlderMessages`, where the oldest id changes.
  const oldestMessageId = instance?.messages?.[0]?.id ?? null;
  useEffect(() => {
    if (!instance?.messages?.length) return;
    if (!initialPermissionMode) {
      const initialMode = findInitialPermissionMode(instance.messages);
      if (initialMode) {
        setInitialPermissionMode(initialMode);
      } else if (hasRemoteSessionStartMessage(instance.messages)) {
        setInitialPermissionMode('bypassPermissions');
      }
    }
    const latestMode = findLatestPermissionMode(instance.messages);
    if (latestMode) {
      setPermissionMode(prev => (prev === latestMode ? prev : latestMode));
      setPendingPermissionMode(prev => (prev === latestMode ? null : prev));
    }
    const latestThinking = findLatestThinkingSetting(instance.messages);
    if (latestThinking !== null) {
      setThinkingSettingEnabled(prev => (prev === latestThinking ? prev : latestThinking));
    }
    const latestAgentMode = findLatestAgentMode(instance.messages);
    if (latestAgentMode) {
      setOpencodeAgentMode(prev => (prev === latestAgentMode ? prev : latestAgentMode));
      setPendingOpencodeAgentMode(prev => (prev === latestAgentMode ? null : prev));
    }
    const latestModel = findLatestModel(instance.messages);
    if (latestModel) {
      setConfirmedModel(prev => (prev === latestModel ? prev : latestModel));
      setPendingModel(prev => (prev === latestModel ? null : prev));
    }
    const latestEffort = findLatestEffort(instance.messages);
    if (latestEffort) {
      setConfirmedEffort(prev => (prev === latestEffort ? prev : latestEffort));
      setPendingEffort(prev => (prev === latestEffort ? null : prev));
    }
    // `instance?.messages` is intentionally NOT a dep — see comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instance?.id, oldestMessageId, initialPermissionMode]);

  useEffect(() => {
    if (pendingPermissionTimer.current) {
      clearTimeout(pendingPermissionTimer.current);
      pendingPermissionTimer.current = null;
    }

    if (pendingPermissionMode) {
      const target = pendingPermissionMode;
      const label = getPermissionModeLabel(target);
      pendingPermissionTimer.current = setTimeout(() => {
        setPendingPermissionMode(prev => (prev === target ? null : prev));
        setPermissionModeError(`Couldn't change to ${label}. Please try again.`);
        setIsAgentThinking(false);
      }, 20000);
    }

    return () => {
      if (pendingPermissionTimer.current) {
        clearTimeout(pendingPermissionTimer.current);
        pendingPermissionTimer.current = null;
      }
    };
  }, [pendingPermissionMode]);

  useEffect(() => {
    if (!permissionModeError) {
      return;
    }

    const timeout = setTimeout(() => {
      setPermissionModeError(null);
    }, 6000);

    return () => clearTimeout(timeout);
  }, [permissionModeError]);

  // Switching sessions always drops any sticky peek.
  useEffect(() => {
    setPeekSticky(false);
  }, [instanceId]);
  useEffect(() => {
    if (!fileOverlay) setPeekSticky(false);
  }, [fileOverlay]);

  // Spring-loaded peek: hold the "Peek chat" shortcut (Settings → Keyboard
  // shortcuts, default `) to reveal the chat while held, release to snap back.
  // Only while focused, and ignored while typing so a bare-key binding never
  // eats a real keystroke. A window blur releases it (no stuck peek).
  useEffect(() => {
    if (!fileOverlay) return;
    const isTyping = (el: EventTarget | null) => {
      const node = el as HTMLElement | null;
      const tag = node?.tagName;
      return (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        node?.isContentEditable === true
      );
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || isTyping(e.target)) return;
      if (!matchesShortcut(e, 'peek-chat')) return;
      e.preventDefault();
      setPeekHold(true);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      // Release on the binding's main key (its modifiers may already be up).
      if (e.code === getShortcutCombo('peek-chat').code) setPeekHold(false);
    };
    const onBlur = () => setPeekHold(false);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    window.addEventListener('blur', onBlur);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
      setPeekHold(false);
    };
  }, [fileOverlay]);

  // Latching peek: the no-hold sibling of the gesture above (default ⌥`). Tap to
  // lock the chat visible beneath the file layer, tap again to snap back — the
  // same toggle the header's peek button drives. Only in focus mode, and
  // ignored while typing so the near-bare key never eats a real keystroke.
  useEffect(() => {
    if (!fileOverlay) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const node = e.target as HTMLElement | null;
      const tag = node?.tagName;
      const isTyping =
        tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || node?.isContentEditable === true;
      if (e.repeat || isTyping || !matchesShortcut(e, 'peek-chat-toggle')) return;
      e.preventDefault();
      setPeekSticky((v) => !v);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [fileOverlay]);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-4xl space-y-8 animate-pulse">
          {[...Array(5)].map((_, i) => {
            const isEven = i % 2 === 0;
            return (
              <div key={i} className={`flex items-start ${isEven ? '' : 'justify-end'}`}>
                <div className={`flex ${isEven ? 'max-w-[75%]' : 'max-w-[70%]'} flex-col gap-3 ${isEven ? '' : 'items-end'}`}>
                  <div className="h-4 w-64 rounded-full bg-muted" />
                  <div className="h-4 w-[20rem] rounded-full bg-muted/70" />
                  <div className="h-4 w-36 rounded-full bg-muted/50" />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Only a session with nothing to paint surfaces the error screen — when a
  // cached conversation is already on screen, a failed background revalidate
  // must not blank it (the cache stays valid; the next fetch clears `error`).
  if (!instance) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-600">Error: {error || 'Instance not found'}</div>
      </div>
    );
  }

  const isClaudeCodeAgent = (instance.agent_type_name || '').toLowerCase().includes('claude');

  // Determine agent type for slash commands
  const agentType = resolveAgentType(instance.agent_type_name || undefined);
  const isOpencodeAgent = agentType === 'opencode';
  const isCodexAgent = agentType === 'codex';

  // Absolute project root — lets tool-use file paths render relative to it.
  const projectRootPath = toAbsolutePath(instance.project, instance.home_dir);

  // Session config snapshot: prefer session_config from backend, fall back to live state.
  const sessionConfigSnapshot = extractSessionConfigFromInstance(instance);
  const canShowSessionConfig = isClaudeCodeAgent || isCodexAgent || isOpencodeAgent;

  const sessionCatalogAgent = agentById(AGENT_CATALOG_FALLBACK, agentType);
  const sessionModels = sessionCatalogAgent?.models?.map((m) => ({ id: m.id, label: m.label })) ?? undefined;
  // Both native agents advertise their machine's real models onto
  // session_config — codex from its `model/list` RPC (account/version
  // filtered), claude from the catalog merged with the machine's own slugs
  // (~/.claude/settings.json + ANTHROPIC_*_MODEL). Prefer that live list over
  // the static catalog so the gear shows what the installed agent actually
  // accepts. Falls back to the catalog before the daemon's first PATCH, or on
  // a CLI too old to report. Note the opt-in gates below still resolve against
  // the *static* catalog entry, so a machine-only slug correctly gets the
  // common set of efforts/permission modes and nothing model-specific.
  const nativeLive = (isClaudeCodeAgent || isCodexAgent) ? extractAcpControlsFromInstance(instance) : null;
  const nativeHasLiveModels = !!nativeLive && nativeLive.models.length > 0;
  const sessionEffortLabel = 'Effort';
  const sessionEfforts = (() => {
    const entries = isCodexAgent ? sessionCatalogAgent?.reasoning_efforts : sessionCatalogAgent?.thinking_efforts;
    if (!entries?.length) return undefined;
    if (isCodexAgent) return entries.map((e) => ({ id: e.id, label: e.label }));
    const activeModel = sessionCatalogAgent?.models?.find((m) => m.id === sessionConfigSnapshot.model);
    const optIns = new Set(activeModel?.thinking_efforts ?? []);
    return entries.filter((e) => !e.opt_in || optIns.has(e.id)).map((e) => ({ id: e.id, label: e.label }));
  })();

  const sessionPermissionModes = (() => {
    const modes = sessionCatalogAgent?.permission_modes;
    if (!modes?.length) return undefined;
    const activeModelId = confirmedModel ?? sessionConfigSnapshot.model;
    const activeModel = sessionCatalogAgent?.models?.find((m) => m.id === activeModelId);
    const optIns = new Set(activeModel?.permission_modes ?? []);
    const filtered = modes.filter((m) => !m.opt_in || optIns.has(m.id));
    // Claude only: bypassPermissions is sticky in the interactive CLI — its
    // Shift+Tab cycle can't reach YOLO unless the session launched in it — so
    // the TUI wrapper can't be switched into YOLO mid-session and the gear
    // hides it there. Headless (daemon-spawned) sessions set it through the
    // SDK's set_permission_mode, so they can switch in freely. A session
    // already running in YOLO always keeps the entry so the gear can label its
    // own current value.
    // Codex exposes bypassPermissions ("Full Access") unconditionally per catalog.
    if (agentType === 'claude') {
      const canUseBypass =
        isHeadlessSpawnedSession(instance) ||
        initialPermissionMode === 'bypassPermissions' ||
        permissionMode === 'bypassPermissions' ||
        sessionConfigSnapshot.permissionMode === 'bypassPermissions';
      return filtered
        .filter((m) => m.id !== 'bypassPermissions' || canUseBypass)
        .map((m) => ({ value: m.id, label: m.label }));
    }
    return filtered.map((m) => ({ value: m.id, label: m.label }));
  })();

  // OpenCode agent modes from catalog (build / plan).
  const sessionOpencodeModes = sessionCatalogAgent?.modes?.map((m) => ({ value: m.id, label: m.label }));

  // ACP agents (cursor / gemini / copilot / kimi / hermes …) aren't covered by
  // the big-3 gates above — web's resolveAgentType collapses them to "claude".
  // Source their gear from the live session_config the wrapper advertised, and
  // fall back to the *static catalog entry for the real agent id* when it isn't
  // there yet, so the gear shows immediately (these agents are all in the
  // catalog) instead of only after the wrapper's first session_config PATCH.
  const isAcpAgent = !isClaudeCodeAgent && !isCodexAgent && !isOpencodeAgent;
  const rawAgentId = (instance.agent_type_name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const acpLive = isAcpAgent ? extractAcpControlsFromInstance(instance) : null;
  const acpCatalogAgent = isAcpAgent ? agentById(AGENT_CATALOG_FALLBACK, rawAgentId) : undefined;
  const acpStaticModes = acpCatalogAgent?.permission_modes ?? acpCatalogAgent?.modes ?? [];
  const acpModels = (acpLive && acpLive.models.length > 0)
    ? acpLive.models
    : (acpCatalogAgent?.models?.map((m) => ({ id: m.id, label: m.label })) ?? []);
  const acpModes = (acpLive && acpLive.modes.length > 0)
    ? acpLive.modes
    : acpStaticModes.map((m) => ({ value: m.id, label: m.label }));
  const acpDefaultModel = acpCatalogAgent?.models?.find((m) => m.is_default)?.id ?? acpModels[0]?.id ?? null;
  const acpDefaultMode = acpStaticModes.find((m) => m.is_default)?.id ?? null;
  const acpHasControls = acpModels.length > 0 || acpModes.length > 0;

  // Gear shows for the catalog-driven big-3 and for ACP agents with controls;
  // SessionConfigDropdown self-hides when handed nothing.
  const showGear = canShowSessionConfig || acpHasControls;
  // Non-claude/codex agents (opencode + ACP) get the single-column scrollable
  // model list — their model lists can be long or have long ids.
  const singleColumnModels = !(isClaudeCodeAgent || isCodexAgent);

  // Resolved config-dropdown inputs. ACP agents apply changes optimistically
  // (handleAcp*) and show no pending spinner — their raw ids never echo back
  // through the claude/codex confirm path. Big-3 keep the echo-driven pending.
  const gearModels = canShowSessionConfig
    ? (nativeHasLiveModels ? nativeLive!.models : sessionModels)
    : (acpModels.length > 0 ? acpModels : undefined);
  const gearCurrentModel = canShowSessionConfig
    ? (confirmedModel ?? sessionConfigSnapshot.model ?? nativeLive?.currentModel ?? undefined)
    : (acpModel ?? acpLive?.currentModel ?? acpDefaultModel);
  const gearPendingModel = isAcpAgent ? null : pendingModel;
  const gearOnModelChange = isAcpAgent ? handleAcpModelChange : (canShowSessionConfig ? handleModelChange : undefined);

  const gearPermissionModes = canShowSessionConfig ? sessionPermissionModes : (acpModes.length > 0 ? acpModes : undefined);
  // Same fallback shape as gearCurrentModel: the message scan is authoritative
  // for live switches, but a session that never emitted a permission-mode
  // control message (every headless spawn — the mode rides session_config, not
  // the transcript) would otherwise render "—" instead of what it's running.
  const gearCurrentPermissionMode = ((isClaudeCodeAgent || isCodexAgent)
    ? (permissionMode ?? sessionConfigSnapshot.permissionMode)
    : (isAcpAgent ? (acpMode ?? acpLive?.currentMode ?? acpDefaultMode) : null)) as PermissionModeValue | null;
  const gearPendingPermissionMode = isAcpAgent ? null : ((isClaudeCodeAgent || isCodexAgent) ? pendingPermissionMode : null);
  const gearOnPermissionModeChange = isAcpAgent
    ? (acpModes.length > 0 ? (handleAcpModeChange as (mode: string) => void) : undefined)
    : ((isClaudeCodeAgent || isCodexAgent) ? handlePermissionModeSelect : undefined);

  // Drag-drop is offered only while the composer can actually take input; a
  // closed session shows no overlay and ignores drops.
  const dropEnabled = instance.status !== 'COMPLETED' && canSendMessage;
  const isFileDrag = (e: React.DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes('Files');
  const handleDropDragEnter = (e: React.DragEvent) => {
    if (!dropEnabled || !isFileDrag(e)) return;
    e.preventDefault();
    dragDepthRef.current += 1;
    setIsDropTarget(true);
  };
  const handleDropDragOver = (e: React.DragEvent) => {
    if (!dropEnabled || !isFileDrag(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };
  const handleDropDragLeave = (e: React.DragEvent) => {
    if (!dropEnabled || !isFileDrag(e)) return;
    dragDepthRef.current -= 1;
    if (dragDepthRef.current <= 0) {
      dragDepthRef.current = 0;
      setIsDropTarget(false);
    }
  };
  const handleDropFiles = (e: React.DragEvent) => {
    if (!dropEnabled || !isFileDrag(e)) return;
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDropTarget(false);
    // Snapshots the transfer synchronously, then resolves across awaits.
    void collectComposerDrop(e.dataTransfer).then(({ files, folderPaths }) => {
      if (folderPaths.length > 0) chatInputRef.current?.addFolderRefs(folderPaths);
      if (files.length > 0) chatInputRef.current?.addFiles(files);
    });
  };

  return (
    <div className="h-full flex">
      <div
        className="relative flex-1 min-w-0 flex flex-col h-full"
        onDragEnter={handleDropDragEnter}
        onDragOver={handleDropDragOver}
        onDragLeave={handleDropDragLeave}
        onDrop={handleDropFiles}
      >
        {isDropTarget && (
          <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-background/70 backdrop-blur-[1px]">
            <div className="flex flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-primary/60 bg-background/80 px-8 py-6 text-center shadow-lg">
              <FolderPlus className="h-7 w-7 text-primary" />
              <span className="text-sm font-medium text-foreground">Drop to attach</span>
            </div>
          </div>
        )}
      {/* Header with title and controls. On desktop the middle panel spans the
          full window height, so its header sits at the top edge — make it a
          drag region (harmless in the browser). Interactive children below opt
          back out with NO_DRAG so they stay clickable. */}
      <div style={DRAG_REGION} className="flex items-center justify-between pl-2 xl:pl-6 pr-2 py-2 flex-shrink-0">
        <TooltipProvider>
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {/* Collapsed desktop sidebar: keep the brand + expand control here so
                the chat title flows after it (instead of sliding to the far left
                under a floating overlay). */}
            {desktopChrome.isDesktop && desktopChrome.sidebarCollapsed && (
              <div style={DRAG_REGION} className="flex h-full shrink-0 items-center gap-1.5">
                <DesktopTitlebarLead />
                <span className="text-sm font-normal text-foreground">Vicoa</span>
                <button
                  type="button"
                  onClick={desktopChrome.expandSidebar}
                  style={NO_DRAG}
                  title="Expand sidebar"
                  aria-label="Expand sidebar"
                  className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <PanelLeft className="h-4 w-4" />
                </button>
              </div>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              style={NO_DRAG}
              className="xl:hidden h-8 w-8 flex-shrink-0"
              onClick={openSidebar}
              title="Open sidebar"
            >
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open sidebar</span>
            </Button>
            <AgentTypeIcon agentTypeName={instance.agent_type_name} size={14} whiteForOpenAI />
            {instance.pinned_at ? <Pin className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" /> : null}
            <h1 className="text-sm font-normal font-mono flex items-center gap-2 min-w-0 max-w-md">
              {(() => {
                // Helper function to extract last part of path
                const getLastPathPart = (path: string) => {
                  const cleanPath = path.replace(/\/+$/, ''); // Remove trailing slashes
                  const parts = cleanPath.split('/');
                  return parts[parts.length - 1] || path;
                };

                const agentTypeName = instance.agent_type_name || 'Code agent';
                let displayName = '';

                // If name exists, use it
                if (instance.name) {
                  displayName = instance.name;
                }
                // If project exists, use last part of the path
                else if (instance.project) {
                  displayName = getLastPathPart(instance.project);
                }
                // Otherwise just show agent type name
                else {
                  displayName = agentTypeName;
                }

                return (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="truncate cursor-default">{displayName}</span>
                    </TooltipTrigger>
                    <TooltipContent align="start">
                      <p>{displayName}</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })()}
            </h1>
            {instance.project && (
              <>
                <span className="text-muted-foreground flex-shrink-0">·</span>
                {/* Folder chip: basename only, full path in the tooltip. */}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="flex min-w-0 max-w-[16vw] cursor-default items-center gap-1 font-mono text-sm text-muted-foreground">
                      <Folder className="h-3.5 w-3.5 flex-shrink-0" />
                      <span className="truncate">
                        {instance.project.replace(/\/+$/, '').split('/').pop() || instance.project}
                      </span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent align="start">
                    <p>{instance.project}</p>
                  </TooltipContent>
                </Tooltip>
                <GitBranchBadge machineId={instance.machine_id ?? null} cwd={instance.project} />
                {/* Focus-mode peek toggle: sits right after the branch (or after
                    the project path when there's no branch, since the badge
                    renders nothing then). Only shown while focused; hold ` for a
                    momentary peek. */}
                {fileOverlay && (
                  <button
                    type="button"
                    style={NO_DRAG}
                    onClick={() => setPeekSticky((v) => !v)}
                    aria-label={peeking ? 'Back to file' : 'Peek chat'}
                    title={peeking ? 'Back to file' : 'Peek chat (hold ` for a quick look)'}
                    className={`ml-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded hover:bg-muted ${
                      peeking ? 'text-foreground' : 'text-muted-foreground'
                    }`}
                  >
                    {peeking ? <FileCode className="h-4 w-4" /> : <MessageCircle className="h-4 w-4" />}
                  </button>
                )}
              </>
            )}
          </div>
        </TooltipProvider>
        <div style={NO_DRAG} className="flex items-center gap-0.5">
          <FilesGitPanelToggle open={panel.open} onToggle={panel.toggleOpen} />
          <SessionActionsMenu
            onResume={() => void handleResumeSession()}
            showResume={canResume}
            resumeDisabledReason={
              isResuming
                ? 'Resuming…'
                : resumeBlocked
                  ? resumeBlockedMessage(resumeBlocked)
                  : null
            }
            resumeBlockedLabel={
              isResuming
                ? 'Resuming…'
                : resumeBlocked
                  ? resumeBlockedShortLabel(resumeBlocked)
                  : null
            }
            onPin={handleTogglePin}
            isPinned={!!instance.pinned_at}
            onRename={handleOpenRenameDialog}
            onCopyId={() => {
              void handleCopySessionId();
            }}
            copied={copiedSessionId === (instance?.id || instanceId)}
            onMarkDone={
              instance.status !== 'COMPLETED'
                ? () => {
                    const sessionName = instance.name || '';
                    handleMarkSessionComplete(instanceId, sessionName);
                  }
                : undefined
            }
            showMarkDone={instance.status !== 'COMPLETED'}
            onUnread={
              instance.status === 'REVIEWED'
                ? () => {
                    void handleMarkSessionUnread(instanceId);
                  }
                : undefined
            }
            showUnread={instance.status === 'REVIEWED'}
            onDelete={() => {
              const sessionName = instance.name || '';
              handleDeleteSession(instanceId, sessionName);
            }}
            className="h-8 w-8 p-0 hover:bg-muted"
            iconClassName="h-4 w-4"
            contentClassName="font-mono"
          />
          {/* The files/git panel takes the window's right edge only as the right
              rail; reserve here when it's closed OR maximized into the center
              overlay (which no longer sits at the top-right edge). */}
          {(!panel.open || fileOverlay) && <DesktopWindowControlsSpacer />}
        </div>
      </div>

      {/* Message Stats Row */}
      {/* <div className="px-6 py-3 bg-muted/30 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-6 text-sm text-muted-foreground">
          <div>
            <span className="font-medium">Total Messages: </span>
            {instance.messages.length}
          </div>
          <div>
            <span className="font-medium">User Messages: </span>
            {instance.messages.filter(m => 
              m.sender_type === 'user' || 
              m.sender_type === 'human' || 
              m.sender_type === 'USER' ||
              m.sender_type === 'HUMAN'
            ).length}
          </div>
          <div>
            <span className="font-medium">Agent Messages: </span>
            {instance.messages.filter(m => 
              !(m.sender_type === 'user' || 
                m.sender_type === 'human' || 
                m.sender_type === 'USER' ||
                m.sender_type === 'HUMAN')
            ).length}
          </div>
          <div>
            <span className="font-medium">Status: </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">
              <span className="w-2 h-2 rounded-full bg-muted-foreground mr-1.5" />
              {instance.status}
            </span>
          </div>
        </div>
      </div> */}

      {/* Messages Area - virtualized via react-virtuoso */}
      <FindHighlightProvider query={findOpen ? findQuery : ''} activeKey={findActiveKey}>
      <div className="relative flex-1 min-h-0">
        {!hasMessageItems ? (
          // No real messages yet (a lone "thinking" item doesn't count — it
          // would otherwise render as just the bare vibing text). A freshly
          // spawned / still-working session reads as active work; an idle or
          // closed session shows the static "Session ready" card.
          <SessionEmptyState
            // Only the prompt-started flow shows the active "Starting your
            // session" loader; a session with no prompt (or unknown origin,
            // e.g. CLI) shows the idle "Session ready / Waiting for your
            // message" card.
            loading={initialPromptHint === true}
            vibingMessage={vibingMessage}
          />
        ) : (
          <Virtuoso
            key={instanceId}
            ref={virtuosoRef}
            scrollerRef={handleScrollerRef}
            data={chatItems}
            // overscroll-none kills the rubber-band/bounce when scrolling past
            // the last message (contain only stops chaining, not the bounce).
            className="absolute inset-0 overscroll-none [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-corner]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full dark:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/20"
            // Object form with `align: 'end'` anchors the last item to the
            // bottom of the viewport on first paint — matches what a real chat
            // window looks like when you open it.
            initialTopMostItemIndex={{
              index: Math.max(0, chatItems.length - 1),
              align: 'end',
            }}
            // Rough average row height. Tightening Virtuoso's initial estimate
            // means the first scroll offset is much closer to the real bottom,
            // so the post-measurement reflow chunks are smaller and shorter.
            defaultItemHeight={120}
            alignToBottom
            // Follow on our own intent, not Virtuoso's geometric atBottom: while
            // we're sticking to the bottom, every append snaps down — even if a
            // mid-measurement reflow has Virtuoso momentarily thinking we're off
            // bottom. The scroller listeners flip the intent off the instant the
            // user scrolls up, so this never yanks them back down.
            followOutput={() => (followBottomRef.current ? 'auto' : false)}
            // Generous so normal message growth keeps Virtuoso reporting
            // "at bottom" and doesn't churn atBottomStateChange while following.
            atBottomThreshold={100}
            atTopStateChange={(atTop) => {
              // Virtuoso's measure-then-scroll loop on first paint briefly
              // parks scrollTop at 0 before settling at the bottom — without
              // this gate, loadOlderMessages fires there, prepends 200 rows,
              // and forces another full reflow. Defer until the first paint
              // has stabilized.
              if (!viewReadyRef.current) return;
              if (atTop && hasOlderMessages && !isLoadingOlderRef.current) {
                void loadOlderMessages();
              }
            }}
            atBottomStateChange={(atBottom) => {
              // Reaching the bottom always re-arms follow + hides the button.
              if (atBottom) {
                setFollowBottom(true);
              } else if (followBottomRef.current) {
                // Off the bottom while still following = involuntary drift (a
                // user scroll-up would already have flipped followBottomRef via
                // the scroller listeners). This is the trailing signal after the
                // measurement burst stops, so re-stick here or we'd stay parked
                // above the bottom with no button (the reported bug).
                stickToBottomNow('auto');
              } else {
                setIsNearBottom(false);
              }
            }}
            // Each item Virtuoso measures bumps total height — once those bumps
            // stop for ~160 ms we know the measure-and-adjust cycle has settled
            // and it's safe to reveal. armStabilize() resets the debounce on
            // every change, so a long burst of measurements still waits.
            totalListHeightChanged={handleListHeightChanged}
            // Keep a tall band of rows above the viewport MEASURED rather than
            // virtualized: when only the bottom rows are rendered, Virtuoso
            // estimates the rest at defaultItemHeight (120px, ~4x too tall for
            // short messages), so the total height — and thus the "bottom" we
            // stick to — swings by hundreds of px as rows toggle between
            // estimated and measured. That swing is what the stick was chasing
            // (the bounce). A large top band means small scrolls near the bottom
            // don't re-virtualize the active region, so the total stays stable
            // and the only height changes left are real per-message growth.
            increaseViewportBy={{ top: 3000, bottom: 1200 }}
            computeItemKey={(_, item) => item.key}
            itemContent={(_, item) => {
              if (item.type === 'separator') {
                return (
                  <div className="max-w-4xl mx-auto px-6">
                    <DateSeparator date={item.date} />
                  </div>
                );
              }
              if (item.type === 'thinking') {
                return (
                  <div className="max-w-4xl mx-auto px-6">
                    <ThinkingIndicator vibingMessage={vibingMessage} />
                  </div>
                );
              }
              if (item.type === 'tool-group') {
                return (
                  <div className="max-w-4xl mx-auto px-6">
                    <div className="flex justify-start mb-1">
                      <div className="rounded-xl px-4 py-0.5 flex-1 min-w-0 text-sm leading-relaxed font-mono">
                        <ToolUseGroup
                          messages={item.messages}
                          agentType={agentType}
                          expanded={expandedToolItems.has(item.key)}
                          onToggle={() => toggleToolItem(item.key)}
                          projectPath={projectRootPath}
                        />
                      </div>
                    </div>
                  </div>
                );
              }
              if (item.type === 'subagent-group') {
                return (
                  <div className="max-w-4xl mx-auto px-6">
                    <div className="flex justify-start mb-1">
                      <div className="rounded-xl px-4 py-0.5 flex-1 min-w-0 text-sm leading-relaxed font-mono">
                        <SubagentGroup
                          messages={item.messages}
                          subagentType={item.subagentType}
                          description={item.description}
                          expanded={expandedToolItems.has(item.key)}
                          onToggle={() => toggleToolItem(item.key)}
                          renderMessage={(message) => (
                            <MessageItem
                              message={message}
                              onOptionClick={handleOptionClick}
                              onAskUserQuestionSubmit={handleAskUserQuestionSubmit}
                              onAskUserQuestionCancel={handleAskUserQuestionCancel}
                              agentTypeName={instance.agent_type_name}
                              projectPath={projectRootPath}
                              compact
                            />
                          )}
                        />
                      </div>
                    </div>
                  </div>
                );
              }
              return (
                <div className="max-w-4xl mx-auto px-6">
                  <MessageItem
                    message={item.message}
                    onOptionClick={handleOptionClick}
                    onAskUserQuestionSubmit={handleAskUserQuestionSubmit}
                    onAskUserQuestionCancel={handleAskUserQuestionCancel}
                    agentTypeName={instance.agent_type_name}
                    projectPath={projectRootPath}
                  />
                </div>
              );
            }}
            components={{
              Header: () =>
                hasOlderMessages || isLoadingOlder ? (
                  <div className="flex items-center justify-center py-3 text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  </div>
                ) : (
                  <div className="h-6" />
                ),
              Footer: () => <div className="h-32" />,
            }}
          />
        )}

        {/* Holds back the paint until Virtuoso has measured and scrolled to the
           tail. Without this the list visibly seeks down through 3-4 reposition
           steps as item heights are discovered. */}
        {!isViewReady && hasMessageItems && (
          <div className="absolute inset-0 z-10 bg-background pointer-events-none" />
        )}

        {isViewReady && !isNearBottom && hasMessageItems && (
          <Button
            type="button"
            variant="secondary"
            size="icon"
            onClick={scrollToBottom}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 h-9 w-9 rounded-full border border-border/70 shadow-lg bg-background text-foreground"
            aria-label="Scroll to latest message"
          >
            <ArrowDown className="w-3 h-3" />
          </Button>
        )}

        {/* Find-in-conversation bar. Hidden while the file overlay is up, since
            that's a different search target. */}
        {findOpen && !fileOverlay && (
          <ChatFindBar
            query={findQuery}
            onQueryChange={setFindQuery}
            matchCount={findMatches.length}
            activeOrdinal={findMatches.length > 0 ? findActive + 1 : 0}
            onNext={() => gotoRelativeMatch(1)}
            onPrev={() => gotoRelativeMatch(-1)}
            onClose={closeFind}
          />
        )}

        {/* Maximized files/git panel: a full-width layer over the transcript,
            between the header and composer. The chat list above stays mounted
            (this only covers it), so exiting restores the exact scroll position.
            Peeking fades the layer out (and lets clicks through) to reveal the
            live chat beneath — momentary or sticky; the file layer never
            unmounts, so returning is instant and lossless. */}
        {fileOverlay && (
          <div
            className={`absolute inset-0 z-20 transition-opacity duration-150 ${
              peeking ? 'pointer-events-none opacity-0' : 'opacity-100'
            }`}
          >
            <FilesGitPanel
              machineId={instance?.machine_id ?? null}
              cwd={instance?.project ?? null}
              homeDir={instance?.home_dir ?? null}
              instanceId={instanceId}
              panel={panel}
              pendingAction={pendingPanelActionRef}
              openFileRequest={openFileRequest}
              overlay
              canMaximize
            />
          </div>
        )}
      </div>
      </FindHighlightProvider>

      {/* Git Changes Button */}
      {/* {instance.git_diff && (() => {
        const stats = getGitDiffStats(instance.git_diff);
        return (
          <div className="flex-shrink-0 border-border bg-muted/5">
            <div className="px-4 pt-4">
              <div className="max-w-4xl mx-auto">
                <div className="flex items-end gap-3 w-full">
                  <button
                    onClick={() => setShowGitDiffPanel(true)}
                    className="flex-1 flex items-center justify-between px-4 py-2.5 bg-background border border-border rounded-full hover:bg-muted/50 hover:border-muted-foreground/20 hover:shadow-md transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  >
                    <div className="flex items-center gap-3">
                      <GitBranch className="w-4 h-4 text-muted-foreground" />
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-foreground font-medium">{stats.files} file{stats.files !== 1 ? 's' : ''} changed</span>
                        {stats.additions > 0 && (
                          <span className="text-emerald-600 font-medium">+{stats.additions}</span>
                        )}
                        {stats.deletions > 0 && (
                          <span className="text-red-600 font-medium">-{stats.deletions}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <ChevronDown className="w-4 h-4 text-muted-foreground rotate-[-90deg]" />
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })()} */}

      {/* Fixed Chat Input at Bottom */}
      <div className="flex-shrink-0 bg-muted/10">
        <div className="p-4">
          <div className="max-w-4xl mx-auto">
            {instance.status !== 'COMPLETED' && permissionModeError && (
              <div
                role="alert"
                className="mb-4 flex items-start justify-between gap-3 rounded-xl border border-amber-200/70 bg-amber-50/80 px-4 py-2 text-xs text-amber-900 shadow-sm"
              >
                <div className="flex items-start gap-2">
                  <p className="leading-5">{permissionModeError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setPermissionModeError(null)}
                  className="flex items-center self-center text-amber-700 font-normal transition hover:text-amber-900"
                  aria-label="Dismiss permission mode error"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            {/* Suppressed when liveness is the reason input is refused — the
                composer placeholder already says so, more specifically. */}
            {instance.status !== 'COMPLETED' && !canSendMessage && instance.status !== 'STARTING' && !livenessBlocksSending && (
              <div className={`mb-2 text-xs ${instance.status === 'FAILED' ? 'text-red-600' : 'text-yellow-600'}`}>
                {instance.status === 'FAILED'
                  ? "This session failed to start. See the message above for the reason (most often the agent CLI isn't signed in on that machine)."
                  : instance.status === 'KILLED'
                  ? 'This session was stopped and is no longer accepting input.'
                  : 'Agent not accepting input in current status'}
              </div>
            )}
            {instance.status !== 'COMPLETED' && streamError && (
              <div className="mb-2 text-xs text-orange-600">
                Streaming connection error - messages will refresh manually
              </div>
            )}
            <ChatInput
              ref={chatInputRef}
              canSendMessage={canSendMessage}
              requiresUserAction={requiresUserAction}
              onSendMessage={sendMessage}
              isSending={isSending}
              permissionMode={gearCurrentPermissionMode}
              pendingPermissionMode={gearPendingPermissionMode}
              onPermissionModeChange={gearOnPermissionModeChange}
              sessionPermissionModes={gearPermissionModes}
              showControlSettings={showGear}
              thinkingEnabled={isClaudeCodeAgent ? thinkingSettingEnabled : null}
              onThinkingToggle={isClaudeCodeAgent ? handleThinkingToggle : undefined}
              onInterrupt={handleInterrupt}
              agentActive={agentIsWorking}
              instanceId={instanceId}
              agentType={agentType}
              agentLogoName={instance.agent_type_name}
              projectPath={toAbsolutePath(instance.project, instance.home_dir)}
              machineId={instance.machine_id ?? null}
              sessionOpencodeModes={isOpencodeAgent ? sessionOpencodeModes : undefined}
              opencodeAgentMode={isOpencodeAgent ? opencodeAgentMode : null}
              pendingOpencodeAgentMode={isOpencodeAgent ? pendingOpencodeAgentMode : null}
              onOpencodeAgentModeChange={isOpencodeAgent ? handleOpencodeAgentModeSelect : undefined}
              disabled={instance.status === 'COMPLETED'}
              placeholder={
                instance.status === 'COMPLETED'
                  ? 'Session closed. This chat is no longer available for new messages.'
                  : (chatLiveStateHint ?? undefined)
              }
              sessionModels={gearModels}
              currentModel={gearCurrentModel}
              pendingModel={gearPendingModel}
              onModelChange={gearOnModelChange}
              sessionEfforts={canShowSessionConfig ? sessionEfforts : undefined}
              sessionEffortLabel={sessionEffortLabel}
              currentEffort={confirmedEffort ?? sessionConfigSnapshot.effort}
              pendingEffort={pendingEffort}
              onEffortChange={canShowSessionConfig ? handleEffortChange : undefined}
              singleColumnModels={singleColumnModels}
              usage={instance.instance_metadata?.usage ?? null}
              queuedItems={queuedItems}
            />
          </div>
        </div>
      </div>


      </div>

      {/* Right rail. When maximized the panel renders as the center overlay
          above instead, so skip the rail to avoid a second instance. */}
      {panel.open && !fileOverlay && (
        <FilesGitPanel
          machineId={instance?.machine_id ?? null}
          cwd={instance?.project ?? null}
          homeDir={instance?.home_dir ?? null}
          instanceId={instanceId}
          panel={panel}
          pendingAction={pendingPanelActionRef}
          openFileRequest={openFileRequest}
          canMaximize
        />
      )}

      {/* Session Dialogs */}
      <RenameSessionDialog
        open={renameDialog.open}
        onOpenChange={(open) => setRenameDialog(prev => ({ ...prev, open }))}
        sessionId={renameDialog.sessionId}
        currentName={renameDialog.currentName}
        onRename={performRename}
      />

      <CompleteSessionDialog
        open={completeDialog.open}
        onOpenChange={(open) => setCompleteDialog(prev => ({ ...prev, open }))}
        sessionId={completeDialog.sessionId}
        sessionName={completeDialog.sessionName}
        onComplete={performComplete}
      />

      <DeleteSessionDialog
        open={deleteDialog.open}
        onOpenChange={(open) => setDeleteDialog(prev => ({ ...prev, open }))}
        sessionId={deleteDialog.sessionId}
        sessionName={deleteDialog.sessionName}
        onDelete={performDelete}
      />

      {/* ⌘P file finder (opened by the keydown effect above). */}
      <FileSearchPalette
        open={fileSearchOpen}
        onOpenChange={setFileSearchOpen}
        machineId={instance.machine_id ?? null}
        projectPath={projectRootPath}
        onOpenFile={handleOpenSearchedFile}
      />
    </div>
  );
}

export default function AgentInstancePage() {
  return <AgentInstanceContent />;
}
