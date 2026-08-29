import { describe, expect, it } from 'vitest';
import {
  computeDiffStatFromContent,
  describeToolRun,
  editedFileFromContent,
  isFileEditToolName,
  isToolUseContent,
  parseToolUse,
  relativizeFilePath,
  summarizeToolUse,
} from './tool-use-parsing';

describe('isToolUseContent', () => {
  it('recognizes the tool-use prefixes', () => {
    expect(isToolUseContent('Using tool: **Edit** - `/a/b.ts`')).toBe(true);
    expect(isToolUseContent('🔧 Using tool: Bash - `ls`')).toBe(true);
    expect(isToolUseContent('**Exec:** `ls -la`')).toBe(true);
    expect(isToolUseContent('✏️ Applying patch to 1 file (+3 -1)\n└ a.ts')).toBe(true);
    expect(isToolUseContent('Here is my plan:')).toBe(false);
  });
});

describe('parseToolUse', () => {
  it('parses the standard Using tool pattern with a path and code block', () => {
    const content = 'Using tool: **Edit** - `/Users/n/proj/file.tsx`\n```diff\n- a\n+ b\n```';
    const parsed = parseToolUse(content, 'claude')!;
    expect(parsed.toolName).toBe('Edit');
    expect(parsed.toolDescription).toBe('`/Users/n/proj/file.tsx`');
    expect(parsed.remainingContent).toContain('```diff');
    expect(parsed.isMultilineDescription).toBe(false);
  });

  it('renames TodoWrite to Todos', () => {
    const parsed = parseToolUse('Using tool: TodoWrite - Todo List\n- [ ] a', 'claude')!;
    expect(parsed.toolName).toBe('Todos');
  });

  it('classifies codex Exec commands', () => {
    expect(parseToolUse('**Exec:** `ls -la`', 'codex')!.toolName).toBe('List');
    expect(parseToolUse('**Exec:** `rg -n foo`', 'codex')!.toolName).toBe('Search');
    expect(parseToolUse("**Exec:** `sed -n '1,20p' a.py`", 'codex')!.toolName).toBe('Read');
  });

  it('strips codex status lines before parsing', () => {
    const content = 'Using tool: **Bash** - `pwd`\n**Status:** running\nnoise';
    const parsed = parseToolUse(content, 'codex')!;
    expect(parsed.remainingContent).toBe('');
  });

  it('returns null for non-tool content', () => {
    expect(parseToolUse('Just some text', 'claude')).toBeNull();
  });
});

describe('describeToolRun', () => {
  it('dedupes in first-use order, counts commands/files, and sentence-cases', () => {
    const contents = [
      'Using tool: **Bash** - `ls -la`',
      'Using tool: **Edit** - `/p/a.ts`\n```diff\n+ x\n```',
      'Using tool: **Bash** - `pwd`',
      'Using tool: **Edit** - `/p/b.ts`\n```diff\n+ y\n```',
      'Using tool: **Read** - `/p/c.ts`\n```\nz\n```',
    ];
    expect(describeToolRun(contents, 'claude')).toBe('Run 2 commands, edit 2 files, read a file');
  });

  it('labels a single shell call as "Run a command"', () => {
    expect(describeToolRun(['Using tool: **Bash** - `pwd`'], 'claude')).toBe('Run a command');
  });

  it('says "a file" when the same path is touched repeatedly', () => {
    const contents = [
      'Using tool: **Edit** - `/p/a.ts`\n```diff\n+ x\n```',
      'Using tool: **Edit** - `/p/a.ts`\n```diff\n- x\n```',
    ];
    expect(describeToolRun(contents, 'claude')).toBe('Edit a file');
  });

  it('falls back to a count when nothing parses', () => {
    expect(describeToolRun(['plain', 'text'], 'claude')).toBe('2 tool uses');
  });

  it('drops edit segments when excludeFileEdits is set', () => {
    const contents = [
      'Using tool: **Bash** - `ls -la`',
      'Using tool: **Edit** - `/p/a.ts`\n```diff\n+ x\n```',
      'Using tool: **Read** - `/p/c.ts`\n```\nz\n```',
    ];
    expect(describeToolRun(contents, 'claude', { excludeFileEdits: true })).toBe(
      'Run a command, read a file',
    );
  });

  it('returns an empty label when an all-edit run excludes edits', () => {
    const contents = [
      'Using tool: **Edit** - `/p/a.ts`\n```diff\n+ x\n```',
      'Using tool: **Write** - `/p/b.ts`\n```diff\n+ y\n```',
    ];
    expect(describeToolRun(contents, 'claude', { excludeFileEdits: true })).toBe('');
  });
});

describe('computeDiffStatFromContent', () => {
  it('counts +/- lines inside fences, ignoring +++/--- headers', () => {
    const content = '```diff\n--- a.ts\n+++ b.ts\n+ one\n+ two\n- three\n ctx\n```';
    expect(computeDiffStatFromContent(content)).toBe('+2 -1');
  });

  it('returns null for non-diff blocks and fence-less content', () => {
    expect(computeDiffStatFromContent('```\nconst a = 1;\n```')).toBeNull();
    expect(computeDiffStatFromContent('plain text + more - less')).toBeNull();
  });
});

