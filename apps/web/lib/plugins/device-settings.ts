/**
 * Plugin settings declared with `scope: "device"`: kept by this browser, not
 * by the plugin's machine. Shared by the page bridge and Settings › Plugins so
 * both read and write the same values.
 */

import type { DeviceSettingsStore } from './bridge/host';

const keyFor = (pluginId: string) => `vicoa.plugin-device-settings.${pluginId}`;

export function deviceSettingsStore(pluginId: string): DeviceSettingsStore {
  const key = keyFor(pluginId);
  const read = (): Record<string, unknown> => {
    try {
      const raw = window.localStorage.getItem(key);
      const parsed: unknown = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  };
  return {
    get: read,
    set(patch) {
      try {
        window.localStorage.setItem(key, JSON.stringify({ ...read(), ...patch }));
      } catch {
        // Storage full or blocked: the value lives until reload.
      }
    },
  };
}
