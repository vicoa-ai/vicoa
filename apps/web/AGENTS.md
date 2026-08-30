# Repository Guidelines

## Project Structure & Module Organization
- The Next.js App Router lives in `app/`, split by audience: `app/(marketing)/` holds the public pages (landing `/`, pricing, blog, `vs`, features, help, legal) behind one server-rendered shell that owns the shared header + footer; `app/dashboard/` is the authenticated app as a plain `/dashboard/*` segment with its own client shell; `app/(login)/` holds the auth screens. `app/docs` renders MDX-driven docs from `content/` via Fumadocs. Co-locate server actions and loaders beside their page.
- Shared UI primitives stay in `components/`; prefer extending existing primitives before creating new folders. Global providers live in `components/theme-provider` and `app/layout.tsx`.
- Domain logic sits inside `lib/`: `lib/db` holds Drizzle schema, migrations, and seeds; `lib/auth`, `lib/payments`, and `lib/utils.ts` centralize reusable logic. Static assets are under `public/`; shared types live in `types/`.

### Route groups: when to add one
A route group (`app/(name)/`) earns its keep for exactly one reason: to give a shared `layout.tsx` to routes that **don't share a URL prefix**. The parenthesized folder name is invisible in the URL. Before adding one, check:
- **Multiple prefix-less siblings that need one shell?** → group them. That is why `(marketing)` exists: `/`, `/pricing`, `/blog`, `/vs` share no common prefix but want one header+footer shell.
- **Everything under a single `/foo/*` prefix?** → no group. Give the segment its own `app/foo/layout.tsx`; it already scopes a shared layout to those routes. This is why the app is `app/dashboard/`, not `app/(app)/dashboard/` — a same-named group wrapping the one `dashboard` segment adds a folder and groups nothing.
- **Only one child?** → no group. Put the layout on the segment.
- Don't add a group speculatively. Example: the desktop **settings** page is `/dashboard/settings` and branches on `IS_DESKTOP` *inside* the page, so it stays under the `dashboard` segment and needs no group. You would only introduce an `(app)` group once authenticated areas start living at **other** top-level URLs (e.g. `/settings`, `/billing`) that must share the app shell — group them then, not before.

## Build, Test, and Development Commands
- `pnpm dev` runs the Next.js dev server (Turbopack). Use `pnpm dev:no-turbo` if Turbopack misbehaves.
- `pnpm build` and `pnpm start` produce and run a production build.
- `pnpm db:setup` scaffolds `.env.local`; follow with `pnpm db:migrate` and `pnpm db:seed` to sync Postgres (or use `docker-compose up postgres`).
- `pnpm db:generate` regenerates Drizzle migrations; `pnpm db:studio` opens the schema explorer.

## Coding Style & Naming Conventions
- TypeScript is required for app code; keep files under `app/**` and `components/**` as `.tsx`. Use PascalCase for components and camelCase for functions, with server-only utilities in `lib/**`.
- Follow the repo’s two-space indentation and Tailwind-first styling; compose classes with `clsx`/`tailwind-merge`.
- Prefer async/await, avoid anonymous default exports, and reuse the `@/` path alias instead of relative `../../` imports.
- Every scrollable container (`overflow-y-auto` / `overflow-x-auto`) must also carry the `custom-scrollbar` utility class (defined in `app/globals.css`): it renders the site-wide thin 6px scrollbar with a transparent track in both themes. Never ship a dashboard scroll area on the default browser scrollbar.
- Keyboard-shortcut hints in UI must come from `lib/desktop-shortcuts.ts` (`comboKeycaps`/`comboInline`), which pick ⌘ vs Ctrl per platform — never hardcode `⌘K`. Compute them in a post-mount `useEffect` (platform detection reads `navigator`, so computing during render causes a hydration mismatch), and render keycaps as small bordered `<kbd>` chips (`rounded border bg-muted px-1 py-0.5 text-[10px]`, see the sidebar Search entry) rather than plain muted text.
- Anything clickable must show the hand cursor on hover — add `cursor-pointer` to every interactive element (buttons, links, tabs, menu items, clickable cards/rows, icon buttons, custom toggles). The browser reset gives native `<button>` a default arrow cursor, so this is required even on real `<button>`/`role="button"` elements, not just `<div>` handlers. Skip it only for disabled controls (pair with `cursor-not-allowed`) and text inputs.

## Testing Guidelines
- There is not yet a formal automated test suite—new features should include unit coverage placed alongside the module (e.g., `lib/foo/foo.test.ts`) or documented manual steps.
- Always run `pnpm db:seed` before testing features that depend on seeded users, and capture edge-case scenarios (auth, billing, webhook flows) in your PR description.

## Commit & Pull Request Guidelines
- Follow the existing history: short, imperative commit subjects (for example, `add documentation`, `hide agents tab`). Squash fixup commits locally.
- PRs must describe the change, list required migrations or env vars, and include screenshots/GIFs for UI updates. Link related issues and note any follow-up tasks or Stripe webhook changes.
- Validate locally (`pnpm build`, critical flows) before requesting review; note anything you could not verify.
- `.source/index.ts` is generated by Fumadocs from `content/` (MDX, `meta.json`, etc.). When your change touches `content/` and `.source/index.ts` shows up in `git status` as a result, include it in the same commit — otherwise the next dev's build regenerates it and produces a noisy unrelated diff.

## Security & Configuration Tips
- Store secrets in `.env.local` and never commit them. Run `pnpm db:setup` after pulling to refresh keys.
- Stripe and Supabase webhooks should use environment-specific secrets; rotate keys promptly if exposed and update `source.config.ts` when documentation sources change.


## Adding a New "Featured On" Badge

Badges are listed in `components/landing/sections/featured-section.tsx` and scroll in a marquee on the landing page.

### Steps

1. **Get the badge image.** Try the directory's embed page. If the badge URL is an external SVG or PNG, test it first:
   ```bash
   curl -I <badge-url>
   ```
   If it returns 200, use the external URL directly. If it returns 403 or is Cloudflare-protected, download it manually in a browser and save it to `public/images/featured/<name>-badge.<ext>`.

2. **For local files**, place the image in `public/images/featured/` and reference it as `/images/featured/<name>-badge.<ext>`.

3. **Add the entry** to the `featuredIn` array in `featured-section.tsx`:
   ```ts
   {
     name: 'Directory Name',
     logo: '/images/featured/dirname-badge.svg', // or external URL if reliable
     url: 'https://directory.com/vicoa',
     width: 120,  // check actual badge dimensions
     height: 40,
   },
   ```

4. **Rendering note**: SVGs and `LaunchIgniter` use a plain `<img>` tag (no Next.js Image optimization). All other formats use Next.js `<Image fill>`. This is handled automatically by the component — no code change needed.

5. **Check badge dimensions** — use the actual pixel dimensions of the badge so it renders without distortion. Common sizes: `120×40`, `150×54`, `179×32`.
