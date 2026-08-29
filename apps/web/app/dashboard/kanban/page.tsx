'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowUp, Columns, Loader2, MessageCircleMore, RefreshCw } from 'lucide-react';
import { AskUserQuestionPanel, AskUserQuestionSubmitPayload, buildAskUserQuestionCancelPersistMessage, buildAskUserQuestionControlMessage, buildAskUserQuestionSummaryMessage, parseAskUserQuestionPayload } from '@/components/dashboard/ask-user-question-panel';
import { DeleteSessionDialog } from '@/components/dashboard/session-dialogs';
import { SessionActionsMenu } from '@/components/dashboard/session-actions-menu';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { StartEllipsisText } from '@/components/ui/start-ellipsis-text';
import { extractMessageOptions } from '@/components/ui/message-markdown-utils';
import { AgentInstanceDetail, AgentInstanceResponse, MessageResponse } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { cn } from '@/lib/utils';

type ColumnKey = 'running' | 'needInput' | 'toReview' | 'done' | 'closed';

type ColumnConfig = {
  key: ColumnKey;
  title: string;
  description: string;
};

const AGENT_MANAGER_VISIBLE_COLUMNS_STORAGE_KEY = 'agent-manager-visible-columns';
const defaultVisibleColumns: ColumnKey[] = ['running', 'needInput', 'done'];

function getInitialVisibleColumns(): Set<ColumnKey> {
  if (typeof window === 'undefined') {
    return new Set(defaultVisibleColumns);
  }

  try {
    const storedValue = window.localStorage.getItem(AGENT_MANAGER_VISIBLE_COLUMNS_STORAGE_KEY);
    if (!storedValue) {
      return new Set(defaultVisibleColumns);
    }

    const parsed = JSON.parse(storedValue);
    if (!Array.isArray(parsed)) {
      return new Set(defaultVisibleColumns);
    }

    const validColumns = parsed.filter((value): value is ColumnKey =>
      columns.some((column) => column.key === value)
    );

    return new Set(validColumns.length > 0 ? validColumns : defaultVisibleColumns);
  } catch (error) {
    console.warn('Failed to restore agent manager columns preference:', error);
    return new Set(defaultVisibleColumns);
  }
}

const columns: ColumnConfig[] = [
  { key: 'running', title: 'In Progress', description: 'Agents working in progress.' },
  { key: 'needInput', title: 'To Input', description: 'Waiting for your input.' },
  { key: 'toReview', title: 'To Review', description: 'Ready for your review.' },
  { key: 'done', title: 'Done', description: 'Completed and reviewed tasks.' },
  { key: 'closed', title: 'Closed', description: 'Closed agent session.' },
];

function getLastMessage(detail?: AgentInstanceDetail): MessageResponse | undefined {
  return detail?.messages[detail.messages.length - 1];
}

