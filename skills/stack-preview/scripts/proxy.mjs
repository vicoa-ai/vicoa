#!/usr/bin/env node
// One origin for the whole preview stack, so a single tunnel can serve it.
//
//   /ws          -> agent-facing server (realtime WebSocket)
//   /api/v1/...  -> user-facing backend REST API
//   anything else -> web dashboard (pages, assets, Next route handlers, HMR)
//
// The web app has its own Next route handlers under /api/ (attachments,
// avatars, ...) but none under /api/v1/, so the split is unambiguous. Because
// the browser sees a single origin there is no CORS preflight, and an ngrok
// interstitial cookie covers the API calls too.
//
// Zero dependencies on purpose: it runs from the skill folder, outside any
// node_modules.
//
//   node proxy.mjs <listen-port> <web-port> <backend-port> <server-port>

import http from 'node:http';
import net from 'node:net';

const [listenPort, webPort, backendPort, serverPort] = process.argv
  .slice(2)
  .map((value) => Number.parseInt(value, 10));

if (![listenPort, webPort, backendPort, serverPort].every(Number.isInteger)) {
  console.error('usage: proxy.mjs <listen-port> <web-port> <backend-port> <server-port>');
  process.exit(2);
}

const HOST = '127.0.0.1';

/** @param {string | undefined} url */
function route(url) {
  const path = (url ?? '/').split('?')[0];
  if (path === '/ws') return { name: 'server', port: serverPort };
  if (path === '/api/v1' || path.startsWith('/api/v1/')) {
    return { name: 'backend', port: backendPort };
  }
  return { name: 'web', port: webPort };
}

const proxy = http.createServer((req, res) => {
  const target = route(req.url);
  const upstream = http.request(
    {
      host: HOST,
      port: target.port,
      method: req.method,
      path: req.url,
      // Host stays the public hostname: Next dev and the backend both see the
      // origin the browser used, exactly as with a direct tunnel.
      headers: req.headers,
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.statusMessage, [
        ...upstreamRes.rawHeaders,
        'x-vicoa-preview',
        target.name,
      ]);
      upstreamRes.pipe(res);
    },
  );
  upstream.on('error', (error) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    res.writeHead(502, { 'content-type': 'text/plain', 'x-vicoa-preview': target.name });
    res.end(`stack-preview: ${target.name} on 127.0.0.1:${target.port} is not answering (${error.message})\n`);
  });
  req.pipe(upstream);
});

// WebSocket (and Next's HMR socket): replay the request head to the upstream
// and splice the two sockets together.
proxy.on('upgrade', (req, socket, head) => {
  const target = route(req.url);
  const upstream = net.connect(target.port, HOST, () => {
    let raw = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      raw += `${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}\r\n`;
    }
    upstream.write(`${raw}\r\n`);
    if (head.length > 0) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on('error', () => socket.destroy());
  socket.on('error', () => upstream.destroy());
});

// Long-lived responses (SSE, slow uploads) must not be cut by Node's defaults.
proxy.requestTimeout = 0;

proxy.listen(listenPort, HOST, () => {
  console.log(
    `stack-preview proxy on http://${HOST}:${listenPort} -> web :${webPort}, backend :${backendPort}, server :${serverPort}`,
  );
});
