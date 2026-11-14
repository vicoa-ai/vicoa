/**
 * Which `(entity, entity_id)` pairs a socket has already received an `update`
 * for, so a caller that starts waiting late can tell the row already arrived.
 *
 * Why it exists: after `spawn-session` the dashboard waits for the new
 * session's row (`WsClient.waitForEntity`). The server broadcasts that row at
 * registration, which is BEFORE the daemon answers the RPC, so the update
 * reaches the client ahead of the RPC result. A wait that only listens for
 * future updates misses it and sits until the row's next change (a heartbeat
 * up to ~2s later, or its 15s timeout).
 *
 * Bounded: the oldest pair is forgotten once `capacity` is exceeded, which is
 * far more than a spawn's few hundred milliseconds can produce.
 */
export class RecentEntities {
  private readonly keys = new Set<string>();

  constructor(private readonly capacity = 500) {}

  note(entity: string, entityId: string): void {
    const key = RecentEntities.key(entity, entityId);
    // Re-insert so a pair that keeps changing counts as recent.
    this.keys.delete(key);
    this.keys.add(key);
    if (this.keys.size > this.capacity) {
      const oldest = this.keys.values().next();
      if (!oldest.done) this.keys.delete(oldest.value);
    }
  }

  has(entity: string, entityId: string): boolean {
    return this.keys.has(RecentEntities.key(entity, entityId));
  }

  private static key(entity: string, entityId: string): string {
    return `${entity}\u0000${entityId}`;
  }
}
