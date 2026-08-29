import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { RootProvider } from 'fumadocs-ui/provider';
import type { ReactNode } from 'react';
import { docsOptions } from './layout.config';
import Image from 'next/image';
import Link from 'next/link';

export default function Layout({ children }: { children: ReactNode }) {
  const customOptions = {
    ...docsOptions,
    nav: {
      ...docsOptions.nav,
      title: (
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-5 h-5 flex-shrink-0 bg-transparent">
            <Image 
              src="/images/vicoa-light.webp" 
              alt="Vicoa Logo" 
              width={20} 
              height={20}
              className="rounded-sm w-full h-full object-cover"
              priority
              unoptimized
            />
          </div>
          <span className="font-semibold whitespace-nowrap text-inherit">Vicoa</span>
        </div>
      ),
    },
    sidebar: {
      ...docsOptions.sidebar,
      footer: (
        <div className="p-4">
          <a 
            href="/" 
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to Vicoa
          </a>
        </div>
      ),
    },
  };

  return (
    <RootProvider>
      <DocsLayout {...customOptions}>
        {children}
      </DocsLayout>
    </RootProvider>
  );
}
