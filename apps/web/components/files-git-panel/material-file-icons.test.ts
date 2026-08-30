import { describe, test, expect } from 'vitest';
import { getFileIconSvg } from './material-file-icons';

describe('getFileIconSvg', () => {
  test('resolves TypeScript to the material typescript color', () => {
    expect(getFileIconSvg('index.ts')).toContain('#0288d1');
    expect(getFileIconSvg('component.tsx')).toContain('#0288d1');
  });

  test('resolves JavaScript to the amber icon', () => {
    expect(getFileIconSvg('app.js')).toContain('#ffca28');
  });

  test('is case-insensitive on the extension', () => {
    expect(getFileIconSvg('README.MD')).toBe(getFileIconSvg('readme.md'));
  });

  test('unknown and extensionless names fall back to the default icon', () => {
    const fallback = getFileIconSvg('LICENSE');
    expect(getFileIconSvg('data.zzzznope')).toBe(fallback);
    expect(fallback).toContain('#90a4ae');
  });
});
