'use client';

/**
 * One agent's pane: identity, configuration, instructions, run history.
 *
 * The config body is the SAME `<SessionConfigEditor>` the automation editor and
 * the new-session composer use — a preset is nothing more than a saved instance
 * of the picker the user already knows, and sharing the component means the two
 * can never offer different options for the same provider.
 *
 * Edits save on blur rather than behind a Save button. There is no partially
 * valid agent (every field is independently meaningful, and the config chips
 * commit on click), so a form-level commit step would only add a way to lose
 * work by navigating away.
 */

import { useMemo, useState } from 'react';
import { Loader2, Trash2, X } from 'lucide-react';

import { AvatarEditor } from '@/components/dashboard/avatar-editor';
import { SessionConfigEditor } from '@/components/dashboard/session-config-editor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  reconcileAgainst,
  type AgentCatalog,
  type SessionConfig,
} from '@/lib/agent-catalog';
import type { AgentProfile, AgentProfileInput, getBackendAPI } from '@/lib/backend-api';
import { agentPrincipal } from '@/lib/use-agent-profiles';
import { FieldGroup } from '../../automation/components/field-row';
import { RunHistorySection } from './run-history-section';

type Api = ReturnType<typeof getBackendAPI>;

/** A profile's stored `config` is already a SessionConfig — this only repairs
 *  stale ids against the live catalog, which is the whole reason the column is
 *  stored in that exact shape. */
function toSessionConfig(profile: AgentProfile, catalog: AgentCatalog): SessionConfig {
  return reconcileAgainst(
    { ...(profile.config as unknown as SessionConfig), agent: profile.agent },
    catalog,
  );
}

export function AgentDetailPanel({
  api,
  profile,
  catalog,
  onReplace,
  onDelete,
  onClose,
}: {
  api: Api;
  profile: AgentProfile;
  catalog: AgentCatalog;
  /** Hand the server's updated row back to the list, which owns the state. */
  onReplace: (profile: AgentProfile) => void;
  onDelete: (profile: AgentProfile) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(profile.name);
  const [description, setDescription] = useState(profile.description ?? '');
  const [systemPrompt, setSystemPrompt] = useState(profile.system_prompt ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const config = useMemo(() => toSessionConfig(profile, catalog), [profile, catalog]);

  /** Every write goes through here: one busy flag, one error surface, and the
   *  server's row is what lands in state — never an optimistic local guess. */
  const commit = async (write: () => Promise<AgentProfile>) => {
    setBusy(true);
    setError(null);
    try {
      onReplace(await write());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save.');
    } finally {
      setBusy(false);
    }
  };

  const save = (input: AgentProfileInput) =>
    commit(() => api.updateAgentProfile(profile.id, input));

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
        <span className="text-xs text-muted-foreground">Agent</span>
        <div className="ml-auto flex items-center gap-1.5">
          {busy && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Saving…
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() => onDelete(profile)}
          >
            <Trash2 className="size-3.5" />
            Delete
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {/* Identity. Only the avatar and the name pair up — the avatar names the
            thing, so it sits beside what it names. Every field below starts at
            the pane's left edge, Description included: indenting it under the
            avatar put it on a private margin that Configuration and
            Instructions don't share, which reads as an accident. */}
        <div className="flex items-center gap-4">
          <AvatarEditor
            principal={agentPrincipal(profile)}
            onUploadImage={(file) =>
              commit(() => api.uploadAgentProfileAvatar(profile.id, file))
            }
            onRemoveImage={() => commit(() => api.deleteAgentProfileAvatar(profile.id))}
            onSetEmoji={(emoji) => save({ emoji })}
            onClearEmoji={() => save({ emoji: null })}
          />
          <div className="flex-1 space-y-1.5">
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

        <FieldGroup title="Configuration">
          {/* The editor brings its own flex-wrap row of chips. */}
          <div className="px-2 py-2">
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
        </FieldGroup>

        <div className="space-y-1.5">
          <Label htmlFor={`agent-prompt-${profile.id}`}>Instructions</Label>
          <textarea
            id={`agent-prompt-${profile.id}`}
            spellCheck={false}
            value={systemPrompt}
            placeholder="Define this agent's role, expertise, working style…"
            className="custom-scrollbar h-32 w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-xs leading-relaxed outline-none focus:border-primary/60"
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
              setSystemPrompt(e.target.value)
            }
            onBlur={() => {
              if (systemPrompt !== (profile.system_prompt ?? '')) {
                void save({ system_prompt: systemPrompt.trim() || null });
              }
            }}
          />
        </div>

        <RunHistorySection api={api} agentId={profile.id} />

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
    </div>
  );
}
