'use client';

import { useMemo } from 'react';
import { buildGraphRow, ROW_H, type CommitViewModel, type GraphColorId } from './commit-graph';
import { PANEL_BG } from './styles';

/** Ring "holes" fill with the panel's own surface, so they stay invisible in
 *  either theme; lane ids resolve to the themed `--git-graph-*` vars. */
function color(id: GraphColorId | 'bg'): string {
  return id === 'bg' ? PANEL_BG : `var(--${id})`;
}

export function CommitGraphSvg({ viewModel }: { viewModel: CommitViewModel }) {
  const row = useMemo(() => buildGraphRow(viewModel), [viewModel]);
  return (
    <svg
      width={row.width}
      height={ROW_H}
      viewBox={`0 0 ${row.width} ${ROW_H}`}
      className="shrink-0 overflow-visible"
      aria-hidden
    >
      {row.paths.map((p, i) => (
        <path
          key={`p${i}`}
          d={p.d}
          fill="none"
          stroke={color(p.color)}
          strokeWidth={1}
          strokeLinecap="round"
        />
      ))}
      {row.circles.map((c, i) => (
        <circle
          key={`c${i}`}
          cx={c.cx}
          cy={c.cy}
          r={c.r}
          fill={color(c.fill)}
          stroke={c.stroke ? color(c.stroke) : undefined}
          strokeWidth={c.strokeWidth}
        />
      ))}
    </svg>
  );
}
