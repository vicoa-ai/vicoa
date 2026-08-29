import Image from 'next/image';
import Link from 'next/link';

const IOS_APP_URL = 'http://apps.apple.com/sg/app/id6751626168';
const ANDROID_APP_URL = 'https://play.google.com/store/apps/details?id=app.vicoa';

type MobilePlatform = {
  name: string;
  href: string;
  badgeSrc: string;
  badgeAlt: string;
  badgeWidth: number;
  badgeHeight: number;
  qrSrc: string;
};

const MOBILE_PLATFORMS: MobilePlatform[] = [
  {
    name: 'iOS',
    href: IOS_APP_URL,
    badgeSrc: '/images/appstore.webp',
    badgeAlt: 'Download Vicoa on the App Store',
    badgeWidth: 130,
    badgeHeight: 36,
    qrSrc: '/images/vicoa-ios-qrcode.png',
  },
  {
    name: 'Android',
    href: ANDROID_APP_URL,
    badgeSrc: '/images/android-google-play.webp',
    badgeAlt: 'Get Vicoa on Google Play',
    badgeWidth: 130,
    badgeHeight: 38,
    qrSrc: '/images/vicoa-android-qrcode.png',
  },
];

export function MobileAppDownload() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="text-center">
        <h2 className="text-2xl font-medium tracking-tight">Get the mobile app</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground sm:text-base">
          Put your coding agents in your pocket. Monitor, steer, and ship from anywhere.
        </p>
      </div>

      <div className="mt-6 flex flex-wrap justify-center gap-x-20 gap-y-6">
        {MOBILE_PLATFORMS.map((platform) => (
          <div key={platform.name} className="flex flex-col items-center gap-3">
            <Link
              href={platform.href}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-white p-1.5"
            >
              <Image
                src={platform.qrSrc}
                alt={`QR code to download Vicoa for ${platform.name}`}
                width={96}
                height={96}
                className="h-auto w-24"
              />
            </Link>
            <Link
              href={platform.href}
              target="_blank"
              rel="noopener noreferrer"
              className="transition-opacity hover:opacity-80"
            >
              <Image
                src={platform.badgeSrc}
                alt={platform.badgeAlt}
                width={platform.badgeWidth}
                height={platform.badgeHeight}
                className="h-auto w-[6.5rem]"
              />
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
