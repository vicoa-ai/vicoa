import { blog as blogDocs } from '@/.source/index';

export type BlogPost = (typeof blogDocs)[number];

// Re-export blog from generated source
export const blog = blogDocs;

export interface BlogFrontmatter {
  title: string;
  description: string;
  publishedAt: string;
  updatedAt?: string;
  author: {
    name: string;
    avatar?: string;
    role?: string;
  };
  tags?: string[];
  image?: string;
  imageAlt?: string;
}

const blogPostsBySlug = new Map(
  blog.map((post) => {
    const slug = post.info.path.replace(/\.mdx$/, '');
    return [slug, post] as const;
  })
);

export function getBlogPostData(post: BlogPost) {
  const raw = post as any;
  return {
    ...((raw.frontmatter ?? {}) as Record<string, unknown>),
    ...raw,
  } as BlogFrontmatter & Record<string, unknown>;
}

export function getAllBlogPosts(): BlogPost[] {
  return Array.from(blog).sort((a, b) => {
    const postA = getBlogPostData(a);
    const postB = getBlogPostData(b);
    const dateA = new Date(postA.publishedAt || 0).getTime();
    const dateB = new Date(postB.publishedAt || 0).getTime();
    return dateB - dateA; // Newest first
  });
}

export function getBlogPostBySlug(slug: string): BlogPost | undefined {
  return blogPostsBySlug.get(slug);
}

export function getBlogPostsByCategory(category: string): BlogPost[] {
  return [];
}

export function getBlogPostsByTag(tag: string): BlogPost[] {
  return getAllBlogPosts().filter((post) =>
    getBlogPostData(post)
      .tags?.some((t: string) => t.toLowerCase() === tag.toLowerCase())
  );
}

export function getAllCategories(): string[] {
  return [];
}

export function getAllTags(): string[] {
  const tags = new Set<string>();
  getAllBlogPosts().forEach((post) => {
    const data = getBlogPostData(post);
    if (data.tags) {
      (data.tags as string[]).forEach((tag: string) => tags.add(tag));
    }
  });
  return Array.from(tags).sort();
}

export function getRelatedPosts(currentPost: BlogPost, limit = 2): BlogPost[] {
  const currentSlug = currentPost.info.path.replace(/\.mdx$/, '');
  const allPosts = getAllBlogPosts().filter(
    (post) => post.info.path.replace(/\.mdx$/, '') !== currentSlug
  );

  // Score posts by relevance
  const scoredPosts = allPosts.map((post) => {
    let score = 0;
    const data = getBlogPostData(post);
    const currentData = getBlogPostData(currentPost);

    // Shared tags = +1 point each
    if (data.tags && currentData.tags) {
      const sharedTags = (data.tags as string[]).filter((tag: string) =>
        (currentData.tags as string[])?.includes(tag)
      );
      score += sharedTags.length;
    }

    return { post, score };
  });

  const withSharedTags = scoredPosts
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score);

  if (withSharedTags.length >= limit) {
    return withSharedTags.slice(0, limit).map((item) => item.post);
  }

  // Fallback: fill remaining slots with newest posts, even if tags don't overlap.
  const selected = withSharedTags.map((item) => item.post);
  const selectedSlugs = new Set(
    selected.map((post) => post.info.path.replace(/\.mdx$/, ''))
  );

  for (const post of allPosts) {
    const slug = post.info.path.replace(/\.mdx$/, '');
    if (selectedSlugs.has(slug)) continue;
    selected.push(post);
    selectedSlugs.add(slug);
    if (selected.length >= limit) break;
  }

  return selected;
}

export function calculateReadingTime(content: string): number {
  const wordsPerMinute = 200;
  const wordCount = content.trim().split(/\s+/).length;
  return Math.ceil(wordCount / wordsPerMinute);
}

export function formatDate(date: string | Date | undefined): string {
  if (!date) return 'Date not available';

  const parsedDate = new Date(date);

  // Check if date is valid
  if (isNaN(parsedDate.getTime())) {
    return 'Invalid date';
  }

  return parsedDate.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function getBlogPostUrl(post: BlogPost): string {
  const slug = post.info.path.replace(/\.mdx$/, '');
  return `/blog/${slug}`;
}
