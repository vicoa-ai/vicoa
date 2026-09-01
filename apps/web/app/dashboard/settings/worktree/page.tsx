'use client';

/**
 * Per-repo worktree setup/teardown editor. Reached from a project's three-dot
 * menu in the sidebar (carries `machineId` + `dir`). It reads/edits/writes the
 * committed config file (`.vicoa/config.json`, else root `vicoa.json`) on that
 * machine over the daemon's `read-file`/`write-file` RPCs — the same file the
 * daemon runs at worktree create/remove. No cloud storage: the config lives in
 * the repo, git-versioned, exactly like Paseo's `paseo.json`.
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, GitBranch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SingleDotSpinner } from '@/components/ui/spinners';
import { rpcReadFile, rpcWriteFile, isWriteConflict } from '@/components/files-git-panel/rpc';
import { RpcError } from '@/lib/ws-client';
import {
  applyDraftToConfig,
  configToDraft,
  isDraftEmpty,
  type WorktreeConfigDraft,
} from '@/lib/worktree-config-form';

// Priority order mirrors the daemon's reader (protocol.worktree_config).
const CONFIG_FILES = ['.vicoa/config.json', 'vicoa.json'] as const;

interface Loaded {
  targetPath: string;
  baseHash: string | null;
  baseConfig: unknown;
  draft: WorktreeConfigDraft;
}

function isPathNotFound(err: unknown): boolean {
  return err instanceof RpcError && err.message === 'path_not_found';
}

/** Read the first existing config file; default a new one to root vicoa.json
 * (repo root always exists — write-file can't create the `.vicoa/` dir). */
async function loadConfig(machineId: string, dir: string): Promise<Loaded> {
  for (const path of CONFIG_FILES) {
    let content: string;
    let hash: string | null;
    try {
      const res = await rpcReadFile(machineId, dir, path);
      content = res.content;
      hash = res.content_hash ?? null;
    } catch (err) {
      if (isPathNotFound(err)) continue;
      throw err;
    }
    let parsed: unknown;
    try {
      parsed = content.trim().length === 0 ? {} : JSON.parse(content);
    } catch {
      throw new Error(`${path} is not valid JSON — fix it manually before editing here.`);
    }
    return { targetPath: path, baseHash: hash, baseConfig: parsed, draft: configToDraft(parsed) };
  }
  return {
    targetPath: 'vicoa.json',
    baseHash: null,
    baseConfig: null,
    draft: configToDraft(null),
  };
}

function WorktreeSettingsInner() {
  const params = useSearchParams();
  const machineId = params.get('machineId') ?? '';
  const dir = params.get('dir') ?? '';
  const label = params.get('label') ?? '';

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<WorktreeConfigDraft | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<
    { kind: 'idle' } | { kind: 'saving' } | { kind: 'saved' } | { kind: 'error'; message: string }
  >({ kind: 'idle' });

  const reload = useCallback(async () => {
    if (!machineId || !dir) {
      setLoadError('Missing machine or directory.');
      return;
    }
    setLoaded(null);
    setDraft(null);
    setLoadError(null);
    setSaveState({ kind: 'idle' });
    try {
      const next = await loadConfig(machineId, dir);
      setLoaded(next);
      setDraft(next.draft);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load config.');
    }
  }, [machineId, dir]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const dirty = useMemo(() => {
    if (!loaded || !draft) return false;
    return (
      draft.setupText !== loaded.draft.setupText ||
      draft.teardownText !== loaded.draft.teardownText
    );
  }, [loaded, draft]);

  const save = useCallback(async () => {
    if (!loaded || !draft) return;
    setSaveState({ kind: 'saving' });
    const next = applyDraftToConfig(draft, loaded.baseConfig);
    // Nothing to write for a never-existed, now-empty config.
    if (loaded.baseHash === null && Object.keys(next).length === 0) {
      setLoaded({ ...loaded, draft });
      setSaveState({ kind: 'saved' });
      return;
    }
    const content = `${JSON.stringify(next, null, 2)}\n`;
    try {
      const res = await rpcWriteFile(machineId, dir, loaded.targetPath, content, loaded.baseHash);
      if (isWriteConflict(res)) {
        setSaveState({
          kind: 'error',
          message: 'The file changed on disk (agent or another edit). Reload before saving.',
        });
        return;
      }
      setLoaded({ ...loaded, baseHash: res.content_hash, baseConfig: next, draft });
      setSaveState({ kind: 'saved' });
    } catch (err) {
      setSaveState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Save failed.',
      });
    }
  }, [loaded, draft, machineId, dir]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-4 lg:p-6">
      <div className="flex items-center gap-3">
        <Link
          href="/dashboard"
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          title="Back"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex min-w-0 items-center gap-2">
          <GitBranch className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h1 className="truncate text-lg font-medium">Worktree setup{label ? ` — ${label}` : ''}</h1>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        Shell commands run when a worktree of this repo is created (<b>setup</b>) or removed
        (<b>teardown</b>) — one command per line. Stored in the repo&apos;s config file
        {loaded ? (
          <>
            {' '}
            (<code className="font-mono text-xs">{loaded.targetPath}</code>)
          </>
        ) : null}
        , so <b>commit it</b> for teardown and other machines to pick it up.
      </p>

      {loadError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
          <div className="mt-2">
            <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void reload()}>
              Retry
            </Button>
          </div>
        </div>
      ) : !draft ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <SingleDotSpinner /> Loading config…
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="wt-setup">Setup</Label>
            <textarea
              id="wt-setup"
              spellCheck={false}
              value={draft.setupText}
              onChange={(e) => setDraft({ ...draft, setupText: e.target.value })}
              placeholder={'npm ci\nnpm run build'}
              className="custom-scrollbar h-40 w-full resize-y rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-primary/60"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="wt-teardown">Teardown</Label>
            <textarea
              id="wt-teardown"
              spellCheck={false}
              value={draft.teardownText}
              onChange={(e) => setDraft({ ...draft, teardownText: e.target.value })}
              placeholder={'rm -rf node_modules'}
              className="custom-scrollbar h-28 w-full resize-y rounded-md border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed outline-none focus:border-primary/60"
            />
          </div>

          <div className="flex items-center gap-3">
            <Button
              className="cursor-pointer"
              disabled={!dirty || saveState.kind === 'saving'}
              onClick={() => void save()}
            >
              {saveState.kind === 'saving' ? 'Saving…' : 'Save'}
            </Button>
            {saveState.kind === 'saved' && !dirty ? (
              <span className="text-sm text-muted-foreground">Saved{isDraftEmpty(draft) ? ' (empty)' : ''}.</span>
            ) : null}
            {saveState.kind === 'error' ? (
              <span className="flex items-center gap-2 text-sm text-destructive">
                {saveState.message}
                <button
                  className="cursor-pointer underline"
                  onClick={() => void reload()}
                  type="button"
                >
                  Reload
                </button>
              </span>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

export default function WorktreeSettingsPage() {
  return (
    <Suspense fallback={null}>
      <WorktreeSettingsInner />
    </Suspense>
  );
}
