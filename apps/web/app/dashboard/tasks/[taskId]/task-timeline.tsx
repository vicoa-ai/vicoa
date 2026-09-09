'use client';

// The task-detail timeline: comments, generated activity and agent sessions in
// one chronological stream.
//
// Three rules hold the whole thing together, and they are the reason it does
// not look like a chat log:
//
// 1. ONE COLUMN. Every row — comment, activity line, session card — puts its
//    leading glyph at the same x and uses the same avatar size. Cards carry a
//    real border and bare rows a transparent one so a 1px edge can't knock the
//    column out of true.
// 2. ONE SURFACE PER THREAD. A root, its replies and the box you answer in
//    share a single card with dividers between them, rather than each comment
//    getting its own floating bubble. The thread is the object; the card is its
//    edge. (Before threads existed this grouped *runs* of comments instead —
//    once a comment can be answered, the run is no longer the real unit.)
// 3. SESSIONS ABSORB THEIR OWN NOISE. A session's status hops (in_progress →
//    done → in_review) are real activity rows, but they are folded into that
//    session's card via `details.agent_instance_id` instead of being listed
//    three times in the stream. Without this the timeline of a task that ran
//    three sessions is nine automated lines and no content.
// 4. A THREAD SITS WHERE IT STARTED, AND NEVER BRANCHES — SO IT NEVER INDENTS.
//    Replies are one level deep (the server guarantees it): under a root they
//    are a single ordered chain, never a tree. That is exactly why they are NOT
//    indented — an indent encodes depth, and there is no second level for it to
//    distinguish. The card's edge and the reply box at its foot already say
//    "one conversation", so rule 1 holds with no exception. The thread is placed
//    at its ROOT's timestamp, so an answer written a day later appears next to
//    the thing it answers rather than stranded at the bottom of the page.
// 5. THE REPLY BOX IS ALWAYS THERE. Every thread ends in a quiet "Leave a
//    reply…" row — click and type. A hover-revealed or click-to-open affordance
//    costs a click to discover that it exists, and this page is also a phone
//    browser, where hover does not exist at all.

import { useMemo, useState } from 'react';
import { ChevronDown, ExternalLink, SmilePlus } from 'lucide-react';
import Link from 'next/link';

import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { MessageMarkdown } from '@/components/ui/message-markdown';
import { SessionAgentIcon } from '@/components/dashboard/agent-type-icon';
import { formatSidebarTime, getSessionTitle } from '@/components/dashboard/session-display';
import {
  AgentInstanceResponse,
  TaskActivityResponse,
  TaskCommentResponse,
  TaskReactionSummary,
} from '@/lib/backend-api';
import { EmojiPicker } from '@/components/ui/emoji-picker';
import { CommentComposer } from './comment-composer';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  principalDisplayName,
  principalForAvatar,
  principalFromResponse,
  type Principal,
} from '@/lib/principals';
import { cn } from '@/lib/utils';

// See rule 1. Both values are used by the composer too, so the stream and the
// box you type into share a left edge.
const ROW_INSET = 'border px-3';
const CARD_ROW = `${ROW_INSET} rounded-lg border-border bg-card`;
const BARE_ROW = `${ROW_INSET} border-transparent`;

/** A root comment and the replies hanging off it. Never deeper than this. */
type Thread = { root: TaskCommentResponse; replies: TaskCommentResponse[] };

type Entry =
  | { kind: 'thread'; id: string; at: string; thread: Thread }
  | { kind: 'activity'; id: string; at: string; items: TaskActivityResponse[] }
  | {
      kind: 'session';
      id: string;
      at: string;
      session: AgentInstanceResponse;
      absorbed: TaskActivityResponse[];
    };

const STATUS_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  todo: 'Todo',
  in_progress: 'In Progress',
  in_review: 'In Review',
  done: 'Done',
  blocked: 'Blocked',
  cancelled: 'Cancelled',
};

function pretty(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'none';
  const text = String(value);
  return STATUS_LABELS[text] ?? text;
}

