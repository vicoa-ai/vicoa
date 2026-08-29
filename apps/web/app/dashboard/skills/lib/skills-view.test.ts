import { describe, expect, it } from 'vitest';
import type { SkillSummary } from './skills-rpc';
import {
  groupSkillsByFolder,
  parentFolder,
  scopeLabel,
  skillMatchesQuery,
  skillTitle,
} from './skills-view';

function skill(name: string, description = ''): SkillSummary {
  return { name, description, path: '', scope: 'user', source: null, installed_at: null };
}

describe('parentFolder / skillTitle', () => {
  it('splits on the last colon', () => {
    expect(parentFolder('web:forms:date')).toBe('web:forms');
    expect(skillTitle('web:forms:date')).toBe('date');
  });
  it('treats a top-level skill as unfoldered', () => {
    expect(parentFolder('solo')).toBeNull();
    expect(skillTitle('solo')).toBe('solo');
  });
});

describe('groupSkillsByFolder', () => {
  it('puts top-level skills first, then folders alpha, sorted within', () => {
    const groups = groupSkillsByFolder([
      skill('web:zeta'),
      skill('solo-b'),
      skill('web:alpha'),
      skill('solo-a'),
      skill('api:call'),
    ]);
    expect(groups.map((g) => g.folder)).toEqual([null, 'api', 'web']);
    expect(groups[0].skills.map((s) => s.name)).toEqual(['solo-a', 'solo-b']);
    expect(groups[2].skills.map((s) => s.name)).toEqual(['web:alpha', 'web:zeta']);
  });

  it('omits the null group when every skill is foldered', () => {
    const groups = groupSkillsByFolder([skill('a:one'), skill('a:two')]);
    expect(groups.map((g) => g.folder)).toEqual(['a']);
  });
});

describe('scopeLabel', () => {
  it('maps known scopes and passes through unknown', () => {
    expect(scopeLabel('user')).toBe('User');
    expect(scopeLabel('shared')).toBe('Shared');
    expect(scopeLabel('whatever')).toBe('whatever');
  });
});

describe('skillMatchesQuery', () => {
  it('matches on name (incl. folder) and description, case-insensitively', () => {
    expect(skillMatchesQuery(skill('web:forms', 'Build a form'), 'FORM')).toBe(true);
    expect(skillMatchesQuery(skill('web:forms', 'Build a form'), 'web')).toBe(true);
    expect(skillMatchesQuery(skill('web:forms', 'Build a form'), 'xyz')).toBe(false);
  });
  it('treats an empty or whitespace query as match-all', () => {
    expect(skillMatchesQuery(skill('a'), '')).toBe(true);
    expect(skillMatchesQuery(skill('a'), '   ')).toBe(true);
  });
});
