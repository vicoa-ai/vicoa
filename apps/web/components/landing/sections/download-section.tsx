import Image from 'next/image';
import Link from 'next/link';
import { Terminal } from '@/components/terminal';
import { Globe } from 'lucide-react';

export function DownloadSection() {
  return (
    <section className="relative pt-0 pb-4 overflow-hidden">
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col lg:flex-row items-center justify-center text-center">
          <div className="relative w-full max-w-lg">
            <div className="flex items-center justify-center gap-2">
              <span className="text-sm text-muted-foreground/60 whitespace-nowrap">Step 1</span>
              <div className="w-full max-w-sm rounded-2xl p-1 shadow-lg">
                  <Terminal />
              </div>
            </div>
          </div>
          <div className="relative w-full max-w-lg">
            <div className="flex items-center justify-center gap-2">
              <span className="text-sm text-muted-foreground/60 whitespace-nowrap">Step 2</span>
              <div className="flex flex-col sm:flex-row items-center gap-4 rounded-2xl px-4 py-3 shadow-lg">
                <div className="relative group">
                  <Link href="http://apps.apple.com/sg/app/id6751626168" target="_blank" rel="noopener noreferrer">
                    <Image
                      src="/images/appstore.webp"
                      alt="Download Vicoa on the App Store"
                      width={160}
                      height={37}
                      className="hover:opacity-80 transition-opacity duration-300"
                    />
                  </Link>
                  <div className="absolute top-full left-1/2 mt-2 -translate-x-1/2 opacity-0 transition-opacity duration-300 pointer-events-none group-hover:opacity-100 z-50">
                    <div className="bg-gray-900 p-6 rounded-xl shadow-2xl border border-gray-700 min-w-[200px]">
                      <Image
                        src="/images/vicoa-ios-qrcode.png"
                        alt="QR Code to download Vicoa app"
                        width={240}
                        height={240}
                        className="mx-auto"
                      />
                      <p className="text-sm text-gray-300 text-center mt-4">Scan to download Vicoa</p>
                    </div>
                  </div>
                </div>
                <Link
                  href="/dashboard"
                  className="inline-flex items-center justify-center gap-2 px-7 py-3 border border-gray-700 text-base rounded-xl text-white bg-gray-900 hover:bg-gray-800 hover:border-gray-600 transition-colors duration-300 shadow-sm"
                >
                  <Globe className="w-5 h-5" />
                  Web App
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
