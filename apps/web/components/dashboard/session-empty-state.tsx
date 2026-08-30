'use client';

import { memo } from 'react';
import { MessageCircleMore } from 'lucide-react';

/**
 * Empty-chat state, mirroring the mobile `SessionLoadingIndicator` / "Session
 * ready" split (`vicoa-app/.../components/session_loading_indicator.dart`).
 *
 * - `loading` (a freshly spawned session spinning up its first response): the
 *   icon badge breathes slowly and the "vibing" wave text animates, so the wait
 *   reads as active work rather than a stalled screen.
 * - otherwise: a static idle card ("Session ready" / "Waiting for messages").
 */
export const SessionEmptyState = memo(function SessionEmptyState({
  loading,
  vibingMessage,
}: {
  loading: boolean;
  vibingMessage: string;
}) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center text-muted-foreground font-mono">
      <style>{`
        @keyframes session-breathe {
          0%, 100% { opacity: 0.6; transform: scale(0.97); }
          50% { opacity: 1; transform: scale(1.03); }
        }
        @keyframes session-blink-wave {
          0% { opacity: 0.3; }
          50% { opacity: 0.8; }
          100% { opacity: 0.3; }
        }
        .session-vibing-text span {
          display: inline-block;
          animation: session-blink-wave 6s ease-in-out infinite;
        }
      `}</style>
      <div
        className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted-foreground/10 text-muted-foreground"
        style={loading ? { animation: 'session-breathe 2.8s ease-in-out infinite' } : undefined}
      >
        <MessageCircleMore className="h-7 w-7" strokeWidth={1.75} />
      </div>
      <p className="mt-4 text-base font-medium text-foreground">
        {loading ? 'Starting your session' : 'Session ready'}
      </p>
      {loading ? (
        <span className="session-vibing-text mt-2 text-sm">
          {vibingMessage.split('').map((char, i) => (
            <span key={i} style={{ animationDelay: `${i * 0.15}s` }}>
              {char}
            </span>
          ))}
        </span>
      ) : (
        <p className="mt-2 text-sm">Waiting for your message</p>
      )}
    </div>
  );
});
