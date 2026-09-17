'use client';

// The one honest failure page for `/s/<token>` (collaboration §10.5): unknown,
// revoked, expired and audience-restricted links all look the same to the
// visitor, by design — a page that distinguished them would be an oracle. The
// one useful hint is that signing in might help, so an anonymous visitor gets a
// sign-in button that returns them here.

import { useEffect, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { readBrowserIdentity } from '@/lib/auth/browser-token';

export default function ShareNotFound() {
  const pathname = usePathname();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    readBrowserIdentity()
      .then((me) => {
        if (!cancelled) setSignedIn(me !== null);
      })
      .catch(() => {
        if (!cancelled) setSignedIn(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <Image src="/images/vicoa-logo-text.webp" alt="Vicoa" width={0} height={0} sizes="100vw" className="h-8 w-auto" priority />
      <div className="space-y-1">
        <h1 className="text-lg font-medium">This link isn&apos;t available</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          It may have been revoked or expired
          {signedIn ? '.' : ', or it may be limited to signed-in Vicoa users.'}
        </p>
      </div>
      <div className="flex gap-2">
        {signedIn === false && (
          <Button asChild size="sm" variant="outline">
            <Link href={`/sign-in?redirect=${encodeURIComponent(pathname ?? '/')}`}>Sign in</Link>
          </Button>
        )}
        <Button asChild size="sm">
          <Link href="/">Go to Vicoa</Link>
        </Button>
      </div>
    </div>
  );
}
