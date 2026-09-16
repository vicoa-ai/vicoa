import { describe, test, expect } from 'vitest';
import {
  messageUrlTransform,
  parseMessageLink,
  type MessageLink,
  type WorkspaceContext,
} from './message-links';

const POSIX: WorkspaceContext = { cwd: '/Users/nick/proj', homeDir: '/Users/nick' };
const WINDOWS: WorkspaceContext = { cwd: 'C:\\Users\\Nick\\proj', homeDir: 'C:\\Users\\Nick' };

/** The file a link resolves to, or the non-file verdict, for terse assertions. */
function resolve(href: string, ctx: WorkspaceContext = POSIX): MessageLink {
  return parseMessageLink(messageUrlTransform(href), ctx);
}

describe('messageUrlTransform', () => {
  test('keeps web URLs, file: URLs and paths', () => {
    for (const url of [
      'https://vicoa.ai/docs',
      'http://localhost:3000',
      'mailto:hi@vicoa.ai',
      'file:///Users/nick/proj/src/a.ts',
      'src/a.ts',
      './a.ts',
      '../sibling/a.ts',
      'a.ts:42',
      'C:/Users/Nick/proj/a.ts',
      '#section',
    ]) {
      expect(messageUrlTransform(url)).toBe(url);
    }
  });

  test('strips dangerous schemes', () => {
    expect(messageUrlTransform('javascript:alert(1)')).toBe('');
    expect(messageUrlTransform('data:text/html,<script>')).toBe('');
    expect(messageUrlTransform('vbscript:msgbox')).toBe('');
  });
});

describe('parseMessageLink — web URLs', () => {
  test('http(s) and mailto stay external', () => {
    expect(resolve('https://vicoa.ai/docs')).toEqual({
      kind: 'external',
      href: 'https://vicoa.ai/docs',
    });
    expect(resolve('mailto:hi@vicoa.ai')).toEqual({ kind: 'external', href: 'mailto:hi@vicoa.ai' });
  });

  test('a stripped javascript: href is inert, not a link to the current page', () => {
    expect(resolve('javascript:alert(1)')).toEqual({ kind: 'inert' });
  });

  test('in-document fragments and protocol-relative URLs are inert', () => {
    expect(resolve('#installation')).toEqual({ kind: 'inert' });
    expect(resolve('//evil.example/x')).toEqual({ kind: 'inert' });
  });
});

describe('parseMessageLink — workspace files', () => {
  test('relative paths resolve against the working directory', () => {
    expect(resolve('src/foo.ts')).toEqual({ kind: 'file', file: { path: 'src/foo.ts' } });
    expect(resolve('./src/foo.ts')).toEqual({ kind: 'file', file: { path: 'src/foo.ts' } });
    expect(resolve('src/./nested/../foo.ts')).toEqual({ kind: 'file', file: { path: 'src/foo.ts' } });
    expect(resolve('README.md')).toEqual({ kind: 'file', file: { path: 'README.md' } });
  });

  test('absolute paths inside the working directory are relativised', () => {
    expect(resolve('/Users/nick/proj/src/foo.ts')).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts' },
    });
  });

  test('file: URLs are decoded', () => {
    expect(resolve('file:///Users/nick/proj/src/foo.ts')).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts' },
    });
    expect(resolve('file:///Users/nick/proj/src/my%20file.ts')).toEqual({
      kind: 'file',
      file: { path: 'src/my file.ts' },
    });
  });

  test('~ expands to the machine home directory', () => {
    expect(resolve('~/proj/src/foo.ts')).toEqual({ kind: 'file', file: { path: 'src/foo.ts' } });
  });

  test('a tilde-stored project still matches an absolute link into it', () => {
    // How sessions actually store `project` — see vicoa-ai/vicoa#46.
    const tilde: WorkspaceContext = { cwd: '~/projects/vicoa-ai/vicoa', homeDir: '/Users/nick' };
    expect(resolve('/Users/nick/projects/vicoa-ai/vicoa/text.txt', tilde)).toEqual({
      kind: 'file',
      file: { path: 'text.txt' },
    });
    expect(resolve('/Users/nick/projects/vicoa-ai/vicoa/text.txt:1', tilde)).toEqual({
      kind: 'file',
      file: { path: 'text.txt', line: 1 },
    });
    expect(resolve('~/projects/vicoa-ai/vicoa/apps/web/lib/x.ts', tilde)).toEqual({
      kind: 'file',
      file: { path: 'apps/web/lib/x.ts' },
    });
    expect(resolve('/Users/nick/projects/other/x.ts', tilde)).toEqual({
      kind: 'outside',
      path: '/Users/nick/projects/other/x.ts',
    });
  });

  test('tilde on both sides still matches with no home directory known', () => {
    const noHome: WorkspaceContext = { cwd: '~/projects/app', homeDir: null };
    expect(resolve('~/projects/app/src/foo.ts', noHome)).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts' },
    });
  });

  test('Windows paths and drive letters survive, case-insensitively', () => {
    expect(resolve('C:\\Users\\Nick\\proj\\src\\foo.ts', WINDOWS)).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts' },
    });
    expect(resolve('file:///c:/users/nick/proj/src/foo.ts', WINDOWS)).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts' },
    });
    expect(resolve('src\\foo.ts', WINDOWS)).toEqual({ kind: 'file', file: { path: 'src/foo.ts' } });
  });
});

describe('parseMessageLink — line references', () => {
  test('the shapes agents emit all yield the line', () => {
    for (const href of [
      'src/foo.ts#L42',
      'src/foo.ts#42',
      'src/foo.ts#L42-L57',
      'src/foo.ts:42',
      'src/foo.ts:42:7',
      'file:///Users/nick/proj/src/foo.ts#L42',
    ]) {
      expect(resolve(href)).toEqual({ kind: 'file', file: { path: 'src/foo.ts', line: 42 } });
    }
  });

  test('a bare filename with a line ref is a path, not a URL scheme', () => {
    expect(resolve('foo.ts:42')).toEqual({ kind: 'file', file: { path: 'foo.ts', line: 42 } });
  });

  test('a named fragment is dropped rather than read as a line', () => {
    expect(resolve('docs/guide.md#getting-started')).toEqual({
      kind: 'file',
      file: { path: 'docs/guide.md' },
    });
  });

  test('a Windows drive colon is not a line separator', () => {
    expect(resolve('C:\\Users\\Nick\\proj\\src\\foo.ts:42', WINDOWS)).toEqual({
      kind: 'file',
      file: { path: 'src/foo.ts', line: 42 },
    });
  });
});

describe('parseMessageLink — refusals', () => {
  test('paths outside the working directory are reported, never followed', () => {
    expect(resolve('/etc/passwd')).toEqual({ kind: 'outside', path: '/etc/passwd' });
    expect(resolve('../other-project/secrets.env')).toEqual({
      kind: 'outside',
      path: '../other-project/secrets.env',
    });
    expect(resolve('~/.ssh/id_rsa')).toEqual({ kind: 'outside', path: '~/.ssh/id_rsa' });
    expect(resolve('file://host/share/x.txt')).toEqual({ kind: 'inert' });
  });

  test('the working directory itself is not a file', () => {
    expect(resolve('/Users/nick/proj')).toEqual({ kind: 'inert' });
    expect(resolve('./')).toEqual({ kind: 'inert' });
  });

  test('bare words are prose, not paths', () => {
    expect(resolve('somewhere')).toEqual({ kind: 'inert' });
  });

  test('without a working directory nothing is openable', () => {
    expect(resolve('src/foo.ts', { cwd: null, homeDir: null })).toEqual({ kind: 'inert' });
  });
});
