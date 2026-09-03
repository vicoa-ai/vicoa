'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import Image from 'next/image';
import { Bell, BookOpen, Download, Menu, Newspaper } from 'lucide-react';

import { UnifiedUserMenu } from '@/components/unified-user-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { GithubIcon } from '@/components/github-icon';
import { GITHUB_REPO_URL } from '@/lib/constants/links';

export function NavigationHeader() {
  return (
    <header className="border-border bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
        <Link href="/" className="flex items-center">
          <Image
            src="/images/vicoa-logo-text.webp"
            alt="Vicoa Logo"
            width={0}
            height={0}
            sizes="100vw"
            className="h-10 w-auto"
          />
        </Link>

        <nav className="hidden md:flex items-center space-x-2">
          <DropdownMenu>
            <DropdownMenuTrigger className="text-sm font-medium text-foreground/80 hover:text-foreground hover:bg-muted px-4 py-2 rounded-md transition-all focus:outline-none focus-visible:outline-none">
              Resources
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-68">
              <DropdownMenuItem asChild>
                <Link href="/download" className="cursor-pointer w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-900 rounded-sm transition-colors">
                  <div className="flex items-center justify-center h-10 w-10 bg-gray-100 dark:bg-gray-800 rounded-md flex-shrink-0">
                    <Download className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="font-large">Download</span>
                    <span className="text-xs text-muted-foreground">Get Vicoa on every platform</span>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/docs" className="cursor-pointer w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-900 rounded-sm transition-colors">
                  <div className="flex items-center justify-center h-10 w-10 bg-gray-100 dark:bg-gray-800 rounded-md flex-shrink-0">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="font-large">Docs</span>
                    <span className="text-xs text-muted-foreground">Learn about Vicoa and get started</span>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/blog" className="cursor-pointer w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-900 rounded-sm transition-colors">
                  <div className="flex items-center justify-center h-10 w-10 bg-gray-100 dark:bg-gray-800 rounded-md flex-shrink-0">
                    <Newspaper className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="font-large">Blog</span>
                    <span className="text-xs text-muted-foreground">Ideas, guides, and user stories</span>
                  </div>
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/updates" className="cursor-pointer w-full flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-900 rounded-sm transition-colors">
                  <div className="flex items-center justify-center h-10 w-10 bg-gray-100 dark:bg-gray-800 rounded-md flex-shrink-0">
                    <Bell className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="font-large">Updates</span>
                    <span className="text-xs text-muted-foreground">What's new with Vicoa?</span>
                  </div>
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <Link
            href="/pricing"
            className="text-sm font-medium text-foreground/80 hover:text-foreground hover:bg-muted px-4 py-2 rounded-md transition-all"
          >
            Pricing
          </Link>

          <Link
            href="/features"
            className="text-sm font-medium text-foreground/80 hover:text-foreground hover:bg-muted px-4 py-2 rounded-md transition-all"
          >
            Features
          </Link>
        </nav>

        <div className="flex items-center space-x-4">
          <Suspense fallback={<div className="h-9" />}>
            <DropdownMenu>
              <DropdownMenuTrigger className="md:hidden text-foreground/80 hover:text-foreground hover:bg-muted p-2 rounded-md transition-all">
                <Menu className="h-5 w-5" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem asChild>
                  <Link href="/docs" className="cursor-pointer w-full">
                    Docs
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/blog" className="cursor-pointer w-full">
                    Blog
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/updates" className="cursor-pointer w-full">
                    Updates
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/download" className="cursor-pointer w-full">
                    Download
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/pricing" className="cursor-pointer w-full">
                    Pricing
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href="/features" className="cursor-pointer w-full">
                    Features
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Vicoa on GitHub"
              title="Vicoa is open source — star us on GitHub"
              className="flex h-10 w-10 items-center justify-center rounded-full text-foreground/80 hover:text-foreground hover:bg-muted transition-all"
            >
              <GithubIcon className="h-5 w-5" />
            </a>
            <div className="hidden md:flex">
              <UnifiedUserMenu variant="button" />
            </div>
          </Suspense>
        </div>
      </div>
    </header>
  );
}
