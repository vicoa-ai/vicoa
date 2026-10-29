'use client';

import { NodeViewWrapper, ReactNodeViewRenderer, type ReactNodeViewProps } from '@tiptap/react';

import { ReferenceChipLink } from '@/components/dashboard/reference-chip';
import { cn } from '@/lib/utils';

import { ReferenceNode, type ReferenceAttrs } from './reference-node';

function ReferenceNodeView({ node, selected }: ReactNodeViewProps) {
  const { kind, id, label } = node.attrs as ReferenceAttrs;
  return (
    <NodeViewWrapper as="span" className={cn('rich-markdown-reference', selected && 'is-selected')}>
      <ReferenceChipLink kind={kind} id={id} label={label} />
    </NodeViewWrapper>
  );
}

/**
 * The reference node with its chip, for the editor. A chip is an object, not
 * text, so a plain click opens it, as everywhere else it appears; the caret
 * goes beside it, and Backspace takes it out whole.
 */
export const ReferenceNodeWithChip = ReferenceNode.extend({
  addNodeView() {
    return ReactNodeViewRenderer(ReferenceNodeView, {
      // The chip's link owns its pointer events. Left to ProseMirror, a press
      // node-selects the chip and the click that follows never navigates.
      stopEvent: ({ event }) => /^(mouse|pointer|click|auxclick)/.test(event.type),
    });
  },
});
