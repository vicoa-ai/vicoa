/**
 * The `window.vicoa` runtime the host injects into every plugin page, as plain
 * JavaScript source. It is a string (not a bundled function) so no build step
 * can rewrite it: it runs as-is inside the sandboxed iframe, before the
 * plugin's own scripts.
 *
 * It holds no privileges of its own. Every call becomes a request the host
 * checks against the plugin's declared permissions. Requests travel over a
 * private MessagePort the host hands this runtime once the page has loaded:
 * page code never sees the port (the hand-over listener runs first, in the
 * capture phase, and stops the event), so it can't send raw messages to the
 * host or read the host's replies to someone else, and a document that ever
 * replaced this one in the frame would have no port at all.
 *
 * Keep it dependency-free ES2020 and free of backticks and `${` sequences.
 */

export const PLUGIN_CLIENT_SCRIPT = String.raw`(function () {
  'use strict';
  var TAG = '__vicoa';
  var init = window.__vicoaInit || {};
  // Native functions, taken before any page script can replace them.
  var portPost = MessagePort.prototype.postMessage;
  var portListen = MessagePort.prototype.addEventListener;
  var portStart = MessagePort.prototype.start;
  var stopEvent = Event.prototype.stopImmediatePropagation;
  var port = null;
  var outbox = [];
  var seq = 0;
  var pending = new Map();
  var listeners = new Map();
  var watches = new Map();
  var route = typeof init.route === 'string' ? init.route : '';
  var logQueue = [];
  var logTimer = null;

  function post(message) {
    message[TAG] = 1;
    if (port) portPost.call(port, message);
    else outbox.push(message);
  }

  function makeError(body) {
    var err = new Error((body && body.message) || 'Vicoa request failed');
    err.code = (body && body.code) || 'failed';
    return err;
  }

  function call(method, params) {
    return new Promise(function (resolve, reject) {
      seq += 1;
      var id = seq;
      pending.set(id, { resolve: resolve, reject: reject });
      try {
        post({ kind: 'req', id: id, method: method, params: params === undefined ? null : params });
      } catch (e) {
        pending.delete(id);
        reject(makeError({ code: 'invalid_params', message: 'Arguments must be plain JSON data' }));
      }
    });
  }

  function emit(name, payload) {
    var set = listeners.get(name);
    if (!set) return;
    set.forEach(function (cb) {
      try { cb(payload); } catch (e) { report(e); }
    });
  }

  function on(name, cb) {
    if (typeof cb !== 'function') throw new TypeError('vicoa.events.on needs a callback');
    if (!listeners.has(name)) listeners.set(name, new Set());
    listeners.get(name).add(cb);
    return function () { listeners.get(name).delete(cb); };
  }

  function applyTheme(theme) {
    if (!theme) return;
    var el = document.getElementById('vicoa-theme');
    if (el && typeof theme.css === 'string') el.textContent = theme.css;
    if (theme.mode) {
      document.documentElement.setAttribute('data-vicoa-theme', theme.mode);
      document.documentElement.style.colorScheme = theme.mode;
    }
  }

  function onHostMessage(event) {
    var m = event.data;
    if (!m || m[TAG] !== 1) return;
    if (m.kind === 'res') {
      var p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      if (m.ok) p.resolve(m.result); else p.reject(makeError(m.error));
      return;
    }
    if (m.kind !== 'event') return;
    if (m.name === 'watch') {
      var w = m.payload && watches.get(m.payload.watchId);
      if (w) { try { w(m.payload.data); } catch (e) { report(e); } }
      return;
    }
    if (m.name === 'theme') applyTheme(m.payload);
    if (m.name === 'route') route = (m.payload && m.payload.path) || '';
    emit(m.name, m.payload);
  }

  // The host's port arrives once, from the frame around this page.
  window.addEventListener('message', function (event) {
    var m = event.data;
    if (port || event.source !== window.parent || !m || m[TAG] !== 1 || m.kind !== 'port') return;
    if (!event.ports || !event.ports[0]) return;
    stopEvent.call(event);
    port = event.ports[0];
    portListen.call(port, 'message', onHostMessage);
    portStart.call(port);
    var queued = outbox.splice(0);
    for (var i = 0; i < queued.length; i++) {
      try { portPost.call(port, queued[i]); } catch (e) { var p = pending.get(queued[i].id); if (p) { pending.delete(queued[i].id); p.reject(makeError({ code: 'invalid_params', message: 'Arguments must be plain JSON data' })); } }
    }
  }, true);

  function watch(method, filter, cb) {
    if (typeof cb !== 'function') return Promise.reject(new TypeError('watch needs a callback'));
    return call(method, filter || {}).then(function (res) {
      watches.set(res.watchId, cb);
      try { cb(res.data); } catch (e) { report(e); }
      return function stop() {
        watches.delete(res.watchId);
        call('watch.stop', { watchId: res.watchId }).catch(function () {});
      };
    });
  }

  function flushLogs() {
    logTimer = null;
    if (!logQueue.length) return;
    var entries = logQueue.splice(0, 50);
    call('log.write', { entries: entries }).catch(function () {});
    if (logQueue.length) logTimer = setTimeout(flushLogs, 1000);
  }

  function stringify(args) {
    return Array.prototype.map.call(args, function (a) {
      if (a instanceof Error) return a.stack || a.message;
      if (typeof a === 'string') return a;
      try { return JSON.stringify(a); } catch (e) { return String(a); }
    }).join(' ');
  }

  function log(level, args) {
    if (logQueue.length >= 200) return;
    logQueue.push({ level: level, message: stringify(args).slice(0, 2000), at: new Date().toISOString() });
    if (!logTimer) logTimer = setTimeout(flushLogs, 500);
  }

  function report(e) { log('error', [e]); }

  window.addEventListener('error', function (e) {
    log('error', [(e.error && e.error.stack) || e.message || 'error']);
  });
  window.addEventListener('unhandledrejection', function (e) {
    log('error', ['Unhandled rejection:', e.reason]);
  });

  var vicoa = {
    apiVersion: 1,
    context: { get: function () { return call('context.get'); } },
    projects: { list: function () { return call('projects.list'); } },
    tasks: {
      list: function (filter) { return call('tasks.list', filter || {}); },
      get: function (id) { return call('tasks.get', { id: id }); },
      comments: function (id) { return call('tasks.comments', { id: id }); },
      watch: function (filter, cb) { return watch('tasks.watch', filter, cb); },
      comment: function (id, body) { return call('tasks.comment', { id: id, body: body }); },
      update: function (id, patch) { return call('tasks.update', { id: id, patch: patch }); },
      create: function (data) { return call('tasks.create', data || {}); }
    },
    sessions: {
      list: function (filter) { return call('sessions.list', filter || {}); },
      get: function (id) { return call('sessions.get', { id: id }); },
      messages: function (id, opts) { return call('sessions.messages', Object.assign({ id: id }, opts || {})); },
      watch: function (filter, cb) { return watch('sessions.watch', filter, cb); },
      send: function (id, text) { return call('sessions.send', { id: id, text: text }); },
      start: function (opts) { return call('sessions.start', opts || {}); }
    },
    automations: {
      list: function (filter) { return call('automations.list', filter || {}); },
      runs: function (id, opts) { return call('automations.runs', Object.assign({ id: id }, opts || {})); },
      run: function (id) { return call('automations.run', { id: id }); }
    },
    files: {
      read: function (path) {
        return call('files.read', { path: path }).then(function (r) { return r.content; });
      },
      readJson: function (path) {
        return call('files.read', { path: path }).then(function (r) { return JSON.parse(r.content); });
      }
    },
    settings: {
      get: function () { return call('settings.get'); },
      set: function (patch) { return call('settings.set', { patch: patch }); },
      onChange: function (cb) { return on('settings', cb); }
    },
    open: {
      task: function (id, opts) { return call('open.task', Object.assign({ id: id }, opts || {})); },
      session: function (id, opts) { return call('open.session', Object.assign({ id: id }, opts || {})); },
      newSession: function (prefill) { return call('open.newSession', prefill || {}); },
      url: function (url) { return call('open.url', { url: url }); },
      page: function (surfaceId, params) { return call('open.page', { surfaceId: surfaceId, params: params || {} }); }
    },
    ui: {
      setHeader: function (header) { return call('ui.setHeader', header || {}); },
      toast: function (text, opts) { return call('ui.toast', Object.assign({ text: text }, opts || {})); }
    },
    route: {
      get: function () { return route; },
      set: function (path, opts) {
        route = String(path || '');
        return call('route.set', { path: route, replace: !!(opts && opts.replace) });
      },
      onChange: function (cb) { return on('route', function (p) { cb(p.path); }); }
    },
    events: { on: on },
    log: {
      info: function () { log('info', arguments); },
      warn: function () { log('warn', arguments); },
      error: function () { log('error', arguments); }
    },
    backend: { call: function (name, input) { return call('backend.call', { name: name, input: input }); } }
  };

  Object.defineProperty(window, 'vicoa', { value: Object.freeze(vicoa), writable: false, configurable: false });
  applyTheme(init.theme);
})();`;
