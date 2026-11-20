/**
 * The create dialog's assignee rules, kept out of the component so they can
 * be tested: what the line above the pills says once an agent is picked, and
 * which assignee survives moving the new task to another project.
 */

import type { AgentProfile, ProjectResponse, TaskStatus } from '@/lib/backend-api';
import { agentsForProject } from '@/lib/project-vocabulary';

export type TaskAssignee = { type: 'user' | 'agent'; id: string };

/** Whether creating the task starts the agent, in the words of the task
 *  page's assign toasts. Mirrors the backend: nothing starts in Backlog or a
 *  closed status, and a team agent can't start a run at all yet. */
export function agentStartHint(
  agent: Pick<AgentProfile, 'name' | 'team_id'>,
  status: TaskStatus,
): string {
  if (agent.team_id) return "Team agents can't start work yet, so nothing will run.";
  if (status === 'backlog') return `${agent.name} will work on this once it leaves Backlog.`;
  if (status === 'done' || status === 'cancelled') {
    return `${agent.name} will work on this if it is reopened.`;
  }
  return `${agent.name} will work on this as soon as it's created.`;
}

type ProjectOwner = Pick<ProjectResponse, 'team_id'> | null;

/** Whether `assignee` can stay on the task once it moves from project `from`
 *  to `to`, as the backend checks it: you anywhere, an agent the new project
 *  offers, another person only within the same team. */
export function assigneeFitsProject(
  assignee: TaskAssignee,
  {
    viewerId,
    from,
    to,
    agentProfiles,
  }: {
    viewerId: string | null | undefined;
    from: ProjectOwner;
    to: ProjectOwner;
    agentProfiles: AgentProfile[];
  },
): boolean {
  if (assignee.type === 'agent') {
    return agentsForProject(agentProfiles, to).some((p) => p.id === assignee.id);
  }
  if (assignee.id === viewerId) return true;
  return !!to?.team_id && to.team_id === from?.team_id;
}