/** The one-line phrase an activity row reads as. */
export function activityText(entry: TaskActivityResponse): string {
  const d = entry.details ?? {};
  switch (entry.action) {
    case 'created':
      return 'created this task';
    case 'status_changed':
      return `moved from ${pretty(d.from)} to ${pretty(d.to)}`;
    case 'priority_changed':
      return `changed priority from ${pretty(d.from)} to ${pretty(d.to)}`;
    case 'assigned':
      return d.to ? 'changed the assignee' : 'cleared the assignee';
    case 'title_changed':
      return 'edited the title';
    case 'description_changed':
      return 'edited the description';
    case 'label_added':
      return `added label ${pretty(d.label)}`;
    case 'label_removed':
      return `removed label ${pretty(d.label)}`;
    case 'due_date_set':
      return d.to ? 'set a due date' : 'removed the due date';
    case 'start_date_set':
      return d.to ? 'set a start date' : 'removed the start date';
    case 'project_changed':
      return 'moved this task to another project';
    case 'parent_changed':
      return d.to ? 'changed the parent task' : 'removed the parent task';
    default:
      return entry.action.replace(/_/g, ' ');
  }
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * Group a flat comment list into one-level threads.
 *
 * Built from `parent_comment_id` rather than from arrival order: the server
 * already sends the list threaded, but a client that silently depends on that
 * ordering breaks in a way nobody notices until a reply renders as a root.
 * A reply whose root isn't in the list is promoted to a root — a comment that
 * exists must be readable.
 */
export function buildThreads(comments: TaskCommentResponse[]): Thread[] {
  const threads = new Map<string, Thread>();
  const order: string[] = [];
  const orphans: TaskCommentResponse[] = [];

  for (const comment of comments) {
    if (comment.parent_comment_id === null) {
      threads.set(comment.id, { root: comment, replies: [] });
      order.push(comment.id);
    }
  }
  for (const comment of comments) {
    if (comment.parent_comment_id === null) continue;
    const thread = threads.get(comment.parent_comment_id);
    if (thread) thread.replies.push(comment);
    else orphans.push(comment);
  }
  for (const orphan of orphans) {
    threads.set(orphan.id, { root: orphan, replies: [] });
    order.push(orphan.id);
  }

  const out = order.map((id) => threads.get(id)!);
  out.sort((a, b) => a.root.created_at.localeCompare(b.root.created_at));
  for (const thread of out) {
    thread.replies.sort((a, b) => a.created_at.localeCompare(b.created_at));
  }
  return out;
}

/**
 * Fold the three sources into one ordered stream.
 *
 * Sessions are placed at their start time and swallow the activity rows they
 * caused (rule 3); whatever is left merges by kind, so a burst of edits becomes
 * one line and a back-and-forth becomes one card.
 */
export function buildEntries(
  comments: TaskCommentResponse[],
  activity: TaskActivityResponse[],
  sessions: AgentInstanceResponse[],
): Entry[] {
  // Threads are placed by their ROOT's timestamp (rule 4), so a reply never
  // pulls its thread down the page away from the conversation it belongs to.
  const threads = buildThreads(comments);
  // Only a session that is actually on this task can absorb anything. An
  // activity row naming a session the task no longer links to (unlinked, or
  // deleted) would otherwise be bucketed against a card that never renders and
  // vanish from the timeline — the change really happened, so it stays as a
  // normal line instead.
  const linked = new Set(sessions.map((session) => session.id));
  const bySession = new Map<string, TaskActivityResponse[]>();
  const loose: TaskActivityResponse[] = [];
  for (const row of activity) {
    const instanceId = row.details?.agent_instance_id;
    if (typeof instanceId === 'string' && linked.has(instanceId)) {
      const bucket = bySession.get(instanceId);
      if (bucket) bucket.push(row);
      else bySession.set(instanceId, [row]);
    } else {
      loose.push(row);
    }
  }

  type Raw =
    | { at: string; kind: 'comment'; thread: Thread }
    | { at: string; kind: 'activity'; row: TaskActivityResponse }
    | { at: string; kind: 'session'; session: AgentInstanceResponse };

  const raw: Raw[] = [
    ...threads.map((thread) => ({
      at: thread.root.created_at,
      kind: 'comment' as const,
      thread,
    })),
    ...loose.map((row) => ({ at: row.created_at, kind: 'activity' as const, row })),
    // A session with no start time sorts to the top rather than being dropped;
    // it is still a real link on the task.
    ...sessions.map((session) => ({
      at: session.started_at ?? new Date(0).toISOString(),
      kind: 'session' as const,
      session,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  const entries: Entry[] = [];
  for (const item of raw) {
    const last = entries[entries.length - 1];
    if (item.kind === 'comment') {
      // Never merged with the thread before it (rule 2): each thread owns its
      // own card because each thread owns its own reply box.
      entries.push({
        kind: 'thread',
        id: `c-${item.thread.root.id}`,
        at: item.at,
        thread: item.thread,
      });
    } else if (item.kind === 'activity') {
      if (last?.kind === 'activity') last.items.push(item.row);
      else
        entries.push({ kind: 'activity', id: `a-${item.row.id}`, at: item.at, items: [item.row] });
    } else {
      entries.push({
        kind: 'session',
        id: `s-${item.session.id}`,
        at: item.at,
        session: item.session,
        absorbed: bySession.get(item.session.id) ?? [],
      });
    }
  }
  return entries;
}

/**
 * "Nick and Ada reacted with 👍" — the sentence a pill's tooltip reads.
 *
 * The signed-in user comes first and reads as "You", the way Slack and GitHub
 * put you at the front of your own reactions. Past the server's cap the
 * remainder collapses to "and N others" rather than the list simply ending,
 * so the tooltip never quietly under-reports who is on a pill.
 */
export function describeReactors(
  reaction: TaskReactionSummary,
  viewer: Principal | null,
): string {
  const named = reaction.reactors.map((r) => {
    const principal = principalFromResponse(r);
    const isViewer = !!viewer?.id && r.id === viewer.id;
    return isViewer ? 'You' : principalDisplayName(principal, viewer);
  });
  const mine = named.indexOf('You');
  if (mine > 0) named.unshift(...named.splice(mine, 1));

  const unnamed = reaction.count - named.length;
  if (unnamed > 0) named.push(`${unnamed} other${unnamed === 1 ? '' : 's'}`);

  const people =
    named.length <= 1
      ? (named[0] ?? 'Someone')
      : `${named.slice(0, -1).join(', ')} and ${named[named.length - 1]}`;
  return `${people} reacted with ${reaction.emoji}`;
}

/**
 * The pill row plus its add button.
 *
 * The add button opens the shared `<EmojiPicker>` — the one project icons and
 * avatars already use — in its `reaction` variant: a curated set of things
 * people actually answer with, a search box, and "All emoji" for the full
 * Unicode set behind a click. A fixed six-emoji strip is the thing this
 * replaces; there is no reason a reaction can be 👍 but not 🤯.
 */
export function ReactionRow({
  reactions,
  viewer,
  onToggle,
  className,
}: {
  reactions: TaskReactionSummary[];
  /** Resolves a nameless reactor to "You" rather than "Unknown". */
  viewer: Principal | null;
  onToggle: (emoji: string) => void;
  className?: string;
}) {
  const [picking, setPicking] = useState(false);
  return (
    <div className={cn('flex flex-wrap items-center gap-1', className)}>
      <TooltipProvider delayDuration={200}>
        {reactions.map((reaction) => (
          <Tooltip key={reaction.emoji}>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => onToggle(reaction.emoji)}
                className={cn(
                  'flex cursor-pointer items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] transition-colors',
                  reaction.reacted
                    ? 'border-primary/40 bg-primary/10 text-foreground'
                    : 'bg-muted/50 hover:bg-muted',
                )}
              >
                {reaction.emoji} {reaction.count}
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-56">
              {describeReactors(reaction, viewer)}
            </TooltipContent>
          </Tooltip>
        ))}
      </TooltipProvider>
      <Popover open={picking} onOpenChange={setPicking}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label="Add reaction"
            className="flex size-6 cursor-pointer items-center justify-center rounded-full border text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground"
          >
            <SmilePlus className="size-3.5" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <EmojiPicker
            variant="reaction"
            onSelect={(emoji) => {
              onToggle(emoji);
              setPicking(false);
            }}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}

function CommentBody({
  comment,
  viewer,
  onToggleReaction,
}: {
  comment: TaskCommentResponse;
  viewer: Principal | null;
  onToggleReaction: (commentId: string, emoji: string) => void;
}) {
  const author = principalFromResponse(comment.author);
  return (
    <>
      <div className="flex items-center gap-2">
        <PrincipalAvatar principal={principalForAvatar(author, viewer)} size="xs" />
        <span className="text-sm font-medium">
          {principalDisplayName(author, viewer)}
        </span>
        {comment.author.type === 'agent' && (
          <span className="rounded bg-muted px-1 py-px text-[10px] text-muted-foreground">
            agent
          </span>
        )}
        <span className="text-xs text-muted-foreground">
          {timeLabel(comment.created_at)}
        </span>
        {comment.edited_at && (
          <span className="text-xs text-muted-foreground/60">(edited)</span>
        )}
      </div>
      {comment.deleted_at || comment.body === null ? (
        // The tombstone stays: its replies are still on screen under it, and a
        // thread with a hole where its opening post was is unreadable.
        <div className="mt-1.5 text-sm italic text-muted-foreground/60">
          This comment was deleted.
        </div>
      ) : (
        <>
          {/* Body starts at the avatar's left edge, not indented under the
              name — the indent buys nothing and costs the column. */}
          <div className="mt-1.5 text-sm leading-relaxed">
            <MessageMarkdown>{comment.body}</MessageMarkdown>
          </div>
          <ReactionRow
            className="mt-2"
            reactions={comment.reactions}
            viewer={viewer}
            onToggle={(emoji) => onToggleReaction(comment.id, emoji)}
          />
        </>
      )}
    </>
  );
}

function ThreadCard({
  thread,
  viewer,
  onToggleReaction,
  onReply,
}: {
  thread: Thread;
  viewer: Principal | null;
  onToggleReaction: (commentId: string, emoji: string) => void;
  onReply?: (parentCommentId: string, body: string) => Promise<void>;
}) {
  return (
    <div className={cn(CARD_ROW, 'px-0')}>
      <div className="px-3 py-2.5">
        <CommentBody comment={thread.root} viewer={viewer} onToggleReaction={onToggleReaction} />
      </div>
      {/* Not indented (rule 4). The card's edge already says these belong
          together, and there is no second level to distinguish them from — a
          reply cannot itself be replied to, so an indent would only encode
          depth that cannot exist. */}
      {thread.replies.map((reply) => (
        <div key={reply.id} className="border-t px-3 py-2.5">
          <CommentBody comment={reply} viewer={viewer} onToggleReaction={onToggleReaction} />
        </div>
      ))}
      {onReply && (
        <div className="border-t px-3 py-1.5">
          <CommentComposer
            variant="inline"
            placeholder="Leave a reply…"
            leading={
              <PrincipalAvatar
                principal={viewer ?? { type: 'user', name: null }}
                size="xs"
              />
            }
            onSubmit={(body) => onReply(thread.root.id, body)}
          />
        </div>
      )}
    </div>
  );
}

function ActivityLine({
  row,
  viewer,
}: {
  row: TaskActivityResponse;
  viewer: Principal | null;
}) {
  const actor = principalFromResponse(row.actor);
  return (
    <div className={cn(BARE_ROW, 'flex items-center gap-2 py-1 text-xs text-muted-foreground')}>
      <PrincipalAvatar principal={principalForAvatar(actor, viewer)} size="xs" />
      <span className="min-w-0 truncate">
        <span className="text-foreground/70">{principalDisplayName(actor, viewer)}</span>{' '}
        {activityText(row)}
      </span>
      <span className="shrink-0 opacity-50">{timeLabel(row.created_at)}</span>
    </div>
  );
}

function ActivityRun({
  rows,
  viewer,
}: {
  rows: TaskActivityResponse[];
  viewer: Principal | null;
}) {
  const [open, setOpen] = useState(false);
  if (rows.length === 1) return <ActivityLine row={rows[0]} viewer={viewer} />;

  const actors = Array.from(
    new Set(
      rows.map((row) => principalDisplayName(principalFromResponse(row.actor), viewer)),
    ),
  );
  const lead = principalFromResponse(rows[0].actor);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          BARE_ROW,
          'flex w-full cursor-pointer items-center gap-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground',
        )}
      >
        <PrincipalAvatar principal={principalForAvatar(lead, viewer)} size="xs" />
        <span>
          <span className="text-foreground/70">{actors.join(' & ')}</span> made {rows.length}{' '}
          changes
        </span>
        <span className="opacity-50">{timeLabel(rows[0].created_at)}</span>
        <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="ml-5 mt-1 space-y-0.5 border-l">
          {rows.map((row) => (
            <ActivityLine key={row.id} row={row} viewer={viewer} />
          ))}
        </div>
      )}
    </div>
  );
}

