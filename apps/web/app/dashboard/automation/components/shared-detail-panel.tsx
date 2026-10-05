'use client';

import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { ProjectIcon } from '@/components/dashboard/task-ui';
import {
  sessionConfigSummaryRows,
  type AgentCatalog,
  type SessionConfig,
} from '@/lib/agent-catalog';
import type {
  AutomationResponse,
  getBackendAPI,
  ProjectResponse,
} from '@/lib/backend-api';
import { principalDisplayName, principalFromResponse } from '@/lib/principals';
import { summarizeSchedule } from '../lib/frequency';
import { FieldGroup, FieldRow } from './field-row';
import { RunHistorySection } from './run-history-section';

type Api = ReturnType<typeof getBackendAPI>;

/**
 * Someone else's automation, read-only. It reaches the viewer through a
 * project whose sessions they can see; editing, running and deleting stay with
 * its author, because a run starts an agent on the author's machine. The row
 * arrives redacted (no machine, the folder's name only), so this panel shows
 * what the automation does and when, never where it runs.
 */
export function SharedDetailPanel({
  api,
  automation,
  project,
  catalog,
  onClose,
}: {
  api: Api;
  automation: AutomationResponse;
  project: ProjectResponse | null;
  catalog: AgentCatalog;
  onClose: () => void;
}) {
  const author = principalFromResponse(automation.owner);
  const config = automation.session_config as unknown as SessionConfig;
  const agentRows = config.agent ? sessionConfigSummaryRows(catalog, config) : [];

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
        <span className="min-w-0 truncate text-xs text-muted-foreground">
          {automation.enabled ? 'Active' : 'Paused'}
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 cursor-pointer"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <div className="space-y-1.5">
          <h2 className="break-words text-lg font-medium">{automation.title}</h2>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {author && <PrincipalAvatar principal={author} size="xs" />}
            <span>
              {principalDisplayName(author)}&apos;s automation. Only they can edit, run or
              pause it.
            </span>
          </div>
        </div>

        <div className="whitespace-pre-wrap break-words rounded-lg border border-border/60 bg-card/40 px-3 py-2 text-sm">
          {automation.prompt}
        </div>

        <FieldGroup title="Details">
          {project && (
            <FieldRow label="Project">
              <span className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
                <ProjectIcon project={project} />
                <span className="truncate">{project.name}</span>
              </span>
            </FieldRow>
          )}
          {automation.directory && (
            <FieldRow label="Folder">
              <span className="truncate text-sm text-muted-foreground">
                {automation.directory}
              </span>
            </FieldRow>
          )}
          {agentRows.length > 0 && (
            <FieldRow label="Agent" align="start">
              <div className="flex min-w-0 flex-col items-end gap-0.5 pt-1 text-sm text-muted-foreground">
                {agentRows.map((row) => (
                  <span key={row.join('/')} className="truncate">
                    {row.join(' · ')}
                  </span>
                ))}
              </div>
            </FieldRow>
          )}
          <FieldRow label="Schedule">
            <span className="truncate text-sm text-muted-foreground">
              {summarizeSchedule(automation)}
            </span>
          </FieldRow>
        </FieldGroup>

        <RunHistorySection
          api={api}
          automationId={automation.id}
          title={automation.title}
        />
      </div>
    </div>
  );
}
