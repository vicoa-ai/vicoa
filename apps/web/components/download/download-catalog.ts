/**
 * Single source of truth for everything the download page offers.
 *
 * A target with no `href` renders as a placeholder (Linux desktop, for now).
 * Adding a release URL to a target is all it takes to make both the hero button
 * and the matching pill live.
 */

export const IOS_APP_URL = 'http://apps.apple.com/sg/app/id6751626168';
export const ANDROID_APP_URL = 'https://play.google.com/store/apps/details?id=app.vicoa';
export const WEB_APP_URL = '/dashboard';
export const CHANGELOG_URL = '/docs/changelog';
export const CLI_INSTALL_COMMAND = 'npm i -g @vicoa/cli && vicoa';

export const TAGLINE = 'Orchestrate AI agents in parallel and get 10x more done';

export type PlatformId = 'macos' | 'windows' | 'linux' | 'ios' | 'android';
export type MacArch = 'apple-silicon' | 'intel' | 'unknown';

/** Latest desktop installer URLs, resolved server-side from GitHub Releases. */
export type DesktopUrls = {
  macArm64: string | null;
  macX64: string | null;
  winX64: string | null;
};

export type HeroAction = {
  label: string;
  /** Omit for a placeholder — the desktop builds aren't out yet. */
  href?: string;
  external?: boolean;
  track: string;
};

export type HeroContent = {
  /** Heading reads "Vicoa for {osLabel}". */
  osLabel: string;
  /** First action is the primary button; any others render as secondary. */
  actions: HeroAction[];
};

export function heroFor(
  platform: PlatformId,
  macArch: MacArch = 'unknown',
  urls?: DesktopUrls
): HeroContent {
  const macAppleSilicon: HeroAction = {
    label: 'Download for Apple Silicon',
    href: urls?.macArm64 ?? undefined,
    track: 'hero-macos-arm64',
  };
  const macIntel: HeroAction = {
    label: 'Download for Intel',
    href: urls?.macX64 ?? undefined,
    track: 'hero-macos-x64',
  };

  switch (platform) {
    case 'macos':
      if (macArch === 'apple-silicon') return { osLabel: 'macOS', actions: [macAppleSilicon] };
      if (macArch === 'intel') return { osLabel: 'macOS', actions: [macIntel] };
      // Architecture is unknowable here — offer both rather than hand someone
      // the wrong binary.
      return { osLabel: 'macOS', actions: [macAppleSilicon, { ...macIntel, label: 'Intel' }] };
    case 'windows':
      return {
        osLabel: 'Windows',
        actions: [
          {
            label: 'Download for Windows',
            href: urls?.winX64 ?? undefined,
            track: 'hero-windows-x64',
          },
        ],
      };
    case 'linux':
      return {
        osLabel: 'Linux',
        actions: [{ label: 'Download AppImage', track: 'hero-linux-appimage' }],
      };
    case 'ios':
      return {
        osLabel: 'iOS',
        actions: [
          { label: 'Get it on the App Store', href: IOS_APP_URL, external: true, track: 'hero-ios' },
        ],
      };
    case 'android':
      return {
        osLabel: 'Android',
        actions: [
          {
            label: 'Get it on Google Play',
            href: ANDROID_APP_URL,
            external: true,
            track: 'hero-android',
          },
        ],
      };
  }
}

export function detectPlatform(): PlatformId | null {
  if (typeof navigator === 'undefined') return null;
  const ua = navigator.userAgent;

  if (/Windows/i.test(ua)) return 'windows';
  if (/Android/i.test(ua)) return 'android';
  if (/iPhone|iPod/i.test(ua)) return 'ios';
  // iPadOS 13+ reports a desktop Safari UA; touch points are what give it away.
  if (/iPad/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1)) return 'ios';
  if (/Mac/i.test(ua)) return 'macos';
  if (/Linux|X11/i.test(ua)) return 'linux';
  return null;
}

/**
 * Apple Silicon vs Intel, best effort.
 *
 * There is no direct API: `navigator.platform` reports "MacIntel" on Apple
 * Silicon too, and the UA string never carries the architecture. The GPU
 * renderer string is the one broadly available signal — Apple Silicon reports
 * an Apple GPU, Intel Macs report Intel/AMD. Browsers that mask the renderer
 * (or block WebGL) yield 'unknown', and the caller offers both builds instead.
 */
export function detectMacArch(): MacArch {
  if (typeof document === 'undefined') return 'unknown';
  try {
    const canvas = document.createElement('canvas');
    const gl = (canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl')) as WebGLRenderingContext | null;
    if (!gl) return 'unknown';

    const info = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = String(
      info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
    );

    if (/Apple\s*(M\d|GPU|Silicon)/i.test(renderer)) return 'apple-silicon';
    if (/Intel|AMD|Radeon|NVIDIA|GeForce/i.test(renderer)) return 'intel';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}
