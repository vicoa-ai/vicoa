'use client';

import { useState, useRef, useCallback, useEffect, useMemo, memo, forwardRef, useImperativeHandle } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, ArrowUp, Square, X, File as FileIcon } from 'lucide-react';
import { formatFileSize } from '@/components/chat-attachments';
import { useMessageDraft } from '@/lib/hooks/use-message-draft';
import { useSlashCommands } from '@/lib/hooks/use-slash-commands';
import { MentionTextarea } from '@/components/mention-textarea';
import type { SlashCommand, AgentType } from '@/lib/constants/slash-commands';
import { SessionConfigChips } from '@/components/dashboard/session-config-dropdown';
import { AddToChatMenu } from '@/components/dashboard/add-to-chat-menu';
import { ChatUsageIndicator } from '@/components/chat-usage-indicator';
import { fetchClaudeUsageWindows } from '@/lib/claude-usage';
import type { SessionUsage } from '@/lib/backend-api';
import { SlashCommandSuggestions } from '@/components/dashboard/slash-command-suggestions';
import { QueuedMessagesBar, type QueuedMessageItem } from '@/components/dashboard/queue-status';
import { applySlashCommandSelection, commandInsertText, detectSlashCommand, slashCommandMatches } from '@/lib/slash-command-utils';
import { shouldShowStopButton } from '@/lib/chat-composer';
import { getDesktopConfig } from '@/lib/runtime-config';
import { comboInline, getShortcutCombo, matchesShortcut } from '@/lib/desktop-shortcuts';
import { folderPathToMention } from '@/lib/chat-drop';
import { FolderRefChip } from '@/components/folder-ref-chip';
import { getDesktopShellBridge } from '@/lib/desktop-shell';

/** Imperative surface a parent drives via `ref` — focus, plus the drag-drop
 * entry points (the mid-panel owns the drop zone; the composer owns the
 * attachment + draft state the drop feeds). */
export interface ChatInputHandle {
  focus: (options?: FocusOptions) => void;
  /** Queue local files for upload (dropped files / a web-dropped folder's contents). */
  addFiles: (files: File[]) => void;
  /** Add desktop-dropped folders as `@path/` reference chips (absolute paths in). */
  addFolderRefs: (paths: string[]) => void;
}

/** Upload response from POST /api/attachments — doubles as the optimistic
 * message_metadata.attachments entry at send time. Non-image files carry no
 * width/height. */
export interface ChatUploadedAttachment {
  id: string;
  mime_type: string;
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  filename?: string | null;
}

/** One picked file: local preview immediately (thumbnail for images, a chip
 * for other files), server id once the eager upload completes. */
interface PendingUpload {
  key: string;
  previewUrl: string;
  file: File;
  isImage: boolean;
  uploading: boolean;
  failed: boolean;
  meta?: ChatUploadedAttachment;
}

/** Mirrors the backend's published cap (`MAX_ATTACHMENTS_PER_MESSAGE` in
 * `vicoa-backend/src/backend/models.py`); shared with the new-session prompt. */
export const MAX_ATTACHMENTS_PER_MESSAGE = 5;

/** Client-side size guard, matching the backend `MAX_UPLOAD_BYTES` (25MB). */
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

