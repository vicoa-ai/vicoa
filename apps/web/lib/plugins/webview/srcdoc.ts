/**
 * Builds the two documents a plugin page runs in.
 *
 * The outer one is the host's **shell**: a tiny sandboxed page whose policy
 * says `frame-src 'none'`. A frame's navigations are checked against the
 * policy of the document that contains it, so the plugin page, framed inside
 * the shell, can't navigate itself anywhere (no `location = 'https://…?data'`,
 * no 204 trick, no meta refresh), and the request is never sent. It can't
 * navigate the shell or the app either: sandboxed frames may only navigate
 * themselves. The shell also hands the plugin the host's MessagePort once the
 * page has loaded, and reports if the inner frame ever loads a second time.
 *
 * The inner one is the plugin's **page**: the host's preamble (content
 * security policy, theme variables, base styles, the `window.vicoa` runtime)
 * followed by the plugin's own HTML.
 *
 * The preamble goes first, before any plugin markup, even when the plugin
 * ships a full `<!doctype html><html><head>` document: the parser folds the
 * plugin's later `<html>`/`<head>` tags into the ones already open, and the
 * policy is guaranteed to exist before any plugin script runs. A meta policy
 * can only be tightened afterwards, never loosened.
 */

import { PLUGIN_CLIENT_SCRIPT } from '../bridge/client-script';

/** Values handed to the runtime before the plugin's scripts start. */
export interface PageInit {
  pluginId: string;
  surfaceId: string;
  route: string;
  theme: { mode: 'dark' | 'light'; css: string };
}

/**
 * The page's policy. Scripts and styles may be inline (a page is one file);
 * everything that touches the network is limited to the declared origins, so
 * with no `network` the page can reach nothing at all.
 */
export function buildCsp(network: readonly string[] = []): string {
  const net = network.join(' ');
  const withNet = (...base: string[]) => [...base, net].filter(Boolean).join(' ');
  return [
    "default-src 'none'",
    `script-src ${withNet("'unsafe-inline'", "'unsafe-eval'")}`,
    `style-src ${withNet("'unsafe-inline'")}`,
    `img-src ${withNet('data:', 'blob:')}`,
    `font-src ${withNet('data:')}`,
    `media-src ${withNet('data:', 'blob:')}`,
    `connect-src ${net || "'none'"}`,
    'worker-src blob:',
    "frame-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ');
}

/** Starting styles. The plugin's own CSS comes later and wins. */
export const BASE_CSS = [
  'html{color-scheme:var(--vicoa-color-scheme,dark)}',
  'html,body{margin:0;min-height:100%}',
  'body{background:var(--vicoa-background);color:var(--vicoa-foreground);',
  'font-family:var(--vicoa-font-sans);font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}',
  'a{color:var(--vicoa-primary)}',
  'button,input,select,textarea{font:inherit;color:inherit}',
].join('');

function escapeAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/** JSON that is safe inside an inline `<script>`. */
export function scriptJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/** Text that is safe inside an inline `<style>`. */
function styleText(css: string): string {
  return css.replace(/<\/style/gi, '<\\/style');
}

export function buildSrcdoc(options: { html: string; network?: readonly string[]; init: PageInit }): string {
  const { html, network = [], init } = options;
  const preamble = [
    '<!doctype html>',
    '<meta charset="utf-8">',
    `<meta http-equiv="Content-Security-Policy" content="${escapeAttr(buildCsp(network))}">`,
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    `<style id="vicoa-base">${BASE_CSS}</style>`,
    `<style id="vicoa-theme">${styleText(init.theme.css)}</style>`,
    `<script>window.__vicoaInit=${scriptJson(init)};</script>`,
    `<script>${PLUGIN_CLIENT_SCRIPT}</script>`,
  ].join('');
  return preamble + html;
}


const SHELL_SCRIPT = String.raw`(function () {
  var TAG = '__vicoa';
  var inner = document.createElement('iframe');
  inner.setAttribute('sandbox', 'allow-scripts');
  inner.setAttribute('referrerpolicy', 'no-referrer');
  inner.setAttribute('title', document.title);
  inner.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;border:0;display:block;background:transparent';
  var loads = 0;
  var port = null;
  var ready = false;
  function hand() {
    if (!port || !ready || !inner.contentWindow) return;
    var m = {}; m[TAG] = 1; m.kind = 'port';
    inner.contentWindow.postMessage(m, '*', [port]);
    port = null;
  }
  window.addEventListener('message', function (e) {
    var m = e.data;
    if (e.source !== window.parent || !m || m[TAG] !== 1 || m.kind !== 'port' || !e.ports || !e.ports[0]) return;
    if (port || ready === null) return;
    port = e.ports[0];
    hand();
  });
  inner.addEventListener('load', function () {
    loads += 1;
    if (loads === 1) { ready = true; hand(); return; }
    // The page left its first document (a browser let a navigation through,
    // or blocked one and showed an error page): stop it here.
    ready = null;
    inner.remove();
    var m = {}; m[TAG] = 1; m.kind = 'stopped';
    window.parent.postMessage(m, '*');
  });
  inner.srcdoc = window.__vicoaPage;
  document.body.appendChild(inner);
})();`;

/**
 * The shell document around a plugin page (see the top of this file). Its
 * policy is the page's own: a srcdoc page inherits its parent's policy, so a
 * stricter shell would also cut the page off from its declared sites. What
 * matters here is `frame-src 'none'`, which `buildCsp` always includes.
 */
export function buildShell(pageSrcdoc: string, title: string, network: readonly string[] = []): string {
  return [
    '<!doctype html>',
    '<meta charset="utf-8">',
    `<meta http-equiv="Content-Security-Policy" content="${escapeAttr(buildCsp(network))}">`,
    `<title>${title.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c] ?? c)}</title>`,
    '<style>html,body{margin:0;height:100%;background:transparent}</style>',
    '<body>',
    `<script>window.__vicoaPage=${scriptJson(pageSrcdoc)};</script>`,
    `<script>${SHELL_SCRIPT}</script>`,
  ].join('');
}
