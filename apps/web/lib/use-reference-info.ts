'use client';

// What a `#` reference chip shows about the item it points at, looked up by
// id when shown (the stored markdown keeps only the token and the id, see
// lib/reference-links). SWR-keyed per item, so a task referenced in the
// description and twice in comments is fetched once.

import useSWR from 'swr';

import { getBackendAPI, type ReferenceKind } from '@/lib/backend-api';

export interface ReferenceInfo {
  /** The task or automation title, or the session's name (null if unnamed). */
  title: string | null;
  /** Tasks: the key, `VIC-42`, when the task has one. */
  identifier?: string | null;
  /** Sessions: what the sidebar draws for the row, the agent's mark or the
   *  saved agent that started it. */
  agentTypeName?: string | null;
  agentProfileId?: string | null;
}

async function fetchReferenceInfo(kind: ReferenceKind, id: string): Promise<ReferenceInfo> {
  const api = getBackendAPI(true);
  switch (kind) {
    case 'task': {
      const task = await api.getTask(id);
      return { title: task.title, identifier: task.identifier ?? null };
    }
    case 'session': {
      // One message is the least the detail route will send.
      const session = await api.getInstanceDetail(id, 1);
      return {
        title: session.name,
        agentTypeName: session.agent_type_name,
        agentProfileId: session.agent_profile_id ?? null,
      };
    }
    case 'automation': {
      const automation = await api.getAutomation(id);
      return { title: automation.title };
    }
  }
}

/**
 * The item behind a reference. `missing` once the lookup failed: deleted, or
 * not something this viewer can see. The chip then falls back to the stored
 * token rather than guessing.
 */
export function useReferenceInfo(
  kind: ReferenceKind,
  id: string,
): { info: ReferenceInfo | null; missing: boolean } {
  const { data, error } = useSWR(['reference-info', kind, id], () => fetchReferenceInfo(kind, id), {
    // A title rarely changes under you; a refetch per window focus per chip
    // would be most of this hook's traffic.
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  return { info: data ?? null, missing: !!error };
}
