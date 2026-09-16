'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { WorkspaceFileLink } from '@/lib/message-links';

interface FileLinkValue {
  /** The session's working directory on the agent's machine, if known. */
  cwd: string | null;
  /** That machine's home directory, so `~/…` links can be expanded. */
  homeDir: string | null;
  /** Reveal a workspace file in the files panel. `null` on surfaces that have
   *  no panel to open into (the task timeline, previews), where a file link
   *  renders as plain text rather than as a click that goes nowhere. */
  openFile: ((file: WorkspaceFileLink) => void) | null;
}

const FileLinkContext = createContext<FileLinkValue>({
  cwd: null,
  homeDir: null,
  openFile: null,
});

/**
 * Tells the message renderer which workspace the messages below it describe, so
 * the file paths agents cite can be resolved and opened in-app instead of being
 * handed to the browser as if they were web links (vicoa-ai/vicoa#46).
 */
export function FileLinkProvider({
  cwd,
  homeDir,
  openFile,
  children,
}: {
  cwd: string | null;
  homeDir: string | null;
  openFile: ((file: WorkspaceFileLink) => void) | null;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ cwd, homeDir, openFile }), [cwd, homeDir, openFile]);
  return <FileLinkContext.Provider value={value}>{children}</FileLinkContext.Provider>;
}

export function useFileLinks(): FileLinkValue {
  return useContext(FileLinkContext);
}
