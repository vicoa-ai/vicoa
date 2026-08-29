'use client';

import { useState } from 'react';
import Image from 'next/image';
import { cn } from '@/lib/utils';

interface LiteYouTubeEmbedProps {
  videoId: string;
  title: string;
  className?: string;
  coverImage?: string;
  onPlay?: () => void;
}

export function LiteYouTubeEmbed({ videoId, title, className, coverImage, onPlay }: LiteYouTubeEmbedProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const maxResThumbnail = `https://i.ytimg.com/vi/${videoId}/maxresdefault.jpg`;
  const hqThumbnail = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
  const [thumbnailSrc, setThumbnailSrc] = useState(coverImage ?? maxResThumbnail);

  if (isLoaded) {
    return (
      <iframe
        src={`https://www.youtube.com/embed/${videoId}?autoplay=1&modestbranding=1&rel=0`}
        title={title}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className={cn('absolute inset-0 h-full w-full', className)}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => { setIsLoaded(true); onPlay?.(); }}
      className={cn(
        'group absolute inset-0 flex h-full w-full cursor-pointer items-center justify-center overflow-hidden text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/60',
        className
      )}
      aria-label={`Play ${title}`}
    >
      <Image
        src={thumbnailSrc}
        alt=""
        fill
        priority
        quality={95}
        sizes="(max-width: 640px) 100vw, (max-width: 1024px) 90vw, (max-width: 1536px) 60vw, 1200px"
        onError={() => {
          if (thumbnailSrc === coverImage) {
            setThumbnailSrc(maxResThumbnail);
            return;
          }
          if (thumbnailSrc === maxResThumbnail) {
            setThumbnailSrc(hqThumbnail);
          }
        }}
        className="rounded-xl object-contain transition-transform duration-500 group-hover:scale-[1.03]"
      />
      <span className="absolute inset-0 rounded-xl ring-1 ring-white/10" />
      <span className="relative inline-flex flex-col items-center justify-center gap-2 z-10">
        <span className="inline-flex h-6 w-8 items-center justify-center rounded-md bg-black/35 text-white shadow-sm backdrop-blur-sm transition-transform duration-300 group-hover:scale-105">
          <svg
            className="h-4 w-4 translate-x-0.5"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M4.5 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.97l-11.54 6.348A1.125 1.125 0 014.5 18.347V5.653z" />
          </svg>
        </span>
      </span>
    </button>
  );
}
