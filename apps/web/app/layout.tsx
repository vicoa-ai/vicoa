import './globals.css';
import type { Metadata, Viewport } from 'next';
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import Script from 'next/script';
import { SWRConfig } from 'swr';
import { ThemeProvider } from '@/components/theme-provider';
import { PluginThemeStyle } from '@/components/plugins/plugin-theme-style';
import { PostHogIdentify } from '@/components/posthog-identify';
import { DesktopAuthGate } from '@/components/dashboard/desktop-auth-gate';
import { DesktopAuthHandoff } from '@/components/dashboard/desktop-auth-handoff';
import { DesktopWindowControls } from '@/components/desktop/window-chrome';

export const metadata: Metadata = {
  metadataBase: new URL('https://vicoa.ai'),
  title: 'Vicoa - Run & Manage a Team of AI Agents Anywhere',
  description: 'Vicoa is an agent-native IDE that lets you orchestrate parallel AI agents like Claude Code, Codex, and OpenCode on your phone and desktop. Put your coding agents in your pocket and start building from anywhere.',
  icons: [
    { rel: 'icon', url: '/favicon.ico', sizes: 'any' },
    { rel: 'shortcut icon', url: '/favicon.ico' },
    { rel: 'icon', url: '/favicon-192x192.png', sizes: '192x192', type: 'image/png' },
    { rel: 'icon', url: '/favicon-512x512.png', sizes: '512x512', type: 'image/png' },
    { rel: 'apple-touch-icon', url: '/favicon-apple.png', sizes: '180x180' },
  ],
  manifest: '/manifest.json',
  keywords: [
    'Vicoa',
    'Vicoa app',
    'Vicoa mobile',
    'Remove control',
    'Claude Code remote control',
    'Codex remote control',
    'Opencode remote control',
    'Gemini remote control',
    'Cursor remote control',
    'Code with AI',
    'coding agents',
    'mobile coding',
    'AI coding agents', 
    'Claude Code mobile',
    'Claude Code anywhere',
    'vibe coding',
    'vibe coding anywhere',
    'mobile development',
    'AI programming',
    'code anywhere',
    'code everywhere',
    'mobile AI assistant',
    'developer tools mobile',
    'developer tools everywhere',
    'coding on mobile',
    'coding everywhere',
    'AI-assisted development',
    'remote coding',
    'remote coding everywhere',
    'mobile code editor',
    'artificial intelligence coding',
    'programming assistant'
  ],
  authors: [{ name: 'Vicoa Team' }],
  creator: 'Vicoa',
  publisher: 'Vicoa',
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: 'https://vicoa.ai',
    siteName: 'Vicoa - Run & Manage a Team of AI Agents Anywhere',
    title: 'Vicoa - Run & Manage a Team of AI Agents Anywhere',
    description: 'Vicoa is an agent-native IDE that lets you orchestrate parallel AI agents like Claude Code, Codex, and OpenCode on your phone and desktop. Put your coding agents in your pocket and start building from anywhere.',
    images: [
      {
        url: '/images/vicoa-banner.png',
        width: 1200,
        height: 630,
        alt: 'Vicoa - Run & Manage a Team of AI Agents Anywhere',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    site: '@Vicoa',
    creator: '@Vicoa',
    title: 'Vicoa - Run & Manage a Team of AI Agents Anywhere',
    description: 'Vicoa is an agent-native IDE that lets you orchestrate parallel AI agents like Claude Code, Codex, and OpenCode on your phone and desktop. Put your coding agents in your pocket and start building from anywhere.',
    images: ['/images/vicoa-banner.png'],
  },
  alternates: {
    canonical: 'https://vicoa.ai',
  },
  category: 'technology',
  classification: 'Developer Tools',
  applicationName: 'Vicoa',
  referrer: 'origin-when-cross-origin',
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  other: {
    'apple-itunes-app': 'app-id=6751626168',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#1a1a1a' }
  ]
};

// Desktop builds run their own local Next server with this flag set. As a
// compile-time constant it is identical on server and client, so it can gate
// desktop-only chrome below without a hydration mismatch.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} dark`}
      suppressHydrationWarning
    >
      <head>
        {/* Pre-hydration theme class. `<html>` ships with `dark` as the no-JS
            default; this blocking script runs before first paint and swaps in
            the user's stored choice so light-mode users never see a dark flash.
            Mirrors theme-provider.tsx: storageKey `ui-theme`, `system` resolves
            via matchMedia, and `plugin:` themes fall back to their dark base
            until the provider resolves the real base post-mount. Must stay a
            raw <script> (not next/script, which defers). */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('ui-theme')||'dark';var c='dark';if(t==='light')c='light';else if(t==='system')c=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';else if(t.indexOf('plugin:')===0)c='dark';var e=document.documentElement;e.classList.remove('light','dark');e.classList.add(c);}catch(e){}})();`,
          }}
        />
        <Script
          src="https://www.googletagmanager.com/gtag/js?id=G-EWZH9BN2RK"
          strategy="lazyOnload"
        />
        <Script id="gtag-init" strategy="lazyOnload">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-EWZH9BN2RK');
          `}
        </Script>
      </head>
      <body 
        className="min-h-[100dvh] bg-background text-foreground"
        suppressHydrationWarning
      >
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Organization",
              "name": "Vicoa",
              "alternateName": "Vibe Code Anywhere",
              "url": "https://vicoa.ai",
              "logo": "https://vicoa.ai/images/vicoa-light.png",
            })
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              "name": "Vicoa",
              "alternateName": "Vibe Code Anywhere",
              "url": "https://vicoa.ai",
              "description":
                "Vicoa lets you orchestrate dozens of coding agents in parallel, anywhere. Run Claude Code and other AI coding agents on any device — start on your laptop, switch seamlessly to mobile or web, get alerts when an agent needs input, and approve changes with one tap.",
              "applicationCategory": "DeveloperApplication",
              "operatingSystem": "Web, iOS, Android",
              "image": "https://vicoa.ai/images/vicoa-banner.png",
              "screenshot": "https://vicoa.ai/images/hero.png",
              "publisher": {
                "@type": "Organization",
                "name": "Vicoa",
                "url": "https://vicoa.ai",
              },
              "offers": {
                "@type": "AggregateOffer",
                "priceCurrency": "USD",
                "lowPrice": "0",
                "highPrice": "12",
                "offerCount": "3",
              },
            })
          }}
        />
        <PostHogIdentify />
        <ThemeProvider defaultTheme="dark">
          {/* Injects token overrides for the active plugin theme (Tier 1); renders
              nothing for the built-in dark/light/system themes. */}
          <PluginThemeStyle />
          <SWRConfig value={{}}>
            {/* Desktop: mint the CLI key whenever a Supabase session appears in
                local mode. Mounted here (not just in the dashboard layout) so it
                also fires on the auth screens under login-required gating. */}
            {IS_DESKTOP ? <DesktopAuthHandoff /> : null}
            <DesktopAuthGate>{children}</DesktopAuthGate>
            {/* Windows custom title bar controls (min/max/close). Mounted last in
                DOM order so Electron's drag hit-test leaves them clickable over the
                surrounding drag strips; renders nothing on macOS/web. */}
            {IS_DESKTOP ? <DesktopWindowControls /> : null}
          </SWRConfig>
        </ThemeProvider>
      </body>
    </html>
  );
}
