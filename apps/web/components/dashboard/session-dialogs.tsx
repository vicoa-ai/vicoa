import { useEffect, useState } from 'react';
import { GitBranch, GitCommitHorizontal, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CheckoutRefTag } from '@/components/checkout-ref-tag';
import { checkoutRefLabel, checkoutRefTag, type CheckoutRef } from '@/lib/checkout-ref';

export function RenameSessionDialog({
  open,
  onOpenChange,
  sessionId,
  currentName,
  onRename
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  currentName: string;
  onRename: (id: string, name: string) => void;
}) {
  const [name, setName] = useState(currentName);

  // The dialog stays mounted, so useState(currentName) only captures the
  // initial (empty) value. Re-sync to the current name each time it opens.
  useEffect(() => {
    if (open) {
      setName(currentName);
    }
  }, [open, currentName]);

  const handleSubmit = () => {
    if (name.trim() && name !== currentName) {
      onRename(sessionId, name.trim());
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>Rename Session</DialogTitle>
          <DialogDescription>
            Enter a new name for this session.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="flex items-center gap-4">
            <Label htmlFor="name">
              Name
            </Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 focus:border-0"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleSubmit();
                }
              }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!name.trim() || name === currentName}>
            Rename
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteSessionDialog({
  open,
  onOpenChange,
  sessionId,
  sessionName,
  onDelete
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  sessionName: string;
  onDelete: (id: string) => void;
}) {
  const handleDelete = () => {
    onDelete(sessionId);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>Delete Session</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete this session? This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {sessionName && (
          <div className="p-3 border rounded-md bg-muted/50">
            <div className="font-medium text-sm">{sessionName}</div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            className="text-destructive-foreground"
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Confirm removing a git worktree from the sidebar (feature #4). Shown when the
 * removal isn't clean — a live session and/or uncommitted changes. A running
 * session is archived before the folder is removed; the branch and its commits
 * are always kept, which the copy states so the user knows work survives. A
 * detached worktree has no branch to keep its commits, and one mid-rebase loses
 * the rebase, so for those the copy says what is kept instead.
 */
export function WorktreeDeleteDialog({
  open,
  onOpenChange,
  checkoutRef,
  hasSession,
  isDirty,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What the worktree has checked out; null only while the dialog is closed. */
  checkoutRef: CheckoutRef | null;
  hasSession: boolean;
  isDirty: boolean;
  error: string | null;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>Delete worktree</DialogTitle>
          <DialogDescription>
            {checkoutRef?.kind === 'detached'
              ? "This removes the worktree's folder. It isn't on a branch, so commits that exist only in it are not kept."
              : checkoutRef?.kind === 'rebasing'
                ? "This removes the worktree's folder and drops the rebase in progress. Its branch keeps the commits it had before the rebase."
                : "This removes the worktree's folder. Its branch and commits are kept."}
          </DialogDescription>
        </DialogHeader>
        <div className="p-3 border rounded-md bg-muted/50 flex items-center gap-2">
          {checkoutRef?.kind === 'detached' ? (
            <GitCommitHorizontal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span
            className="font-medium text-sm truncate"
            title={checkoutRef ? checkoutRefTag(checkoutRef)?.title : undefined}
          >
            {checkoutRef ? checkoutRefLabel(checkoutRef) : ''}
          </span>
          {checkoutRef && <CheckoutRefTag checkoutRef={checkoutRef} />}
        </div>
        {(hasSession || isDirty) && (
          <ul className="text-xs text-muted-foreground list-disc pl-5 space-y-0.5">
            {hasSession && <li>Its running session will be archived first.</li>}
            {isDirty && <li>Uncommitted changes in it will be lost.</li>}
          </ul>
        )}
        {error && (
          <div className="text-xs text-destructive break-words">
            Couldn&apos;t delete: {error}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            className="text-destructive-foreground"
            onClick={onConfirm}
          >
            {error ? 'Retry' : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Generic destructive-action confirm, the same shape as `DeleteSessionDialog`:
 * header + consequence copy, the subject echoed in a muted card, Cancel /
 * destructive Delete. `onConfirm` runs to completion before the dialog closes;
 * a thrown error stays open so the caller can surface it. Used by the label
 * and project deletes in Settings.
 */
export function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  subject,
  confirmLabel = 'Delete',
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  /** Rendered in the muted card — the row being deleted. */
  subject?: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  const handleConfirm = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {subject && <div className="rounded-md border bg-muted/50 p-3">{subject}</div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            className="text-destructive-foreground"
            onClick={() => void handleConfirm()}
            disabled={busy}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
