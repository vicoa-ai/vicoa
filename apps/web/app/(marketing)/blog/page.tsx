import { Metadata } from 'next';
import { getAllBlogPosts } from '@/lib/blog-source';
import { BlogCard } from '@/components/blog/blog-card';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/blog', {
  title: 'Blog | Vicoa: Vibe Code Anywhere',
  description:
    'Vibe code anywhere with AI coding agents. Learn tips, tutorials, and workflows for Claude Code, Codex, and other AI developer tools. Remote coding, LLM integrations, and productivity hacks.',
  openGraph: {
    title: 'Blog | Vicoa: Vibe Code Anywhere',
    description:
      'Vibe code anywhere with AI coding agents. Learn tips, tutorials, and workflows for Claude Code, Codex, and other AI developer tools. Remote coding, LLM integrations, and productivity hacks.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Blog | Vicoa: Vibe Code Anywhere',
    description:
      'Vibe code anywhere with AI coding agents. Learn tips, tutorials, and workflows for Claude Code, Codex, and other AI developer tools. Remote coding, LLM integrations, and productivity hacks.',
  },
});

export default function BlogPage() {
  const posts = getAllBlogPosts();

  return (
    <>
      <div className="bg-background">
        {/* Header */}
        <div className="bg-muted/30">
          <div className="container mx-auto px-4 py-16 max-w-7xl text-center">
            <h1 className="text-4xl md:text-5xl mb-4">Blog</h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Tips, tutorials, and workflows for coding with AI agents anywhere.
            </p>
          </div>
        </div>

        <div className="container mx-auto px-4 py-12 max-w-7xl">
          {posts.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-muted-foreground text-lg">
                No blog posts yet. Check back soon!
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {posts.map((post, index) => (
                <BlogCard
                  key={post.info.path}
                  post={post}
                  priority={index < 3}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
