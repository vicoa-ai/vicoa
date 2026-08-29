import { BlogPost } from '@/lib/blog-source';
import { BlogCard } from './blog-card';

interface RelatedPostsProps {
  posts: BlogPost[];
}

export function RelatedPosts({ posts }: RelatedPostsProps) {
  if (posts.length === 0) return null;

  return (
    <div className="mt-16 border-t border-border pt-12">
      <h2 className="text-2xl mb-8">Related Posts</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {posts.map((post) => (
          <BlogCard key={post.info.path} post={post} />
        ))}
      </div>
    </div>
  );
}