function SessionCard({
  session,
  absorbed,
}: {
  session: AgentInstanceResponse;
  absorbed: TaskActivityResponse[];
}) {
  const [open, setOpen] = useState(false);
  const live = session.status === 'ACTIVE';
  return (
    <div className={cn(CARD_ROW, 'px-0')}>
      <div className="flex items-center gap-2 px-3 py-2.5">
        <SessionAgentIcon
          agentTypeName={session.agent_type_name}
          status={session.status}
          size={16}
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{getSessionTitle(session)}</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            {live ? (
              <span className="flex items-center gap-1 text-emerald-500">
                <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
                running
              </span>
            ) : (
              <span>{String(session.status).toLowerCase()}</span>
            )}
            <span className="opacity-40">·</span>
            <span>{formatSidebarTime(session)}</span>
          </div>
        </div>
        <Link
          href={`/dashboard?instance=${session.id}`}
          className="flex shrink-0 cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          Open <ExternalLink className="size-3" />
        </Link>
      </div>
      {absorbed.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex w-full cursor-pointer items-center gap-1.5 border-t px-3 py-1.5 text-left text-[11px] text-muted-foreground/70 transition-colors hover:text-muted-foreground"
          >
            <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} />
            {absorbed.length} status change{absorbed.length === 1 ? '' : 's'} from this session
          </button>
          {open && (
            <div className="space-y-1 border-t px-3 py-2 text-[11px] text-muted-foreground">
              {absorbed.map((row) => (
                <div key={row.id}>{activityText(row)}</div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function TaskTimeline({
  comments,
  activity,
  sessions,
  viewer,
  onToggleCommentReaction,
  onReply,
}: {
  comments: TaskCommentResponse[];
  activity: TaskActivityResponse[];
  sessions: AgentInstanceResponse[];
  /** The signed-in user, so a nameless principal can still read as "You". */
  viewer: Principal | null;
  onToggleCommentReaction: (commentId: string, emoji: string) => void;
  /** Omitted on a read-only surface (P4's public board): no composer, no Reply. */
  onReply?: (parentCommentId: string, body: string) => Promise<void>;
}) {
  const entries = useMemo(
    () => buildEntries(comments, activity, sessions),
    [comments, activity, sessions],
  );

  return (
    <div className="space-y-1.5">
      {entries.map((entry) => {
        if (entry.kind === 'thread') {
          return (
            <ThreadCard
              key={entry.id}
              thread={entry.thread}
              viewer={viewer}
              onToggleReaction={onToggleCommentReaction}
              onReply={onReply}
            />
          );
        }
        if (entry.kind === 'activity') {
          return <ActivityRun key={entry.id} rows={entry.items} viewer={viewer} />;
        }
        return <SessionCard key={entry.id} session={entry.session} absorbed={entry.absorbed} />;
      })}
    </div>
  );
}

export type { Entry, Thread, Principal };
