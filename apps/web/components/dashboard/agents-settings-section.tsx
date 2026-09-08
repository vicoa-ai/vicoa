'use client';

/**
 * Settings > Agents — where saved agent presets are created and edited
 * (collaboration P1, `plans/todos/agent-profiles-p1.md`).
 *
 * An "Agent" is a name + avatar over `provider + model + config + instructions`.
 * The config body is the SAME `<SessionConfigEditor>` the automation editor
 * uses, deliberately: a preset is nothing more than a saved instance of the
 * picker the user already knows, and reusing it means the two can never offer
 * different options for the same agent.
 *
 * Rendered from both settings trees (web `app/dashboard/settings/page.tsx` and
 * desktop `desktop-settings.tsx`) — see §11 of the parent plan for why that has
 * to be explicit.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { UserAvatarEditor } from '@/components/dashboard/user-avatar-editor';
import { SessionConfigEditor } from '@/components/dashboard/session-config-editor';
import {
  AGENT_CATALOG_FALLBACK,
  defaultsFor,
  reconcileAgainst,
  type AgentCatalog,
  type SessionConfig,
} from '@/lib/agent-catalog';
import { getBackendAPI, type AgentProfile } from '@/lib/backend-api';
import { cn } from '@/lib/utils';

/** A profile's stored `config` is already a SessionConfig — this only repairs
 *  stale ids against the live catalog, which is the whole reason the column is
 *  stored in that exact shape. */
function toSessionConfig(profile: AgentProfile, catalog: AgentCatalog): SessionConfig {
  return reconcileAgainst(
    { ...(profile.config as unknown as SessionConfig), agent: profile.agent },
    catalog,
  );
}

function principalFor(profile: AgentProfile) {
  return {
    type: 'agent' as const,
    id: profile.id,
    name: profile.name,
    avatarImageUri: profile.avatar_image_uri,
    updatedAt: profile.updated_at,
  };
}

