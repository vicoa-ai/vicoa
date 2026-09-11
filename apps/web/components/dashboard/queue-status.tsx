'use client';

import { useState } from 'react';
import { X, Loader2, Undo2, Zap } from 'lucide-react';
import { MessageResponse } from '@/lib/backend-api';
import { cancelQueuedMessage, steerQueuedMessage } from '@/lib/agent-instance-api';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

/**
 * `queued` → waiting for the current turn to end. `steer` → the user pressed
 * Steer; the daemon is delivering it into the running turn and will settle it
 * to `consumed` (with `steered`) or back to `queued`. `consumed` / `cancelled`
 * are terminal.
 */
export type QueueMessageStatus = 'queued' | 'steer' | 'consumed' | 'cancelled';

export interface QueuePayload {
  status: QueueMessageStatus;
  /** Set on a `consumed` message the agent took mid-turn (a Steer). */
  steered?: boolean;
}

/**
 * Parse `message.message_metadata.queue` — set by the backend when a user
 * message arrives while the agent is busy (D1). Mirrors
 * `parseAskUserQuestionPayload` in `ask-user-question-panel.tsx`. Only USER
 * messages carry this; callers are responsible for that check. Returns null
 * when the metadata is absent or malformed.
 */
export function parseQueuePayload(message: MessageResponse): QueuePayload | null {
  const metadata = message.message_metadata as Record<string, unknown> | null | undefined;
  const queueRaw = metadata?.queue as Record<string, unknown> | undefined;
  if (!queueRaw || typeof queueRaw !== 'object') {
    return null;
  }
  const status = queueRaw.status;
  if (status !== 'queued' && status !== 'steer' && status !== 'consumed' && status !== 'cancelled') {
    return null;
  }
  return queueRaw.steered === true ? { status, steered: true } : { status };
}

/** A message still living in the queue bar: waiting, or being steered. */
export function isPendingQueueStatus(status: QueueMessageStatus | undefined): boolean {
  return status === 'queued' || status === 'steer';
}

export interface QueuedMessageItem {
  id: string;
  text: string;
  /** Optimistic row whose real backend id hasn't echoed back yet. Cancel and
   *  retrieve both call the backend by id, so they're disabled until the echo
   *  swaps in the real id (a sub-second round-trip). */
  pending?: boolean;
  /** `queue.status === 'steer'`: the daemon is delivering this message into
   *  the running turn. Rendered with a steering indicator; actions disabled. */
  steering?: boolean;
}

/**
 * One not-yet-sent message in the queue stack. Owns only its cancel-in-flight
 * (spinner/disabled) state — it never optimistically drops itself. On success
 * the WS `message-update` patch flips the message off `queued`, and the parent
 * page re-derives the list without it.
 */
