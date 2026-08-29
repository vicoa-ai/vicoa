import Link from 'next/link';
import Image from 'next/image';
import type { Metadata } from 'next';

// PPR can commit a 200 for a streamed shell before `notFound()` runs, so some
// missing pages surface as soft 404s. Without this they inherit the root
// layout's index/follow and its homepage canonical.
export const metadata: Metadata = {
  title: 'Page Not Found',
  robots: { index: false, follow: false },
  alternates: {},
};

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-[100dvh]">
      <div className="max-w-md space-y-8 p-4 text-center">
        <div className="flex justify-center">
          <Image 
            src="/images/vicoa-light.webp"
            alt="Vibe Code Anywhere Logo" 
            width={0} 
            height={0} 
            sizes="100vw"
            className="h-12 w-auto opacity-90" 
          />
        </div>
        <h1 className="text-4xl text-foreground tracking-tight">
          Page Not Found
        </h1>
        <p className="text-base text-muted-foreground">
          The page you are looking for is unavailable.
        </p>
        <Link
          href="/"
          className="max-w-48 mx-auto flex justify-center py-2 px-4 border border-border rounded-full shadow-sm text-sm font-medium text-foreground bg-background hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-ring"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}
