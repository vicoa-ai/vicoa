/**
 * The shape of ~/.vicoa/credentials.json, shared with the `vicoa` CLI and the
 * daemon this shell supervises. A TypeScript mirror of
 * backend/src/vicoa/credentials_state.py; keep the two in step, because the
 * daemon reads what this writes.
 *
 * The file holds one key per deployment, keyed by the normalized agent-server
 * base URL: `{"keys": {"https://agents.vicoa.ai": {"write_key": "…"}}}`.
 * Legacy files hold a single top-level `write_key`, which belongs to whichever
 * server the reader targets; the first save moves it into `keys` and strips it.
 * Once `keys` exists a top-level `write_key` is ignored, exactly as the daemon
 * ignores it.
 *
 * Pure functions over the parsed file, so `check.ts` can exercise them without
 * Electron or a real home directory.
 */

export type CredentialsFile = Record<string, unknown>;

type KeyEntries = Record<string, Record<string, unknown>>;

const WRITE_KEY = 'write_key';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Canonical lookup key for a base URL (`normalize_base_url` in machine_state.py). */
export function normalizeBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '').toLowerCase();
}

/** The `keys` map, reading a legacy flat file as the entry for `baseUrl` (`_get_keys_section`). */
function keyEntries(state: CredentialsFile, baseUrl: string): KeyEntries {
  const keys = state['keys'];
  if (isRecord(keys)) {
    const entries: KeyEntries = {};
    for (const [url, entry] of Object.entries(keys)) {
      if (isRecord(entry)) entries[url] = entry;
    }
    return entries;
  }
  const legacy = state[WRITE_KEY];
  if (typeof legacy === 'string' && legacy !== '') {
    return { [normalizeBaseUrl(baseUrl)]: { [WRITE_KEY]: legacy } };
  }
  return {};
}

/** `state` with `keys` written back and the legacy flat key stripped (`_write_keys_section`). */
function withKeyEntries(state: CredentialsFile, keys: KeyEntries): CredentialsFile {
  const next: CredentialsFile = { ...state, keys };
  delete next[WRITE_KEY];
  return next;
}

/** The stored key for `baseUrl`, or null (`load_api_key`). */
export function getWriteKey(state: CredentialsFile, baseUrl: string): string | null {
  const token = keyEntries(state, baseUrl)[normalizeBaseUrl(baseUrl)]?.[WRITE_KEY];
  return typeof token === 'string' && token !== '' ? token : null;
}

/** `state` with `key` stored for `baseUrl`; other deployments' keys survive (`save_api_key`). */
export function withWriteKey(state: CredentialsFile, baseUrl: string, key: string): CredentialsFile {
  const keys = keyEntries(state, baseUrl);
  keys[normalizeBaseUrl(baseUrl)] = { [WRITE_KEY]: key };
  return withKeyEntries(state, keys);
}

/**
 * `state` without the entry for `baseUrl`; other deployments' keys survive
 * (`clear_api_key`). Null when there was no entry, so the caller can skip the write.
 */
export function withoutWriteKey(state: CredentialsFile, baseUrl: string): CredentialsFile | null {
  const keys = keyEntries(state, baseUrl);
  const url = normalizeBaseUrl(baseUrl);
  if (!(url in keys)) return null;
  delete keys[url];
  return withKeyEntries(state, keys);
}
