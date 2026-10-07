import { describe, expect, it } from 'vitest';
import { buildSessionActions, type SessionActionChoice } from './session-actions-menu';

const noop = () => {};

describe('buildSessionActions — Project submenu', () => {
  const choices: SessionActionChoice[] = [
    { key: 'p1', label: 'alpha', checked: true, onSelect: noop },
    { key: 'no-project', label: 'No project', separatorBefore: true, onSelect: noop },
  ];

  it('sits right after Rename and carries the choices as its submenu', () => {
    const actions = buildSessionActions({
      onPin: noop,
      onRename: noop,
      projectChoices: choices,
      onCopyId: noop,
    });
    expect(actions.map((a) => a.key)).toEqual(['pin', 'rename', 'project', 'copy-id']);
    const project = actions.find((a) => a.key === 'project');
    expect(project?.label).toBe('Project');
    expect(project?.submenu).toBe(choices);
  });

  it('is left out when there is nowhere to file the session', () => {
    expect(buildSessionActions({ onRename: noop }).map((a) => a.key)).toEqual(['rename']);
    expect(
      buildSessionActions({ onRename: noop, projectChoices: [] }).map((a) => a.key),
    ).toEqual(['rename']);
  });
});
