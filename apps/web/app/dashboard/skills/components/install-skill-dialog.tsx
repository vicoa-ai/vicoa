'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  describeSkillError,
  installSkill,
  SkillOpError,
  type SkillAgentType,
  type SkillSummary,
} from '../lib/skills-rpc';

// Where each agent's install lands, shown as a hint under the picker.
const DEST_HINT: Record<string, string> = {
  claude: 'Installs to Claude Code’s skills (~/.claude/skills).',
  codex: 'Installs to the shared skills dir (~/.agents/skills) — also visible to OpenCode.',
  opencode: 'Installs to OpenCode’s skills (~/.config/opencode/skills).',
};

interface InstallSkillDialogProps {
  open: boolean;
  machineId: string | null;
  agents: { value: SkillAgentType; label: string }[];
  defaultAgent: SkillAgentType;
  onOpenChange: (open: boolean) => void;
  onInstalled: (agent: SkillAgentType, skill: SkillSummary) => void;
}

/** Install a skill from a git repo URL onto the selected machine. */
export function InstallSkillDialog({
  open,
  machineId,
  agents,
  defaultAgent,
  onOpenChange,
  onInstalled,
}: InstallSkillDialogProps) {
  const [agent, setAgent] = useState<SkillAgentType>(defaultAgent);
  const [gitUrl, setGitUrl] = useState('');
  const [subdir, setSubdir] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A skill_exists error arms an "Overwrite" confirmation on the next submit.
  const [allowOverwrite, setAllowOverwrite] = useState(false);

  // Re-seed the agent picker to the caller's default each time the dialog opens
  // (the page passes the section the user launched install from).
  useEffect(() => {
    if (open) setAgent(defaultAgent);
  }, [open, defaultAgent]);

  function reset() {
    setGitUrl('');
    setSubdir('');
    setError(null);
    setBusy(false);
    setAllowOverwrite(false);
  }

  async function submit() {
    if (!machineId || !gitUrl.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const skill = await installSkill(machineId, agent, {
        git_url: gitUrl.trim(),
        subdir: subdir.trim() || undefined,
        overwrite: allowOverwrite,
      });
      onInstalled(agent, skill);
      reset();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof SkillOpError && err.code === 'skill_exists') {
        setAllowOverwrite(true);
      }
      setError(describeSkillError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Install a skill</DialogTitle>
          <DialogDescription>
            Clone a public git repository whose root (or a subdirectory) contains a{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">SKILL.md</code>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="skill-agent">Agent</Label>
            <Select value={agent} onValueChange={(v) => setAgent(v as SkillAgentType)}>
              <SelectTrigger id="skill-agent" className="cursor-pointer">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agents.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="cursor-pointer">
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {DEST_HINT[agent] && (
              <p className="text-xs text-muted-foreground">{DEST_HINT[agent]}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="skill-url">Git repository URL</Label>
            <Input
              id="skill-url"
              placeholder="https://github.com/owner/skill-repo"
              value={gitUrl}
              autoFocus
              onChange={(e) => {
                setGitUrl(e.target.value);
                setAllowOverwrite(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submit();
              }}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="skill-subdir">
              Subdirectory <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="skill-subdir"
              placeholder="skills/my-skill"
              value={subdir}
              onChange={(e) => setSubdir(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Use when the skill lives in a folder inside a larger repo.
            </p>
          </div>

          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={busy || !machineId || !gitUrl.trim()}
            className="gap-1.5"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {allowOverwrite ? 'Overwrite & install' : 'Install'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
