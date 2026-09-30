'use client';

/**
 * Move a project into a team, or out of one into your own space
 * (collaboration §3.3). Opened from the project's settings (General → Owner)
 * and from a team's page ("Move a project here"); both hand it the project
 * and the destinations the caller may pick.
 *
 * Keys are unique within the owner (§3.5), so a move can collide where the
 * project never did: the server answers 409 with a free suggestion and the
 * dialog turns into "pick a new key" rather than failing.
 */

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { SeatLimitNotice } from '@/components/billing/seat-limit-notice';
import { ProjectIcon } from '@/components/dashboard/task-ui';
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
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  getBackendAPI,
  seatLimitFromError,
  type ProjectResponse,
  type TeamSummary,
} from '@/lib/backend-api';
import {
  isValidProjectKey,
  moveConsequences,
  normalizeProjectKey,
  projectKeyConflict,
  type MoveDestination,
} from '@/lib/project-transfer';
import { cn } from '@/lib/utils';

const PERSONAL_VALUE = '__personal__';

function DestinationLabel({ destination }: { destination: MoveDestination }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {destination.team ? (
        <PrincipalAvatar
          principal={{
            type: 'team',
            id: destination.team.id,
            name: destination.team.name,
            avatarImageUri: destination.team.avatar_image_uri,
            updatedAt: destination.team.updated_at,
          }}
          size="xs"
        />
      ) : null}
      <span className="truncate">{destination.name}</span>
    </span>
  );
}

export function MoveProjectDialog({
  open,
  onOpenChange,
  project,
  destinations,
  currentTeam,
  initialTeamId,
  onMoved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  project: ProjectResponse;
  destinations: MoveDestination[];
  /** The team that owns it now, when it is a team's. */
  currentTeam: Pick<TeamSummary, 'name'> | null;
  /** Preselect a destination (the team page's "Move a project here"). */
  initialTeamId?: string | null;
  onMoved: (project: ProjectResponse) => void;
}) {
  const valueOf = (d: MoveDestination) => d.teamId ?? PERSONAL_VALUE;
  const [target, setTarget] = useState<string>('');
  const [newKey, setNewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seatLimit, setSeatLimit] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    // Moving hands the project to other people, so where it goes is always
    // a deliberate pick: preselected only when the caller came from that
    // team's page, or when there is nowhere else it could go.
    const preset =
      initialTeamId !== undefined && destinations.some((d) => d.teamId === initialTeamId)
        ? (initialTeamId ?? PERSONAL_VALUE)
        : destinations.length === 1
          ? valueOf(destinations[0])
          : '';
    setTarget(preset);
    setNewKey(null);
    setError(null);
    setSeatLimit(null);
    // Reset per opening only; destinations are stable while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const destination = destinations.find((d) => valueOf(d) === target) ?? null;
  const consequences = destination
    ? moveConsequences(destination, { teamName: currentTeam?.name ?? null }, destination.team?.role ?? null)
    : [];
  const keyInvalid = newKey !== null && !isValidProjectKey(newKey);

  const submit = async () => {
    if (!destination || busy || keyInvalid) return;
    setBusy(true);
    setError(null);
    setSeatLimit(null);
    try {
      const moved = await getBackendAPI(true).transferProject(project.id, {
        team_id: destination.teamId,
        ...(newKey !== null ? { key: normalizeProjectKey(newKey) } : {}),
      });
      onMoved(moved);
      onOpenChange(false);
    } catch (err) {
      const clash = projectKeyConflict(err);
      const seats = seatLimitFromError(err);
      if (clash) {
        setNewKey((prev) => (prev === null ? (clash.suggestedKey ?? '') : prev));
        if (newKey !== null) setError(`That key is also used in ${destination.name}. Try another.`);
      } else if (seats) {
        setSeatLimit(seats.detail);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to move the project');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>Move project</DialogTitle>
          <DialogDescription>
            Change who owns this project. Its tasks, sessions and share links come with it.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2 rounded-md border bg-muted/50 p-3 text-sm">
          <ProjectIcon project={project} />
          <span className="truncate">{project.name}</span>
          {project.key && <span className="shrink-0 text-xs text-muted-foreground">{project.key}</span>}
        </div>

        {destinations.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Join or create a team first, in Settings → Teams.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="move-project-destination" className="text-xs text-muted-foreground">
                Move to
              </Label>
              <Select
                value={target}
                onValueChange={(value) => {
                  setTarget(value);
                  setNewKey(null);
                  setError(null);
                  setSeatLimit(null);
                }}
                disabled={busy}
              >
                <SelectTrigger id="move-project-destination" className="h-9 cursor-pointer text-sm">
                  <SelectValue placeholder="Choose where" />
                </SelectTrigger>
                <SelectContent className="font-mono">
                  {destinations.map((d) => (
                    <SelectItem key={valueOf(d)} value={valueOf(d)} className="cursor-pointer text-sm">
                      <DestinationLabel destination={d} />
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {newKey !== null && destination && (
              <div className="space-y-1.5">
                <Label htmlFor="move-project-key" className="text-xs text-muted-foreground">
                  {project.key} is already used by another project in {destination.name}. New task key
                </Label>
                <Input
                  id="move-project-key"
                  value={newKey}
                  onChange={(e) => {
                    setNewKey(e.target.value.toUpperCase());
                    setError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void submit();
                  }}
                  maxLength={8}
                  autoFocus
                  disabled={busy}
                  className={cn('h-9 w-32 uppercase', keyInvalid && 'border-destructive')}
                />
                <p className="text-xs text-muted-foreground">
                  {keyInvalid
                    ? '2 to 8 letters and digits, starting with a letter.'
                    : `Its tasks will read ${normalizeProjectKey(newKey) || 'KEY'}-1, ${normalizeProjectKey(newKey) || 'KEY'}-2, and so on.`}
                </p>
              </div>
            )}

            {consequences.length > 0 && (
              <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                {consequences.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {seatLimit && <SeatLimitNotice detail={seatLimit} />}
        {error && <p className="text-xs text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={busy || !destination || keyInvalid}
            className="cursor-pointer"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Move project'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
