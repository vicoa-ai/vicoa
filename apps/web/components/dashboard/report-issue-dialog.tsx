'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { getBackendAPI } from '@/lib/backend-api';

const MAX_LENGTH = 1000;

const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

const SUSPICIOUS_PATTERN =
  /<[a-z]|function\s*\(|WebSocket|eval\s*\(|setTimeout|setInterval|document\.|window\.|SELECT\s+\*|DROP\s+TABLE|INSERT\s+INTO|<script|<iframe|javascript:/i;

interface ReportIssueDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userEmail?: string;
}

export function ReportIssueDialog({ open, onOpenChange, userEmail }: ReportIssueDialogProps) {
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleClose = () => {
    if (isSubmitting) return;
    setMessage('');
    setError(null);
    setSuccess(false);
    onOpenChange(false);
  };

  const handleSubmit = async () => {
    const trimmed = message.trim();
    if (!trimmed) return;

    if (SUSPICIOUS_PATTERN.test(trimmed)) {
      setError('Your message contains content that cannot be submitted. Please revise it.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const systemInfo = [
        `Platform: ${IS_DESKTOP ? 'desktop' : 'web'}`,
        `OS: ${navigator.platform || 'unknown'}`,
        `UA: ${navigator.userAgent}`,
        userEmail ? `User: ${userEmail}` : null,
        `Date: ${new Date().toISOString()}`,
      ]
        .filter(Boolean)
        .join('\n');

      const fullMessage = `${trimmed}\n\n---\n${systemInfo}`;

      await getBackendAPI(true).reportIssue({ message: fullMessage });
      setSuccess(true);
      setMessage('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const remaining = MAX_LENGTH - message.length;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Report an Issue</DialogTitle>
          <DialogDescription>
            Describe the issue you encountered; we'll fix it.
          </DialogDescription>
        </DialogHeader>

        {success ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <CheckCircle2 className="h-10 w-10 text-green-500" />
            <p className="font-medium">Thank you for sharing with us!</p>
            <p className="text-sm text-muted-foreground">
              We'll review the issue and try our best to fix it for you.
            </p>
            <Button variant="ghost" onClick={handleClose} className="mt-2">
              Close
            </Button>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <textarea
                className="w-full min-h-[140px] resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                placeholder="The issue is…"
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value.slice(0, MAX_LENGTH));
                  setError(null);
                }}
                disabled={isSubmitting}
              />
              <div className="flex items-center justify-between">
                {error ? (
                  <span className="flex items-center gap-1.5 text-xs text-destructive">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    {error}
                  </span>
                ) : (
                  <span />
                )}
                <span
                  className={`ml-auto text-xs tabular-nums ${
                    remaining <= 0
                      ? 'text-destructive'
                      : remaining < 100
                        ? 'text-yellow-500'
                        : 'text-muted-foreground'
                  }`}
                >
                  {remaining}/{MAX_LENGTH}
                </span>
              </div>
            </div>

            <DialogFooter>
              <Button variant="ghost" onClick={handleClose} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={!message.trim() || isSubmitting || remaining < 0}
              >
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Send
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
