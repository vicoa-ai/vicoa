import { describe, expect, it } from 'vitest';
import { isDeclaredOrigin } from './plugin-page';

describe('isDeclaredOrigin', () => {
  it('opens declared sites without asking, anything else asks first', () => {
    const network = ['https://cdn.example.com', 'https://api.example.com:8443'];
    expect(isDeclaredOrigin('https://cdn.example.com/lib.js', network)).toBe(true);
    expect(isDeclaredOrigin('https://api.example.com:8443/x', network)).toBe(true);
    expect(isDeclaredOrigin('https://api.example.com/x', network)).toBe(false);
    expect(isDeclaredOrigin('https://evil.example/?data=1', network)).toBe(false);
    expect(isDeclaredOrigin('https://cdn.example.com.evil.example/', network)).toBe(false);
    expect(isDeclaredOrigin('not a url', network)).toBe(false);
  });
});
