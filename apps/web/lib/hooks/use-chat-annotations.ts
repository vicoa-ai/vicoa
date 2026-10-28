'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  loadSessionAnnotations,
  saveSessionAnnotations,
  type ChatAnnotation,
} from '@/lib/chat-annotations';

interface UseChatAnnotationsReturn {
  annotations: ChatAnnotation[];
  add: (annotation: ChatAnnotation) => void;
  updateComment: (id: string, comment: string) => void;
  remove: (id: string) => void;
  clear: () => void;
}

/**
 * The composer's annotation list for one session, persisted per instance in
 * sessionStorage (see lib/chat-annotations.ts). The list is tagged with the
 * instance it was loaded for, so a session switch never writes one session's
 * annotations under the other's key, and never shows them for a render.
 */
export function useChatAnnotations(instanceId: string | null): UseChatAnnotationsReturn {
  const [state, setState] = useState<{ instanceId: string | null; items: ChatAnnotation[] }>({
    instanceId: null,
    items: [],
  });

  useEffect(() => {
    setState({ instanceId, items: instanceId ? loadSessionAnnotations(instanceId) : [] });
  }, [instanceId]);

  const loaded = state.instanceId === instanceId;
  const annotations = loaded ? state.items : [];

  // Persist after every change once the list for this session is in place.
  useEffect(() => {
    if (state.instanceId) saveSessionAnnotations(state.instanceId, state.items);
  }, [state]);

  const mutate = useCallback(
    (fn: (items: ChatAnnotation[]) => ChatAnnotation[]) => {
      setState((prev) => (prev.instanceId === instanceId ? { instanceId, items: fn(prev.items) } : prev));
    },
    [instanceId],
  );

  const add = useCallback((annotation: ChatAnnotation) => mutate((items) => [...items, annotation]), [mutate]);
  const updateComment = useCallback(
    (id: string, comment: string) =>
      mutate((items) => items.map((a) => (a.id === id ? { ...a, comment: comment.trim() } : a))),
    [mutate],
  );
  const remove = useCallback((id: string) => mutate((items) => items.filter((a) => a.id !== id)), [mutate]);
  const clear = useCallback(() => mutate(() => []), [mutate]);

  return { annotations, add, updateComment, remove, clear };
}
