import Image from 'next/image';
import Link from 'next/link';

const IOS_APP_URL = 'http://apps.apple.com/sg/app/id6751626168';
const ANDROID_APP_URL = 'https://play.google.com/store/apps/details?id=app.vicoa';
// Public canonical download link — must be identical on server and client. Do NOT
// derive it from the server-only BASE_URL: that var is undefined in the client
// bundle (only NEXT_PUBLIC_* survive), so BASE_URL=http://localhost:3000 on the
// server vs the fallback on the client is a hydration mismatch. Matches the
// constant used in how-it-works-section.tsx.
const MOBILE_ONELINK_URL =
  process.env.NEXT_PUBLIC_MOBILE_ONELINK_URL || 'https://vicoa.ai/download-mobile-app';
const MOBILE_ONELINK_QR_IMAGE = '/images/vicoa-app-qrcode.png';

export function MobileDownloadCta({
  title = 'Install Vicoa on iPhone or Android',
  text = 'Open the same coding sessions from your phone with a real mobile app, not a terminal.',
}: {
  title?: string;
  text?: string;
}) {
  return (
    <div className="mt-14 rounded-3xl border border-border/60 bg-muted/30 px-6 py-8 shadow-sm sm:px-8 lg:pl-20">
      <div className="grid items-center gap-8 lg:gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="text-center lg:text-left">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Get The Mobile App
          </p>
          <h3 className="mt-3 text-2xl text-foreground sm:text-3xl">
            {title}
          </h3>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
            {text}
          </p>
          <div className="mt-6 flex flex-col items-center justify-center gap-4 sm:flex-row lg:justify-start">
            <Link href={IOS_APP_URL} target="_blank" rel="noopener noreferrer">
              <Image
                src="/images/appstore.webp"
                alt="Download Vicoa on the App Store"
                width={170}
                height={47}
                className="transition-opacity duration-300 hover:opacity-80"
              />
            </Link>
            <Link href={ANDROID_APP_URL} target="_blank" rel="noopener noreferrer">
              <Image
                src="/images/android-google-play.webp"
                alt="Get Vicoa on Google Play"
                width={170}
                height={50}
                className="transition-opacity duration-300 hover:opacity-80"
              />
            </Link>
          </div>
        </div>

        <div className="flex justify-center">
          <Link
            href={MOBILE_ONELINK_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="group rounded-3xl p-4 text-center shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-md"
          >
            <img
              src={MOBILE_ONELINK_QR_IMAGE}
              alt="QR code to download Vicoa mobile app"
              width={180}
              height={180}
              className="mx-auto"
            />
            <p className="mt-4 text-sm font-medium text-foreground">Scan to download the app</p>
          </Link>
        </div>
      </div>
    </div>
  );
}
