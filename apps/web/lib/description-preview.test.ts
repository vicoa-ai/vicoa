import { describe, expect, it } from 'vitest';

import { descriptionPreview } from './description-preview';

describe('descriptionPreview', () => {
  it('is empty for no description', () => {
    expect(descriptionPreview(null)).toBe('');
    expect(descriptionPreview(undefined)).toBe('');
    expect(descriptionPreview('  \n\n ')).toBe('');
  });

  it('leaves plain text alone', () => {
    expect(descriptionPreview('Make the dialog link to the task.')).toBe(
      'Make the dialog link to the task.',
    );
  });

  it('drops heading, quote and emphasis markers', () => {
    expect(descriptionPreview('## Goal\n> **Ship** it ~~now~~ _soon_ with `care`')).toBe(
      'Goal\nShip it now soon with care',
    );
  });

  it('keeps a link or reference by its label', () => {
    expect(
      descriptionPreview('Blocked by [#ACM-42](/dashboard/tasks/abc), see [docs](https://x.dev/a_b).'),
    ).toBe('Blocked by #ACM-42, see docs.');
    expect(descriptionPreview('![screenshot](https://x.dev/s.png)')).toBe('screenshot');
  });

  it('keeps list items and drops task checkboxes', () => {
    expect(descriptionPreview('- [ ] one\n- [x] two\n* three\n1. four\n  - nested')).toBe(
      '- one\n- two\n- three\n1. four\n  - nested',
    );
  });

  it('leaves identifiers with underscores and stars in maths alone', () => {
    expect(descriptionPreview('rename snake_case_name and 2 * 3 * 4')).toBe(
      'rename snake_case_name and 2 * 3 * 4',
    );
  });

  it('drops code fences and rules but keeps the code', () => {
    expect(descriptionPreview('Run:\n```bash\npnpm test\n```\n---\nDone')).toBe('Run:\npnpm test\nDone');
  });

  it('collapses blank lines', () => {
    expect(descriptionPreview('one\n\n\n\ntwo\r\n\r\nthree')).toBe('one\ntwo\nthree');
  });

  it('cuts a very long description short', () => {
    const preview = descriptionPreview('word '.repeat(1000));
    expect(preview.length).toBeLessThanOrEqual(601);
    expect(preview.endsWith('…')).toBe(true);
  });
});
