'use client';

import { useEffect } from 'react';
import { Footer } from '@/components/footer';
import { NavigationHeader } from '@/components/navigation-header';

const IOS_APP_URL = 'http://apps.apple.com/sg/app/id6751626168';
const ANDROID_APP_URL = 'https://play.google.com/store/apps/details?id=app.vicoa';
const DESKTOP_URL = 'https://vicoa.ai';

export default function DownloadMobileAppPage() {
  useEffect(() => {
    const userAgent = navigator.userAgent || navigator.vendor;

    if (/android/i.test(userAgent)) {
      window.location.replace(ANDROID_APP_URL);
      return;
    }

    if (/iPad|iPhone|iPod|Apple/.test(userAgent) && !(window as Window & { MSStream?: unknown }).MSStream) {
      window.location.replace(IOS_APP_URL);
      return;
    }

    window.location.replace(DESKTOP_URL);
  }, []);

  return (
    <section className="flex min-h-screen flex-col bg-background text-foreground">
      <NavigationHeader />
      <main className="flex flex-1 items-center justify-center px-5 py-16 text-center sm:px-8">
        <div className="max-w-2xl">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Redirecting...
          </h1>
          <p className="mt-4 text-lg text-muted-foreground">
            Please wait while we redirect you to the appropriate app store.
          </p>
        </div>
      </main>
      <Footer />
    </section>
  );
}
