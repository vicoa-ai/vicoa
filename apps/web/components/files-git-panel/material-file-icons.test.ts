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

  test('resolves the documents an agent hands back that Vicoa cannot preview', () => {
    // Office + PDF come from the theme's own extension map, so the variants
    // (xls/xlsm/csv → table, doc → word, ppt → powerpoint) ride along.
    const table = getFileIconSvg('report.xlsx');
    expect(table).toContain('#8bc34a');
    expect(getFileIconSvg('legacy.xls')).toBe(table);
    expect(getFileIconSvg('export.csv')).toBe(table);
    expect(getFileIconSvg('brief.docx')).toBe(getFileIconSvg('brief.doc'));
    expect(getFileIconSvg('deck.pptx')).toBe(getFileIconSvg('deck.ppt'));
    expect(getFileIconSvg('paper.pdf')).not.toBe(getFileIconSvg('LICENSE'));
    expect(getFileIconSvg('bundle.tar.gz')).toBe(getFileIconSvg('bundle.zip'));
    expect(getFileIconSvg('analysis.ipynb')).not.toBe(getFileIconSvg('LICENSE'));
  });

  test('dot-files resolve on their bare name', () => {
    expect(getFileIconSvg('.zshrc')).toBe(getFileIconSvg('setup.sh'));
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
