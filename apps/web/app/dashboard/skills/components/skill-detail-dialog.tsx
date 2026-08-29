'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, FileText, Loader2, Play, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import {
  describeSkillError,
  getSkill,
  type SkillAgentType,
  type SkillDetail,
  type SkillSummary,
} from '../lib/skills-rpc';
import { skillTitle } from '../lib/skills-view';

interface SkillDetailDialogProps {
  open: boolean;
  machineId: string | null;
  agent: SkillAgentType | null;
  skill: SkillSummary | null;
  onOpenChange: (open: boolean) => void;
  onUninstall: (skill: SkillSummary) => void;
  /** Seed a new session with this skill's `/`-command. */
  onTry: (skill: SkillSummary) => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Read-only detail: full SKILL.md + supporting files, with Try / Uninstall. */
export function SkillDetailDialog({
  open,
  machineId,
  agent,
  skill,
  onOpenChange,
  onUninstall,
  onTry,
}: SkillDetailDialogProps) {
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !machineId || !agent || !skill) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetail(null);
    getSkill(machineId, agent, skill.name)
      .then((d) => !cancelled && setDetail(d))
      .catch((err) => !cancelled && setError(describeSkillError(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, machineId, agent, skill]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex min-w-0 items-center gap-2 pr-6">
            {agent && <AgentTypeIcon agentTypeName={agent} size={18} whiteForOpenAI />}
            <span className="truncate">{skill ? skillTitle(skill.name) : ''}</span>
          </DialogTitle>
        </DialogHeader>

        {skill?.description && (
          <p className="break-words text-sm text-muted-foreground">{skill.description}</p>
        )}
        {skill?.source && <SourceLine source={skill.source} />}

        <div className="min-h-[8rem] min-w-0">
          {loading ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : error ? (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          ) : detail ? (
            <div className="min-w-0 space-y-3">
              {/* min-w-0 + break-words lets the pre shrink inside the Dialog's
                  CSS grid (children default to min-width:auto) so long,
                  unbreakable lines wrap instead of widening the dialog; the
                  overflow is the fallback for content that truly can't wrap. */}
              <pre className="custom-scrollbar max-h-[45vh] min-w-0 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 text-xs leading-relaxed">
                {detail.content}
                {detail.truncated && '\n\n… (truncated)'}
              </pre>
              {detail.files.length > 0 && (
                <div>
                  <div className="mb-1 text-xs font-medium text-muted-foreground">
                    Supporting files
                  </div>
                  <ul className="space-y-0.5">
                    {detail.files.map((f) => (
                      <li key={f.path} className="flex items-center gap-1.5 text-xs">
                        <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate font-mono">{f.path}</span>
                        <span className="shrink-0 text-muted-foreground">
                          {formatBytes(f.size)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : null}
        </div>

        <div className="flex items-center gap-2 pt-1">
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
            {detail?.path ?? skill?.path ?? ''}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 gap-1.5 text-destructive hover:text-destructive"
            onClick={() => {
              if (skill) onUninstall(skill);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Uninstall
          </Button>
          <Button
            size="sm"
            className="shrink-0 gap-1.5"
            onClick={() => {
              if (skill) onTry(skill);
            }}
          >
            <Play className="h-3.5 w-3.5" />
            Try now
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SourceLine({ source }: { source: string }) {
  const isHttp = source.startsWith('http://') || source.startsWith('https://');
  if (!isHttp) {
    return <p className="truncate text-xs text-muted-foreground">Installed from {source}</p>;
  }
  return (
    <a
      href={source}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex max-w-full cursor-pointer items-center gap-1 truncate text-xs text-muted-foreground hover:text-foreground hover:underline"
    >
      <ExternalLink className="h-3 w-3 shrink-0" />
      <span className="truncate">{source.replace(/^https?:\/\//, '')}</span>
    </a>
  );
}
