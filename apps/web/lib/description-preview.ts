/**
 * Task descriptions are markdown (the rich editor saves `##`, `**`, lists and
 * `[#ACM-42](/dashboard/tasks/…)` references). A peek at one, in a hover card,
 * wants the words without the syntax. This is not a markdown renderer: it drops
 * the markers, keeps the line breaks and the text, and stops early so a long
 * description is never put in the page whole. The card clamps what is left.
 */

/** More than a clamped card can show; the cap only keeps the string small. */
const MAX_CHARS = 600;

export function descriptionPreview(markdown: string | null | undefined): string {
  if (!markdown) return '';
  const lines = markdown
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .filter((line) => !/^\s*(```|~~~)/.test(line) && !/^\s*([-*_])(\s*\1){2,}\s*$/.test(line))
    .map((line) =>
      line
        .replace(/^\s{0,3}#{1,6}\s+/, '')
        .replace(/^\s*>\s?/, '')
        .replace(/^(\s*)(?:[-*+]|\d+[.)])\s+\[[ xX]\]\s+/, '$1- ')
        .replace(/^(\s*)\*\s+/, '$1- ')
        .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
        .replace(/(\*\*|__)(.+?)\1/g, '$2')
        .replace(/~~(.+?)~~/g, '$1')
        .replace(/(?<![*\w])\*(?!\s)([^*]+?)(?<!\s)\*(?![*\w])/g, '$1')
        .replace(/(?<![_\w])_(?!\s)([^_]+?)(?<!\s)_(?![_\w])/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .trimEnd(),
    )
    .filter((line) => line.trim() !== '');
  const text = lines.join('\n');
  return text.length > MAX_CHARS ? `${text.slice(0, MAX_CHARS).trimEnd()}…` : text;
}
