/** `@joplin/turndown-plugin-gfm` ships no types (CommonJS, named exports). */
declare module '@joplin/turndown-plugin-gfm' {
  import type TurndownService from 'turndown';

  /** Every GFM extension below, in one call. */
  export function gfm(service: TurndownService): void;
  export function tables(service: TurndownService): void;
  export function strikethrough(service: TurndownService): void;
  export function taskListItems(service: TurndownService): void;
  export function highlightedCodeBlock(service: TurndownService): void;
}
