import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { AGENT_LOGOS } from './intro-slides';

/* How many chips fit one row of the agent strip.
   The web modal is the narrower of the two surfaces that render the deck: a
   `max-w-3xl` card (768px) less its `p-8`, so 704px of usable width. Chips are
   `h-9 w-9` (36px) in a `gap-2.5` (10px) row. Mirror any change to those
   classes here. */
const CHIP_PX = 36;
const GAP_PX = 10;
const MODAL_INNER_PX = 704;
const MAX_CHIPS_PER_ROW = Math.floor((MODAL_INNER_PX + GAP_PX) / (CHIP_PX + GAP_PX));

describe('the intro deck agent strip', () => {
  it('points every chip at a mark that exists', () => {
    // A missing SVG renders an empty white square — visible only by looking at
    // the slide, which nobody does on every logo edit.
    const missing = AGENT_LOGOS.filter(
      (logo) => !existsSync(join(process.cwd(), 'public', logo.src)),
    ).map((logo) => logo.src);
    expect(missing).toEqual([]);
  });

  it('stays on one row', () => {
    // A second row pushes the hero screenshot up until its mat overlaps the
    // slide title, so this is a real constraint, not a style preference.
    // `+ 1` is the trailing ellipsis chip that stands in for the rest.
    expect(AGENT_LOGOS.length + 1).toBeLessThanOrEqual(MAX_CHIPS_PER_ROW);
  });

  it('has no duplicate chips', () => {
    expect(new Set(AGENT_LOGOS.map((l) => l.src)).size).toBe(AGENT_LOGOS.length);
  });
});
