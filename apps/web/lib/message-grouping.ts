import { MessageResponse } from '@/lib/backend-api';

// Time-based grouping of chat messages into dated sections, with the header
// label each section shows. Extracted from the agent instance page.

/**
 * Parse a timestamp string as UTC. Bare strings like "2024-01-15T07:05:23.456789"
 * (no Z, no offset) are treated as local time by V8, so we append Z when no
 * timezone designator is present.
 */
function parseUTCTimestamp(ts: string): Date {
  if (!ts) return new Date(0);
  const hasTimezone = ts.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(ts);
  return new Date(hasTimezone ? ts : ts + 'Z');
}

// Helper function to format date for grouping
function formatDateGroup(date: Date): string {
  const today = new Date();
  const messageDate = new Date(date);

  // Reset time to compare dates only
  const todayStart = new Date(today);
  todayStart.setHours(0, 0, 0, 0);
  const messageDateStart = new Date(messageDate);
  messageDateStart.setHours(0, 0, 0, 0);

  const diffTime = todayStart.getTime() - messageDateStart.getTime();
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

  const time = messageDate.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });

  if (diffDays === 0) {
    // For today, show time in format like "10:30 AM"
    return time;
  } else if (diffDays === 1) {
    // For yesterday, show "Yesterday 10:30 AM"
    return 'Yesterday ' + time;
  } else {
    // For all other dates, show date with time
    const currentYear = today.getFullYear();
    const messageYear = messageDate.getFullYear();

    if (currentYear === messageYear) {
      // Same year: "Jan 15, 10:30 AM"
      return messageDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' + time;
    } else {
      // Different year: "Jan 15, 2024, 10:30 AM"
      return messageDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ', ' + time;
    }
  }
}

// Helper function to group messages by time periods
// Display-order key. A queued message keeps its queue-time `created_at`, but
// the agent actually consumes it later — after finishing the turn it was
// queued behind. Sorting a consumed message by its `consumed_at` lands it
// where the agent picked it up (after the prior reply, before its own reply)
// instead of back at the moment it was queued. Everything else sorts by
// `created_at`.
export function messageSortKey(message: MessageResponse): string {
  const queue = (
    message.message_metadata as { queue?: { status?: unknown; consumed_at?: unknown } } | null | undefined
  )?.queue;
  if (queue?.status === 'consumed' && typeof queue.consumed_at === 'string') {
    return queue.consumed_at;
  }
  return message.created_at ?? '';
}

export function groupMessagesByDate(messages: MessageResponse[]): { date: string; messages: MessageResponse[] }[] {
  const groups: { date: string; messages: MessageResponse[] }[] = [];
  let currentGroup: { date: string; messages: MessageResponse[] } | null = null;

  messages.forEach((message, index) => {
    const messageTime = parseUTCTimestamp(messageSortKey(message));

    // Determine if we should create a new group
    let shouldCreateNewGroup = false;

    if (index === 0) {
      // Always create group for first message
      shouldCreateNewGroup = true;
    } else {
      const prevMessage = messages[index - 1];
      const prevMessageTime = parseUTCTimestamp(messageSortKey(prevMessage));
      const timeDiffBetweenMessages = (messageTime.getTime() - prevMessageTime.getTime()) / (1000 * 60 * 60);

      // Create new group if messages are more than 2 hours apart
      if (Math.abs(timeDiffBetweenMessages) >= 2) {
        shouldCreateNewGroup = true;
      }
    }

    if (shouldCreateNewGroup) {
      const dateKey = formatDateGroup(messageTime);
      currentGroup = { date: dateKey, messages: [message] };
      groups.push(currentGroup);
    } else if (currentGroup) {
      currentGroup.messages.push(message);
    }
  });

  return groups;
}