interface ChatInputProps {
  canSendMessage: boolean;
  requiresUserAction: boolean;
  onSendMessage: (message: string, attachments?: ChatUploadedAttachment[]) => void;
  isSending: boolean;
  permissionMode?: PermissionModeValue | null;
  pendingPermissionMode?: PermissionModeValue | null;
  onPermissionModeChange?: (mode: PermissionModeValue) => void;
  showControlSettings?: boolean;
  thinkingEnabled?: boolean | null;
  onThinkingToggle?: (enabled: boolean) => void;
  onInterrupt?: () => void;
  // True while a turn is running. Turns the send button into a Stop square
  // (as long as the composer is empty) so stopping is one tap on the control
  // the thumb is already on.
  agentActive?: boolean;
  instanceId?: string | null;
  agentType?: AgentType;
  // Raw agent id (e.g. 'kimi', 'cursor') for the config-chip logo. `agentType`
  // is narrowed to the big-3 for behavior gating, which collapses ACP agents to
  // the Claude logo; this keeps the chip showing the real agent's mark.
  agentLogoName?: string | null;
  projectPath?: string;
  // Machine the project lives on. Lets `@` mentions read the live daemon index
  // instead of the CLI-synced DB copy; null falls back to the DB.
  machineId?: string | null;
  sessionPermissionModes?: { value: string; label: string }[];
  sessionOpencodeModes?: { value: string; label: string }[];
  opencodeAgentMode?: OpencodeAgentModeValue | null;
  pendingOpencodeAgentMode?: OpencodeAgentModeValue | null;
  onOpencodeAgentModeChange?: (mode: OpencodeAgentModeValue) => void;
  placeholder?: string;
  disabled?: boolean;
  // Model (all agents)
  sessionModels?: { id: string; label: string }[];
  currentModel?: string | null;
  pendingModel?: string | null;
  onModelChange?: (id: string) => void;
  // Effort: "Thinking" for claude, "Reasoning" for codex
  sessionEfforts?: { id: string; label: string }[];
  sessionEffortLabel?: string;
  currentEffort?: string | null;
  pendingEffort?: string | null;
  onEffortChange?: (id: string) => void;
  // Render the gear's model list as a single scrollable column (non-claude/
  // codex agents, whose model lists can be long or many).
  singleColumnModels?: boolean;
  // Live context-window + rate-limit usage (Claude + Codex). Shown as a small
  // ring + popover next to the config chips; omit/null hides it.
  usage?: SessionUsage | null;
  // Not-yet-sent messages the agent will consume in order, oldest → newest.
  // Rendered as a stack attached to the top of the input; empty hides it.
  queuedItems?: QueuedMessageItem[];
}

export type PermissionModeValue = 'default' | 'plan' | 'acceptEdits' | 'bypassPermissions' | 'auto';
export type OpencodeAgentModeValue = 'build' | 'plan';

// Permission modes
const permissionModes: { value: PermissionModeValue; label: string }[] = [
  { value: 'default', label: 'Default' },
  { value: 'plan', label: 'Plan mode' },
  { value: 'auto', label: 'Auto mode' },
  { value: 'acceptEdits', label: 'Accept edits' },
  { value: 'bypassPermissions', label: 'YOLO' },
];

const opencodeAgentModes: { value: OpencodeAgentModeValue; label: string }[] = [
  { value: 'build', label: 'Build' },
  { value: 'plan', label: 'Plan' },
];

