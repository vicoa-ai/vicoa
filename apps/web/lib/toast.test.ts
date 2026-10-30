import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The queue is module state, so each test loads a fresh copy.
async function load() {
  vi.resetModules();
  return import('./toast');
}

describe('toast queue', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('queues errors and successes with their description', async () => {
    const { toast, getToasts } = await load();
    toast.error("Couldn't pin session");
    toast.success('Test notification sent', { description: 'Check your notifications.' });
    expect(getToasts().map(({ kind, title, description, open }) => ({ kind, title, description, open }))).toEqual([
      { kind: 'error', title: "Couldn't pin session", description: undefined, open: true },
      { kind: 'success', title: 'Test notification sent', description: 'Check your notifications.', open: true },
    ]);
  });

  it('replaces a repeat of the same message instead of stacking it', async () => {
    const { toast, getToasts } = await load();
    const first = toast.error("Couldn't pin session");
    toast.error("Couldn't rename session");
    const again = toast.error("Couldn't pin session");
    expect(again).not.toBe(first);
    expect(getToasts().map((t) => t.title)).toEqual(["Couldn't rename session", "Couldn't pin session"]);
  });

  it('keeps only the newest few', async () => {
    const { toast, getToasts, MAX_TOASTS } = await load();
    for (let i = 0; i < MAX_TOASTS + 2; i++) toast.error(`Error ${i}`);
    expect(getToasts().map((t) => t.title)).toEqual(
      Array.from({ length: MAX_TOASTS }, (_, i) => `Error ${i + 2}`),
    );
  });

  it('closes first, then drops the toast once the exit animation is done', async () => {
    const { toast, getToasts, EXIT_MS } = await load();
    const id = toast.error("Couldn't pin session");
    toast.dismiss(id);
    expect(getToasts()).toEqual([expect.objectContaining({ id, open: false })]);
    vi.advanceTimersByTime(EXIT_MS);
    expect(getToasts()).toEqual([]);
  });

  it('notifies subscribers until they unsubscribe', async () => {
    const { toast, subscribeToasts } = await load();
    const listener = vi.fn();
    const unsubscribe = subscribeToasts(listener);
    toast.error('One');
    unsubscribe();
    toast.error('Two');
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
