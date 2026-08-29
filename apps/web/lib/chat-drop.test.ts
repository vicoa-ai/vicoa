import { describe, it, expect } from 'vitest';
import { folderPathToMention, folderDisplayName } from './chat-drop';

describe('folderDisplayName', () => {
  it('takes the last segment of an absolute path', () => {
    expect(folderDisplayName('/home/u/app/src/components')).toBe('components');
  });

  it('ignores a trailing slash', () => {
    expect(folderDisplayName('/home/u/app/lib/')).toBe('lib');
  });

  it('handles a relative path', () => {
    expect(folderDisplayName('src/components/')).toBe('components');
  });

  it('falls back to the raw value for the filesystem root', () => {
    expect(folderDisplayName('/')).toBe('/');
  });
});

describe('folderPathToMention', () => {
  it('makes a path inside the project relative, with a trailing slash', () => {
    expect(folderPathToMention('/home/u/app/src/components', '/home/u/app')).toBe(
      'src/components/',
    );
  });

  it('keeps an absolute path when outside the project', () => {
    expect(folderPathToMention('/other/place/assets', '/home/u/app')).toBe(
      '/other/place/assets/',
    );
  });

  it('tolerates a trailing slash on the project root', () => {
    expect(folderPathToMention('/home/u/app/lib', '/home/u/app/')).toBe('lib/');
  });

  it('does not treat a sibling with a shared prefix as inside the project', () => {
    // "/home/u/app-2" must NOT be seen as inside "/home/u/app".
    expect(folderPathToMention('/home/u/app-2/src', '/home/u/app')).toBe(
      '/home/u/app-2/src/',
    );
  });

  it('maps the project root itself to "./"', () => {
    expect(folderPathToMention('/home/u/app', '/home/u/app')).toBe('./');
  });

  it('never double-slashes an already-trailing-slash input', () => {
    expect(folderPathToMention('/home/u/app/src/', '/home/u/app')).toBe('src/');
  });

  it('falls back to the raw path (plus slash) with no project context', () => {
    expect(folderPathToMention('/some/dir')).toBe('/some/dir/');
  });
});
