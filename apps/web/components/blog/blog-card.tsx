import Link from 'next/link';
import Image from 'next/image';
import { Card } from '@/components/ui/card';
import { BlogPost, getBlogPostUrl } from '@/lib/blog-source';
import {
  formatDate,
  calculateReadingTime,
  getBlogPostData,
} from '@/lib/blog-source';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';

interface BlogCardProps {
  post: BlogPost;
  priority?: boolean;
}

export function BlogCard({ post, priority = false }: BlogCardProps) {
  const postData = getBlogPostData(post);
  const title = postData.title as string;
  const description = postData.description as string;
  const publishedAt = postData.publishedAt as string;
  const author = postData.author as any;
  const category = postData.category as string | undefined;
  const tags = postData.tags as string[] | undefined;
  const image = postData.image as string | undefined;
  const imageAlt = postData.imageAlt as string | undefined;

  const readingTime = calculateReadingTime(''); // TODO: get content length
  const url = getBlogPostUrl(post);

  return (
    <Link href={url} className="block group">
      <Card className="h-full overflow-hidden border border-border hover:border-primary/50 transition-all duration-300 py-0 pb-4">
        {image && (
          <div className="relative w-full aspect-video overflow-hidden bg-muted">
            <Image
              src={image}
              alt={imageAlt || title}
              fill
              sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
              className="object-cover group-hover:scale-105 transition-transform duration-300"
              priority={priority}
            />
          </div>
        )}
        <div className="px-4 space-y-4">
          {category && (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
                {category}
              </span>
            </div>
          )}

          <div>
            <h3 className="text-xl mb-2 group-hover:text-primary transition-colors">
              {title}
            </h3>
            <p className="text-muted-foreground text-sm line-clamp-3">
              {description}
            </p>
          </div>

          <div className="flex items-center justify-between pt-5 border-t border-border">
            <div className="flex items-center gap-2">
              {author?.avatar && (
                <Avatar className="h-8 w-8">
                  <Image
                    src={author.avatar}
                    alt={author.name}
                    width={32}
                    height={32}
                    className="rounded-full"
                  />
                  <AvatarFallback>
                    {author.name
                      .split(' ')
                      .map((n: string) => n[0])
                      .join('')
                      .toUpperCase()}
                  </AvatarFallback>
                </Avatar>
              )}
              <div className="flex flex-col">
                <span className="text-sm font-medium">{author?.name}</span>
                {author?.role && (
                  <span className="text-xs text-muted-foreground">
                    {author.role}
                  </span>
                )}
              </div>
            </div>
            <div className="flex flex-col items-end text-xs text-muted-foreground">
              <span>{formatDate(publishedAt)}</span>
            </div>
          </div>
        </div>
      </Card>
    </Link>
  );
}
