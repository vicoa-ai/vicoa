import { Activity, CalendarRange, Lightbulb, type LucideIcon } from 'lucide-react';
import type { ScheduleDraft } from './frequency';

/** A starter automation shown on the empty state. Picking one opens the create
 *  panel pre-filled with the title/prompt and a sensible default cadence. */
export interface AutomationTemplate {
  id: string;
  icon: LucideIcon;
  /** Card heading + prefilled automation title. */
  title: string;
  /** Card subtitle. */
  description: string;
  /** Prefilled agent prompt. */
  prompt: string;
  /** Overrides merged onto the default schedule draft. */
  schedule?: Partial<ScheduleDraft>;
  /**
   * Prefilled machine, when the source already knows one (e.g. an automation
   * seeded from a task's linked project directory). Honored only if it matches
   * a connected machine; otherwise create mode falls back to the first machine.
   */
  machineId?: string;
  /** Prefilled project directory, paired with `machineId`. */
  directory?: string;
}

export const AUTOMATION_TEMPLATES: AutomationTemplate[] = [
  {
    id: 'suggest-next-steps',
    icon: Lightbulb,
    title: 'Suggest next steps',
    description: 'Ideas for what to work on next in this project',
    prompt:
      'Look through this project folder to understand what it is and its current ' +
      'state. Then propose 2–3 concrete, actionable next steps or improvements ' +
      'worth doing, ordered by impact, with a sentence on why each matters. Base ' +
      'this on the files in the folder — a git history is not required.',
    schedule: { repeat: 'daily', time: '09:00' },
  },
  {
    id: 'weekly-planning',
    icon: CalendarRange,
    title: 'Weekly planning',
    description: 'Summarize the backlog and plan the week ahead',
    prompt:
      'List my tasks with `vicoa task ls`. Summarize what got done recently and ' +
      'what is still open, flag anything stale or blocked, and draft a plan for the ' +
      'week ahead with a suggested order of work.',
    schedule: { repeat: 'weekly', weekdays: [1], time: '09:00' },
  },
  {
    id: 'session-audit',
    icon: Activity,
    title: 'Session audit',
    description: 'Find stale running sessions and suggest cleanup',
    prompt:
      'List the running vicoa sessions with `vicoa ls`. Identify any that look old, ' +
      'idle, or outdated, and for each one recommend whether to keep or stop it — ' +
      'including the exact `vicoa stop <id>` command to clean it up. Do not stop ' +
      'anything without my confirmation.',
    schedule: { repeat: 'daily', time: '18:00' },
  },
];
