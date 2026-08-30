import 'server-only';

/**
 * Resolves the latest published desktop build from GitHub Releases.
 *
 * Asset names carry the version (`Vicoa-0.1.13-arm64.dmg`, `Vicoa-0.1.13.dmg`,
 * `Vicoa-Setup-0.1.13.exe`), so there's no static "latest" URL to link — we read
 * the release feed and pull the two macOS DMGs and the Windows installer out of
 * it. Linux isn't published yet.
 */

const RELEASES_API = 'https://api.github.com/repos/vicoa-ai/vicoa/releases/latest';

export type DesktopRelease = {
  version: string;
  macArm64Url: string | null;
  macX64Url: string | null;
  winX64Url: string | null;
};

type GithubAsset = { name: string; browser_download_url: string };

export async function getLatestDesktopRelease(): Promise<DesktopRelease | null> {
  try {
    const res = await fetch(RELEASES_API, {
      headers: { Accept: 'application/vnd.github+json' },
      next: { revalidate: 3600 },
    });
    if (!res.ok) return null;

    const data = (await res.json()) as { tag_name?: string; assets?: GithubAsset[] };
    const assets = data.assets ?? [];
    const dmgs = assets.filter((a) => a.name.toLowerCase().endsWith('.dmg'));

    const macArm64Url = dmgs.find((a) => /arm64/i.test(a.name))?.browser_download_url ?? null;
    const macX64Url = dmgs.find((a) => !/arm64/i.test(a.name))?.browser_download_url ?? null;
    // Windows ships as a single 64-bit NSIS installer (`Vicoa-Setup-<v>.exe`).
    const winX64Url =
      assets.find((a) => a.name.toLowerCase().endsWith('.exe'))?.browser_download_url ?? null;

    return { version: data.tag_name ?? '', macArm64Url, macX64Url, winX64Url };
  } catch {
    return null;
  }
}
