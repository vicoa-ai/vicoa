'use client';

// A `#` reference shown as a chip: the item's current title, under the icon
// the sidebar gives that kind of thing. Used wherever a reference link is
// drawn (the description editor and MessageMarkdown), so a reference looks
// the same in a description and in the comments under it.

import Link from 'next/link';
import { CalendarClock, ListTodo, MessageCircle } from 'lucide-react';

import { AgentTypeIcon } from '@/components/dashboard/agent-type-icon';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import type { ReferenceKind } from '@/lib/backend-api';
import { referenceHref } from '@/lib/reference-links';
import { isTextSelectionClick } from '@/lib/text-selection';
import { agentPrincipal, useAgentProfiles } from '@/lib/use-agent-profiles';
import { useReferenceInfo, type ReferenceInfo } from '@/lib/use-reference-info';
import { cn } from '@/lib/utils';

// `self-center`: the chip lines its text up on the baseline (see ReferenceChip)
// and the icon, which has none, sits in the middle.
const ICON_CLASS = 'size-3.5 shrink-0 self-center text-muted-foreground';

/** The sidebar's icon for each kind: the Tasks and Automations nav entries,
 *  and a session row's agent (the saved agent's face when it started one). */
function ReferenceIcon({ kind, info }: { kind: ReferenceKind; info: ReferenceInfo | null }) {
  const { byId } = useAgentProfiles();
  if (kind === 'task') return <ListTodo className={ICON_CLASS} />;
  if (kind === 'automation') return <CalendarClock className={ICON_CLASS} />;
  const profile = info?.agentProfileId ? byId.get(info.agentProfileId) : undefined;
  if (profile) return <PrincipalAvatar principal={agentPrincipal(profile)} size="xs" className="self-center" />;
  // Before the lookup lands, or when it can't: the session glyph.
  if (!info?.agentTypeName) return <MessageCircle className={ICON_CLASS} />;
  return <AgentTypeIcon agentTypeName={info.agentTypeName} size={12} whiteForOpenAI className="self-center" />;
}

export function ReferenceChip({
  kind,
  id,
  label,
  className,
}: {
  kind: ReferenceKind;
  id: string;
  /** The stored link text, `#VIC-42`: shown until the item is read, and for
   *  good when it can't be (deleted, or not visible to this viewer). */
  label: string;
  className?: string;
}) {
  const { info, missing } = useReferenceInfo(kind, id);
  const title = info?.title?.trim() || null;
  const fallback = label.replace(/^#/, '');
  return (
    <span
      className={cn(
        // Baseline-aligned items make the text's baseline the chip's own, so
        // it sits on the line like a word. Led by an icon (no baseline of its
        // own), it would otherwise ride up by the icon's descent.
        'inline-flex max-w-full items-baseline gap-1 rounded-md border border-border bg-muted/50 px-1.5 align-baseline',
        'text-[13px] leading-5 text-foreground transition-colors',
        missing && 'text-muted-foreground',
        className,
      )}
      title={title ?? undefined}
    >
      <ReferenceIcon kind={kind} info={info} />
      {kind === 'task' && info?.identifier && (
        <span className="shrink-0 text-muted-foreground">{info.identifier}</span>
      )}
      <span className="min-w-0 truncate">{title ?? fallback}</span>
    </span>
  );
}

/** The chip as a link to the item's page, navigated in the app. */
export function ReferenceChipLink({
  kind,
  id,
  label,
}: {
  kind: ReferenceKind;
  id: string;
  label: string;
}) {
  return (
    <Link
      href={referenceHref(kind, id)}
      draggable={false}
      // Marked so the markdown link styles (blue, underlined) leave it alone.
      data-reference-chip=""
      className="group/ref inline-block max-w-full cursor-pointer align-baseline no-underline"
      onClick={(e) => {
        // A drag that selects text across the chip must not also navigate.
        if (isTextSelectionClick(e)) e.preventDefault();
      }}
    >
      <ReferenceChip kind={kind} id={id} label={label} className="group-hover/ref:bg-accent" />
    </Link>
  );
}
