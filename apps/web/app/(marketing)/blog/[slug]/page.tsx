import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import {
  getAllBlogPosts,
  getBlogPostBySlug,
  getRelatedPosts,
  getBlogPostData,
  getBlogPostUrl,
  formatDate,
  calculateReadingTime,
} from '@/lib/blog-source';
// import { TagList } from '@/components/blog/tag-list';
import { RelatedPosts } from '@/components/blog/related-posts';
import { BlogTableOfContents } from '@/components/blog/table-of-contents';
import { MdxPre } from '@/components/blog/mdx-pre';
import { BlogImage } from '@/components/blog/blog-image';
import { pageMetadata } from '@/lib/seo';
import type { TableOfContents } from 'fumadocs-core/server';

interface BlogPostPageProps {
  params: Promise<{
    slug: string;
  }>;
}

export async function generateStaticParams() {
  const posts = getAllBlogPosts();
  return posts.map((post) => ({
    slug: post.info.path.replace(/\.mdx$/, ''),
  }));
}

export async function generateMetadata(
  props: BlogPostPageProps
): Promise<Metadata> {
  const params = await props.params;
  const post = getBlogPostBySlug(params.slug);

  if (!post) {
    return {
      title: 'Post Not Found',
    };
  }

  const postData = getBlogPostData(post);
  const { title, description, publishedAt, author, image, imageAlt } = postData;

  return pageMetadata(getBlogPostUrl(post), {
    title: `${title} | Vicoa Blog`,
    description,
    authors: author ? [{ name: author.name }] : undefined,
    openGraph: {
      title: `${title} | Vicoa Blog`,
      description,
      type: 'article',
      publishedTime: publishedAt,
      authors: author ? [author.name] : undefined,
      images: image
        ? [
            {
              url: image,
              alt: imageAlt || title,
            },
          ]
        : undefined,
    },
    twitter: {
      card: 'summary_large_image',
      title: `${title} | Vicoa Blog`,
      description,
      images: image ? [image] : undefined,
    },
  });
}

export default async function BlogPostPage(props: BlogPostPageProps) {
  const params = await props.params;
  const post = getBlogPostBySlug(params.slug);

  if (!post) {
    notFound();
  }

  const postData = getBlogPostData(post);
  const toc = (post as any).toc as TableOfContents | undefined;
  const {
    title,
    description,
    publishedAt,
    updatedAt,
    author,
    // tags,
    image,
    imageAlt,
  } = postData;

  const MDXContent = post.body as React.ComponentType<any>;
  const readingTime = 5; // TODO: calculate from content
  const relatedPosts = getRelatedPosts(post);
  const url = `https://vicoa.ai${getBlogPostUrl(post)}`;

  // JSON-LD structured data for SEO
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    headline: title,
    description,
    image: image || undefined,
    datePublished: publishedAt,
    dateModified: updatedAt || publishedAt,
    author: author ? {
      '@type': 'Person',
      name: author.name,
    } : undefined,
    publisher: {
      '@type': 'Organization',
      name: 'Vicoa',
      logo: {
        '@type': 'ImageObject',
        url: 'https://vicoa.ai/images/vicoa-light.png',
      },
    },
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <div className="bg-background">
        {/* Hero Section */}
        <div className="border-b border-border">
          <div className="container mx-auto px-4 py-12 max-w-6xl">
            <div className="grid lg:grid-cols-[minmax(0,1.5fr)_minmax(30rem,1fr)] gap-12 items-start">
              <div className="min-w-0">
            {/* Breadcrumb */}
            <nav className="mb-6 text-sm text-muted-foreground">
              <Link href="/" className="hover:text-primary">
                Home
              </Link>
              {' / '}
              <Link href="/blog" className="hover:text-primary">
                Blog
              </Link>
              {' / '}
              <span className="text-foreground">{title}</span>
            </nav>

            {/* Title */}
            <h1 className="text-2xl md:text-4xl mb-4 leading-tight">
              {title}
            </h1>

            {/* Description */}
            <p className="text-base md:text-lg text-muted-foreground mb-6">{description}</p>

            {/* Meta Info */}
                <div className="flex items-center gap-6 text-sm text-muted-foreground">
                  {author && (
                    <>
                      <div className="flex items-center gap-2">
                        {author.avatar && (
                          <Image
                            src={author.avatar}
                            alt={author.name}
                            width={32}
                            height={32}
                            className="rounded-full border border-border"
                          />
                        )}
                        <span className="font-medium text-foreground">
                          {author.name}
                        </span>
                        {author.role && <span>• {author.role}</span>}
                      </div>
                      <span>•</span>
                    </>
                  )}
                  <time dateTime={publishedAt}>{formatDate(publishedAt)}</time>
                  {updatedAt && updatedAt !== publishedAt && (
                    <span>Updated {formatDate(updatedAt)}</span>
                  )}
                  <span className="hidden md:inline">•</span>
                  <span className="hidden md:inline">{readingTime} min read</span>
                </div>
              </div>

              {image && (
                <div className="hidden lg:block lg:mt-6 relative w-full" style={{ paddingBottom: '56.25%' }}>
                  <Image
                    src={image}
                    alt={imageAlt || title}
                    fill
                    sizes="(min-width: 1024px) 40vw, 0vw"
                    className="object-cover rounded-xl border border-border shadow-sm"
                    priority
                    fetchPriority="high"
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Featured Image */}
        {image && (
          <div className="container mx-auto px-4 pt-0 pb-8 max-w-6xl lg:hidden">
            <div className="relative w-full" style={{ paddingBottom: '56.25%' }}>
              <Image
                src={image}
                alt={imageAlt || title}
                fill
                sizes="(max-width: 1024px) 100vw, 0vw"
                className="object-cover rounded-xl border border-border shadow-sm"
                priority
                fetchPriority="high"
              />
            </div>
          </div>
        )}

        {/* Article Content */}
        <article className="container mx-auto px-4 py-12 max-w-6xl">
          <div className="grid lg:grid-cols-[minmax(0,3fr)_minmax(16rem,1fr)] gap-12">
            <div className="min-w-0">
              <div className="prose prose-lg prose-neutral dark:prose-invert max-w-none">
                <MDXContent components={{ pre: MdxPre, img: BlogImage }} />
              </div>

              {/* Tags */}
              {/* {tags && tags.length > 0 && (
                <div className="mt-12 pt-8 border-t border-border">
                  <h3 className="text-sm mb-4 text-muted-foreground uppercase tracking-wide">
                    Tags
                  </h3>
                  <TagList tags={tags} />
                </div>
              )} */}

              {/* Related Posts */}
              <RelatedPosts posts={relatedPosts} />
            </div>

            <BlogTableOfContents toc={toc} shareUrl={url} shareTitle={title} />
          </div>
        </article>
      </div>
    </>
  );
}
