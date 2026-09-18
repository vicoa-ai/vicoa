import type { Metadata } from 'next';

// Public share links (collaboration §8.4, P4): `/share/<token>`. Outside
// `/dashboard`, so the auth middleware already lets it through; no marketing
// header/footer — the viewer draws its own "Shared read-only via Vicoa" chrome.
// Every page under here is noindex: a share page's existence is the secret.
export const metadata: Metadata = {
  robots: { index: false, follow: false, googleBot: { index: false, follow: false } },
};

export default function ShareLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
