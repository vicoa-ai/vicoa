import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import {
  BLOG_COVER_FONT_FAMILY,
  BLOG_COVER_GRADIENT_FROM,
  BLOG_COVER_GRADIENT_TO,
  BLOG_COVER_HEIGHT,
  BLOG_COVER_TEXT_COLOR,
  BLOG_COVER_WIDTH,
  blogCoverLayout,
} from '../lib/blog-cover';

const VALID_FORMATS = ['webp', 'jpg', 'jpeg', 'png', 'svg'] as const;
type Format = (typeof VALID_FORMATS)[number];

type CliOptions = {
  text: string;
  out?: string;
  width: number;
  height: number;
  logo: string;
  format: Format;
};

const DEFAULT_WIDTH = BLOG_COVER_WIDTH;
const DEFAULT_HEIGHT = BLOG_COVER_HEIGHT;
const DEFAULT_OUTPUT_DIR = 'public/images/blog';
const DEFAULT_LOGO_PATH = 'public/images/vicoa-logo-text-white.png';
const DEFAULT_FORMAT: Format = 'webp';
// Rasterize at 2x the SVG's logical size for crisp retina output.
const RASTER_SCALE = 2;

function printUsageAndExit(message?: string): never {
  if (message) {
    console.error(`Error: ${message}`);
  }

  console.error(`
Usage:
  pnpm blog:cover --text "How to Use Claude Code with OpenRouter?"

Options:
  --text, -t    Required title text
  --out, -o     Output path (default: public/images/blog/blog-<slug>.<ext>)
  --format, -f  Output format: webp | jpg | png | svg (default: webp)
  --width       Image width in px (default: 800)
  --height      Image height in px (default: 450)
  --logo        Logo file path (default: public/images/vicoa-logo-text-white.png)

Note: webp/jpg/png are recommended — the frontmatter image doubles as the
OpenGraph/Twitter social-card, and most platforms don't render SVG previews.
SVG stays available via --format svg.
`);
  process.exit(1);
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    logo: DEFAULT_LOGO_PATH,
    format: DEFAULT_FORMAT,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === '--text' || arg === '-t') {
      if (!next) printUsageAndExit('Missing value for --text');
      options.text = next.trim();
      i += 1;
      continue;
    }

    if (arg === '--out' || arg === '-o') {
      if (!next) printUsageAndExit('Missing value for --out');
      options.out = next.trim();
      i += 1;
      continue;
    }

    if (arg === '--format' || arg === '-f') {
      if (!next) printUsageAndExit('Missing value for --format');
      const fmt = next.trim().toLowerCase();
      if (!VALID_FORMATS.includes(fmt as Format)) {
        printUsageAndExit(`Invalid --format "${next}". Use one of: ${VALID_FORMATS.join(', ')}`);
      }
      options.format = fmt as Format;
      i += 1;
      continue;
    }

    if (arg === '--width') {
      const width = Number(next);
      if (!Number.isFinite(width) || width <= 0) printUsageAndExit('Invalid --width');
      options.width = width;
      i += 1;
      continue;
    }

    if (arg === '--height') {
      const height = Number(next);
      if (!Number.isFinite(height) || height <= 0) printUsageAndExit('Invalid --height');
      options.height = height;
      i += 1;
      continue;
    }

    if (arg === '--logo') {
      if (!next) printUsageAndExit('Missing value for --logo');
      options.logo = next.trim();
      i += 1;
      continue;
    }

    if (arg === '--help' || arg === '-h') {
      printUsageAndExit();
    }

    printUsageAndExit(`Unknown argument "${arg}"`);
  }

  if (!options.text) {
    printUsageAndExit('Missing --text');
  }

  return options as CliOptions;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/['"]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'blog-cover';
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function getMimeType(filepath: string): string {
  const ext = path.extname(filepath).toLowerCase();
  if (ext === '.png') return 'image/png';
  if (ext === '.jpg' || ext === '.jpeg') return 'image/jpeg';
  if (ext === '.webp') return 'image/webp';
  if (ext === '.svg') return 'image/svg+xml';
  return 'application/octet-stream';
}

function buildSvg(text: string, width: number, height: number, logoDataUri: string): string {
  const { lines, fontSize, baselines, logo } = blogCoverLayout(text, width, height);

  const titleLines = lines
    .map((line, index) => {
      return `<text x="${width / 2}" y="${baselines[index]}" text-anchor="middle" font-family="${BLOG_COVER_FONT_FAMILY}" font-size="${fontSize}" font-weight="700" fill="${BLOG_COVER_TEXT_COLOR}">${escapeXml(line)}</text>`;
    })
    .join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="${width}" y2="${height}" gradientUnits="userSpaceOnUse">
      <stop stop-color="${BLOG_COVER_GRADIENT_FROM}"/>
      <stop offset="1" stop-color="${BLOG_COVER_GRADIENT_TO}"/>
    </linearGradient>
  </defs>

  <rect width="${width}" height="${height}" fill="url(#bg)"/>
  ${titleLines}

  <image href="${logoDataUri}" x="${logo.x}" y="${logo.y}" width="${logo.width}" height="${logo.height}" preserveAspectRatio="xMidYMid meet"/>
</svg>`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const slug = slugify(options.text);
  const ext = options.format === 'jpeg' ? 'jpg' : options.format;
  const output = options.out || path.join(DEFAULT_OUTPUT_DIR, `blog-${slug}.${ext}`);
  const outputDir = path.dirname(output);
  const logoPath = options.logo;
  const logoBuffer = await fs.readFile(logoPath);
  const logoMime = getMimeType(logoPath);
  const logoDataUri = `data:${logoMime};base64,${logoBuffer.toString('base64')}`;
  const svg = buildSvg(options.text, options.width, options.height, logoDataUri);

  await fs.mkdir(outputDir, { recursive: true });

  if (options.format === 'svg') {
    await fs.writeFile(output, svg, 'utf8');
  } else {
    // Rasterize the SVG at 2x so the hero stays crisp on retina displays.
    const width = options.width * RASTER_SCALE;
    const height = options.height * RASTER_SCALE;
    let pipeline = sharp(Buffer.from(svg), { density: 72 * RASTER_SCALE }).resize(width, height);

    if (options.format === 'webp') {
      pipeline = pipeline.webp({ quality: 90 });
    } else if (options.format === 'png') {
      pipeline = pipeline.png();
    } else {
      // jpg / jpeg — flatten any alpha onto white (JPEG has no transparency).
      pipeline = pipeline.flatten({ background: '#ffffff' }).jpeg({ quality: 88 });
    }

    await pipeline.toFile(output);
  }

  console.log(`Generated cover: ${output}`);
  console.log(`Use in frontmatter image field: /${output.replace(/^public\//, '')}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
