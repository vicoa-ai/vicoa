import { describe, it, expect } from 'vitest';
import { bannerViewForStatus, type UpdateStatus } from '@/lib/desktop-updates';

describe('bannerViewForStatus', () => {
  it('stays hidden for idle / checking / not-available', () => {
    const hidden: UpdateStatus[] = [
      { state: 'idle' },
      { state: 'checking' },
      { state: 'not-available' },
    ];
    for (const status of hidden) {
      expect(bannerViewForStatus(status, null, false)).toBeNull();
    }
  });

  it('surfaces an available update', () => {
    expect(bannerViewForStatus({ state: 'available', version: '1.2.0' }, null, false)).toEqual({
      kind: 'available',
      version: '1.2.0',
    });
  });

  it('hides an available update once that version is dismissed', () => {
    expect(bannerViewForStatus({ state: 'available', version: '1.2.0' }, '1.2.0', false)).toBeNull();
  });

  it('re-shows when a newer version arrives after a dismissal', () => {
    expect(bannerViewForStatus({ state: 'available', version: '1.3.0' }, '1.2.0', false)).toEqual({
      kind: 'available',
      version: '1.3.0',
    });
  });

  it('shows download progress and clamps is not needed here (main clamps)', () => {
    expect(
      bannerViewForStatus({ state: 'downloading', percent: 42, version: '1.2.0' }, null, false),
    ).toEqual({ kind: 'downloading', percent: 42 });
  });

  it('shows a downloaded update, dismissible per version', () => {
    expect(bannerViewForStatus({ state: 'downloaded', version: '1.2.0' }, null, false)).toEqual({
      kind: 'downloaded',
      version: '1.2.0',
    });
    expect(bannerViewForStatus({ state: 'downloaded', version: '1.2.0' }, '1.2.0', false)).toBeNull();
  });

  it('only surfaces errors the user triggered (never background checks)', () => {
    const err: UpdateStatus = { state: 'error', message: 'network down' };
    expect(bannerViewForStatus(err, null, false)).toBeNull();
    expect(bannerViewForStatus(err, null, true)).toEqual({ kind: 'error', message: 'network down' });
  });
});
