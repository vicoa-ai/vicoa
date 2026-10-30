/**
 * App-wide toasts, the replacement for `window.alert()`.
 *
 * Call `toast.error("Couldn't pin session")` from anywhere: a component, a
 * hook, a plain async helper. `<Toaster>` (components/ui/toaster.tsx, mounted
 * once in the root layout) draws the queue. The queue lives in this module,
 * outside React, so a caller needs no provider or hook.
 */

export type ToastKind = 'error' | 'success';

export interface ToastOptions {
  /** A second, muted line: the reason it failed, or what to do next. */
  description?: string;
}

export interface ToastItem {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
  /** False while the toast plays its exit animation, just before it is dropped. */
  open: boolean;
}

/** A burst of failures shows the newest few; older ones are dropped. */
export const MAX_TOASTS = 3;
/** Longer than the exit animation, so the toast is gone from the screen before it unmounts. */
export const EXIT_MS = 200;

let toasts: ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit(next: ToastItem[]): void {
  toasts = next;
  for (const listener of listeners) listener();
}

function show(kind: ToastKind, title: string, options?: ToastOptions): number {
  const id = nextId++;
  const description = options?.description;
  // The same message again (a double-click, a retry that failed the same way)
  // replaces the one on screen instead of stacking a copy, and restarts its timer.
  const others = toasts.filter(
    (t) => !(t.kind === kind && t.title === title && t.description === description),
  );
  emit([...others, { id, kind, title, description, open: true }].slice(-MAX_TOASTS));
  return id;
}

function dismiss(id: number): void {
  if (!toasts.some((t) => t.id === id && t.open)) return;
  emit(toasts.map((t) => (t.id === id ? { ...t, open: false } : t)));
  setTimeout(() => emit(toasts.filter((t) => t.id !== id)), EXIT_MS);
}

export const toast = {
  error: (title: string, options?: ToastOptions): number => show('error', title, options),
  success: (title: string, options?: ToastOptions): number => show('success', title, options),
  dismiss,
};

export function subscribeToasts(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getToasts(): ToastItem[] {
  return toasts;
}
