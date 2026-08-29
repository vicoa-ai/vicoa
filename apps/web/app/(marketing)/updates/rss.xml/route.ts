import {
  UPDATES_BASE_URL,
  getAllUpdates,
  getUpdateData,
  getUpdateUrl
} from '@/lib/updates-source';

export const dynamic = 'force-static';

export async function GET() {
  const entries = getAllUpdates();

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Vicoa Updates</title>
    <link>${UPDATES_BASE_URL}/updates</link>
    <description>New features, agent support, and improvements shipped to the Vicoa app, web dashboard, and CLI.</description>
    <language>en-us</language>
    <atom:link href="${UPDATES_BASE_URL}/updates/rss.xml" rel="self" type="application/rss+xml" />
    ${entries
      .map((entry) => {
        const data = getUpdateData(entry);
        const url = `${UPDATES_BASE_URL}${getUpdateUrl(entry)}`;
        return `
    <item>
      <title>${escapeXml(data.title)}</title>
      <link>${url}</link>
      <description>${escapeXml(data.summary || data.description || '')}</description>
      <pubDate>${new Date(data.publishedAt).toUTCString()}</pubDate>
      <guid isPermaLink="true">${url}</guid>
    </item>`;
      })
      .join('')}
  </channel>
</rss>`;

  return new Response(rss, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600'
    }
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
