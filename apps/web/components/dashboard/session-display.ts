/**
 * Presentation helpers for session rows, shared by the web sidebar
 * (dashboard-layout.tsx) and the desktop sidebar (desktop-sidebar.tsx).
 */

export function formatSidebarTime(instance: {
  latest_message_at?: string | null;
  started_at?: string | null;
}): string {
  const now = new Date();
  const messageTime = new Date(instance.latest_message_at || instance.started_at || '');
  const diffMs = now.getTime() - messageTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffMs < 60000) return `${Math.max(1, Math.floor(diffMs / 1000))}s`;
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;

  const currentYear = now.getFullYear();
  const messageYear = messageTime.getFullYear();
  if (currentYear === messageYear) {
    return messageTime.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
  return messageTime.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function getSessionTitle(instance: {
  name?: string | null;
  latest_message?: string | null;
  chat_length?: number;
  agent_type_name?: string | null;
}): string {
  if (instance.name) return instance.name;
  const isErrorMessage = instance.latest_message?.includes('API Error') ||
    instance.latest_message?.includes('error') ||
    instance.latest_message?.includes('Error');
  if (!isErrorMessage && instance.latest_message) return instance.latest_message;
  if ((instance.chat_length ?? 0) <= 1) return 'New session';
  const name = instance.agent_type_name || 'Session';
  return name.charAt(0).toUpperCase() + name.slice(1);
}
