import { describe, expect, it, vi } from 'vitest';

import { HandBackError, runHandBack } from './hand-back';

type Task = { id: string; status: string };

const inReview: Task = { id: 't1', status: 'in_review' };

function steps(over: { postFails?: boolean; moveFails?: boolean } = {}) {
  return {
    postReply: vi.fn(async (_body: string) => {
      if (over.postFails) throw new Error('post failed');
    }),
    moveToReview: vi.fn(async (): Promise<Task> => {
      if (over.moveFails) throw new Error('move failed');
      return inReview;
    }),
  };
}

describe('runHandBack', () => {
  it('posts the reply, then moves the task to review', async () => {
    const posted = { current: null };
    const s = steps();
    await expect(runHandBack('done, over to you', posted, s)).resolves.toBe(inReview);
    expect(s.postReply).toHaveBeenCalledWith('done, over to you');
    expect(s.moveToReview).toHaveBeenCalledTimes(1);
    expect(posted.current).toBeNull();
  });

  it('leaves the status alone when the reply did not post', async () => {
    const posted = { current: null };
    const s = steps({ postFails: true });
    const err = await runHandBack('hi', posted, s).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(HandBackError);
    expect((err as HandBackError).replyPosted).toBe(false);
    expect((err as HandBackError).reason).toBeInstanceOf(Error);
    expect(s.moveToReview).not.toHaveBeenCalled();
    expect(posted.current).toBeNull();
  });

  it('says the reply went out when only the status change failed', async () => {
    const posted = { current: null };
    const err = await runHandBack('hi', posted, steps({ moveFails: true })).catch(
      (e: unknown) => e,
    );
    expect((err as HandBackError).replyPosted).toBe(true);
    expect(posted.current).toBe('hi');
  });

  it('does not post the same reply twice on a retry', async () => {
    // The reply landed, the status didn't: the kept draft is retried as is.
    const posted = { current: null as string | null };
    await runHandBack('hi', posted, steps({ moveFails: true })).catch(() => undefined);
    const retry = steps();
    await expect(runHandBack('hi', posted, retry)).resolves.toBe(inReview);
    expect(retry.postReply).not.toHaveBeenCalled();
    expect(retry.moveToReview).toHaveBeenCalledTimes(1);
    expect(posted.current).toBeNull();
  });

  it('posts again when the draft was edited before the retry', async () => {
    const posted = { current: null as string | null };
    await runHandBack('hi', posted, steps({ moveFails: true })).catch(() => undefined);
    const retry = steps();
    await runHandBack('hi, and one more thing', posted, retry);
    expect(retry.postReply).toHaveBeenCalledWith('hi, and one more thing');
  });
});
