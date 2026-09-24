---
title: Markdown live editor — sample
status: draft
tags: [editor, markdown, fixture]
note: "**not bold**, `not code`, [not a link](x) — front matter is left alone"
---

# Markdown live editor sample

Open this in the files panel with **Edit** on. Every section says what it should
look like, so anything that does not match is a bug. Put the caret inside a
construct to reveal its raw markdown — that is by design, and how you edit it.

## 1. Front matter

Scroll to the top. Expected: a dimmed monospace block on a faint background,
**both** `---` fences visible, `tags: [editor, markdown, fixture]` keeping its
square brackets, and the `**not bold**` inside it rendered literally.

## 2. Headings

# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6

Expected: no `#` markers, each level a bit smaller than the last.

Setext heading (known gap)
==========================

Expected today: the `====` line disappears and the title keeps whatever the
syntax theme does with a heading (bold/underlined in light, coloured in dark),
but not our heading *size* — only `#`-style headings are sized. Worth fixing.

## 3. Inline styles

Plain, **bold**, *italic*, ***bold italic***, ~~struck out~~, `inline code`,
and an escaped \*not italic\* pair.

Expected: no `**`, `*`, `~~` or backticks visible; code on a tinted chip. The
escaped pair still shows its backslashes (`\*not italic\*`) — a rendered
document would show `*not italic*`. Small gap.

## 4. Links

Cmd/Ctrl+click follows these; a plain click puts the caret in them. Hold the
modifier and the link under the pointer takes the standard link look — link
blue, underlined — and a hand cursor; a bare URL, which carries none of that on
its own, is where the change shows most. Hovering (no modifier) shows the
destination in a tooltip.

- Inline: [the docs](https://example.com/docs)
- With a title: [titled](https://example.com "A title")
- Destination with a space: [spaced](<https://example.com/a b>)
- Bare autolink: https://example.com/bare
- Angle autolink: <https://example.com/angle>
- Reference: [explicit][ref], [collapsed][], [shortcut]
- Mail: [mail me](mailto:someone@example.com)
- Empty link text: [](https://example.com/empty)

Expected: all of the above open in the browser. The empty one renders as
nothing at all (it has no text) — it used to crash the whole preview layer.

These must **not** open, and must not error:

- Relative: [AGENTS.md](./AGENTS.md)
- Absolute local: [a file](/etc/hosts)
- Anchor: [back to top](#markdown-live-editor-sample)
- Script: [do not run](javascript:alert(1))

Known gap: these look exactly like the openable links above — same blue,
same underline — and only do nothing when you Cmd+click. The chat renderer
mutes them with a dotted underline instead; the editor should match.

## 5. Lists

- first bullet
- second bullet
  - nested bullet
    - deeper still
- last bullet

1. first
2. second
   1. nested ordered
3. third

- [ ] unchecked task (known gap)
- [x] checked task (known gap)

Expected: bullets and numbers stay as written (no rendered discs). Task boxes
show as raw `[ ]` / `[x]` — no checkbox yet.

## 6. Blockquote

> A quote with **bold** and a [link](https://example.com/quoted).
> Second line of the same quote.
>
> > Nested quote.

Expected: `>` markers hidden, a left border and dimmed text on every line.

## 7. Dividers

Three flavours, each on its own line:

---

***

___

Expected: three thin full-width rules. Put the caret on one and the raw
characters come back.

## 8. Tables

| step | owner | done |
| --- | :---: | ---: |
| parse | live layer | yes |
| render | widget | no |

Expected: a real grid — left, centre and right alignment respectively, header
row tinted — and it stays a grid while you edit it:

- Click a cell and type. The markdown underneath changes as you type; the grid
  never turns back into pipes, and the column grows with the text.
- Tab / Shift+Tab move between cells, Enter and ↑/↓ move down and up a row.
- A typed `|` is escaped into the source, so it cannot split the row.
- Typing in the empty cell the grid pads a short row with adds that cell to the
  row (try the `k`/`v` table below).
- ⌘S, ⌘Z and the rest of the editor's shortcuts still work from inside a cell;
  ⌘A/⌘C/⌘V/⌘X mean the cell's own text.
- Escape leaves the grid for the markdown, caret on the same character — that
  is how you make the edits a grid cannot express: adding a column, changing
  the alignment row. Clicking the grid's outer padding does the same.

Escaped pipes:

| pattern | meaning |
| --- | --- |
| `a \| b` | a literal pipe inside a cell |

Expected: one row, the cell reading ``a | b``. Known gap: cells render as plain
text, so the backticks show — no inline markdown inside a rendered table.

A table inside a list item:

- item with a table

  | k | v |
  | --- | --- |
  | a | 1 |

Not a table (no delimiter row) — must stay raw text:

| a | b |
| 1 | 2 |

## 9. Code blocks

```ts
const x: number = 1;
console.log(`hello ${x}`);
```

Expected today (known gap): the ``` fences are hidden but the `ts` language
tag is still shown on its own line, and the code gets no background or
highlighting. Both worth fixing.

    an indented code block
    second line

Expected: left exactly as written.

## 10. Images

![a remote image](https://example.com/a.png)

![a repo image](./apps/web/public/images/featured/none.png)

Expected: image markdown stays as source by design — the `!` tells you it is an
image, and nothing remote is fetched. Cmd+click on the URL text opens it.

## 11. Raw HTML

<div class="callout">An HTML block: shown literally, never executed.</div>

Inline <b>bold tag</b> and a <a href="https://example.com">tag link</a>.

Expected: all of it as plain text.

## 12. Footnotes (known gap)

Some claim needing a source[^1].

[^1]: The footnote body.

Expected today: `[^1]` renders as a link-styled `^1` with its brackets hidden,
and Cmd+click does nothing (there is no matching definition). Harmless, but not
right.

## 13. Paste

Needs a real clipboard, so it is a manual check:

1. Copy a block from a web page (a heading, a list, a link, a table) and paste
   it here. Expected: markdown — `## heading`, `- item`, `[text](url)`, a GFM
   table — not a wall of bare words.
2. Copy a few lines out of a code editor or a terminal and paste. Expected:
   exactly what you copied. That clipboard carries styled HTML too, and
   converting it would escape and mangle the code.
3. Paste anything into the code fence above, or into the front matter at the
   top. Expected: the plain text, unconverted.

## 14. Text handling

A deliberately long line to check wrapping: lorem ipsum dolor sit amet,
consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et
dolore magna aliqua, ut enim ad minim veniam quis nostrud exercitation ullamco.

中文段落，带**粗体**、`行内代码` 和一个[链接](https://example.com/zh)，用来检查
换行、光标定位和选区。Emoji: 🎉 👍 ✅ — and a mixed 中英 line with `code`.

Drag-select across the whole section and check the selection tracks the mouse.

[ref]: https://example.com/reference-explicit
[collapsed]: https://example.com/reference-collapsed
[shortcut]: https://example.com/reference-shortcut
