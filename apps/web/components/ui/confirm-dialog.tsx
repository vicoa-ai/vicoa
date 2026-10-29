'use client';

// The in-app "are you sure?" — use it instead of `window.confirm()`. A browser
// confirm is drawn by the browser (or Electron) in its own chrome, ignores the
// theme, and blocks the page; this is the same Dialog as Delete Session and
// Delete Automation, so every confirmation in the product looks like one thing.

import type { ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  preview,
  confirmLabel = 'Delete',
  destructive = true,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  /** What is about to go, shown in a box under the description (a name, a comment's text). */
  preview?: ReactNode;
  confirmLabel?: string;
  /** Red confirm button. On by default: nearly every confirmation is a delete. */
  destructive?: boolean;
  /** Called after the dialog closes; the caller owns any pending/error state. */
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="font-mono">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {preview && <div className="rounded-md border bg-muted/50 p-3 text-sm">{preview}</div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            className={destructive ? 'text-destructive-foreground' : undefined}
            onClick={() => {
              onOpenChange(false);
              onConfirm();
            }}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
