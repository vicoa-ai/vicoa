'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, MessageCircle, Plus, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { getSessionTitle } from '@/components/dashboard/session-display';
import type { getBackendAPI } from '@/lib/backend-api';

type Api = ReturnType<typeof getBackendAPI>;

/** A session an automation can run in, as the picker shows it. */
export interface SessionTarget {
  id: string;
  title: string;
  machine_id: string;
  project: string;
  /** Catalog agent id, when the row carries the session's config. */
  agent?: string | null;
}

interface Row extends SessionTarget {
  at: string | null;
}

const SEARCH_DEBOUNCE_MS = 200;
const RECENT_LIMIT = 50;
const SEARCH_LIMIT = 20;

/** The fields both the session list and the search results carry. */
interface SessionLike {
  id: string;
  name?: string | null;
  latest_message?: string | null;
  latest_message_at?: string | null;
  started_at?: string | null;
  agent_type_name?: string | null;
  machine_id?: string | null;
  project?: string | null;
  status?: string;
  session_config?: Record<string, unknown> | null;
}

/** A session the scheduler can always reach: one with a computer and a folder
 *  to resume it in. Terminal sessions without either are left out. */
function toRow(s: SessionLike): Row | null {
  if (!s.machine_id || !s.project || s.status === 'DELETED') return null;
  const agent = s.session_config?.agent;
  return {
    id: s.id,
    title: getSessionTitle({ ...s, chat_length: 2 }),
    machine_id: s.machine_id,
    project: s.project,
    agent: typeof agent === 'string' ? agent : null,
    at: s.latest_message_at ?? s.started_at ?? null,
  };
}

function shortDate(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  });
}

/**
 * The automation editor's "Runs in" picker: a new session for every run (the
 * default), or one of your existing sessions that every run continues. Empty
 * search lists your recent sessions; typing searches all of them by name,
 * folder and message text, like the ⌘K palette.
 */
export function SessionTargetPicker({
  api,
  selectedId,
  onChange,
  children,
}: {
  api: Api;
  /** The session runs continue, or null for a new session each run. */
  selectedId: string | null;
  onChange: (target: SessionTarget | null) => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(
      () => {
        const load: Promise<SessionLike[]> = q
          ? api
              .search(q, { limit: SEARCH_LIMIT, signal: controller.signal })
              .then((res) => res.sessions)
          : api
              .listAllAgentInstancesPage({ scope: 'me', limit: RECENT_LIMIT })
              .then((page) => page.items);
        load
          .then((sessions) => {
            if (controller.signal.aborted) return;
            setRows(sessions.map(toRow).filter((r): r is Row => r !== null));
          })
          .catch(() => {
            if (!controller.signal.aborted) setRows([]);
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });
      },
      q ? SEARCH_DEBOUNCE_MS : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, open, query]);

  const pick = (target: SessionTarget | null) => {
    onChange(target);
    setOpen(false);
  };

  const rowClass =
    'flex w-full cursor-pointer items-center gap-2 rounded-sm px-2.5 py-1.5 text-left text-xs text-popover-foreground transition-colors hover:bg-foreground/[0.06] focus-visible:bg-foreground/10 focus-visible:outline-none dark:hover:bg-foreground/10';

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setQuery('');
      }}
    >
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        align="end"
        side="bottom"
        sideOffset={8}
        className="w-[min(32rem,calc(100vw-2rem))] space-y-1 rounded-xl border border-foreground/15 bg-menu p-1.5 shadow-xl"
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          inputRef.current?.focus({ preventScroll: true });
        }}
      >
        <div className="flex items-center gap-2 px-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={query}
            placeholder="Search sessions"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && rows[0]) {
                e.preventDefault();
                pick(rows[0]);
              }
            }}
            className="h-8 border-0 bg-transparent px-0 text-xs shadow-none focus-visible:border-0 focus-visible:ring-0 md:text-xs dark:bg-transparent"
          />
        </div>
        <button type="button" className={rowClass} onClick={() => pick(null)}>
          <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="flex-1 truncate">New session each run</span>
          {selectedId === null && <Check className="h-3.5 w-3.5 shrink-0" />}
        </button>
        <div className="px-2.5 pb-0.5 pt-1.5 text-[0.8rem] font-normal text-muted-foreground">
          {query.trim() ? 'Matching sessions' : 'Recent sessions'}
        </div>
        <div className="custom-scrollbar max-h-72 space-y-0.5 overflow-y-auto">
          {rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className={rowClass}
              onClick={() => pick(row)}
              title={row.project}
            >
              <MessageCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 truncate">{row.title}</span>
              <span className="shrink-0 text-muted-foreground">{shortDate(row.at)}</span>
              <span className="flex-1" />
              {row.id === selectedId && <Check className="h-3.5 w-3.5 shrink-0" />}
            </button>
          ))}
          {!loading && rows.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-muted-foreground">
              {query.trim() ? 'No sessions match.' : 'No sessions yet.'}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
