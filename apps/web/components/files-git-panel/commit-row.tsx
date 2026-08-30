'use client';

import { ChevronDown } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { CommitViewModel, GraphColorId } from './commit-graph';
import { refColor } from './commit-graph';
import { CommitGraphSvg } from './commit-graph-svg';
import { CommitRefBadge } from './commit-ref-badge';

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** One commit row: lane graph + subject + ref pills + short sha. Hovering the
 *  subject shows a card with the full message, author, date, and sha. The
 *  expanded file list is rendered by the parent below this. */
export function CommitRow({
  viewModel,
  colorMap,
  expanded,
  onToggle,
}: {
  viewModel: CommitViewModel;
  colorMap: Map<string, GraphColorId>;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { item } = viewModel;
  // Branch/remote/tag pills; the bare HEAD pseudo-ref is implied by the node ring.
  const named = item.refs.filter((r) => r.kind !== 'head');
  const pills = named.slice(0, 2);
  const hidden = named.length - pills.length;

  return (
    <button
      type="button"
      onClick={onToggle}
      className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-1.5 px-3 py-0.5 text-left text-xs font-mono hover:bg-muted/30"
      style={{ minHeight: 26 }}
    >
      <CommitGraphSvg viewModel={viewModel} />
      <div className="flex min-w-0 items-center gap-1 overflow-hidden">
        <ChevronDown
          className={`size-3 shrink-0 text-muted-foreground transition-transform ${expanded ? '' : '-rotate-90'}`}
        />
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block min-w-0 flex-1 truncate text-foreground">{item.subject}</span>
          </TooltipTrigger>
          <TooltipContent
            side="bottom"
            sideOffset={6}
            className="max-w-96 border-0 bg-[#2D2D2D] text-foreground shadow-md"
          >
            <div className="flex flex-col gap-1.5 py-0.5 font-mono">
              <div className="whitespace-pre-wrap text-xs font-medium leading-snug text-foreground">
                {item.subject}
              </div>
              {item.body && (
                <div className="whitespace-pre-wrap text-[11px] leading-snug text-muted-foreground">
                  {item.body}
                </div>
              )}
              <div className="mt-0.5 flex flex-col gap-0.5 border-t border-white/10 pt-1 text-[11px] text-muted-foreground">
                <div className="truncate">{`${item.author_name} <${item.author_email}>`}</div>
                <div>
                  {formatDate(item.timestamp)} ·{' '}
                  <span className="tabular-nums">{item.short_id}</span>
                </div>
              </div>
            </div>
          </TooltipContent>
        </Tooltip>
      </div>
      <div className="flex shrink-0 items-center gap-1 overflow-hidden">
        {pills.map((r) => (
          <CommitRefBadge key={`${r.kind}:${r.name}`} name={r.name} color={refColor(viewModel, r, colorMap)} />
        ))}
        {hidden > 0 && <span className="shrink-0 text-[10px] text-muted-foreground">+{hidden}</span>}
        <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">{item.short_id}</span>
      </div>
    </button>
  );
}
