/**
 * What a link inside an agent message actually points at.
 *
 * Agents (Codex especially) cite the files they touched as ordinary markdown
 * links — `[src/foo.ts](src/foo.ts)`, `[foo.ts:42](file:///repo/src/foo.ts#L42)`
 * — and those are NOT web links. Rendering them as `<a target="_blank">` sends
 * the click to the browser: relative hrefs resolve against the dashboard's own
 * origin, and `file:` hrefs are stripped to `href=""` by react-markdown's URL
 * sanitiser, which means "reopen the current page". On desktop the Electron
 * window handler then hands that URL to the OS browser, which has none of the
 * app's session state, so the user lands in a sign-in flow that cannot finish
 * ("Desktop bridge unavailable"). See vicoa-ai/vicoa#46.
 *
 * So every href is classified here first, and only genuine web URLs are allowed
 * to leave the app.
 */

import { toAbsolutePath } from '@/lib/utils';

/** A file inside the session's workspace, as the files panel wants it. */
export interface WorkspaceFileLink {
  /** Project-relative POSIX path, e.g. `src/foo.ts`. Never empty. */
  path: string;
  /** 1-based line the link pointed at, when it carried one. */
  line?: number;
}

export type MessageLink =
  /** A real web URL — safe to open in the browser. */
  | { kind: 'external'; href: string }
  /** A file under the session's working directory. */
  | { kind: 'file'; file: WorkspaceFileLink }
  /** A local path, but not under the working directory — refuse to follow it. */
  | { kind: 'outside'; path: string }
  /** Fragments, empty hrefs, unknown schemes: render as plain text. */
  | { kind: 'inert' };

export interface WorkspaceContext {
  /** The session's working directory on the agent's machine. Often stored
   *  tilde-prefixed (`~/projects/app`), so it is expanded here too — not just
   *  the link — or an absolute link into that very directory reads as being
   *  outside it. */
  cwd: string | null;
  /** That machine's home directory, so `~/…` can be expanded. */
  homeDir: string | null;
}

/** Schemes that may be handed to the OS browser. */
const WEB_SCHEME = /^(?:https?|mailto):/i;
/** `scheme:` at the head of a URL, per RFC 3986. */
const SCHEME = /^([a-z][a-z0-9+.\-]*):/i;
/** `C:\…` / `c:/…` — a Windows drive, not a URL scheme. */
const WINDOWS_DRIVE = /^[a-z]:[\\/]/i;
/** `foo.ts:42`, `foo.ts:42:7` — a bare filename carrying a line reference. The
 *  leading run parses as a URL scheme but is a path; only digits may follow. */
const FILENAME_WITH_LINE = /^[a-z][a-z0-9+.\-]*:\d+(?::\d+)?$/i;

/**
 * react-markdown's `urlTransform`, widened by `file:` and `name:line`.
 *
 * The default drops any scheme outside its allowlist, which turns a
 * `file:///…` href into `''` — indistinguishable from "no href" by the time the
 * `a` renderer sees it, and `<a href="" target="_blank">` reopens the current
 * page. Keeping those intact lets {@link parseMessageLink} recognise them and
 * keep the click inside the app. Everything else (notably `javascript:`) is
 * still stripped, with the same colon-before-slash/query/hash reasoning as
 * upstream so relative paths survive.
 */
export function messageUrlTransform(url: string): string {
  const colon = url.indexOf(':');
  if (colon === -1) return url;
  const slash = url.indexOf('/');
  const question = url.indexOf('?');
  const hash = url.indexOf('#');
  // A colon that comes after a `/`, `?` or `#` belongs to the path, not a scheme.
  if (
    (slash !== -1 && colon > slash) ||
    (question !== -1 && colon > question) ||
    (hash !== -1 && colon > hash)
  ) {
    return url;
  }
  if (WINDOWS_DRIVE.test(url) || FILENAME_WITH_LINE.test(url)) return url;
  const scheme = url.slice(0, colon + 1);
  return WEB_SCHEME.test(scheme) || /^file:$/i.test(scheme) ? url : '';
}

/** Collapse `.`/`..` segments and duplicate slashes. `..` may escape the root,
 *  which the caller detects as a leading `..` segment. */
function normalizeSegments(path: string): string {
  const out: string[] = [];
  for (const segment of path.split('/')) {
    if (segment === '' || segment === '.') continue;
    if (segment === '..') {
      if (out.length > 0 && out[out.length - 1] !== '..') out.pop();
      else out.push('..');
      continue;
    }
    out.push(segment);
  }
  return out.join('/');
}

/** Backslashes → slashes, trailing separator dropped (except a bare root). */
function toPosix(path: string): string {
  const slashed = path.replace(/\\/g, '/');
  return slashed.length > 1 ? slashed.replace(/\/+$/, '') : slashed;
}

/** Anchored at a root of its own, rather than at the working directory: `/x`,
 *  `C:\x`, or a `~` that had no home directory to expand against. */
function isRooted(path: string): boolean {
  return path.startsWith('/') || WINDOWS_DRIVE.test(path) || path === '~' || path.startsWith('~/');
}

/** Collapse `.`/`..` in a rooted path, keeping whichever root it carries. */
function normalizeRooted(path: string): string {
  if (WINDOWS_DRIVE.test(path)) {
    return `${path.slice(0, 2)}/${normalizeSegments(path.slice(2))}`;
  }
  if (isRooted(path) && path.startsWith('~')) {
    const rest = normalizeSegments(path.slice(1));
    return rest ? `~/${rest}` : '~';
  }
  return `/${normalizeSegments(path)}`;
}

