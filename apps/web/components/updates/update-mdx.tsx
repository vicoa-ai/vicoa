import type { AnchorHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import Link from 'next/link';
import { MdxPre } from '@/components/blog/mdx-pre';
import { UpdateImage } from '@/components/updates/update-image';

interface UpdateMdxOptions {
  /**
   * Namespaces heading anchors. The index page stacks every entry into one
   * document, so the ids fumadocs derives from heading text would otherwise
   * collide between entries and `#getting-started` would jump to the wrong one.
   */
  idPrefix?: string;
  /**
   * Demote body headings by one level. On the index page the entry title is the
   * `<h2>`, so a body `##` has to render as `<h3>` to keep a single valid
   * heading outline per document.
   */
  demote?: boolean;
  /** Marks the first screenshot as the LCP candidate. Index page: first entry only. */
  priorityFirstImage?: boolean;
}

type PreProps = HTMLAttributes<HTMLPreElement> & { icon?: unknown };

/**
 * Classes for the MDX container. These cover the elements that have no component
 * override: inline code, and the shiki-highlighted fenced blocks whose colors and
 * padding come from `fumadocs-ui/style.css`. `:not(pre) > code` is what separates
 * the two — inside a `<pre>` the highlighter owns the styling.
 */
export const UPDATE_MDX_CLASS = [
  '[&_:not(pre)>code]:rounded-md',
  '[&_:not(pre)>code]:border',
  '[&_:not(pre)>code]:border-border',
  '[&_:not(pre)>code]:bg-muted',
  '[&_:not(pre)>code]:px-1.5',
  '[&_:not(pre)>code]:py-0.5',
  '[&_:not(pre)>code]:font-mono',
  '[&_:not(pre)>code]:text-[0.85em]',
  '[&_:not(pre)>code]:text-foreground',
  '[&_pre]:rounded-xl',
  '[&_pre]:border',
  '[&_pre]:border-border',
  '[&_pre]:p-4',
  '[&_pre]:text-sm',
  '[&_pre]:overflow-x-auto'
].join(' ');

const HEADING_STYLES = [
  'text-xl font-semibold tracking-tight mt-10 mb-3 first:mt-0',
  'text-base font-semibold tracking-tight mt-8 mb-2',
  'text-sm font-semibold tracking-tight mt-6 mb-2',
];

/**
 * Element overrides for changelog MDX. These replace `@tailwindcss/typography`
 * rather than layering on top of it: the entries need identical typography on
 * the index and the permalink even though the heading *tags* differ between
 * them, which prose's element-based selectors can't express.
 */
export function updateMdxComponents({
  idPrefix,
  demote = false,
  priorityFirstImage = false,
}: UpdateMdxOptions = {}) {
  const withPrefix = (id?: string) => (id && idPrefix ? `${idPrefix}-${id}` : id);
  let imagesRendered = 0;

  function heading(level: number) {
    const tagIndex = Math.min(level + (demote ? 1 : 0), 3);
    const Tag = (['h2', 'h3', 'h4', 'h5'] as const)[tagIndex];
    const styles = HEADING_STYLES[Math.min(level, HEADING_STYLES.length - 1)];

    return function Heading({ id, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
      const anchor = withPrefix(id);

      return (
        <Tag id={anchor} className={`group scroll-mt-28 text-foreground ${styles}`} {...props}>
          {anchor ? (
            <a href={`#${anchor}`} className="no-underline">
              {children}
              <span
                aria-hidden="true"
                className="ml-2 select-none text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
              >
                #
              </span>
            </a>
          ) : (
            children
          )}
        </Tag>
      );
    };
  }

  return {
    h1: heading(0),
    h2: heading(0),
    h3: heading(1),
    h4: heading(2),
    p: ({ children, ...props }: HTMLAttributes<HTMLParagraphElement>) => (
      <p className="my-4 leading-7 text-muted-foreground" {...props}>
        {children}
      </p>
    ),
    ul: ({ children, ...props }: HTMLAttributes<HTMLUListElement>) => (
      <ul className="my-4 list-disc space-y-2 pl-5 leading-7 text-muted-foreground" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }: HTMLAttributes<HTMLOListElement>) => (
      <ol className="my-4 list-decimal space-y-2 pl-5 leading-7 text-muted-foreground" {...props}>
        {children}
      </ol>
    ),
    li: ({ children, ...props }: HTMLAttributes<HTMLLIElement>) => (
      <li className="pl-1 marker:text-muted-foreground/60" {...props}>
        {children}
      </li>
    ),
    strong: ({ children, ...props }: HTMLAttributes<HTMLElement>) => (
      <strong className="font-semibold text-foreground" {...props}>
        {children}
      </strong>
    ),
    a: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => {
      const isInternal = href?.startsWith('/') || href?.startsWith('#');
      const className =
        'font-medium text-foreground underline underline-offset-4 decoration-border hover:decoration-foreground transition-colors';

      if (isInternal && href) {
        return (
          <Link href={href} className={className}>
            {children}
          </Link>
        );
      }

      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className={className} {...props}>
          {children}
        </a>
      );
    },
    // No `code` override: shiki hands the fenced-block `<code>` no className, so
    // an override can't tell it apart from inline code and would style both.
    // Inline code is handled by UPDATE_MDX_CLASS instead.
    pre: ({ children, ...props }: PreProps) => {
      // fumadocs passes its collapse-arrow markup as an `icon` prop, which is
      // not a DOM attribute — drop it rather than emit invalid HTML.
      const { icon: _icon, ...preProps } = props;
      return (
        <div className="my-6">
          <MdxPre {...preProps}>{children as ReactNode}</MdxPre>
        </div>
      );
    },
    blockquote: ({ children, ...props }: HTMLAttributes<HTMLQuoteElement>) => (
      <blockquote
        className="my-6 border-l-2 border-border pl-4 italic text-muted-foreground"
        {...props}
      >
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-10 border-border" />,
    img: ({ src, alt, title }: React.ComponentProps<typeof UpdateImage>) => {
      const isFirst = imagesRendered === 0;
      imagesRendered += 1;
      return (
        <UpdateImage src={src} alt={alt} title={title} priority={priorityFirstImage && isFirst} />
      );
    },
  };
}
