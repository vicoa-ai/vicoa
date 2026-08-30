'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

interface UseMessageDraftOptions {
  instanceId: string | null;
  debounceMs?: number;
  onError?: (error: Error) => void;
}

interface UseMessageDraftReturn {
  draft: string;
  setDraft: (message: string) => void;
  clearDraft: () => void;
  isHydrated: boolean;
}

/**
 * Hook for managing message drafts in sessionStorage
 *
 * Features:
 * - Persists drafts to sessionStorage per instanceId
 * - Debounced auto-save (500ms default)
 * - Handles Next.js hydration safely
 * - Storage key pattern: message-draft-${instanceId}
 *
 * @param instanceId - Unique identifier for the agent instance
 * @param debounceMs - Debounce delay for auto-save (default: 500ms)
 * @param onError - Optional error handler for storage operations
 */
export function useMessageDraft({
  instanceId,
  debounceMs = 500,
  onError,
}: UseMessageDraftOptions): UseMessageDraftReturn {
  // Track hydration state to prevent mismatch
  const [isHydrated, setIsHydrated] = useState(false);

  // Draft state
  const [draft, setDraftState] = useState('');

  // Refs for debouncing and tracking
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSavedDraftRef = useRef('');
  const isInitializedRef = useRef(false);
  const prevInstanceIdRef = useRef<string | null>(null);

  // Generate storage key
  const getStorageKey = useCallback((id: string) => {
    return `message-draft-${id}`;
  }, []);

  // Safe sessionStorage operations with error handling
  const saveToStorage = useCallback((key: string, value: string) => {
    try {
      if (typeof window === 'undefined' || !window.sessionStorage) {
        return;
      }

      if (value.trim()) {
        sessionStorage.setItem(key, value);
        lastSavedDraftRef.current = value;
      } else {
        // Remove empty drafts from storage
        sessionStorage.removeItem(key);
        lastSavedDraftRef.current = '';
      }
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Failed to save draft');
      console.error('Failed to save draft to sessionStorage:', err);
      onError?.(err);
    }
  }, [onError]);

  const loadFromStorage = useCallback((key: string): string => {
    try {
      if (typeof window === 'undefined' || !window.sessionStorage) {
        return '';
      }

      const stored = sessionStorage.getItem(key);
      return stored || '';
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Failed to load draft');
      console.error('Failed to load draft from sessionStorage:', err);
      onError?.(err);
      return '';
    }
  }, [onError]);

  const removeFromStorage = useCallback((key: string) => {
    try {
      if (typeof window === 'undefined' || !window.sessionStorage) {
        return;
      }

      sessionStorage.removeItem(key);
      lastSavedDraftRef.current = '';
    } catch (error) {
      const err = error instanceof Error ? error : new Error('Failed to clear draft');
      console.error('Failed to clear draft from sessionStorage:', err);
      onError?.(err);
    }
  }, [onError]);

  // Initialize on mount - load from storage
  useEffect(() => {
    // Set hydrated flag on first mount
    if (!isInitializedRef.current) {
      setIsHydrated(true);
      isInitializedRef.current = true;
    }

    // Handle no instanceId
    if (!instanceId) {
      setDraftState('');
      prevInstanceIdRef.current = null;
      return;
    }

    // Only load from storage when instanceId changes or on first mount
    const instanceChanged = prevInstanceIdRef.current !== instanceId;
    if (instanceChanged) {
      const key = getStorageKey(instanceId);
      const storedDraft = loadFromStorage(key);
      setDraftState(storedDraft);
      lastSavedDraftRef.current = storedDraft;
      prevInstanceIdRef.current = instanceId;
    }
  }, [instanceId, getStorageKey, loadFromStorage]);

  // Debounced save effect
  useEffect(() => {
    // Don't save until hydrated
    if (!isHydrated || !instanceId) {
      return;
    }

    // Clear existing timeout
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    // Only save if draft has changed from last saved version
    if (draft === lastSavedDraftRef.current) {
      return;
    }

    // Set new timeout for debounced save
    saveTimeoutRef.current = setTimeout(() => {
      const key = getStorageKey(instanceId);
      saveToStorage(key, draft);
    }, debounceMs);

    // Cleanup timeout on unmount or when dependencies change
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [draft, instanceId, debounceMs, isHydrated, getStorageKey, saveToStorage]);

  // Public API: Update draft
  const setDraft = useCallback((newDraft: string) => {
    setDraftState(newDraft);
  }, []);

  // Public API: Clear draft (used after sending)
  const clearDraft = useCallback(() => {
    setDraftState('');

    if (!instanceId) return;

    const key = getStorageKey(instanceId);
    removeFromStorage(key);
  }, [instanceId, getStorageKey, removeFromStorage]);

  return {
    draft,
    setDraft,
    clearDraft,
    isHydrated,
  };
}
