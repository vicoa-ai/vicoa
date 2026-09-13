# Catalog agent marks

The brand marks for the ACP agents in `backend/src/protocol/acp_catalog.py`,
shown in Settings → Providers and anywhere a session of one of those agents is
listed. Mirrored byte-for-byte in `apps/mobile/assets/images/acp/`.

Each name, logo and trademark belongs to its respective owner. They appear here
only to identify the agent a user is choosing to run — Vicoa is not affiliated
with, endorsed by, or distributing any of them. Ask us to drop yours and we
will. Sources, all normalised to `fill="currentColor"`:

| Icons | From | Licence |
| --- | --- | --- |
| 28 | [paseo](https://github.com/getpaseo/paseo)'s ACP provider catalog, collected from each project's own site | — |
| `traecli`, `minimax-code` | [simple-icons](https://github.com/simple-icons/simple-icons) | CC0-1.0 |
| `grok`, `devin`, `kiro` | [@lobehub/icons-static-svg](https://github.com/lobehub/lobe-icons) | MIT |

## Adding one

Drop a `<id>.svg` in **both** directories, named exactly as the catalog id,
then regenerate the lookup index:

```bash
python backend/scripts/gen_acp_icons.py
```

Constraints, all enforced by `apps/web/lib/acp-provider-icons.test.ts` and by
the generator:

- **Monochrome, `fill="currentColor"`.** The mark is painted as a CSS mask over
  `currentColor` (web) or tinted with `BlendMode.srcIn` (mobile), so it follows
  the theme with no light/dark variants. A hardcoded colour is flattened into a
  silhouette and fails the test.
- **Self-contained.** No `<script>`, no event handlers, no remote `href`. A
  mask never enters the DOM, but the next person to use these files somewhere
  that parses them shouldn't have to re-audit them.
- **Legible at 18 px**, which is the size nearly every surface renders.
- A file with no matching catalog entry is an error, not a silent orphan.

A catalog entry with no mark here is fine — it falls back to a generated
initial-square, the same treatment a user's own provider gets. Every entry is
covered today, and a test keeps it that way, so a new one should arrive with
its mark.