/**
 * `child` expressed relative to `parent`, or null when it isn't under it.
 * `parent` itself yields `''` — a directory, which callers treat as no file.
 * Windows paths (a drive-lettered root) compare case-insensitively.
 */
function relativeTo(parent: string, child: string): string | null {
  const fold = (s: string) => (WINDOWS_DRIVE.test(parent) ? s.toLowerCase() : s);
  const p = fold(parent).replace(/\/+$/, '');
  const c = fold(child);
  if (c === p) return '';
  if (!c.startsWith(`${p}/`)) return null;
  return child.slice(p.length + 1);
}

/**
 * Strip a trailing line reference and return it.
 *
 * Understood: `#L42`, `#L42-L57`, `#42`, `:42`, `:42:7` — the shapes agents and
 * editors actually emit. A `#section` fragment is not a line and is dropped
 * along with the rest (an anchor into a source file has nowhere to go).
 */
function splitLineRef(raw: string): { path: string; line?: number } {
  let path = raw;
  let line: number | undefined;

  const hash = path.indexOf('#');
  if (hash !== -1) {
    const fragment = path.slice(hash + 1);
    path = path.slice(0, hash);
    const m = /^L?(\d+)(?:[-,]L?\d+)?$/i.exec(fragment);
    if (m) line = Number(m[1]);
  }
  if (line === undefined) {
    const m = /^(.*?[^:]):(\d+)(?::\d+)?$/.exec(path);
    // Never mistake a drive letter (`C:`) for a line separator.
    if (m && !/(?:^|[\\/])[a-z]$/i.test(m[1])) {
      path = m[1];
      line = Number(m[2]);
    }
  }
  return { path, line: line !== undefined && line > 0 ? line : undefined };
}

/** A bare `foo` is more likely prose than a path; require a separator or a
 *  file extension before treating a relative href as a local file. */
function looksLikePath(path: string): boolean {
  return path.includes('/') || /\.[A-Za-z0-9]{1,12}$/.test(path);
}

/** Decode a `file:` URL (including `file:///C:/…`) to a plain path. */
function pathFromFileUrl(href: string): string | null {
  // Tolerate `file:/x`, `file://x` and `file:///x` alike; a non-empty authority
  // (a UNC host) is not something the daemon can open, so refuse it.
  const m = /^file:(?:\/\/([^/]*))?(\/.*)?$/i.exec(href);
  if (!m || m[1]) return null;
  const raw = m[2];
  if (!raw) return null;
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    decoded = raw;
  }
  // `/C:/Users/…` → `C:/Users/…`
  return /^\/[a-z]:[\\/]/i.test(decoded) ? decoded.slice(1) : decoded;
}

/**
 * Classify one markdown link from an agent message.
 *
 * `href` is what react-markdown handed the `a` renderer, i.e. already through
 * {@link messageUrlTransform}.
 */
export function parseMessageLink(
  href: string | undefined,
  { cwd, homeDir }: WorkspaceContext,
): MessageLink {
  const raw = (href ?? '').trim();
  // Empty (a stripped `javascript:`) or a pure in-document fragment: there is
  // nothing to navigate to, and following it would reopen the current page.
  if (raw === '' || raw.startsWith('#')) return { kind: 'inert' };
  // Protocol-relative (`//host/x`) is a web URL we can't vouch for, not a path.
  if (raw.startsWith('//')) return { kind: 'inert' };

  let candidate = raw;
  const scheme = SCHEME.exec(raw);
  if (scheme && !WINDOWS_DRIVE.test(raw) && !FILENAME_WITH_LINE.test(raw)) {
    if (WEB_SCHEME.test(raw)) return { kind: 'external', href: raw };
    if (!/^file$/i.test(scheme[1])) return { kind: 'inert' };
    const fromUrl = pathFromFileUrl(raw);
    if (fromUrl === null) return { kind: 'inert' };
    candidate = fromUrl;
  }

  const { path: rawPath, line } = splitLineRef(candidate);
  if (rawPath === '') return { kind: 'inert' };

  // Without a working directory there is no panel to open the file in.
  if (!cwd) return { kind: 'inert' };
  // Both sides go through the same `~` expansion, so a tilde-stored project and
  // an absolute link into it still meet. With no home directory to expand
  // against they stay tilde-prefixed — which still compares correctly as long
  // as both sides are.
  const path = toPosix(toAbsolutePath(rawPath, homeDir) ?? rawPath);
  const root = toPosix(toAbsolutePath(cwd, homeDir) ?? cwd);
  if (!isRooted(path) && !looksLikePath(path)) return { kind: 'inert' };

  let relative: string | null;
  if (isRooted(path)) {
    relative = relativeTo(root, normalizeRooted(path));
  } else {
    const joined = normalizeSegments(path);
    // `../` climbing out of the project survives normalisation as a leading
    // `..`, which is exactly the "outside the workspace" case.
    relative = joined.startsWith('..') ? null : joined;
  }

  if (relative === null) return { kind: 'outside', path: rawPath };
  if (relative === '') return { kind: 'inert' }; // the project root itself
  return { kind: 'file', file: { path: relative, ...(line ? { line } : {}) } };
}
