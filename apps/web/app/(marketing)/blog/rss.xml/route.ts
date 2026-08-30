import {
  getAllBlogPosts,
  getBlogPostUrl,
  getBlogPostData,
} from '@/lib/blog-source';

export async function GET() {
  const posts = getAllBlogPosts();
  const baseUrl = 'https://vicoa.ai';

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Vicoa Blog</title>
    <link>${baseUrl}/blog</link>
    <description>Vibe code anywhere with AI coding agents. Tips, tutorials, and workflows for Claude Code, Codex, and other AI developer tools. Remote coding, LLM integrations, and productivity hacks.</description>
    <language>en-us</language>
    <atom:link href="${baseUrl}/blog/rss.xml" rel="self" type="application/rss+xml" />
    ${posts
      .map(
        (post) => {
          const postData = getBlogPostData(post);
          const url = getBlogPostUrl(post);
          return `
    <item>
      <title>${escapeXml(postData.title)}</title>
      <link>${baseUrl}${url}</link>
      <description>${escapeXml(postData.description || '')}</description>
      <pubDate>${new Date(postData.publishedAt).toUTCString()}</pubDate>
      <guid>${baseUrl}${url}</guid>
      ${postData.author ? `<author>${escapeXml(postData.author.name)}</author>` : ''}
        </item>`;
        }
      )
      .join('')}
  </channel>
</rss>`;

  return new Response(rss, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}

function escapeXml(unsafe: string): string {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
