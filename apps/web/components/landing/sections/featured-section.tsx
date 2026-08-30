import Image from 'next/image';

interface FeaturedItem {
  name: string;
  logo: string;
  url: string;
  width?: number;
  height?: number;
}

const featuredIn: FeaturedItem[] = [
  {
    name: 'GoodFirms',
    logo: '/images/featured/Goodfirms-Logo.png',
    url: 'https://www.goodfirms.co',
    width: 120,
    height: 22
  },
  {
    name: 'Startup Fame',
    logo: '/images/featured/startupfame-logo.webp',
    url: 'https://startupfa.me/s/vicoa?utm_source=vicoa.ai',
    width: 130,
    height: 50
  },

  {
    name: 'AIToolHunt',
    logo: 'https://aitoolhunt.co/badge-listed-dark.svg',
    url: 'https://aitoolhunt.co/item/vicoa',
    width: 140,
    height: 40
  },
  {
    name: 'Dang.ai',
    logo: 'https://cdn.prod.website-files.com/63d8afd87da01fb58ea3fbcb/6487e2868c6c8f93b4828827_dang-badge.png',
    url: 'https://dang.ai/',
    width: 100,
    height: 36
  },
  {
    name: 'ToolPilot',
    logo: '/images/featured/toolpilot-badge.png',
    url: 'https://toolpilot.ai',
    width: 120,
    height: 40
  },
  {
    name: 'Fazier',
    logo: 'https://fazier.com/api/v1//public/badges/launch_badges.svg?badge_type=featured&theme=dark',
    url: 'https://fazier.com/launches/vibecodeanywhere.com',
    width: 120,
    height: 40
  },
  {
    name: 'SimilarLabs',
    logo: 'https://similarlabs.com/similarlabs-embed-badge-dark.svg',
    url: 'https://similarlabs.com/?ref=embed',
    width: 120,
    height: 40
  },
  {
    name: 'AI Directories',
    logo: 'https://cdn.aidirectori.es/ai-tools/badges/light-mode.png',
    url: 'https://www.aidirectori.es',
    width: 120,
    height: 40
  },  
  {
    name: 'LaunchIgniter',
    logo: 'https://launchigniter.com/api/badge/vibe-code-anywhere-vicoa?theme=dark',
    url: 'https://launchigniter.com/product/vibe-code-anywhere-vicoa?ref=badge-vibe-code-anywhere-vicoa',
    width: 150,
    height: 55
  },
  {
    name: 'Twelve Tools',
    logo: 'https://twelve.tools/badge0-dark.svg',
    url: 'https://twelve.tools',
    width: 150,
    height: 54
  },
  {
    name: 'Findly Tools',
    logo: 'https://findly.tools/badges/findly-tools-badge-dark.svg',
    url: 'https://findly.tools/vicoa-vibe-code-anywhere?utm_source=vicoa-vibe-code-anywhere',
    width: 150,
    height: 40
  },
  {
    name: 'Turbo0',
    logo: 'https://img.turbo0.com/badge-listed-dark.svg',
    url: 'https://turbo0.com/item/vicoa-vibe-code-anywhere',
    width: 120,
    height: 54
  },
  {
    name: 'Dofollow Tools',
    logo: 'https://dofollow.tools/badge/badge_dark.svg',
    url: 'https://dofollow.tools',
    width: 120,
    height: 54
  },
  {
    name: 'Wired Business',
    logo: 'https://wired.business/badge0-dark.svg',
    url: 'https://wired.business',
    width: 150,
    height: 54
  },
  {
    name: 'yo.directory',
    logo: 'https://cdn.prod.website-files.com/65c1546fa73ea974db789e3d/65e1e171f89ebfa7bd0129ac_yodirectory-featured.png',
    url: 'https://yo.directory/',
    width: 150,
    height: 54
  },
  {
    name: 'Startup Inspire',
    logo: 'https://www.startupinspire.com/images/badge_2.svg',
    url: 'https://www.startupinspire.com',
    width: 120,
    height: 54
  },
  {
    name: 'DailyPings',
    logo: '/images/featured/dailypings-badge.svg',
    url: 'https://dailypings.com/p/vicoa',
    width: 179,
    height: 32
  },
];

function FeaturedItemCard({ item }: { item: FeaturedItem }) {
  const defaultWidth = 120;
  const defaultHeight = 40;

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      className="transition-all hover:opacity-75 hover:-translate-y-0.5 flex-shrink-0"
    >
      <div
        className="relative flex items-center justify-center"
        style={{
          width: `${item.width ?? defaultWidth}px`,
          height: `${item.height ?? defaultHeight}px`
        }}
      >
        {item.name === 'LaunchIgniter' || item.logo.includes('.svg') ? (
          <img
            src={item.logo}
            alt={`Vicoa - Featured on ${item.name}`}
            width={item.width}
            height={item.height}
            className="object-contain"
          />
        ) : (
          <Image
            src={item.logo}
            alt={`Vicoa - Featured on ${item.name}`}
            fill
            className="object-contain"
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
          />
        )}
      </div>
    </a>
  );
}

export function FeaturedSection() {
  return (
    <div className="py-6 mb-32">
      <div className="container mx-auto px-8">
        <div className="flex flex-col items-center">
          <p className="mb-16 text-center text-lg sm:text-xl lg:text-2xl">
            Featured on
          </p>
          <div className="w-full overflow-hidden">
            <div className="flex items-center gap-8 md:gap-12 animate-scroll">
              {featuredIn.map((item, idx) => (
                <FeaturedItemCard key={idx} item={item} />
              ))}
              {featuredIn.map((item, idx) => (
                <FeaturedItemCard key={`duplicate-${idx}`} item={item} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}