export function AgentsSettingsSection() {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [catalog, setCatalog] = useState<AgentCatalog>(AGENT_CATALOG_FALLBACK);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await getBackendAPI(true).listAgentProfiles();
      setProfiles(list);
      setSelectedId((current) => current ?? list[0]?.id ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agents.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    getBackendAPI(true)
      .getAgentCatalog()
      .then(setCatalog)
      .catch(() => {
        /* the baked-in fallback is already in state */
      });
  }, []);

  const selected = useMemo(
    () => profiles.find((p) => p.id === selectedId) ?? null,
    [profiles, selectedId],
  );

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      // Named "New agent 2", "New agent 3"… because the name is unique per user
      // and a second unnamed create would otherwise 409.
      const taken = new Set(profiles.map((p) => p.name.toLowerCase()));
      let name = 'New agent';
      for (let i = 2; taken.has(name.toLowerCase()); i += 1) name = `New agent ${i}`;
      const created = await getBackendAPI(true).createAgentProfile({
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
  };

  const patch = useCallback(
    async (id: string, input: Parameters<ReturnType<typeof getBackendAPI>['updateAgentProfile']>[1]) => {
      const updated = await getBackendAPI(true).updateAgentProfile(id, input);
      setProfiles((prev) => prev.map((p) => (p.id === id ? updated : p)));
      return updated;
    },
    [],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading agents…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Save a provider, model and instructions under one name, then pick it in one
          click when you start a session or schedule an automation.
        </p>
        <Button size="sm" onClick={handleCreate} disabled={creating}>
          {creating ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Plus className="mr-2 h-4 w-4" />
          )}
          New agent
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {profiles.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          No agents yet.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
          <ul className="space-y-1">
            {profiles.map((profile) => (
              <li key={profile.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(profile.id)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors',
                    profile.id === selectedId
                      ? 'bg-muted text-foreground'
                      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                  )}
                >
                  <PrincipalAvatar principal={principalFor(profile)} size="sm" />
                  <span className="min-w-0 truncate">{profile.name}</span>
                </button>
              </li>
            ))}
          </ul>

          {selected && (
            <AgentProfileEditor
              key={selected.id}
              profile={selected}
              catalog={catalog}
              onPatch={patch}
              onDeleted={(id) => {
                setProfiles((prev) => prev.filter((p) => p.id !== id));
                setSelectedId((current) => (current === id ? null : current));
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

function AgentProfileEditor({
  profile,
  catalog,
  onPatch,
  onDeleted,
}: {
  profile: AgentProfile;
  catalog: AgentCatalog;
  onPatch: (
    id: string,
    input: Parameters<ReturnType<typeof getBackendAPI>['updateAgentProfile']>[1],
  ) => Promise<AgentProfile>;
  onDeleted: (id: string) => void;
}) {
  const [name, setName] = useState(profile.name);
  const [description, setDescription] = useState(profile.description ?? '');
  const [systemPrompt, setSystemPrompt] = useState(profile.system_prompt ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const config = useMemo(() => toSessionConfig(profile, catalog), [profile, catalog]);

  const save = async (
    input: Parameters<ReturnType<typeof getBackendAPI>['updateAgentProfile']>[1],
  ) => {
    setBusy(true);
    setError(null);
    try {
      await onPatch(profile.id, input);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save.');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    const affected = await getBackendAPI(true)
      .deleteAgentProfile(profile.id)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to delete.');
        return null;
      });
    if (affected) onDeleted(profile.id);
  };

  return (
    <div className="space-y-5 rounded-xl border p-4">
      <div className="flex items-start gap-4">
        <UserAvatarEditor
          principal={principalFor(profile)}
          onUploadImage={async (file) => {
            await getBackendAPI(true).uploadAgentProfileAvatar(profile.id, file);
            await onPatch(profile.id, {});
          }}
          onRemoveImage={async () => {
            await getBackendAPI(true).deleteAgentProfileAvatar(profile.id);
            await onPatch(profile.id, {});
          }}
        />
        <div className="grid flex-1 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`agent-name-${profile.id}`}>Name</Label>
            <Input
              id={`agent-name-${profile.id}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => {
                const trimmed = name.trim();
                if (trimmed && trimmed !== profile.name) void save({ name: trimmed });
                else setName(profile.name);
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`agent-desc-${profile.id}`}>Description</Label>
            <Input
              id={`agent-desc-${profile.id}`}
              value={description}
              placeholder="What this agent is for"
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => {
                if (description !== (profile.description ?? '')) {
                  void save({ description: description.trim() || null });
                }
              }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Configuration</Label>
        {/* The same picker the new-session composer and automation editor use. */}
        <SessionConfigEditor
          value={config}
          catalog={catalog}
          onChange={(next) =>
            void save({
              agent: next.agent,
              config: next as unknown as Record<string, unknown>,
            })
          }
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`agent-prompt-${profile.id}`}>Instructions</Label>
        <textarea
          id={`agent-prompt-${profile.id}`}
          spellCheck={false}
          value={systemPrompt}
          placeholder="Extra instructions this agent always follows, e.g. &ldquo;Prefer small, reviewable diffs.&rdquo;"
          className="custom-scrollbar h-32 w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-xs leading-relaxed outline-none focus:border-primary/60"
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setSystemPrompt(e.target.value)}
          onBlur={() => {
            if (systemPrompt !== (profile.system_prompt ?? '')) {
              void save({ system_prompt: systemPrompt.trim() || null });
            }
          }}
        />
        <p className="text-xs text-muted-foreground">
          Applied when the session starts, on top of the agent&apos;s own instructions.
          Changing this affects new sessions — a session already running keeps what it
          started with.
        </p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex items-center justify-between">
        {busy ? (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Saving…
          </span>
        ) : (
          <span />
        )}
        <Button variant="ghost" size="sm" onClick={handleDelete}>
          <Trash2 className="mr-2 h-4 w-4" />
          Delete
        </Button>
      </div>
    </div>
  );
}
