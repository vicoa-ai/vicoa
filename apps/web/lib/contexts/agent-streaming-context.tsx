'use client';

import { createContext, useContext, useState, ReactNode, useCallback } from 'react';

interface StreamingStats {
  activeConnections: number;
  totalMessages: number;
  errors: number;
  lastActivity: Date | null;
}

interface AgentStreamingContextType {
  globalStreamingEnabled: boolean;
  setGlobalStreamingEnabled: (enabled: boolean) => void;
  stats: StreamingStats;
  registerConnection: (instanceId: string) => void;
  unregisterConnection: (instanceId: string) => void;
  recordMessage: () => void;
  recordError: () => void;
}

const AgentStreamingContext = createContext<AgentStreamingContextType | undefined>(undefined);

export function useAgentStreaming() {
  const context = useContext(AgentStreamingContext);
  if (context === undefined) {
    throw new Error('useAgentStreaming must be used within an AgentStreamingProvider');
  }
  return context;
}

interface AgentStreamingProviderProps {
  children: ReactNode;
}

export function AgentStreamingProvider({ children }: AgentStreamingProviderProps) {
  const [globalStreamingEnabled, setGlobalStreamingEnabled] = useState(true);
  const [activeConnections, setActiveConnections] = useState<Set<string>>(new Set());
  const [totalMessages, setTotalMessages] = useState(0);
  const [errors, setErrors] = useState(0);
  const [lastActivity, setLastActivity] = useState<Date | null>(null);

  const registerConnection = useCallback((instanceId: string) => {
    setActiveConnections(prev => new Set([...prev, instanceId]));
  }, []);

  const unregisterConnection = useCallback((instanceId: string) => {
    setActiveConnections(prev => {
      const next = new Set(prev);
      next.delete(instanceId);
      return next;
    });
  }, []);

  const recordMessage = useCallback(() => {
    setTotalMessages(prev => prev + 1);
    setLastActivity(new Date());
  }, []);

  const recordError = useCallback(() => {
    setErrors(prev => prev + 1);
  }, []);

  const stats: StreamingStats = {
    activeConnections: activeConnections.size,
    totalMessages,
    errors,
    lastActivity,
  };

  const value: AgentStreamingContextType = {
    globalStreamingEnabled,
    setGlobalStreamingEnabled,
    stats,
    registerConnection,
    unregisterConnection,
    recordMessage,
    recordError,
  };

  return (
    <AgentStreamingContext.Provider value={value}>
      {children}
    </AgentStreamingContext.Provider>
  );
}