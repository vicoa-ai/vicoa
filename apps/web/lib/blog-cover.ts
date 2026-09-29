// Layout of the generated blog cover (gradient + centered title + logo), shared
// by scripts/generate-blog-cover.ts, which rasterizes it into the og:image
// webp, and components/blog/blog-cover.tsx, which draws it inline as the
// on-page hero. Keeping one copy of the math keeps the two pixel-aligned.

export const BLOG_COVER_WIDTH = 800;
export const BLOG_COVER_HEIGHT = 450;
// Diagonal gradient, top-left -> bottom-right.
export const BLOG_COVER_GRADIENT_FROM = '#C9DEFF';
export const BLOG_COVER_GRADIENT_TO = '#FFEDE2';
export const BLOG_COVER_TEXT_COLOR = '#05070A';
export const BLOG_COVER_FONT_FAMILY =
  'system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif';

const MAX_LINES = 3;
const TOP_PADDING_RATIO = 0.24;
const BOTTOM_PADDING_RATIO = 0.06;

export interface BlogCoverLayout {
  lines: string[];
  fontSize: number;
  // SVG `<text>` y (baseline) for each entry of `lines`.
  baselines: number[];
  // Box the logo is fitted into (preserveAspectRatio="xMidYMid meet").
  logo: { x: number; y: number; width: number; height: number };
}

function wrapTitle(text: string, maxCharsPerLine = 26, maxLines = MAX_LINES): string[] {
  const words = text.replace(/\s+/g, ' ').trim().split(' ');
  const lines: string[] = [];
  let currentLine = '';

  for (const word of words) {
    const proposed = currentLine ? `${currentLine} ${word}` : word;
    if (proposed.length <= maxCharsPerLine) {
      currentLine = proposed;
      continue;
    }

    if (currentLine) {
      lines.push(currentLine);
      currentLine = word;
    } else {
      lines.push(word.slice(0, maxCharsPerLine));
      currentLine = word.slice(maxCharsPerLine);
    }

    if (lines.length >= maxLines) break;
  }

  if (lines.length < maxLines && currentLine) {
    lines.push(currentLine);
  }

  if (lines.length > maxLines) {
    lines.length = maxLines;
  }

  if (lines.length === maxLines && words.join(' ').length > lines.join(' ').length) {
    const lastLine = lines[maxLines - 1];
    lines[maxLines - 1] = `${lastLine.slice(0, Math.max(0, maxCharsPerLine - 1)).trimEnd()}…`;
  }

  return lines;
}

function fontSizeForTitle(lines: string[]): number {
  const longestLine = Math.max(...lines.map((line) => line.length));
  if (longestLine <= 18) return 62;
  if (longestLine <= 24) return 56;
  if (longestLine <= 30) return 50;
  if (longestLine <= 36) return 45;
  return 42;
}

export function blogCoverLayout(
  text: string,
  width = BLOG_COVER_WIDTH,
  height = BLOG_COVER_HEIGHT
): BlogCoverLayout {
  const lines = wrapTitle(text);
  const fontSize = fontSizeForTitle(lines);
  const lineHeight = Math.round(fontSize * 1.6);
  const topY = Math.round(height * TOP_PADDING_RATIO) + fontSize;
  const logoWidth = Math.round(width * 0.17);
  const logoHeight = logoWidth;

  return {
    lines,
    fontSize,
    baselines: lines.map((_, index) => topY + index * lineHeight),
    logo: {
      x: Math.round((width - logoWidth) / 2),
      y: height - logoHeight - Math.round(height * BOTTOM_PADDING_RATIO),
      width: logoWidth,
      height: logoHeight,
    },
  };
}
