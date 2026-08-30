import { MetadataRoute } from 'next'
import { getAllBlogPosts, getBlogPostData } from '@/lib/blog-source'
import { docsBySlug, getDocUrl } from '@/lib/docs-source'
import { getAllUpdates, getUpdateData, getUpdateUrl } from '@/lib/updates-source'
import { getAllVsPages, getVsPageData, getVsUrl } from '@/lib/vs-source'

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = 'https://vicoa.ai'

  // Get all blog posts
  const blogPosts = getAllBlogPosts()

  // Changelog entries, newest first. Each has a real publish date, so unlike the
  // docs these can carry an honest lastModified.
  const updates = getAllUpdates()
  const updateEntries: MetadataRoute.Sitemap = updates.map((entry) => {
    const data = getUpdateData(entry)
    const lastModDate = data.updatedAt || data.publishedAt
    return {
      url: `${baseUrl}${getUpdateUrl(entry)}`,
      lastModified: lastModDate ? new Date(lastModDate) : undefined,
      changeFrequency: 'yearly' as const,
      priority: 0.6,
    }
  })

  const latestUpdate = updates[0]
  const latestUpdateDate = latestUpdate
    ? getUpdateData(latestUpdate).updatedAt || getUpdateData(latestUpdate).publishedAt
    : undefined

  // Newest post drives the /blog index's honest lastModified (the index changes
  // when a post lands). getAllBlogPosts() is sorted newest-first.
  const latestBlogPost = blogPosts[0]
  const latestBlogDate = latestBlogPost
    ? getBlogPostData(latestBlogPost).updatedAt || getBlogPostData(latestBlogPost).publishedAt
    : undefined

  // Every docs page except the index, which is listed with the other core pages
  // below. Docs have no frontmatter dates, so we omit lastModified rather than
  // stamping a build time that would claim every page changed on every deploy.
  const docsEntries: MetadataRoute.Sitemap = Array.from(docsBySlug.keys())
    .map((slug) => getDocUrl(slug))
    .filter((url) => url !== '/docs')
    .sort()
    .map((url) => ({
      url: `${baseUrl}${url}`,
      changeFrequency: 'weekly' as const,
      priority: 0.7,
    }))

  // Competitor comparison pages. Each carries an honest last-updated date.
  const vsPages = getAllVsPages()
  const vsEntries: MetadataRoute.Sitemap = vsPages.map((page) => {
    const data = getVsPageData(page)
    const lastModDate = data.updatedAt || data.publishedAt
    return {
      url: `${baseUrl}${getVsUrl(page)}`,
      lastModified: lastModDate ? new Date(lastModDate) : undefined,
      changeFrequency: 'weekly' as const,
      priority: 0.8,
    }
  })

  const latestVsPage = vsPages[0]
  const latestVsDate = latestVsPage
    ? getVsPageData(latestVsPage).updatedAt || getVsPageData(latestVsPage).publishedAt
    : undefined

  // Create sitemap entries for blog posts
  const blogPostEntries: MetadataRoute.Sitemap = blogPosts.map((post) => {
    const postData = getBlogPostData(post);
    const slug = post.info.path.replace(/\.mdx$/, '');
    const lastModDate = postData.updatedAt || postData.publishedAt;
    return {
      url: `${baseUrl}/blog/${slug}`,
      lastModified: lastModDate ? new Date(lastModDate) : undefined,
      changeFrequency: 'weekly' as const,
      priority: 0.8,
    };
  })

  // Static routes are plain React pages with no honest per-page change date, so
  // we omit `lastModified` rather than stamping `new Date()` — build-time stamps
  // would falsely tell crawlers every page changed on every deploy. Only the
  // /blog and /updates indexes carry a date, derived from their newest entry.
  return [
    {
      url: baseUrl,
      changeFrequency: 'weekly',
      priority: 1,
    },
    {
      url: `${baseUrl}/blog`,
      lastModified: latestBlogDate ? new Date(latestBlogDate) : undefined,
      changeFrequency: 'daily',
      priority: 0.9,
    },
    {
      url: `${baseUrl}/features`,
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${baseUrl}/pricing`,
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/coding-agents`,
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/use-cases`,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/use-cases/researchers`,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/vs`,
      lastModified: latestVsDate ? new Date(latestVsDate) : undefined,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/docs`,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/updates`,
      lastModified: latestUpdateDate ? new Date(latestUpdateDate) : undefined,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${baseUrl}/sign-up`,
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${baseUrl}/sign-in`,
      changeFrequency: 'monthly',
      priority: 0.6,
    },
    {
      url: `${baseUrl}/contact`,
      changeFrequency: 'yearly',
      priority: 0.5,
    },
    {
      url: `${baseUrl}/help/cancel-subscription`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${baseUrl}/help/refund-requests`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${baseUrl}/privacy`,
      changeFrequency: 'yearly',
      priority: 0.4,
    },
    {
      url: `${baseUrl}/terms`,
      changeFrequency: 'yearly',
      priority: 0.4,
    },
    ...docsEntries,
    ...vsEntries,
    ...blogPostEntries,
    ...updateEntries,
  ]
}
