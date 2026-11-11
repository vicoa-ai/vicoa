// "Reply and hand back" in the task peek panel: post the reply, then move the
// task to In Review so whoever asked (usually an agent) sees it is their turn.
//
// Two writes, so it can stop halfway. When the reply landed and the status
// change didn't, the reply is already on the timeline; posting it again on the
// retry would put it there twice. `posted` remembers the reply that went out,
// and a retry with the same text only retries the status. Edited text is a new
// reply and goes out again.

/** A hand back that stopped partway; `replyPosted` says how far it got. */
export class HandBackError extends Error {
  readonly reason: unknown;
  readonly replyPosted: boolean;

  constructor(reason: unknown, replyPosted: boolean) {
    super(reason instanceof Error ? reason.message : 'Hand back failed');
    this.name = 'HandBackError';
    this.reason = reason;
    this.replyPosted = replyPosted;
  }
}

export async function runHandBack<T>(
  body: string,
  /** The reply already posted by an earlier attempt that failed on the status. */
  posted: { current: string | null },
  steps: {
    postReply: (body: string) => Promise<void>;
    moveToReview: () => Promise<T>;
  },
): Promise<T> {
  if (posted.current !== body) {
    try {
      await steps.postReply(body);
    } catch (err) {
      throw new HandBackError(err, false);
    }
    posted.current = body;
  }
  try {
    const result = await steps.moveToReview();
    posted.current = null;
    return result;
  } catch (err) {
    throw new HandBackError(err, true);
  }
}