export const ChatInput = memo(forwardRef<ChatInputHandle, ChatInputProps>(function ChatInput({
  canSendMessage,
  requiresUserAction,
  onSendMessage,
  isSending,
  permissionMode,
  pendingPermissionMode,
  onPermissionModeChange,
  showControlSettings = true,
  thinkingEnabled = null,
  onThinkingToggle,
  onInterrupt,
  agentActive = false,
  instanceId = null,
  agentType = 'claude',
  agentLogoName,
  projectPath,
  machineId = null,
  sessionPermissionModes,
  sessionOpencodeModes,
  opencodeAgentMode,
  pendingOpencodeAgentMode,
  onOpencodeAgentModeChange,
  placeholder = 'Type messages, @files, /skills or commands',
  disabled = false,
  sessionModels,
  currentModel,
  pendingModel,
  onModelChange,
  sessionEfforts,
  sessionEffortLabel,
  currentEffort,
  pendingEffort,
  onEffortChange,
  singleColumnModels = false,
  usage = null,
  queuedItems = [],
}: ChatInputProps, ref) {
  const { draft: message, setDraft: setMessage, clearDraft } = useMessageDraft({
    instanceId,
    debounceMs: 500,
    onError: (error) => console.error('Message draft storage error:', error),
  });

  // Fetch slash commands + skills (defaults + the machine's installed set,
  // live from the daemon when available, else the CLI-synced DB copy).
  const { commands: slashCommands } = useSlashCommands({ agentType, machineId, projectPath });

  const [isMultiline, setIsMultiline] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isOpencodeAgent = agentType === 'opencode';
  // Claude and Codex both surface skills (Claude via ~/.claude/skills, Codex
  // via ~/.agents & ~/.codex/skills) alongside commands through the slash
  // trigger. Drives the Add-to-chat menu's label.
  const hasSkills = agentType === 'claude' || agentType === 'opencode' || agentType === 'codex';
  // Live rate-limit refresh is Claude-only: the daemon reads the Claude Code
  // OAuth credential. Codex windows arrive in-band from its app-server stream.
  const usageFetchLimits = useMemo(() => {
    if (agentType !== 'claude' || !machineId) return undefined;
    return () => fetchClaudeUsageWindows(machineId);
  }, [agentType, machineId]);
  // Bumped by the Add-to-chat "+" menu's "Mention files" action to make the
  // MentionTextarea insert "@" and open the file panel.
  const [mentionSignal, setMentionSignal] = useState(0);

  // Image attachments for the next message — eagerly uploaded on pick so the
  // ids are ready at send time. Previews are object URLs of the picked files.
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const pendingUploadsRef = useRef<PendingUpload[]>([]);
  pendingUploadsRef.current = pendingUploads;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasUploadedAttachments = pendingUploads.some(u => u.meta);
  const hasUploadingAttachments = pendingUploads.some(u => u.uploading);

  // Pending folder references (absolute paths) shown as chips — desktop "Add
  // folder" + desktop folder-drops. Not attachments: they carry no bytes and
  // are expanded to `@path/` text at send time. Deduped by path.
  const [pendingFolderRefs, setPendingFolderRefs] = useState<string[]>([]);
  const pendingFolderRefsRef = useRef<string[]>([]);
  pendingFolderRefsRef.current = pendingFolderRefs;

  // Anything the user could send right now — text, a finished upload, or a folder.
  const hasComposerContent =
    !!message.trim() || hasUploadedAttachments || pendingFolderRefs.length > 0;
  const showStopButton = shouldShowStopButton({
    canInterrupt: !!onInterrupt,
    agentActive,
    hasComposerContent,
    disabled,
  });

  // Revoke any leftover preview object URLs on unmount.
  useEffect(() => () => {
    pendingUploadsRef.current.forEach(u => URL.revokeObjectURL(u.previewUrl));
  }, []);

  // Transient, self-clearing notice for rejected picks (too large / too many).
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const attachmentErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flashAttachmentError = useCallback((msg: string) => {
    setAttachmentError(msg);
    if (attachmentErrorTimer.current) clearTimeout(attachmentErrorTimer.current);
    attachmentErrorTimer.current = setTimeout(() => setAttachmentError(null), 5000);
  }, []);
  useEffect(() => () => {
    if (attachmentErrorTimer.current) clearTimeout(attachmentErrorTimer.current);
  }, []);

  const uploadAttachment = useCallback(async (key: string, file: File) => {
    if (!instanceId) return;
    setPendingUploads(prev => prev.map(u =>
      u.key === key ? { ...u, uploading: true, failed: false } : u
    ));
    try {
      const formData = new FormData();
      formData.append('agent_instance_id', instanceId);
      formData.append('file', file);
      const response = await fetch('/api/attachments', { method: 'POST', body: formData });
      if (!response.ok) throw new Error(`upload failed (${response.status})`);
      const meta = (await response.json()) as ChatUploadedAttachment;
      setPendingUploads(prev => prev.map(u =>
        u.key === key ? { ...u, uploading: false, meta } : u
      ));
    } catch (error) {
      console.error('Attachment upload failed:', error);
      setPendingUploads(prev => prev.map(u =>
        u.key === key ? { ...u, uploading: false, failed: true } : u
      ));
    }
  }, [instanceId]);

  const focusTextarea = useCallback(() => {
    textareaRef.current?.focus({ preventScroll: true });
  }, []);

  // Shared by the file picker and drag-drop: apply the count + size caps, then
  // eagerly upload each accepted file. Rejected picks flash the reason.
  const addFilesToPending = useCallback((picked: File[]) => {
    if (picked.length === 0) return;
    const room = MAX_ATTACHMENTS_PER_MESSAGE - pendingUploadsRef.current.length;
    if (room <= 0) {
      flashAttachmentError(`You can attach up to ${MAX_ATTACHMENTS_PER_MESSAGE} files per message.`);
      return;
    }
    const withinSize = picked.filter(file => file.size <= MAX_ATTACHMENT_BYTES);
    const selected = withinSize.slice(0, room);
    if (withinSize.length < picked.length) {
      flashAttachmentError(`Files over ${MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB were skipped.`);
    } else if (selected.length < picked.length) {
      flashAttachmentError(`Only ${MAX_ATTACHMENTS_PER_MESSAGE} files can be attached per message.`);
    }
    for (const file of selected) {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setPendingUploads(prev => [...prev, {
        key,
        file,
        previewUrl: URL.createObjectURL(file),
        isImage: file.type.startsWith('image/'),
        uploading: false,
        failed: false,
      }]);
      void uploadAttachment(key, file);
    }
  }, [uploadAttachment, flashAttachmentError]);

  const handleFilesSelected = useCallback((files: FileList | null) => {
    if (files) addFilesToPending(Array.from(files));
    // Allow re-picking the same file later.
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [addFilesToPending]);

  // "Add folder" / desktop folder-drop: add the folder(s) as chips (deduped by
  // absolute path). They become `@path/` text in `handleSendMessage`.
  const addFolderRefs = useCallback((absPaths: string[]) => {
    if (absPaths.length === 0) return;
    setPendingFolderRefs((prev) => {
      const next = [...prev];
      for (const p of absPaths) if (!next.includes(p)) next.push(p);
      return next;
    });
    requestAnimationFrame(() => focusTextarea());
  }, [focusTextarea]);

  const removeFolderRef = useCallback((path: string) => {
    setPendingFolderRefs((prev) => prev.filter((p) => p !== path));
  }, []);

  const removeUpload = useCallback((key: string) => {
    setPendingUploads(prev => {
      const target = prev.find(u => u.key === key);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter(u => u.key !== key);
    });
  }, []);

  // Slash command state
  const [showSlashCommands, setShowSlashCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);
  const [totalMatchCount, setTotalMatchCount] = useState(0);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const commandListRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // Caret at which the slash menu is anchored (the "/word" the query came from),
  // captured on the last change so selection can replace the right word even if
  // the textarea lost focus (a click on a suggestion blurs it). A live
  // `selectionStart` is preferred when the field is still focused.
  const slashCaretRef = useRef(0);
  const currentCaret = useCallback(
    () => textareaRef.current?.selectionStart ?? slashCaretRef.current,
    [],
  );

  // Imperative surface for parents (drag-drop feeds the composer through this).
  useImperativeHandle(ref, () => ({
    focus: (options?: FocusOptions) =>
      textareaRef.current?.focus(options ?? { preventScroll: true }),
    addFiles: (files: File[]) => addFilesToPending(files),
    addFolderRefs: (paths: string[]) => addFolderRefs(paths),
  }), [addFilesToPending, addFolderRefs]);

  // Coalesce auto-resize work into the next animation frame. Reading
  // `scrollHeight` after writing `height='auto'` forces a synchronous layout
  // flush, and on a page with many DOM nodes (long message list) that flush
  // dominates per-keystroke cost. Throttling to rAF keeps perceived height
  // updates instant while collapsing fast bursts into one reflow per frame.
  const autoResizeFrameRef = useRef<number | null>(null);
  const autoResizeTextarea = useCallback(() => {
    if (autoResizeFrameRef.current !== null) return;
    autoResizeFrameRef.current = requestAnimationFrame(() => {
      autoResizeFrameRef.current = null;
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.style.height = 'auto';
      const newHeight = Math.max(44, Math.min(textarea.scrollHeight, 128));
      textarea.style.height = newHeight + 'px';
      setIsMultiline(newHeight > 44);
    });
  }, []);

  useEffect(() => () => {
    if (autoResizeFrameRef.current !== null) {
      cancelAnimationFrame(autoResizeFrameRef.current);
      autoResizeFrameRef.current = null;
    }
  }, []);

  // ⌘L focuses the chat input (desktop only; rebindable in Settings →
  // Keyboard shortcuts). Capture phase so a focused terminal can't eat it.
  // `showFocusHint` gates the placeholder-side hint to desktop, set
  // post-mount so the SSR pass stays consistent.
  const [showFocusHint, setShowFocusHint] = useState(false);
  useEffect(() => {
    if (getDesktopConfig() === null) return;
    setShowFocusHint(true);
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'focus-chat')) return;
      event.preventDefault();
      textareaRef.current?.focus();
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, []);

  const handleMessageChange = useCallback((value: string) => {
    setMessage(value);
    autoResizeTextarea();

    // Slash-command menu: caret-aware so it also fires when a "/command" word is
    // typed mid-draft, and filters by that word alone (not the whole remainder),
    // so an existing draft or a typed argument no longer suppresses it.
    const caret = textareaRef.current?.selectionStart ?? value.length;
    const { active, query } = detectSlashCommand(value, caret);
    if (active) {
      slashCaretRef.current = caret;
      const allMatches = slashCommands.filter(cmd => slashCommandMatches(cmd, query));
      setTotalMatchCount(allMatches.length);
      setFilteredCommands(allMatches);
      setShowSlashCommands(allMatches.length > 0);
      setSelectedCommandIndex(0);
    } else {
      setShowSlashCommands(false);
      setTotalMatchCount(0);
    }
  }, [autoResizeTextarea, setMessage, slashCommands]);

  const handleMentionOpenChange = useCallback((open: boolean) => {
    if (open) setShowSlashCommands(false);
  }, []);

  // Add-to-chat "+" → "Mention files": let MentionTextarea insert "@" and open
  // the file panel. Hide the slash panel first so the two never overlap.
  const handleInsertMention = useCallback(() => {
    setShowSlashCommands(false);
    setMentionSignal((n) => n + 1);
  }, []);

  // Add-to-chat "+" → "Add folder": desktop only. Opens the native OS folder
  // picker and inserts the chosen folder as an @path/ reference (project-
  // relative when inside the project) — no upload. Hidden on web, where the
  // browser can't hand a real filesystem path to the page.
  const handleInsertFolder = useCallback(() => {
    const bridge = getDesktopShellBridge();
    if (!bridge) return;
    setShowSlashCommands(false);
    void bridge.pickFolder().then((path) => {
      if (path) addFolderRefs([path]);
    });
  }, [addFolderRefs]);

  // Add-to-chat "+" → "Skills or Commands": insert "/" and surface the full
  // command list (mirrors the mobile sheet). Empty draft → "/"; an existing
  // draft is preserved after a separating space, with the cursor parked right
  // after the "/" so the next keystroke filters by command name.
  const handleInsertSlash = useCallback(() => {
    const existing = message;
    const next = existing.trim().length === 0 ? '/' : `/ ${existing}`;
    setMessage(next);
    setFilteredCommands(slashCommands);
    setTotalMatchCount(slashCommands.length);
    setShowSlashCommands(slashCommands.length > 0);
    setSelectedCommandIndex(0);
    // Caret parks right after the "/" (before any preserved draft), so the next
    // keystroke filters the command word — matching where the menu is anchored.
    slashCaretRef.current = 1;
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el) {
        el.focus({ preventScroll: true });
        el.setSelectionRange(1, 1);
      }
    });
  }, [message, slashCommands, setMessage]);

  const handleSendMessage = useCallback(() => {
    const trimmed = message.trim();
    const readyAttachments = pendingUploadsRef.current.filter(u => u.meta);
    const folderRefs = pendingFolderRefsRef.current;
    // Text, an uploaded image, or a folder reference; never mid-upload (the
    // pending id would be silently dropped from the message).
    if ((!trimmed && readyAttachments.length === 0 && folderRefs.length === 0) ||
        pendingUploadsRef.current.some(u => u.uploading)) {
      return;
    }
    // Folder chips expand to `@path/` text, appended after the typed message.
    const folderText = folderRefs
      .map((p) => `@${folderPathToMention(p, projectPath)}`)
      .join(' ');
    const outgoing = [trimmed, folderText].filter(Boolean).join(' ');
    onSendMessage(outgoing, readyAttachments.map(u => u.meta!));
    readyAttachments.forEach(u => URL.revokeObjectURL(u.previewUrl));
    // Failed picks stay in the strip for retry/removal.
    setPendingUploads(prev => prev.filter(u => !u.meta));
    setPendingFolderRefs([]);
    clearDraft();
    // Reset textarea height and refocus
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px';
      setIsMultiline(false);
    }
    // Use requestAnimationFrame to ensure focus happens after all DOM updates
    requestAnimationFrame(() => {
      focusTextarea();
    });
  }, [message, projectPath, onSendMessage, clearDraft, focusTextarea]);

  // Add-to-chat "+" → "Add files": open the system file picker. Deferred a
  // frame so the dropdown closes before the (focus-stealing) dialog opens.
  const handleAddFiles = useCallback(() => {
    requestAnimationFrame(() => fileInputRef.current?.click());
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle slash command navigation
    if (showSlashCommands) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedCommandIndex(prev =>
          prev < filteredCommands.length - 1 ? prev + 1 : 0
        );
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedCommandIndex(prev => (prev > 0 ? prev - 1 : filteredCommands.length - 1));
        return;
      }
      if (e.key === 'Tab') {
        // Tab inserts the command in place of the leading "/…" token, keeping
        // any draft that followed it, and parks the caret after the command.
        e.preventDefault();
        const cmd = filteredCommands[selectedCommandIndex];
        if (cmd) {
          const { value: next, cursor } = applySlashCommandSelection(message, commandInsertText(cmd), currentCaret());
          setMessage(next);
          setShowSlashCommands(false);
          requestAnimationFrame(() => {
            const el = textareaRef.current;
            if (el) { el.focus({ preventScroll: true }); el.setSelectionRange(cursor, cursor); }
          });
        }
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        // Enter sends the selected command immediately — together with any
        // preserved draft so content is never dropped.
        e.preventDefault();
        const cmd = filteredCommands[selectedCommandIndex];
        if (cmd) {
          const toSend = applySlashCommandSelection(message, commandInsertText(cmd), currentCaret()).value.trim();
          onSendMessage(toSend);
          clearDraft();
          setShowSlashCommands(false);
          // Reset textarea height
          if (textareaRef.current) {
            textareaRef.current.style.height = '44px';
            setIsMultiline(false);
          }
        }
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlashCommands(false);
        return;
      }
    }

    // Esc just drops focus out of the composer — it never stops the running
    // turn (that's the Stop button's job). Blurring makes the page-level
    // shortcuts (peek chat, file search, archive…) — which ignore keys while a
    // text field is focused — reachable without reaching for the mouse. (The
    // slash and mention dropdowns claim Esc first, above and inside
    // MentionTextarea respectively.)
    if (e.key === 'Escape') {
      e.preventDefault();
      textareaRef.current?.blur();
      return;
    }

    // Regular enter to send (mention dropdown's Enter is handled inside MentionTextarea)
    if (e.key === 'Enter' && !e.shiftKey && !showSlashCommands) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage, showSlashCommands, filteredCommands, selectedCommandIndex, onSendMessage, clearDraft, message, setMessage, currentCaret]);

  useEffect(() => {
    autoResizeTextarea();
  }, [message, autoResizeTextarea]);

  // Scroll selected command into view on keyboard navigation
  useEffect(() => {
    if (showSlashCommands && commandListRef.current) {
      const selectedElement = commandListRef.current.children[selectedCommandIndex] as HTMLElement;
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedCommandIndex, showSlashCommands]);

  // Document-level Escape key handler to close slash dropdown
  useEffect(() => {
    if (!showSlashCommands) return;
    const handleEscapeKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSlashCommands(false);
      }
    };
    document.addEventListener('keydown', handleEscapeKey);
    return () => document.removeEventListener('keydown', handleEscapeKey);
  }, [showSlashCommands]);

  // Click-outside handler to close slash dropdown
  useEffect(() => {
    if (!showSlashCommands) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSlashCommands(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSlashCommands]);

  // When messages are queued they render as a stack glued to the top of the
  // input; the input then squares its top corners so the two read as one piece.
  const showQueued = !!instanceId && queuedItems.length > 0;

  return (
    <div className="w-full">
      {showQueued && (
        <QueuedMessagesBar
          instanceId={instanceId}
          items={queuedItems}
          onRetrieve={(text) => {
            // Drop the queued text back into the composer (append below any
            // in-progress draft so it's never clobbered), then focus so the
            // user can edit and re-send.
            setMessage(message ? `${message}\n${text}` : text);
            focusTextarea();
          }}
        />
      )}
      <div
        ref={containerRef}
        className="w-full bg-[#2D2D2D] rounded-3xl px-4 py-3 relative font-mono"
      >
      {/* Slash command suggestions */}
      {showSlashCommands && (
        <SlashCommandSuggestions
          commands={filteredCommands}
          selectedIndex={selectedCommandIndex}
          listRef={commandListRef}
          onSelect={(cmd) => {
            const { value: next, cursor } = applySlashCommandSelection(message, commandInsertText(cmd), currentCaret());
            setMessage(next);
            setShowSlashCommands(false);
            requestAnimationFrame(() => {
              const el = textareaRef.current;
              if (el) { el.focus({ preventScroll: true }); el.setSelectionRange(cursor, cursor); }
            });
          }}
          onHover={setSelectedCommandIndex}
        />
      )}

      {/* Rejected-pick notice (too large / too many) */}
      {attachmentError && (
        <div className="mb-2 text-[11px] text-destructive">{attachmentError}</div>
      )}

      {/* Pending attachments (uploads) + folder references (path chips) */}
      {(pendingUploads.length > 0 || pendingFolderRefs.length > 0) && (
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          {pendingFolderRefs.map((path) => (
            <FolderRefChip key={path} path={path} onRemove={() => removeFolderRef(path)} />
          ))}
          {pendingUploads.map((upload) => (
            <div key={upload.key} className="relative">
              <button
                type="button"
                onClick={upload.failed ? () => uploadAttachment(upload.key, upload.file) : undefined}
                className={`block rounded-lg overflow-hidden ${upload.failed ? 'cursor-pointer' : 'cursor-default'}`}
                title={upload.failed ? 'Upload failed — click to retry' : upload.file.name}
              >
                {upload.isImage ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={upload.previewUrl}
                      alt={upload.file.name}
                      className={`w-14 h-14 object-cover ${upload.failed ? 'opacity-40' : ''}`}
                    />
                    {(upload.uploading || upload.failed) && (
                      <span className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg">
                        <RefreshCw className={`w-4 h-4 text-white ${upload.uploading ? 'animate-spin' : ''}`} />
                      </span>
                    )}
                  </>
                ) : (
                  <span
                    className={`flex items-center gap-2 h-14 w-40 px-3 rounded-lg border border-border bg-muted-foreground/5 ${upload.failed ? 'opacity-60' : ''}`}
                  >
                    <RefreshCw
                      className={`w-4 h-4 flex-shrink-0 text-muted-foreground ${upload.uploading ? 'animate-spin' : ''} ${!upload.uploading && !upload.failed ? 'hidden' : ''}`}
                    />
                    {!upload.uploading && !upload.failed && (
                      <FileIcon className="w-4 h-4 flex-shrink-0 text-muted-foreground" />
                    )}
                    <span className="flex min-w-0 flex-col text-left">
                      <span className="truncate text-[11px] font-medium">{upload.file.name}</span>
                      <span className="text-[10px] text-muted-foreground">{formatFileSize(upload.file.size)}</span>
                    </span>
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => removeUpload(upload.key)}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-background border border-border flex items-center justify-center hover:bg-accent"
                title="Remove attachment"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Hidden file picker for the "Add files" action (all types; the backend
          enforces the blocklist and size cap) */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => handleFilesSelected(e.target.files)}
      />

      {/* Input field row */}
      <div className="flex items-center gap-2 w-full mb-0.5">
        <div className="flex-1 relative group/chatinput">
          {/* Right-aligned placeholder-side hint; gone once focused/typing. */}
          {showFocusHint && !message && (
            <span className="pointer-events-none absolute right-2 top-[18px] -translate-y-1/2 text-xs text-muted-foreground/40 group-focus-within/chatinput:hidden">
              {comboInline(getShortcutCombo('focus-chat'))} to focus
            </span>
          )}
          <MentionTextarea
            ref={textareaRef}
            value={message}
            onChange={handleMessageChange}
            projectPath={projectPath}
            machineId={machineId}
            mentionsEnabled={!!projectPath}
            onMentionOpenChange={handleMentionOpenChange}
            placeholder={placeholder}
            disabled={disabled || !canSendMessage || isSending}
            openMentionSignal={mentionSignal}
            className="w-full bg-transparent border-0 py-2 px-2 text-sm resize-none focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-50 leading-5 placeholder:text-muted-foreground/50"
            style={{
              height: '36px',
              minHeight: '36px',
              maxHeight: '128px',
              overflowY: message && textareaRef.current && textareaRef.current.scrollHeight > 128 ? 'auto' : 'hidden',
              scrollbarWidth: 'thin',
              scrollbarColor: 'hsl(var(--border)) transparent',
            }}
            onKeyDown={handleKeyDown}
            rows={1}
          />
        </div>
      </div>

      {/* Control buttons and send button row */}
      <div className="flex items-center justify-between w-full">
        {/* Left control buttons */}
        <div className="flex items-center gap-1">
          {/* Add-to-chat ("+") — always available so @files / commands are one
              tap away regardless of agent. */}
          <AddToChatMenu
            onAddFiles={handleAddFiles}
            onAddFolder={getDesktopShellBridge() ? handleInsertFolder : undefined}
            onMentionFiles={handleInsertMention}
            onCommands={handleInsertSlash}
            hasSkills={hasSkills}
            disabled={disabled || !canSendMessage}
          />

          {showControlSettings && (
            <SessionConfigChips
              disabled={disabled}
              agentTypeName={agentLogoName ?? agentType}
              models={sessionModels}
              currentModel={currentModel}
              pendingModel={pendingModel}
              onModelChange={onModelChange}
              efforts={sessionEfforts}
              effortLabel={sessionEffortLabel}
              currentEffort={currentEffort}
              pendingEffort={pendingEffort}
              onEffortChange={onEffortChange}
              permissionModes={isOpencodeAgent ? undefined : sessionPermissionModes}
              currentPermissionMode={permissionMode}
              pendingPermissionMode={pendingPermissionMode}
              onPermissionModeChange={onPermissionModeChange as ((mode: string) => void) | undefined}
              showYoloInfo={agentType === 'claude'}
              opencodeModes={isOpencodeAgent ? (sessionOpencodeModes ?? opencodeAgentModes) : undefined}
              currentOpencodeMode={opencodeAgentMode}
              pendingOpencodeMode={pendingOpencodeAgentMode}
              onOpencodeMode={onOpencodeAgentModeChange as ((mode: string) => void) | undefined}
              singleColumnModels={singleColumnModels}
            />
          )}

          {/* Context-window + rate-limit usage (Claude + Codex); self-hides
              when the session has no usage to show. Opening the popover on a
              Claude session refreshes the rate-limit windows from the
              machine's daemon (Codex limits stay in-band only). */}
          <ChatUsageIndicator usage={usage} fetchLimits={usageFetchLimits} />

        </div>

        {/* Send button — doubles as Stop while a turn is running.

            The swap is gated on an empty composer so mid-turn queueing still
            works: the moment the user types, the arrow comes back and the
            message goes into the queued-messages bar as before. That also
            means a stale ACTIVE status can never lock the user out of
            sending — typing always restores Send. */}
        <Button
          onClick={showStopButton ? onInterrupt : handleSendMessage}
          title={showStopButton ? 'Stop current task' : undefined}
          aria-label={showStopButton ? 'Stop current task' : 'Send message'}
          disabled={
            showStopButton
              ? false
              : disabled ||
                !canSendMessage ||
                isSending ||
                hasUploadingAttachments ||
                !hasComposerContent
          }
          variant="default"
          size="icon"
          className="shrink-0 rounded-full w-7 h-7 p-0 border-0 focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:border-transparent focus-visible:outline-none"
        >
          {isSending ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : showStopButton ? (
            // `size-*`, not `w-*`/`h-*`: the Button base class carries
            // `[&_svg:not([class*='size-'])]:size-4`, a descendant selector
            // that outspecifies plain width/height utilities and pins any
            // bare svg to 16px. A class containing `size-` is the opt-out the
            // guard is there for.
            <Square className="size-3" fill="currentColor" strokeWidth={0} />
          ) : (
            <ArrowUp className="w-3.5 h-3.5" />
          )}
        </Button>
      </div>
      </div>
    </div>
  );
}));
