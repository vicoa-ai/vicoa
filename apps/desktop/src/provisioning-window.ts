/**
 * First-run "downloading the Vicoa agent…" splash for de-bundled builds.
 *
 * A de-bundled installer ships without the frozen daemon; on first launch we
 * fetch it (cli-bootstrap.ts). That download can be tens to a few hundred MB, so
 * without feedback the app would look hung. This is a tiny, self-contained,
 * frameless BrowserWindow — no preload, no renderer server — driven entirely by
 * executeJavaScript so it can appear the instant the download starts, long before
 * the Next standalone server is up.
 */
import { BrowserWindow } from 'electron';

export interface ProvisioningWindow {
  /** `fraction` 0..1, or null for an indeterminate (marquee) bar. */
  setProgress: (fraction: number | null, label?: string) => void;
  /** Switch to an error state (bar hidden, message shown). */
  fail: (message: string) => void;
  close: () => void;
}

const HTML = `<!doctype html><html><head><meta charset="utf-8"><style>
  :root { color-scheme: dark; }
  html, body { margin: 0; height: 100%; }
  body {
    display: flex; flex-direction: column; justify-content: center; gap: 14px;
    padding: 0 26px; box-sizing: border-box;
    background: #0b0b0c; color: #ededed;
    font: 13px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    -webkit-user-select: none; user-select: none;
  }
  .title { font-size: 14px; font-weight: 600; }
  .label { color: #a1a1a1; min-height: 20px; white-space: pre-line; }
  .track { height: 6px; border-radius: 999px; background: rgba(255,255,255,0.12); overflow: hidden; }
  .bar { height: 100%; width: 0%; border-radius: 999px; background: #ededed; transition: width .2s ease; }
  .bar.indeterminate { width: 40%; animation: slide 1.1s ease-in-out infinite; }
  .label.error { color: #f6b73c; }
  @keyframes slide { 0% { margin-left: -40%; } 100% { margin-left: 100%; } }
</style></head><body>
  <div class="title">Setting up Vicoa</div>
  <div id="track" class="track"><div id="bar" class="bar indeterminate"></div></div>
  <div id="label" class="label">Preparing the Vicoa agent…</div>
  <script>
    window.__set = function (pct, label) {
      var bar = document.getElementById('bar');
      var track = document.getElementById('track');
      var lbl = document.getElementById('label');
      track.style.display = 'block';
      lbl.classList.remove('error');
      if (pct === null || pct === undefined) {
        bar.classList.add('indeterminate');
      } else {
        bar.classList.remove('indeterminate');
        bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
      }
      if (label != null && label !== '') lbl.textContent = label;
    };
    window.__fail = function (message) {
      document.getElementById('track').style.display = 'none';
      var lbl = document.getElementById('label');
      lbl.classList.add('error');
      lbl.textContent = message;
    };
  </script>
</body></html>`;

export function showProvisioningWindow(): ProvisioningWindow {
  const win = new BrowserWindow({
    width: 440,
    height: 190,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    frame: false,
    show: false,
    backgroundColor: '#0b0b0c',
    title: 'Vicoa',
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });

  void win.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(HTML)}`);
  win.once('ready-to-show', () => {
    if (!win.isDestroyed()) win.show();
  });

  // executeJavaScript before the document is ready rejects; buffer the latest
  // state and (re)apply it on load so nothing is lost in the race.
  let loaded = false;
  let lastJs = '';
  win.webContents.on('did-finish-load', () => {
    loaded = true;
    if (lastJs.length > 0) void win.webContents.executeJavaScript(lastJs).catch(() => {});
  });

  const run = (js: string): void => {
    lastJs = js;
    if (loaded && !win.isDestroyed()) {
      void win.webContents.executeJavaScript(js).catch(() => {});
    }
  };

  return {
    setProgress(fraction, label) {
      const pct = fraction === null ? 'null' : String(Math.round(fraction * 100));
      run(`window.__set(${pct}, ${JSON.stringify(label ?? '')})`);
    },
    fail(message) {
      run(`window.__fail(${JSON.stringify(message)})`);
    },
    close() {
      if (!win.isDestroyed()) win.close();
    },
  };
}
