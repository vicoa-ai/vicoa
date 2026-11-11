import { describe, expect, it } from 'vitest';
import { buildCsp, buildShell, buildSrcdoc, scriptJson } from './srcdoc';
import { themeCss, tokenValue } from './theme';

const init = { pluginId: 'p', surfaceId: 'home', route: '', theme: { mode: 'dark' as const, css: ':root{}' } };

describe('buildCsp', () => {
  it('reaches nothing without declared network', () => {
    const csp = buildCsp([]);
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain("connect-src 'none'");
    expect(csp).toContain("form-action 'none'");
    expect(csp).not.toContain('https:');
  });

  it('adds declared origins to network directives only', () => {
    const csp = buildCsp(['https://cdn.jsdelivr.net']);
    expect(csp).toContain("script-src 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net");
    expect(csp).toContain('connect-src https://cdn.jsdelivr.net');
    expect(csp).toContain('worker-src blob:');
  });
});

describe('buildSrcdoc', () => {
  it('puts the policy and runtime before any plugin markup', () => {
    const html = '<!doctype html><html><head><script>steal()</script></head><body>x</body></html>';
    const doc = buildSrcdoc({ html, init });
    const policy = doc.indexOf('Content-Security-Policy');
    expect(policy).toBeGreaterThan(-1);
    expect(policy).toBeLessThan(doc.indexOf('steal()'));
    expect(doc.indexOf('window.vicoa') === -1 ? doc.indexOf("'vicoa'") : doc.indexOf('window.vicoa')).toBeLessThan(
      doc.indexOf('steal()'),
    );
  });

  it('escapes init data so it cannot close the script', () => {
    expect(scriptJson({ route: '</script><script>x()</script>' })).not.toContain('</script>');
    const doc = buildSrcdoc({ html: '', init: { ...init, route: '</script>' } });
    expect(doc.split('</script>').length).toBe(3); // the two host scripts only
  });
});

describe('theme', () => {
  it('turns HSL triplets into colors', () => {
    expect(tokenValue('primary', ' 222.2 47.4% 11.2% ')).toBe('hsl(222.2 47.4% 11.2%)');
    expect(tokenValue('radius', '0.5rem')).toBe('0.5rem');
    expect(tokenValue('primary', '')).toBeNull();
  });

  it('builds --vicoa-* variables and drops unsafe values', () => {
    const css = themeCss((t) => (t === 'background' ? '0 0% 100%' : t === 'border' ? 'red;}body{x' : ''), 'light');
    expect(css).toContain('--vicoa-background:hsl(0 0% 100%)');
    expect(css).toContain('--vicoa-color-scheme:light');
    expect(css).not.toContain('body{x');
  });
});

describe('buildShell', () => {
  it('frames the page under a policy that forbids frame navigation', () => {
    const page = buildSrcdoc({ html: '<p>hi</p>', network: ['https://cdn.example.com'], init });
    const shell = buildShell(page, 'Dash', ['https://cdn.example.com']);
    // The page's navigations are checked against this document's frame-src.
    expect(shell).toContain("frame-src 'none'");
    // A srcdoc page inherits this policy, so it must allow what the page may use.
    expect(shell).toContain('connect-src https://cdn.example.com');
    expect(shell.indexOf('Content-Security-Policy')).toBeLessThan(shell.indexOf('<script>'));
  });

  it('embeds the page so its markup cannot close the shell script', () => {
    const page = buildSrcdoc({ html: '</script><script>evil()</script>', init });
    const shell = buildShell(page, '</title><b>x', []);
    expect(shell.split('</script>').length).toBe(3); // the shell's two scripts only
    expect(shell).not.toContain('</title><b>');
  });
});
