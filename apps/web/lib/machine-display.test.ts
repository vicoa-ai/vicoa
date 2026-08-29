import { describe, expect, it } from 'vitest';
import {
  humanizeDuration,
  lastSeenLabel,
  machineCliVersion,
  machineDisplayName,
  machinePlatformLabel,
} from './machine-display';
import { LIVENESS_ONLINE_THRESHOLD_MS } from './session-liveness';

const NOW = Date.parse('2026-08-12T12:00:00Z');
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString();

describe('machineDisplayName', () => {
  it('prefers display_name, then hostname, then a short id', () => {
    expect(
      machineDisplayName({ display_name: 'Studio', hostname: 'mbp.local', machine_id: 'abcdef123' }),
    ).toBe('Studio');
    expect(
      machineDisplayName({ display_name: '  ', hostname: 'mbp.local', machine_id: 'abcdef123' }),
    ).toBe('mbp.local');
    expect(
      machineDisplayName({ display_name: null, hostname: null, machine_id: 'abcdef123' }),
    ).toBe('Machine abcdef');
  });
});

describe('machinePlatformLabel', () => {
  it('takes the OS family off the platform.platform() string', () => {
    expect(machinePlatformLabel('macOS-15.4-arm64-arm-64bit')).toBe('macOS');
    expect(machinePlatformLabel('Windows-11-10.0.26100-SP0')).toBe('Windows');
    expect(machinePlatformLabel('Linux-5.15.0-91-generic-x86_64-with-glibc2.35')).toBe('Linux');
    expect(machinePlatformLabel(null)).toBeNull();
    expect(machinePlatformLabel('')).toBeNull();
  });
});

describe('humanizeDuration', () => {
  it('picks the largest sensible unit', () => {
    expect(humanizeDuration(45_000)).toBe('45s');
    expect(humanizeDuration(5 * 60_000)).toBe('5m');
    expect(humanizeDuration(3 * 3_600_000)).toBe('3h');
    expect(humanizeDuration(2 * 86_400_000)).toBe('2d');
    // Clamped, never negative — a clock skewed heartbeat shouldn't render "-3s".
    expect(humanizeDuration(-1000)).toBe('0s');
  });
});

describe('lastSeenLabel', () => {
  it('says Online while the heartbeat is fresh', () => {
    expect(lastSeenLabel({ last_heartbeat_at: iso(10_000) }, NOW)).toBe('Online');
  });

  it('flips to a relative label exactly at the liveness threshold', () => {
    expect(
      lastSeenLabel({ last_heartbeat_at: iso(LIVENESS_ONLINE_THRESHOLD_MS) }, NOW),
    ).toBe('Last seen 1m ago');
  });

  it('reports machines that never beat', () => {
    expect(lastSeenLabel({ last_heartbeat_at: null }, NOW)).toBe('Never connected');
    expect(lastSeenLabel({}, NOW)).toBe('Never connected');
    expect(lastSeenLabel({ last_heartbeat_at: 'not-a-date' }, NOW)).toBe('Never connected');
  });
});

describe('machineCliVersion', () => {
  it('reads metadata.cli_version and rejects non-strings', () => {
    expect(machineCliVersion({ metadata: { cli_version: '1.20.0' } })).toBe('1.20.0');
    expect(machineCliVersion({ metadata: { cli_version: 3 } })).toBeNull();
    expect(machineCliVersion({ metadata: null })).toBeNull();
    expect(machineCliVersion({})).toBeNull();
  });
});
