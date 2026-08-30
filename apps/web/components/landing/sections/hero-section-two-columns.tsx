import { LiteYouTubeEmbed } from '@/components/ui/lite-youtube-embed';
import { Terminal } from '@/components/terminal';
import { ArrowRight } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import type { AuthUser } from '@/lib/auth/user';
import { DynamicPhrase } from './dynamic-phrase';

interface HeroSectionProps {
  variant?: 'default' | 'vicoa';
  user?: AuthUser | null;
}

export function HeroSection({ variant = 'default', user }: HeroSectionProps) {
  const content = {
    default: {
      heroTitle: "Code with AI, ",
      heroTitleHighlight: "Anywhere",
      heroDescription: "Run parallel Claude Code, Codex, and OpenCode remotely from any device, keep working and ship more.",
      videoTitle: "Vibe Code Anywhere (Vicoa) Introduction",
    },
    vicoa: {
      heroTitle: "Code with AI, ",
      heroTitleHighlight: "Anywhere",
      heroDescription: "Run parallel Claude Code, Codex, and OpenCode remotely from any device, keep working and ship more.",
      videoTitle: "Vicoa - Vibe Code Anywhere Introduction",
    }
  };

  const currentContent = content[variant];

  return (
    <section className="relative py-12 lg:py-20 bg-muted/30">
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-[36%_64%] gap-8 lg:gap-12 items-center">
          {/* Left Column - Text Content */}
          <div className="text-center lg:text-left">
            <h1 className="text-3xl sm:text-4xl lg:text-7xl text-foreground tracking-tight leading-tight mb-6">
              {currentContent.heroTitle}
              <DynamicPhrase />
            </h1>
            <p className="text-lg lg:text-xl text-muted-foreground mb-8 leading-relaxed">
              {currentContent.heroDescription}
            </p>

            {/* Step 1: Installation */}
            <div className="mb-6 flex justify-center lg:justify-start">
              <Terminal className="w-full max-w-md" />
            </div>

            {/* Step 2: Download Apps */}
            <div className="flex flex-col sm:flex-row items-center lg:items-start sm:items-center gap-4 justify-center lg:justify-start">
              <div className="relative group">
                <Link href="http://apps.apple.com/sg/app/id6751626168" target="_blank" rel="noopener noreferrer">
                  <Image
                    src="/images/appstore.webp"
                    alt="Download Vicoa on the App Store"
                    width={160}
                    height={47}
                    className="hover:opacity-80 transition-opacity duration-300"
                  />
                </Link>
                <div className="absolute top-full left-1/2 mt-2 -translate-x-1/2 opacity-0 transition-opacity duration-300 pointer-events-none group-hover:opacity-100 z-[9999]">
                  <div className="bg-gray-900 p-6 rounded-xl shadow-2xl border border-gray-700 min-w-[200px]">
                    <Image
                      src="/images/vicoa-ios-qrcode.png"
                      alt="QR Code to download Vicoa app"
                      width={240}
                      height={240}
                      className="mx-auto"
                    />
                    <p className="text-sm text-gray-300 text-center mt-4">Scan to download Vicoa</p>
                  </div>
                </div>
              </div>
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center gap-2 px-6 py-3 border border-gray-700 text-base rounded-xl text-white bg-gray-900 hover:bg-gray-800 hover:border-gray-600 transition-colors duration-300 shadow-sm w-full sm:w-auto"
              >
                Get Started Free
                <ArrowRight className="w-5 h-5 hidden sm:inline" />
              </Link>
            </div>
          </div>

          {/* Right Column - Hero Image (Much Larger) */}
          <div className="relative">
            <div className="relative aspect-video rounded-xl overflow-hidden shadow-2xl">
              <LiteYouTubeEmbed
                videoId="ZBpNzqqLYmg"
                title={currentContent.videoTitle}
                className="rounded-xl"
                coverImage="/images/hero.webp"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
