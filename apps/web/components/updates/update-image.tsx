import Image, { type StaticImageData } from 'next/image';

interface UpdateImageProps {
  src?: string | StaticImageData;
  alt?: string;
  title?: string;
  /** True for the first screenshot on the page, which is usually above the fold. */
  priority?: boolean;
}

const IMAGE_CLASS = 'my-6 w-full h-auto rounded-xl border border-border bg-muted/30 shadow-sm';

/**
 * Screenshot inside a changelog entry.
 *
 * fumadocs rewrites local markdown image paths into static imports, so `src` is
 * a `StaticImageData` carrying real dimensions and a blur placeholder — that
 * path gets `next/image` and a reserved box, so the entry doesn't reflow as
 * screenshots load. A plain string only shows up for remote URLs, which have no
 * intrinsic size to hand `next/image`.
 */
export function UpdateImage({ src, alt = '', title, priority }: UpdateImageProps) {
  if (!src) return null;

  if (typeof src === 'string') {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt={alt} title={title} loading="lazy" className={IMAGE_CLASS} />;
  }

  return (
    <Image
      src={src}
      alt={alt}
      title={title}
      sizes="(min-width: 1024px) 42rem, 100vw"
      priority={priority}
      loading={priority ? undefined : 'lazy'}
      placeholder={src.blurDataURL ? 'blur' : undefined}
      className={IMAGE_CLASS}
    />
  );
}
