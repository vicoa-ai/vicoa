import { describe, test, expect } from 'vitest';
import { iconKindForFile, isMarkdownPath, languageForFile } from './file-icon';

describe('isMarkdownPath', () => {
  test('true for markdown extensions (case-insensitive)', () => {
    for (const n of ['README.md', 'a.mdx', 'notes.markdown', 'X.MD']) {
      expect(isMarkdownPath(n)).toBe(true);
    }
  });
  test('false for non-markdown and extensionless', () => {
    for (const n of ['a.ts', 'b.txt', 'c.json', 'LICENSE', 'mdfile']) {
      expect(isMarkdownPath(n)).toBe(false);
    }
  });
});

describe('iconKindForFile', () => {
  test('directories get the folder kind', () => {
    expect(iconKindForFile({ name: 'src', type: 'dir' })).toBe('folder');
  });

  test('common code extensions get the code kind', () => {
    for (const name of ['app.ts', 'app.tsx', 'main.py', 'lib.rs', 'Foo.java', 'index.js']) {
      expect(iconKindForFile({ name, type: 'file' })).toBe('code');
    }
  });

  test('markdown and txt files get the text kind', () => {
    expect(iconKindForFile({ name: 'README.md', type: 'file' })).toBe('text');
    expect(iconKindForFile({ name: 'notes.txt', type: 'file' })).toBe('text');
  });

  test('image extensions get the image kind', () => {
    for (const name of ['logo.png', 'photo.jpg', 'shot.JPEG', 'pic.webp', 'icon.svg']) {
      expect(iconKindForFile({ name, type: 'file' })).toBe('image');
    }
  });

  test('extensionless and unknown files get the generic kind', () => {
    expect(iconKindForFile({ name: 'Makefile', type: 'file' })).toBe('generic');
    expect(iconKindForFile({ name: 'something.xyz', type: 'file' })).toBe('generic');
  });
});

describe('languageForFile', () => {
  test('returns a highlight.js language for known extensions', () => {
    expect(languageForFile('app.ts')).toBe('typescript');
    expect(languageForFile('app.tsx')).toBe('typescript');
    expect(languageForFile('main.py')).toBe('python');
    expect(languageForFile('main.go')).toBe('go');
    expect(languageForFile('lib.rs')).toBe('rust');
    expect(languageForFile('shell.sh')).toBe('bash');
    expect(languageForFile('Dockerfile')).toBe('dockerfile');
  });

  test('returns null for unknown extensions', () => {
    expect(languageForFile('binary.xyz')).toBeNull();
    expect(languageForFile('NOEXT')).toBeNull();
  });
});
