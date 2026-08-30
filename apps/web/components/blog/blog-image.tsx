'use client';

import React from 'react';
import Image from 'next/image';
import type { StaticImageData } from 'next/image';

interface BlogImageProps {
  src?: string | StaticImageData;
  alt?: string;
  className?: string;
  title?: string;
  width?: number;
  height?: number;
}

export function BlogImage({
  src,
  alt = '',
  className = '',
  title,
  width,
  height,
  ...props
}: BlogImageProps) {
  if (!src) {
    console.error('BlogImage: Missing src prop for image');
    return null;
  }

  // If src is a StaticImageData object (from static imports), use Next.js Image
  if (typeof src === 'object' && 'src' in src) {
    return (
      <Image
        src={src}
        alt={alt}
        title={title}
        className={`my-8 w-full rounded-lg border border-border shadow-sm ${className}`.trim()}
        placeholder="blur"
        {...props}
      />
    );
  }

  // For string paths, use regular img tag
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src as string}
      alt={alt}
      title={title}
      className={`my-8 w-full rounded-lg border border-border shadow-sm ${className}`.trim()}
      loading="lazy"
      {...props}
    />
  );
}
