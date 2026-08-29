export const agentStatusColorMap = {
  STARTING: {
    text: 'text-purple-600 dark:text-purple-400',
    bgSoft: 'bg-purple-500/10 dark:bg-purple-500/15',
    badgeBg: 'bg-purple-100 dark:bg-purple-900/20',
    dot: 'bg-purple-500',
    border: 'border-l-purple-500',
  },
  ACTIVE: {
    text: 'text-blue-600 dark:text-blue-400',
    bgSoft: 'bg-blue-500/10 dark:bg-blue-500/15',
    badgeBg: 'bg-blue-100 dark:bg-blue-900/20',
    dot: 'bg-blue-500',
    border: 'border-l-blue-500',
  },
  AWAITING_INPUT: {
    text: 'text-orange-600 dark:text-orange-400',
    bgSoft: 'bg-orange-500/10 dark:bg-orange-500/15',
    badgeBg: 'bg-orange-100 dark:bg-orange-900/20',
    dot: 'bg-orange-500',
    border: 'border-l-orange-500',
  },
  REVIEWED: {
    text: 'text-green-600 dark:text-green-400',
    bgSoft: 'bg-green-500/10 dark:bg-green-500/15',
    badgeBg: 'bg-green-100 dark:bg-green-900/20',
    dot: 'bg-green-500',
    border: 'border-l-green-500',
  },
  PAUSED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-muted',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
  STALE: {
    text: 'text-orange-600 dark:text-orange-400',
    bgSoft: 'bg-orange-500/10 dark:bg-orange-500/15',
    badgeBg: 'bg-orange-100 dark:bg-orange-900/20',
    dot: 'bg-orange-500',
    border: 'border-l-orange-500',
  },
  COMPLETED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-muted',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
  FAILED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-destructive/10',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
  KILLED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-destructive/10',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
  DISCONNECTED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-muted',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
  DELETED: {
    text: 'text-muted-foreground',
    bgSoft: 'bg-muted/40',
    badgeBg: 'bg-destructive/10',
    dot: 'bg-gray-400',
    border: 'border-l-gray-400',
  },
} as const;

export function getAgentStatusColors(status: string) {
  return agentStatusColorMap[status as keyof typeof agentStatusColorMap] ?? agentStatusColorMap.COMPLETED;
}
