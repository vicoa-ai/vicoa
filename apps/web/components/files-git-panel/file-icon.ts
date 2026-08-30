export type IconKind = 'folder' | 'code' | 'text' | 'image' | 'generic';

const CODE_EXTS = new Set([
  'ts', 'tsx', 'js', 'jsx', 'mjs', 'cjs',
  'py', 'rs', 'go', 'java', 'kt', 'kts', 'swift', 'm', 'mm',
  'c', 'cc', 'cpp', 'h', 'hpp', 'cs',
  'rb', 'php', 'lua', 'dart', 'scala', 'clj', 'ex', 'exs',
  'html', 'css', 'scss', 'sass', 'vue', 'svelte', 'sql',
]);

const TEXT_EXTS = new Set(['md', 'mdx', 'markdown', 'txt', 'rst', 'log']);

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico']);

const LANGUAGE_BY_EXT: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  rs: 'rust',
  go: 'go',
  java: 'java',
  kt: 'kotlin',
  swift: 'swift',
  rb: 'ruby',
  php: 'php',
  c: 'c',
  cc: 'cpp',
  cpp: 'cpp',
  h: 'c',
  hpp: 'cpp',
  cs: 'csharp',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'toml',
  xml: 'xml',
  html: 'html',
  css: 'css',
  scss: 'scss',
  sql: 'sql',
  md: 'markdown',
  mdx: 'markdown',
  dart: 'dart',
  lua: 'lua',
  swift_pkg: 'swift',
};

function extOf(name: string): string {
  const i = name.lastIndexOf('.');
  if (i <= 0 || i === name.length - 1) return '';
  return name.slice(i + 1).toLowerCase();
}

const MARKDOWN_EXTS = new Set(['md', 'mdx', 'markdown']);

/** Whether `name` is a markdown file (md/mdx/markdown). Used to gate the
 *  read-only markdown preview — `languageForFile` misses a bare `.markdown`. */
export function isMarkdownPath(name: string): boolean {
  return MARKDOWN_EXTS.has(extOf(name));
}

export function iconKindForFile(entry: { name: string; type: 'dir' | 'file' }): IconKind {
  if (entry.type === 'dir') return 'folder';
  const ext = extOf(entry.name);
  if (!ext) return 'generic';
  if (CODE_EXTS.has(ext)) return 'code';
  if (TEXT_EXTS.has(ext)) return 'text';
  if (IMAGE_EXTS.has(ext)) return 'image';
  return 'generic';
}

export function languageForFile(name: string): string | null {
  if (name === 'Dockerfile' || name.toLowerCase() === 'dockerfile') return 'dockerfile';
  const ext = extOf(name);
  if (!ext) return null;
  return LANGUAGE_BY_EXT[ext] ?? null;
}
