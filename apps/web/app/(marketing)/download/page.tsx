import type { Metadata } from 'next';
import { DownloadHero } from '@/components/download/download-hero';
import {
  ComingSoon,
  CommandBlock,
  DownloadPill,
  DownloadRow,
  DownloadSection,
} from '@/components/download/download-ui';
import {
  ANDROID_APP_URL,
  CHANGELOG_URL,
  CLI_INSTALL_COMMAND,
  IOS_APP_URL,
  WEB_APP_URL,
} from '@/components/download/download-catalog';
import { getLatestDesktopRelease } from '@/lib/desktop-release';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/download', {
  title: 'Download Vicoa for macOS, Windows, Linux, iOS, and Android',
  description:
    'Install Vicoa on every platform. Native desktop apps for macOS, Windows, and Linux, mobile apps for iOS and Android, a web app, and a CLI for servers and headless setups.',
});

const IOS_QR = '/images/vicoa-ios-qrcode.png';
const ANDROID_QR = '/images/vicoa-android-qrcode.png';

export default async function DownloadPage() {
  const release = await getLatestDesktopRelease();
  const desktopUrls = {
    macArm64: release?.macArm64Url ?? null,
    macX64: release?.macX64Url ?? null,
    winX64: release?.winX64Url ?? null,
  };

  return (
    <div className="bg-background">
      <main className="container mx-auto max-w-3xl px-4 py-16 sm:py-20">
        <DownloadHero urls={desktopUrls} />

        <div id="all-platforms" className="mt-12 scroll-mt-8 space-y-6">
          <DownloadSection
            title="Desktop"
            description="Recommended — bundles everything you need"
            icon="monitor"
            footnote="macOS ships as separate Apple Silicon and Intel builds; pick the one that matches your chip. Windows is a 64-bit installer for Windows 10 and 11. Linux builds are coming soon."
          >
            <DownloadRow icon="apple" label="macOS">
              <DownloadPill
                href={desktopUrls.macArm64 ?? undefined}
                label="Apple Silicon"
                track="macos-arm64"
              />
              <DownloadPill href={desktopUrls.macX64 ?? undefined} label="Intel" track="macos-x64" />
            </DownloadRow>
            <DownloadRow icon="windows" label="Windows">
              <DownloadPill
                href={desktopUrls.winX64 ?? undefined}
                label="Download"
                track="windows-x64"
              />
            </DownloadRow>
            <DownloadRow icon="linux" label="Linux">
              <ComingSoon />
            </DownloadRow>
          </DownloadSection>

          <DownloadSection
            title="Mobile"
            description="Start on your laptop, keep going from your pocket"
            icon="phone"
            footnote="On a desktop? Hover a store button to scan the code with your phone."
          >
            <DownloadRow icon="apple" label="iOS">
              <DownloadPill
                href={IOS_APP_URL}
                label="App Store"
                track="ios"
                external
                qr={{ src: IOS_QR, position: 'top' }}
              />
            </DownloadRow>
            <DownloadRow icon="android" label="Android">
              <DownloadPill
                href={ANDROID_APP_URL}
                label="Play Store"
                track="android"
                external
                qr={{ src: ANDROID_QR, position: 'bottom' }}
              />
            </DownloadRow>
          </DownloadSection>

          <DownloadSection
            title="Web"
            description="Nothing to install — run Vicoa from any browser"
            icon="globe"
          >
            <DownloadRow icon="globe" label="Web App">
              <DownloadPill href={WEB_APP_URL} label="Open" track="web" />
            </DownloadRow>
          </DownloadSection>

          <DownloadSection
            title="CLI"
            description="Run Vicoa on a server, remote dev box, or headless setup"
            icon="terminal"
            footnote="Requires Node.js 18+. The same command works over SSH."
          >
            <DownloadRow icon="terminal" label="npm">
              <CommandBlock command={CLI_INSTALL_COMMAND} event="cli_npm" />
            </DownloadRow>
          </DownloadSection>
        </div>

        <p className="mt-8 text-center text-xs text-muted-foreground">
          Release notes for every version are in the{' '}
          <a href={CHANGELOG_URL} className="underline transition-colors hover:text-foreground">
            changelog
          </a>
          .
        </p>
      </main>
    </div>
  );
}
