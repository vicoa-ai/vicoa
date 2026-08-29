import { NavigationHeader } from '@/components/navigation-header';
import { Footer } from '@/components/footer';

// Public marketing surface: landing (/) + pricing, blog, vs, features, help,
// legal, updates, download. Split out of the former (dashboard) grab-bag so
// these pages share one server-rendered shell with no client-side layout
// branching.
//
// Header AND footer are declared once here instead of being repeated in every
// page (they used to be pasted into all ~16 pages). Add a new marketing page and
// it gets both for free.
//
// Server Component on purpose: the shell ships no client JS; NavigationHeader is
// the only interactive island nested inside it. The flex column + flex-1 content
// wrapper keeps the footer pinned to the bottom on short pages (sticky footer) —
// which is why the individual pages no longer carry their own min-h-screen.
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <NavigationHeader />
      <div className="flex-1">{children}</div>
      <Footer />
    </div>
  );
}