function classifyInstance(instance: AgentInstanceResponse, detail?: AgentInstanceDetail): ColumnKey {
  if (instance.status === 'ACTIVE') return 'running';
  if (instance.status === 'REVIEWED') return 'done';

  if (instance.status === 'AWAITING_INPUT') {
    const lastMessage = getLastMessage(detail);
    if (!lastMessage) return 'toReview';

    const hasAskUserQuestion = Boolean(parseAskUserQuestionPayload(lastMessage));
    const hasOptions = extractMessageOptions(lastMessage.content || '').options.length > 0;
    return hasAskUserQuestion || hasOptions ? 'needInput' : 'toReview';
  }

  return 'closed';
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'No activity yet';
  const date = new Date(value);
  const now = new Date();
  const sameYear = date.getFullYear() === now.getFullYear();

  return date.toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function InstanceCard({
  instance,
  detail,
  columnKey,
  busy,
  highlight,
  onOpen,
  onRename,
  onDelete,
  onReply,
  onMarkDone,
  onOptionClick,
  onAskUserQuestionSubmit,
  onAskUserQuestionCancel,
}: {
  instance: AgentInstanceResponse;
  detail?: AgentInstanceDetail;
  columnKey: ColumnKey;
  busy: boolean;
  highlight: boolean;
  onOpen: (instance: AgentInstanceResponse, columnKey: ColumnKey) => void;
  onRename: (instanceId: string, name: string) => Promise<void>;
  onDelete: (instanceId: string) => Promise<void>;
  onReply: (instanceId: string, content: string) => Promise<void>;
  onMarkDone: (instanceId: string) => Promise<void>;
  onOptionClick: (instanceId: string, option: string) => void;
  onAskUserQuestionSubmit: (instanceId: string, payload: AskUserQuestionSubmitPayload) => void;
  onAskUserQuestionCancel: (instanceId: string, messageId: string) => void;
}) {
  const lastMessage = getLastMessage(detail);
  const askUserQuestion = lastMessage ? parseAskUserQuestionPayload(lastMessage) : null;
  const parsedOptions = extractMessageOptions(lastMessage?.content || '');
  const preview = (instance.latest_message || parsedOptions.content || '').trim();
  const canReplyInline = columnKey === 'running' || columnKey === 'toReview' || columnKey === 'done';
  const canMarkDone = columnKey !== 'closed';
  const [draftReply, setDraftReply] = useState('');
  const [draftTitle, setDraftTitle] = useState(instance.name || instance.agent_type_name || 'Unnamed Session');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [copiedId, setCopiedId] = useState(false);
  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    setDraftTitle(instance.name || instance.agent_type_name || 'Unnamed Session');
  }, [instance.agent_type_name, instance.name]);

  const handleRenameSubmit = async () => {
    const nextName = draftTitle.trim();
    if (!nextName || nextName === (instance.name || instance.agent_type_name || 'Unnamed Session')) {
      setIsEditingTitle(false);
      setDraftTitle(instance.name || instance.agent_type_name || 'Unnamed Session');
      return;
    }

    await onRename(instance.id, nextName);
    setIsEditingTitle(false);
  };

  const handleReplySubmit = async () => {
    const nextReply = draftReply.trim();
    if (!nextReply) return;
    await onReply(instance.id, nextReply);
    setDraftReply('');
  };

  useLayoutEffect(() => {
    const node = replyTextareaRef.current;
    if (!node) return;

    node.style.height = '0px';
    node.style.height = `${Math.min(node.scrollHeight, 96)}px`;
  }, [draftReply]);

  const handleCopyId = async () => {
    try {
      await navigator.clipboard.writeText(instance.id);
      setCopiedId(true);
      window.setTimeout(() => setCopiedId(false), 2000);
    } catch (error) {
      console.error('Failed to copy session ID:', error);
    }
  };

  return (
    <div className="relative">
      {busy ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-background/80">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      ) : null}
      <Card
        className={cn(
          "min-w-0 max-w-full cursor-pointer gap-1 overflow-hidden border border-border/70 bg-card/70 shadow-sm transition-[transform,box-shadow,opacity] hover:shadow-md",
          highlight && "animate-in fade-in zoom-in-95 duration-300 ring-1 ring-border/60"
        )}
        onClick={() => onOpen(instance, columnKey)}
      >
        <CardHeader className="space-y-0 pb-0">
          <div className="flex min-w-0 items-start justify-between gap-2 overflow-hidden">
            <div className="min-w-0 flex-1">
              {isEditingTitle ? (
                <div onClick={(event) => event.stopPropagation()}>
                  <Input
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    onBlur={() => {
                      void handleRenameSubmit();
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void handleRenameSubmit();
                      }
                      if (event.key === 'Escape') {
                        event.preventDefault();
                        setDraftTitle(instance.name || instance.agent_type_name || 'Unnamed Session');
                        setIsEditingTitle(false);
                      }
                    }}
                    className="h-7 text-sm"
                    autoFocus
                  />
                </div>
              ) : (
                <div
                  onClick={(event) => event.stopPropagation()}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    setIsEditingTitle(true);
                  }}
                >
                  <CardTitle className="truncate text-sm font-semibold" title={instance.name || instance.agent_type_name || 'Unnamed Session'}>
                    {instance.name || instance.agent_type_name || 'Unnamed Session'}
                  </CardTitle>
                </div>
              )}
              <CardDescription className="mt-1 min-w-0 overflow-hidden text-xs">
                <StartEllipsisText
                  value={instance.project || instance.home_dir || instance.agent_type_name || 'No project path'}
                  className="text-xs"
                />
              </CardDescription>
            </div>
            <div className="shrink-0" onClick={(event) => event.stopPropagation()}>
              <SessionActionsMenu
                onRename={() => setIsEditingTitle(true)}
                onCopyId={() => {
                  void handleCopyId();
                }}
                copied={copiedId}
                onMarkDone={canMarkDone ? () => void onMarkDone(instance.id) : undefined}
                showMarkDone={canMarkDone}
                onDelete={() => {
                  void onDelete(instance.id);
                }}
                className="h-7 w-7 p-0"
                iconClassName="h-4 w-4"
              />
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-2 pt-0">
          {preview ? (
            <div className="rounded-md border border-dashed border-border/70 bg-muted/25 p-3 text-xs leading-relaxed text-message-text whitespace-pre-wrap max-h-48 min-h-28 overflow-y-auto">
              {preview}
            </div>
          ) : null}

          {canReplyInline ? (
            <div
              className="mt-3 mb-2 flex items-end gap-2"
              onClick={(event) => event.stopPropagation()}
            >
              <textarea
                ref={replyTextareaRef}
                value={draftReply}
                onChange={(event) => setDraftReply(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleReplySubmit();
                  }
                }}
                placeholder="Reply"
                rows={1}
                className="max-h-24 min-h-8 w-full resize-none overflow-y-auto rounded-md border border-input bg-transparent px-3 pt-2 pb-3 text-xs shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[1px] focus-visible:ring-ring/60 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              />
              <Button
                type="button"
                size="icon"
                variant="default"
                className="h-8 w-8 shrink-0 self-end rounded-full p-0 border-0 focus:outline-none focus:ring-0 focus-visible:ring-0 focus-visible:border-transparent focus-visible:outline-none"
                disabled={!draftReply.trim() || busy}
                onClick={() => {
                  void handleReplySubmit();
                }}
              >
                {busy ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ArrowUp className="w-3.5 h-3.5" />
                )}
              </Button>
            </div>
          ) : null}

          <div className="flex items-center mt-4 justify-between gap-3 text-xs text-message-text/80">
            <div className="truncate">{formatTimestamp(instance.latest_message_at || instance.started_at)}</div>
            {/* <div className="shrink-0 text-right">{instance.chat_length} messages</div> */}
          </div>

          {columnKey === 'needInput' && askUserQuestion && lastMessage ? (
            <div onClick={(event) => event.stopPropagation()}>
              <AskUserQuestionPanel
                message={lastMessage}
                onSubmit={(payload) => onAskUserQuestionSubmit(instance.id, payload)}
                onCancel={(messageId) => onAskUserQuestionCancel(instance.id, messageId)}
              />
            </div>
          ) : null}

          {columnKey === 'needInput' && !askUserQuestion && parsedOptions.options.length > 0 ? (
            <div className="space-y-2" onClick={(event) => event.stopPropagation()}>
              <div className="text-xs font-medium text-muted-foreground">Quick options</div>
              {parsedOptions.options.map((option, index) => (
                <Button
                  key={`${instance.id}-option-${index}`}
                  variant="outline"
                  className="h-auto w-full justify-start whitespace-normal px-3 py-2 text-left text-xs"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOptionClick(instance.id, option);
                  }}
                >
                  {option}
                </Button>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AgentManagerPage() {
  const router = useRouter();
  const { api, recentInstances, isLoading, error, refreshData, updateInstanceStatus, updateInstance, removeInstance } = useAgentDashboard();
  const [detailsById, setDetailsById] = useState<Record<string, AgentInstanceDetail>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});
  const [busyInstanceId, setBusyInstanceId] = useState<string | null>(null);
  const [animatedInstanceId, setAnimatedInstanceId] = useState<string | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<{ open: boolean; sessionId: string; sessionName: string }>({
    open: false,
    sessionId: '',
    sessionName: '',
  });
  
  const [visibleColumns, setVisibleColumns] = useState<Set<ColumnKey>>(getInitialVisibleColumns);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        AGENT_MANAGER_VISIBLE_COLUMNS_STORAGE_KEY,
        JSON.stringify(Array.from(visibleColumns))
      );
    } catch (error) {
      console.warn('Failed to persist agent manager columns preference:', error);
    }
  }, [visibleColumns]);

  const awaitingInputIds = useMemo(
    () => recentInstances.filter((instance) => instance.status === 'AWAITING_INPUT').map((instance) => instance.id),
    [recentInstances]
  );

  useEffect(() => {
    if (!api || awaitingInputIds.length === 0) return;

    const missingIds = awaitingInputIds.filter((instanceId) => !detailsById[instanceId] && !loadingDetails[instanceId]);
    if (missingIds.length === 0) return;

    missingIds.forEach((instanceId) => {
      setLoadingDetails((prev) => ({ ...prev, [instanceId]: true }));
      api.getInstanceDetail(instanceId, 20)
        .then((detail) => {
          setDetailsById((prev) => ({ ...prev, [instanceId]: detail }));
        })
        .catch((fetchError) => {
          console.error(`Failed to load instance detail for ${instanceId}:`, fetchError);
        })
        .finally(() => {
          setLoadingDetails((prev) => {
            const next = { ...prev };
            delete next[instanceId];
            return next;
          });
        });
    });
  }, [api, awaitingInputIds, detailsById, loadingDetails]);

  const groupedInstances = useMemo(() => {
    const groups: Record<ColumnKey, AgentInstanceResponse[]> = {
      running: [],
      needInput: [],
      toReview: [],
      done: [],
      closed: [],
    };

    const sorted = [...recentInstances].sort((a, b) => {
      const aTime = new Date(a.latest_message_at || a.started_at).getTime();
      const bTime = new Date(b.latest_message_at || b.started_at).getTime();
      return bTime - aTime;
    });

    for (const instance of sorted) {
      const columnKey = classifyInstance(instance, detailsById[instance.id]);
      if (columnKey === 'toReview' && !visibleColumns.has('toReview')) {
        groups.done.push(instance);
      } else {
        groups[columnKey].push(instance);
      }
    }

    return groups;
  }, [detailsById, recentInstances, visibleColumns]);

  const postMessage = useCallback(async (instanceId: string, content: string) => {
    if (!api) return;

    setBusyInstanceId(instanceId);
    updateInstanceStatus(instanceId, 'ACTIVE', content);
    setAnimatedInstanceId(instanceId);

    setDetailsById((prev) => {
      const existing = prev[instanceId];
      if (!existing) return prev;

      return {
        ...prev,
        [instanceId]: {
          ...existing,
          status: 'ACTIVE',
          messages: [
            ...existing.messages,
            {
              id: `optimistic-${Date.now()}`,
              content,
              sender_type: 'user',
              created_at: new Date().toISOString(),
              requires_user_input: false,
              message_metadata: null,
            },
          ],
        },
      };
    });

    window.setTimeout(() => {
      setAnimatedInstanceId((current) => (current === instanceId ? null : current));
    }, 500);

    try {
      await api.createUserMessage(instanceId, { content });
      const detail = await api.getInstanceDetail(instanceId, 20);
      setDetailsById((prev) => ({ ...prev, [instanceId]: detail }));
    } catch (postError) {
      console.error(`Failed to send message to ${instanceId}:`, postError);
      alert('Failed to send message');
      await refreshData();
    } finally {
      setBusyInstanceId((current) => (current === instanceId ? null : current));
    }
  }, [api, refreshData, updateInstanceStatus]);

  const renameInstance = useCallback(async (instanceId: string, name: string) => {
    if (!api) return;

    const previousInstance = recentInstances.find((instance) => instance.id === instanceId);
    setBusyInstanceId(instanceId);
    try {
      updateInstance(instanceId, { name });
      await api.updateAgentInstance(instanceId, { name });
    } catch (renameError) {
      if (previousInstance) {
        updateInstance(instanceId, { name: previousInstance.name });
      }
      console.error(`Failed to rename ${instanceId}:`, renameError);
      alert('Failed to rename session');
    } finally {
      setBusyInstanceId((current) => (current === instanceId ? null : current));
    }
  }, [api, recentInstances, updateInstance]);

  const markDone = useCallback(async (instanceId: string) => {
    if (!api) return;

    setBusyInstanceId(instanceId);
    try {
      await api.updateAgentStatus(instanceId, { status: 'COMPLETED' });
      updateInstanceStatus(instanceId, 'COMPLETED');
      setDetailsById((prev) => {
        const existing = prev[instanceId];
        if (!existing) return prev;
        return {
          ...prev,
          [instanceId]: {
            ...existing,
            status: 'COMPLETED',
          },
        };
      });
    } catch (markDoneError) {
      console.error(`Failed to mark ${instanceId} as completed:`, markDoneError);
      alert('Failed to mark session as done');
      await refreshData();
    } finally {
      setBusyInstanceId((current) => (current === instanceId ? null : current));
    }
  }, [api, refreshData, updateInstanceStatus]);

  const openDeleteDialog = useCallback((instance: AgentInstanceResponse) => {
    setDeleteDialog({
      open: true,
      sessionId: instance.id,
      sessionName: instance.name || instance.agent_type_name || 'Unnamed Session',
    });
  }, []);

  const deleteInstance = useCallback(async (instanceId: string) => {
    if (!api) return;

    setBusyInstanceId(instanceId);
    try {
      await api.deleteAgentInstance(instanceId);
      removeInstance(instanceId);
      setDetailsById((prev) => {
        if (!(instanceId in prev)) {
          return prev;
        }

        const next = { ...prev };
        delete next[instanceId];
        return next;
      });
      setDeleteDialog({ open: false, sessionId: '', sessionName: '' });
    } catch (deleteError) {
      console.error(`Failed to delete ${instanceId}:`, deleteError);
      alert('Failed to delete session');
    } finally {
      setBusyInstanceId((current) => (current === instanceId ? null : current));
    }
  }, [api, removeInstance]);

  const handleOpen = useCallback(async (instance: AgentInstanceResponse, columnKey: ColumnKey) => {
    if (!api) return;

    if (columnKey === 'toReview' && instance.status === 'AWAITING_INPUT') {
      setBusyInstanceId(instance.id);
      try {
        await api.updateAgentStatus(instance.id, { status: 'REVIEWED' });
        updateInstanceStatus(instance.id, 'REVIEWED');
      } catch (statusError) {
        console.error(`Failed to mark ${instance.id} as REVIEWED:`, statusError);
      } finally {
        setBusyInstanceId((current) => (current === instance.id ? null : current));
      }
    }

    router.push(`/dashboard/agents/${instance.id}`);
  }, [api, router, updateInstanceStatus]);

  const handleAskUserQuestionSubmit = useCallback(async (instanceId: string, payload: AskUserQuestionSubmitPayload) => {
    const summaryMessage = buildAskUserQuestionSummaryMessage(payload);
    if (summaryMessage) {
      await postMessage(instanceId, summaryMessage);
    }

    await postMessage(instanceId, buildAskUserQuestionControlMessage('submit', payload));
  }, [postMessage]);

  const handleAskUserQuestionCancel = useCallback(async (instanceId: string, _messageId: string) => {
    await postMessage(instanceId, buildAskUserQuestionCancelPersistMessage());
    await postMessage(instanceId, buildAskUserQuestionControlMessage('cancel'));
  }, [postMessage]);

  const toggleColumn = (key: ColumnKey) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const activeColumns = columns.filter((col) => visibleColumns.has(col.key));
  const gridColsClass = useMemo(() => {
    const count = activeColumns.length;
    if (count === 1) return 'xl:grid-cols-1';
    if (count === 2) return 'xl:grid-cols-2';
    if (count === 3) return 'xl:grid-cols-3';
    if (count === 4) return 'xl:grid-cols-4';
    return 'xl:grid-cols-5';
  }, [activeColumns.length]);

  if (isLoading && recentInstances.length === 0) {
    return (
      <div className="mx-auto flex max-w-[1800px] flex-col gap-6 px-4 py-8 font-mono sm:px-6 lg:px-8">
        <div className="flex flex-col gap-3">
          <div className="h-9 w-64 rounded-full bg-muted animate-pulse" />
          <div className="h-4 w-96 max-w-full rounded-full bg-muted/60 animate-pulse" />
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, columnIndex) => (
            <section key={`manager-skeleton-column-${columnIndex}`} className="flex min-h-[520px] flex-col rounded-2xl bg-muted/20">
              <div className="px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-2">
                    <div className="h-3 w-24 rounded-full bg-muted animate-pulse" />
                    <div className="h-3 w-36 rounded-full bg-muted/60 animate-pulse" />
                  </div>
                  <div className="h-6 w-8 rounded-full bg-muted animate-pulse" />
                </div>
              </div>

              <div className="flex flex-1 flex-col items-center space-y-8 overflow-hidden px-0 py-6">
                {Array.from({ length: 3 }).map((__, cardIndex) => (
                  <div
                    key={`manager-skeleton-card-${columnIndex}-${cardIndex}`}
                    className="h-52 w-[88%] rounded-xl border border-border/70 bg-card/70 shadow-sm animate-pulse"
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 font-mono">
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1800px] flex-col gap-6 px-4 py-8 font-mono sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <h2 className="text-2xl tracking-tight">Agent Kanban</h2>

        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Columns className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>Display</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {columns.map((column) => (
                <DropdownMenuCheckboxItem
                  key={column.key}
                  checked={visibleColumns.has(column.key)}
                  onCheckedChange={() => toggleColumn(column.key)}
                >
                  {column.title}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button variant="outline" onClick={() => refreshData()} disabled={!api || busyInstanceId !== null}>
            <RefreshCw className="size-4" />
          </Button>
        </div>
      </div>

      <div className={cn("grid gap-4 md:grid-cols-2", gridColsClass)}>
        {activeColumns.map((column) => {
          const instances = groupedInstances[column.key];

          return (
            <section
              key={column.key}
              className="flex min-h-[520px] min-w-0 flex-col overflow-x-hidden rounded-2xl bg-muted/20 transition-all"
            >
              <div className="border-b border-border/60 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xs font-bold uppercase tracking-widest text-foreground">
                      {column.title}
                    </h2>
                    <p className="mt-1 text-[10px] leading-tight text-muted-foreground/80">
                      {column.description}
                    </p>
                  </div>
                  <span className="rounded-full border border-border/70 bg-background px-2.5 py-1 text-xs font-bold text-foreground">
                    {instances.length}
                  </span>
                </div>
              </div>

              <div className="flex-1 space-y-3 overflow-x-hidden overflow-y-auto px-0 py-3">
                {instances.length === 0 ? (
                  <div className="mx-0 flex h-40 flex-col items-center justify-center rounded-xl border border-dashed border-border/80 bg-background/40 px-4 text-center">
                    <MessageCircleMore className="mb-3 size-5 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">No sessions</p>
                  </div>
                ) : (
                  instances.map((instance) => (
                    <InstanceCard
                      key={instance.id}
                      instance={instance}
                      detail={detailsById[instance.id]}
                      columnKey={column.key}
                      busy={busyInstanceId === instance.id}
                      highlight={animatedInstanceId === instance.id}
                      onOpen={handleOpen}
                      onRename={renameInstance}
                      onDelete={async (instanceId) => {
                        const instance = recentInstances.find((item) => item.id === instanceId);
                        if (!instance) return;
                        openDeleteDialog(instance);
                      }}
                      onReply={postMessage}
                      onMarkDone={markDone}
                      onOptionClick={(instanceId, option) => postMessage(instanceId, option)}
                      onAskUserQuestionSubmit={handleAskUserQuestionSubmit}
                      onAskUserQuestionCancel={handleAskUserQuestionCancel}
                    />
                  ))
                )}
              </div>
            </section>
          );
        })}
      </div>

      <DeleteSessionDialog
        open={deleteDialog.open}
        onOpenChange={(open) => setDeleteDialog((prev) => ({ ...prev, open }))}
        sessionId={deleteDialog.sessionId}
        sessionName={deleteDialog.sessionName}
        onDelete={deleteInstance}
      />
    </div>
  );
}