describe('summarizeToolUse', () => {
  it('extracts basename + full path for file tools', () => {
    const parsed = parseToolUse('Using tool: **Edit** - `/Users/n/proj/file.tsx`\n```\nx\n```', 'claude')!;
    const summary = summarizeToolUse(parsed);
    expect(summary.fileName).toBe('file.tsx');
    expect(summary.fullPath).toBe('/Users/n/proj/file.tsx');
    expect(summary.hasDetail).toBe(true);
  });

  it('extracts a diff stat from codex patch messages', () => {
    const content = '✏️ Applying patch to 1 file (+12 -3)\n└ src/a.ts\n```\npatch\n```';
    const summary = summarizeToolUse(parseToolUse(content, 'codex')!);
    expect(summary.diffStat).toBe('+12 -3');
    expect(summary.fileName).toBe('a.ts');
    expect(summary.name).toBe('Edited');
  });

  it('keeps plain commands as description without a file name', () => {
    const summary = summarizeToolUse(parseToolUse('Using tool: **Bash** - `ls -la /tmp`', 'claude')!);
    expect(summary.fileName).toBeNull();
    expect(summary.description).toBe('ls -la /tmp');
    expect(summary.hasDetail).toBe(false);
  });

  it('computes a diff stat from the code block when not reported', () => {
    const content =
      'Using tool: **Edit** - `/Users/n/p/a.ts`\n```diff\n- old line\n- gone\n+ new line\n  ctx\n```';
    const summary = summarizeToolUse(parseToolUse(content, 'claude')!);
    expect(summary.diffStat).toBe('+1 -2');
  });

  it('hides the description for Todos', () => {
    const summary = summarizeToolUse(parseToolUse('Using tool: TodoWrite - Todo List\n- [ ] x', 'claude')!);
    expect(summary.description).toBe('');
    expect(summary.hasDetail).toBe(true);
  });
});

describe('isFileEditToolName', () => {
  it('matches the file-editing tools and nothing else', () => {
    for (const name of ['Edit', 'edit', 'Write', 'MultiEdit', 'Edited']) {
      expect(isFileEditToolName(name)).toBe(true);
    }
    for (const name of ['Read', 'Bash', 'Exec', 'Search', 'Todos', '']) {
      expect(isFileEditToolName(name)).toBe(false);
    }
  });
});

describe('relativizeFilePath', () => {
  const root = '/Users/n/proj';
  it('strips the project root from an absolute path under it', () => {
    expect(relativizeFilePath('/Users/n/proj/src/a.ts', 'a.ts', root)).toBe('src/a.ts');
  });
  it('keeps an already-relative path as-is (minus "./")', () => {
    expect(relativizeFilePath('src/a.ts', 'a.ts', root)).toBe('src/a.ts');
    expect(relativizeFilePath('./src/a.ts', 'a.ts', root)).toBe('src/a.ts');
  });
  it('falls back to the basename for an absolute path outside the project', () => {
    expect(relativizeFilePath('/etc/hosts', 'hosts', root)).toBe('hosts');
  });
  it('falls back to the basename when the project root is unknown', () => {
    expect(relativizeFilePath('/Users/n/proj/src/a.ts', 'a.ts', null)).toBe('a.ts');
  });
  it('tolerates a trailing slash on the root', () => {
    expect(relativizeFilePath('/Users/n/proj/a.ts', 'a.ts', '/Users/n/proj/')).toBe('a.ts');
  });
});

describe('editedFileFromContent', () => {
  it('summarizes an Edit into basename, path, stat and diff body', () => {
    const content = 'Using tool: **Edit** - `/Users/n/p/a.ts`\n```diff\n- old\n+ new\n```';
    const edit = editedFileFromContent(content, 'claude')!;
    expect(edit.toolName).toBe('Edit');
    expect(edit.fileName).toBe('a.ts');
    expect(edit.fullPath).toBe('/Users/n/p/a.ts');
    expect(edit.diffStat).toBe('+1 -1');
    expect(edit.diffContent).toContain('```diff');
  });

  it('handles codex patch (Edited) messages', () => {
    const content = '✏️ Applying patch to 1 file (+12 -3)\n└ src/a.ts\n```\npatch\n```';
    const edit = editedFileFromContent(content, 'codex')!;
    expect(edit.toolName).toBe('Edited');
    expect(edit.fileName).toBe('a.ts');
    expect(edit.diffStat).toBe('+12 -3');
  });

  it('returns null for non-edit tools and unparseable content', () => {
    expect(editedFileFromContent('Using tool: **Read** - `/p/a.ts`\n```\nx\n```', 'claude')).toBeNull();
    expect(editedFileFromContent('Using tool: **Bash** - `ls`', 'claude')).toBeNull();
    expect(editedFileFromContent('plain text', 'claude')).toBeNull();
  });
});
