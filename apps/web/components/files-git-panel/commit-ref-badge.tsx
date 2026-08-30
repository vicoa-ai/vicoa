'use client';

import type { GraphColorId } from './commit-graph';

/** A rounded ref pill (branch/remote/tag) colored by its lane color. */
export function CommitRefBadge({ name, color }: { name: string; color: GraphColorId }) {
  const c = `var(--${color})`;
  return (
    <span
      title={name}
      className="max-w-[8rem] shrink-0 truncate rounded-full border px-1.5 py-0.5 text-[10px] leading-none"
      style={{ borderColor: c, color: c }}
    >
      {name}
    </span>
  );
}
