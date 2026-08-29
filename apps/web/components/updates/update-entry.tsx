import Link from 'next/link';
import {
  formatUpdateDate,
  getUpdateData,
  getUpdateSlug,
  getUpdateUrl,
  toIsoDate,
  type UpdateEntry
} from '@/lib/updates-source';
import { UPDATE_MDX_CLASS, updateMdxComponents } from '@/components/updates/update-mdx';

/**
 * Date rail + content column. Exported so the page header and the permalink's
 * prev/next nav can sit on the same two columns as the entries themselves.
 */
export const UPDATE_GRID = 'lg:grid lg:grid-cols-[8rem_minmax(0,1fr)] lg:gap-14';

/**
 * Wrapper for a run of entries. `divide-y` draws a rule *between* siblings, so
 * there is no way to get a stray line above the first entry — unlike a per-entry
 * `border-t` with `first:border-t-0`, which silently stops matching as soon as
 * anything else (the page heading, a breadcrumb) becomes the first child.
 */
export const UPDATE_LIST = 'divide-y divide-border';

interface UpdateEntryBlockProps {
  entry: UpdateEntry;
  /**
   * `index` stacks many entries in one document: the title is an `<h2>` linking
   * to the permalink, and body headings drop a level so the outline stays valid.
   * `permalink` renders the same entry standalone with the title as the `<h1>`.
   */
  variant?: 'index' | 'permalink';
  /** Only the topmost entry on a page competes to be the LCP element. */
  priority?: boolean;
}

export function UpdateEntryBlock({
  entry,
  variant = 'index',
  priority = false
}: UpdateEntryBlockProps) {
  const data = getUpdateData(entry);
  const slug = getUpdateSlug(entry);
  const url = getUpdateUrl(entry);
  const publishedIso = toIsoDate(data.publishedAt);
  const publishedLabel = formatUpdateDate(data.publishedAt);
  const MDXContent = entry.body as React.ComponentType<any>;

  const isIndex = variant === 'index';
  const Title = isIndex ? 'h2' : 'h1';
  const date = <time dateTime={publishedIso}>{publishedLabel}</time>;

  return (
    <article
      id={slug}
      className={`scroll-mt-24 py-12 first:pt-0 md:py-16 ${UPDATE_GRID}`}
    >
      <div className="hidden lg:block lg:sticky lg:top-24 lg:self-start">
        {isIndex ? (
          <Link
            href={url}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {date}
          </Link>
        ) : (
          <p className="text-sm text-muted-foreground">{date}</p>
        )}
      </div>

      <div className="min-w-0">
        <p className="mb-3 text-sm text-muted-foreground lg:hidden">{date}</p>

        <Title className="text-2xl font-semibold tracking-tight md:text-3xl">
          {isIndex ? (
            <Link href={url} className="transition-colors hover:text-muted-foreground">
              {data.title}
            </Link>
          ) : (
            data.title
          )}
        </Title>

        <p className="mt-3 text-base leading-7 text-muted-foreground md:text-lg">{data.summary}</p>

        <div className={`mt-8 ${UPDATE_MDX_CLASS}`}>
          <MDXContent
            components={updateMdxComponents({
              idPrefix: isIndex ? slug : undefined,
              demote: isIndex,
              priorityFirstImage: priority
            })}
          />
        </div>
      </div>
    </article>
  );
}
