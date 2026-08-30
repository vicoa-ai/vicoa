'use client';

import { cn } from '@/lib/utils';

import { getFileIconSvg } from './material-file-icons';

/**
 * Renders a file's Material Icon Theme glyph (colored per language). The SVG
 * comes from `material-file-icons.ts` — static, trusted data baked into the
 * bundle (never user input), so `dangerouslySetInnerHTML` is safe here. The
 * inline SVGs carry a viewBox but no width/height, so the wrapper fixes the
 * box and stretches the svg to fill it.
 */
export function FileTypeIcon({
  fileName,
  size = 16,
  className = '',
}: {
  fileName: string;
  size?: number;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn('inline-flex flex-shrink-0 items-center justify-center [&>svg]:block [&>svg]:h-full [&>svg]:w-full', className)}
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: getFileIconSvg(fileName) }}
    />
  );
}
