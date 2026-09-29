import { cn } from '@/lib/utils';
import {
  BLOG_COVER_FONT_FAMILY,
  BLOG_COVER_GRADIENT_FROM,
  BLOG_COVER_GRADIENT_TO,
  BLOG_COVER_HEIGHT,
  BLOG_COVER_TEXT_COLOR,
  BLOG_COVER_WIDTH,
  blogCoverLayout,
} from '@/lib/blog-cover';

// The monospace wordmark the existing cover webps were rendered with
// (vicoa-logo-text-white-old.png, downsized).
const COVER_LOGO_SRC = '/images/blog/cover-logo.webp';

// The generator's SVG gradient runs corner to corner (userSpaceOnUse, 0,0 ->
// w,h). A CSS gradient at 90deg + atan(h/w) spans exactly that diagonal;
// `to bottom right` would not (its midline joins the other two corners).
const GRADIENT_ANGLE = 90 + (Math.atan2(BLOG_COVER_HEIGHT, BLOG_COVER_WIDTH) * 180) / Math.PI;

interface BlogCoverProps {
  text: string;
  label: string;
  className?: string;
}

/**
 * The post's cover art drawn inline instead of loaded as an image, so it
 * arrives with the HTML and never waits on (or misses) a CDN cache. That keeps
 * it off the mobile LCP critical path: the text paints with the first frame.
 * Matches the `pnpm blog:cover` og:image; the gradient is a CSS background so
 * the two copies on the page need no shared SVG `id`.
 */
export function BlogCover({ text, label, className }: BlogCoverProps) {
  const { lines, fontSize, baselines, logo } = blogCoverLayout(text);

  return (
    <div
      className={cn('aspect-video w-full overflow-hidden', className)}
      style={{
        backgroundImage: `linear-gradient(${GRADIENT_ANGLE}deg, ${BLOG_COVER_GRADIENT_FROM}, ${BLOG_COVER_GRADIENT_TO})`,
      }}
    >
      <svg
        viewBox={`0 0 ${BLOG_COVER_WIDTH} ${BLOG_COVER_HEIGHT}`}
        role="img"
        aria-label={label}
        className="block h-full w-full"
      >
        {lines.map((line, index) => (
          <text
            key={index}
            x={BLOG_COVER_WIDTH / 2}
            y={baselines[index]}
            textAnchor="middle"
            fontFamily={BLOG_COVER_FONT_FAMILY}
            fontSize={fontSize}
            fontWeight={700}
            fill={BLOG_COVER_TEXT_COLOR}
          >
            {line}
          </text>
        ))}
        <image
          href={COVER_LOGO_SRC}
          x={logo.x}
          y={logo.y}
          width={logo.width}
          height={logo.height}
          preserveAspectRatio="xMidYMid meet"
        />
      </svg>
    </div>
  );
}
