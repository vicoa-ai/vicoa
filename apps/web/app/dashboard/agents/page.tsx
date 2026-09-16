'use client';

/**
 * /dashboard/agents — saved agent presets (collaboration P1).
 *
 * An "Agent" is a named provider + model + config + instructions with an
 * avatar: picked in one click when starting a session, referenced by an
 * automation, and (from P2) assignable to a task.
 *
 * It is a top-level page rather than a settings tab because an agent is a thing
 * you *use*, not a preference you set once — and because it has a history. The
 * layout is deliberately the automation page's (list column, draggable divider,
 * detail panel with a Run history card at the bottom): the two are the same kind
 * of object, a saved configuration with a record of what it has done.
 *
 * NOTE the neighbouring routes: `/dashboard/agents/[instanceId]` is a *session*
 * and `/dashboard/agents/new-session` starts one. Those predate this page and
 * keep their URLs; this one owns only the bare path, and selects a row through
 * `?agent=<id>` rather than a sub-route, exactly like `?automation=<id>`.
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Bot, Loader2, Plus } from 'lucide-react';

import { DesktopCollapsedLead } from '@/components/desktop/window-chrome';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AGENT_CATALOG_FALLBACK,
  defaultsFor,
  type AgentCatalog,
} from '@/lib/agent-catalog';
import { DRAG_REGION, NO_DRAG } from '@/lib/app-region';
import type { AgentProfile } from '@/lib/backend-api';
import { useAgentDashboard } from '@/lib/contexts/agent-dashboard-context';
import { AgentDetailPanel } from './components/agent-detail-panel';
import { AgentList } from './components/agent-list';

const LIST_WIDTH_KEY = 'agents:listWidth';

export default function AgentsPage() {
  // useSearchParams needs a Suspense boundary for prerender (same pattern as
  // the automation and new-session pages).
  return (
    <Suspense fallback={null}>
      <AgentsPageInner />
    </Suspense>
  );
}

function AgentsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { api } = useAgentDashboard();

  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AgentProfile | null>(null);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await api.listAgentProfiles();
        if (cancelled) return;
        setProfiles(list);
        // No auto-select: the list is the landing view, same as automations.
        // At full width each row carries its config, description and run count,
        // which is the overview you want before picking one.
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load agents.');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    api
      .getAgentCatalog()
      .then((fresh) => !cancelled && setCatalog(fresh))
      .catch(() => {
        /* the baked-in fallback is already in state */
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  // Deep link (⌘K palette, or a link from the session picker):
  // /dashboard/agents?agent={id} selects that row once it is loaded, then
  // strips the param so refresh/back doesn't re-select it.
  useEffect(() => {
    const agentId = searchParams?.get('agent');
    if (!agentId || !profiles.some((p) => p.id === agentId)) return;
    setSelectedId(agentId);
    router.replace('/dashboard/agents', { scroll: false });
  }, [searchParams, profiles, router]);

  const selected = useMemo(
    () => profiles.find((p) => p.id === selectedId) ?? null,
    [profiles, selectedId],
  );

  const handleCreate = useCallback(async () => {
    if (!api) return;
    setCreating(true);
    setError(null);
    try {
      // Named "New agent 2", "New agent 3"… because the name is unique per user
      // and a second unnamed create would otherwise 409.
      const taken = new Set(profiles.map((p) => p.name.toLowerCase()));
      let name = 'New agent';
      for (let i = 2; taken.has(name.toLowerCase()); i += 1) name = `New agent ${i}`;
      const created = await api.createAgentProfile({
        name,
        agent: 'claude',
        config: defaultsFor(catalog, 'claude') as unknown as Record<string, unknown>,
      });
      setProfiles((prev) => [...prev, created]);
      setSelectedId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create agent.');
    } finally {
      setCreating(false);
    }
  }, [api, catalog, profiles]);

  const replace = useCallback((updated: AgentProfile) => {
    setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!api || !deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    const before = profiles;
    setProfiles((prev) => prev.filter((p) => p.id !== target.id));
    setSelectedId((current) => (current === target.id ? null : current));
    try {
      await api.deleteAgentProfile(target.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent.');
      setProfiles(before);
    }
  }, [api, deleteTarget, profiles]);

  const panelOpen = selected !== null;

  // Draggable divider between the list and the detail panel, persisted so the
  // split survives navigation. Same behaviour as the automation page.
  const [listWidth, setListWidth] = useState(380);
  const listWidthRef = useRef(listWidth);
  listWidthRef.current = listWidth;

  useEffect(() => {
    const saved = Number(window.localStorage.getItem(LIST_WIDTH_KEY));
    if (saved >= 280 && saved <= 720) setListWidth(saved);
  }, []);

  const startDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = listWidthRef.current;
    let latest = startW;
    const onMove = (ev: MouseEvent) => {
      latest = Math.max(280, Math.min(720, startW + (ev.clientX - startX)));
      setListWidth(latest);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      try {
        window.localStorage.setItem(LIST_WIDTH_KEY, String(Math.round(latest)));
      } catch {
        /* ignore */
      }
    };
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  return (
    <main className="flex h-full overflow-hidden">
      <div
        className="flex min-w-0 shrink-0 flex-col"
        style={panelOpen ? { width: listWidth } : { flex: 1 }}
      >
        {/* On desktop this header is the window titlebar: a drag region with the
            controls opting back out via NO_DRAG (and the collapsed-sidebar lead
            clearing the macOS traffic lights). */}
        <div
          style={DRAG_REGION}
          className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4"
        >
          <DesktopCollapsedLead />
          <Bot className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h1 className="shrink-0 text-sm font-medium">Agents</h1>
          <div style={NO_DRAG} className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={() => void handleCreate()}
              disabled={!api || creating}
            >
              {creating ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Plus className="size-3.5" />
              )}
              New agent
            </Button>
          </div>
        </div>

        {error && (
          <div className="border-b border-border bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : profiles.length === 0 ? (
          <EmptyState onCreate={() => void handleCreate()} disabled={!api || creating} />
        ) : (
          <AgentList
            profiles={profiles}
            catalog={catalog}
            selectedId={selectedId}
            onSelect={(p) => setSelectedId(p.id)}
            onDelete={(p) => setDeleteTarget(p)}
            wide={!panelOpen}
          />
        )}
      </div>

      {panelOpen && api && (
        <>
          {/* Thin divider with a wider invisible hit area for grabbing. */}
          <div
            onMouseDown={startDrag}
            className="relative w-px shrink-0 cursor-col-resize bg-border transition-colors before:absolute before:inset-y-0 before:-left-1.5 before:-right-1.5 before:content-[''] hover:bg-primary/40"
            title="Drag to resize"
          />
          <div className="min-w-0 flex-1">
            <AgentDetailPanel
              key={selected.id}
              api={api}
              profile={selected}
              catalog={catalog}
              onReplace={replace}
              onDelete={(p) => setDeleteTarget(p)}
              onClose={() => setSelectedId(null)}
            />
          </div>
        </>
      )}

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete agent</DialogTitle>
            <DialogDescription>
              {/* Deleting is safe by design: an automation that referenced this
                  agent falls back to the configuration it saved alongside the
                  reference, so a scheduled run never lands without one. */}
              Delete{deleteTarget ? ` “${deleteTarget.name}”` : ''}? Sessions it already
              started are unaffected, and automations that use it keep running off
              their saved configuration.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void confirmDelete()}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

function EmptyState({ onCreate, disabled }: { onCreate: () => void; disabled: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <Bot className="size-8 text-muted-foreground/50" />
      <h2 className="mt-4 text-sm font-medium">No agents yet</h2>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">
        An agent saves a provider, model and instructions under one name, so you can
        pick it in one click when you start a session or schedule an automation.
      </p>
      <Button size="sm" className="mt-4 gap-1 text-xs" onClick={onCreate} disabled={disabled}>
        <Plus className="size-3.5" />
        New agent
      </Button>
    </div>
  );
}