function QueuedMessageRow({
  instanceId,
  id,
  text,
  pending,
  steering,
  canSteer,
  onRetrieve,
}: {
  instanceId: string;
  id: string;
  text: string;
  pending?: boolean;
  steering?: boolean;
  canSteer?: boolean;
  onRetrieve?: (text: string) => void;
}) {
  const [isCancelling, setIsCancelling] = useState(false);
  const [isSteering, setIsSteering] = useState(false);
  // Until the real id echoes back, every action would hit the backend with the
  // optimistic id (a 404). Block them for that sub-second window. A message
  // already being steered is out of the user's hands too: the daemon settles
  // it (consumed, or back to queued) within a round-trip.
  const actionsDisabled = isCancelling || isSteering || !!pending || !!steering;

  // "Steer" = deliver into the running turn now, at the agent's next safe
  // boundary, instead of after the turn ends. The request only flips the
  // row's status; the WS patch to `steer` swaps this row into its steering
  // look, and the daemon's `consumed` patch removes it.
  const handleSteer = async () => {
    if (actionsDisabled) return;
    setIsSteering(true);
    try {
      const { steered } = await steerQueuedMessage(instanceId, id);
      // Not steered = no longer plainly queued (already picked up or removed);
      // the WS patch for that state re-derives the row, so just unlock.
      if (!steered) setIsSteering(false);
    } catch (err) {
      console.error('Failed to steer queued message:', err);
      setIsSteering(false);
    }
  };

  const handleRemove = async () => {
    if (actionsDisabled) return;
    setIsCancelling(true);
    try {
      await cancelQueuedMessage(instanceId, id);
    } catch (err) {
      console.error('Failed to cancel queued message:', err);
      setIsCancelling(false);
      // Leave the spinner up on success; the WS patch removes this row.
    }
  };

  // "Retrieve" = unsend + edit: drop the text back into the composer, then
  // remove it from the queue so it isn't also sent when the turn drains. The
  // composer is populated first (optimistically) so the user keeps the text
  // even if the unsend request is slow or fails.
  const handleRetrieve = async () => {
    if (actionsDisabled) return;
    onRetrieve?.(text);
    setIsCancelling(true);
    try {
      await cancelQueuedMessage(instanceId, id);
    } catch (err) {
      console.error('Failed to retrieve queued message:', err);
      setIsCancelling(false);
    }
  };

  const showSteering = !!steering || isSteering;

  return (
    <div className="group flex items-start gap-2 px-1 py-1">
      <span className="flex-1 min-w-0 text-xs leading-5 text-muted-foreground/80 whitespace-pre-wrap break-words line-clamp-2">
        {text}
      </span>
      {showSteering && (
        <span
          className="mt-0.5 inline-flex shrink-0 items-center justify-center p-0.5 text-muted-foreground/60"
          aria-label="Steering into the current turn"
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        </span>
      )}
      {canSteer && !showSteering && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleSteer}
              disabled={actionsDisabled}
              aria-label="Steer: send into the current turn now"
              className={cn(
                'mt-0.5 inline-flex shrink-0 items-center justify-center rounded-full p-0.5 text-muted-foreground/60',
                'hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground disabled:opacity-50 disabled:pointer-events-none',
              )}
            >
              <Zap className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="center">
            Steer — send into the current turn now
          </TooltipContent>
        </Tooltip>
      )}
      {onRetrieve && !showSteering && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleRetrieve}
              disabled={actionsDisabled}
              aria-label="Bring queued message back to input"
              className={cn(
                'mt-0.5 inline-flex shrink-0 items-center justify-center rounded-full p-0.5 text-muted-foreground/60',
                'hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground disabled:opacity-50 disabled:pointer-events-none',
              )}
            >
              <Undo2 className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="center">
            Edit in input
          </TooltipContent>
        </Tooltip>
      )}
      {!showSteering && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleRemove}
              disabled={actionsDisabled}
              aria-label="Remove queued message"
              className={cn(
                'mt-0.5 inline-flex shrink-0 items-center justify-center rounded-full p-0.5 text-muted-foreground/60',
                'hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground disabled:opacity-50 disabled:pointer-events-none',
              )}
            >
              {isCancelling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
            </button>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="center">
            Remove from queue
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

/**
 * Stack of queued (not-yet-sent) user messages, rendered attached to the top
 * of the chat input: rounded top corners, square bottom, so it reads as one
 * piece with the input below. Oldest is at the top, newest at the bottom —
 * the order the agent will consume them. Callers pass `items` already ordered
 * oldest → newest and pre-formatted for display.
 */
export function QueuedMessagesBar({
  instanceId,
  items,
  canSteer,
  onRetrieve,
}: {
  instanceId: string;
  items: QueuedMessageItem[];
  /** The session's agent can take a message mid-turn (catalog
   *  `supports_steer`); shows the per-row Steer button. */
  canSteer?: boolean;
  onRetrieve?: (text: string) => void;
}) {
  if (items.length === 0) return null;

  return (
    <div className="mx-auto w-[90%] rounded-t-3xl bg-menu px-3 pt-2 pb-1.5 border-b border-menu-border">
      <TooltipProvider delayDuration={300}>
        <div className="flex max-h-40 flex-col gap-1 overflow-y-auto">
          {items.map((item) => (
            <QueuedMessageRow
              key={item.id}
              instanceId={instanceId}
              id={item.id}
              text={item.text}
              pending={item.pending}
              steering={item.steering}
              canSteer={canSteer}
              onRetrieve={onRetrieve}
            />
          ))}
        </div>
      </TooltipProvider>
    </div>
  );
}
