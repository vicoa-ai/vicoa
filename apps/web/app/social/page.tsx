import type { Metadata } from 'next';
import Image from 'next/image';
import Link from 'next/link';
import {
  BookOpen,
  Bot,
  Download,
  Globe,
  Linkedin,
  Mail,
  Newspaper,
  ScrollText,
  Sparkles,
} from 'lucide-react';

import { DiscordIcon } from '@/components/discord-icon';
import { Icon as PlatformIcon } from '@/components/download/download-ui';
import {
  ANDROID_APP_URL,
  CHANGELOG_URL,
  IOS_APP_URL,
  WEB_APP_URL,
} from '@/components/download/download-catalog';
import { GithubIcon } from '@/components/github-icon';
import { SocialLink, type SocialLinkProps } from '@/components/social/social-link';
import { XIcon } from '@/components/x-icon';
import {
  CONTACT_EMAIL,
  DISCORD_INVITE_URL,
  GITHUB_REPO_URL,
  LINKEDIN_URL,
  X_URL,
} from '@/lib/constants/links';
import { pageMetadata } from '@/lib/seo';

const PAGE_TITLE = 'Vicoa Links: Apps, Community, and Socials';
const PAGE_DESCRIPTION =
  'Every Vicoa link in one place: the desktop, iOS, and Android apps, plus our Discord, X, GitHub, LinkedIn, docs, blog, and changelog.';

export const metadata: Metadata = pageMetadata('/social', {
  title: PAGE_TITLE,
  description: PAGE_DESCRIPTION,
  openGraph: {
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: PAGE_TITLE,
    description: PAGE_DESCRIPTION,
  },
});

const ICON = 'h-[18px] w-[18px]';

const GROUPS: { id: string; title: string; links: SocialLinkProps[] }[] = [
  {
    id: 'get',
    title: 'Get Vicoa',
    links: [
      {
        id: 'download',
        href: '/download',
        label: 'Download Vicoa',
        detail: 'macOS, Windows, Linux',
        icon: <Download className={ICON} />,
        primary: true,
      },
      {
        id: 'ios',
        href: IOS_APP_URL,
        label: 'iPhone and iPad',
        detail: 'App Store',
        icon: <PlatformIcon name="apple" className={ICON} />,
        external: true,
      },
      {
        id: 'android',
        href: ANDROID_APP_URL,
        label: 'Android',
        detail: 'Google Play',
        icon: <PlatformIcon name="android" className={ICON} />,
        external: true,
      },
      {
        id: 'web-app',
        href: WEB_APP_URL,
        label: 'Web app',
        detail: 'In your browser',
        icon: <Globe className={ICON} />,
      },
    ],
  },
  {
    id: 'community',
    title: 'Community',
    links: [
      {
        id: 'discord',
        href: DISCORD_INVITE_URL,
        label: 'Discord',
        detail: 'Chat with the team',
        icon: <DiscordIcon className={ICON} />,
        external: true,
      },
      {
        id: 'x',
        href: X_URL,
        label: 'X',
        detail: '@vicoaai',
        icon: <XIcon className={ICON} />,
        external: true,
      },
      {
        id: 'github',
        href: GITHUB_REPO_URL,
        label: 'GitHub',
        detail: 'Open source',
        icon: <GithubIcon className={ICON} />,
        external: true,
      },
      {
        id: 'linkedin',
        href: LINKEDIN_URL,
        label: 'LinkedIn',
        icon: <Linkedin className={ICON} />,
        external: true,
      },
      {
        id: 'email',
        href: `mailto:${CONTACT_EMAIL}`,
        label: 'Email us',
        detail: CONTACT_EMAIL,
        icon: <Mail className={ICON} />,
      },
    ],
  },
  {
    id: 'learn',
    title: 'Learn',
    links: [
      {
        id: 'docs',
        href: '/docs',
        label: 'Documentation',
        icon: <BookOpen className={ICON} />,
      },
      {
        id: 'coding-agents',
        href: '/coding-agents',
        label: 'Supported coding agents',
        detail: '40+',
        icon: <Bot className={ICON} />,
      },
      {
        id: 'blog',
        href: '/blog',
        label: 'Blog',
        icon: <Newspaper className={ICON} />,
      },
      {
        id: 'updates',
        href: '/updates',
        label: "What's new",
        icon: <Sparkles className={ICON} />,
      },
      {
        id: 'changelog',
        href: CHANGELOG_URL,
        label: 'Changelog',
        detail: 'Desktop, mobile, CLI',
        icon: <ScrollText className={ICON} />,
      },
    ],
  },
];

// Link-in-bio page: the one URL the X, LinkedIn, Discord and other profiles
// point at. Deliberately outside the (marketing) group, so it renders without
// the site header and footer: a single phone-width column of links is the
// whole page.
export default function SocialPage() {
  return (
    <main className="flex min-h-[100dvh] flex-col items-center px-4 py-12 sm:py-16">
      <div className="w-full max-w-md">
        <header className="flex flex-col items-center text-center">
          <Image
            src="/favicon-512x512.png"
            alt="Vicoa logo"
            width={56}
            height={56}
            priority
            className="h-14 w-14 rounded-[22%]"
          />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-foreground">Vicoa</h1>
          <p className="mt-2 max-w-sm text-balance text-sm leading-relaxed text-muted-foreground">
            Run a team of coding agents in parallel, from your phone, desktop, or browser. Claude
            Code, Codex, and 40+ more.
          </p>
        </header>

        <nav aria-label="Vicoa links" className="mt-10 space-y-8">
          {GROUPS.map((group) => (
            <section key={group.id} aria-labelledby={`social-${group.id}`}>
              <h2
                id={`social-${group.id}`}
                className="mb-2 px-1 text-[0.8rem] font-normal text-muted-foreground"
              >
                {group.title}
              </h2>
              <ul className="space-y-2">
                {group.links.map((link) => (
                  <li key={link.id}>
                    <SocialLink {...link} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>

        <footer className="mt-12 flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <Link href="/" className="cursor-pointer transition-colors hover:text-foreground">
            vicoa.ai
          </Link>
          <span aria-hidden="true">·</span>
          <span>&copy; 2026 Vicoa</span>
        </footer>
      </div>
    </main>
  );
}
