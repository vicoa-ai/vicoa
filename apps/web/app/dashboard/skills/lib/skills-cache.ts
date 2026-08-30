/**
 * Module-level in-memory cache for the Skills tab (same convention as
 * automation-cache.ts / task-cache.ts): revisiting the tab paints the last
 * machine + skill lists instantly, then revalidates on mount.
 */

import type { MachineSummary } from '@/lib/backend-api';
import type { ListSkillsResult, SkillAgentType } from './skills-rpc';

export interface SkillsCacheData {
  machines: MachineSummary[];
  selectedMachineId: string | null;
  /** Keyed by `${machineId}:${agentType}` (see `skillsKey`). */
  skills: Record<string, ListSkillsResult>;
}

let cache: SkillsCacheData | null = null;

export function getSkillsCache(): SkillsCacheData | null {
  return cache;
}

export function setSkillsCache(data: SkillsCacheData): void {
  cache = data;
}

export function skillsKey(machineId: string, agentType: SkillAgentType): string {
  return `${machineId}:${agentType}`;
}
