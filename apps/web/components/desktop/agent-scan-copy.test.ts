import { describe, expect, it } from 'vitest';
import { headingFor } from './agent-scan-step';

describe('agent scan copy', () => {
  it('only names Refresh when that button actually renders', () => {
    // The button is gated on the daemon advertising the RPC. Telling someone to
    // "choose Refresh" when no such button exists is a dead end.
    expect(headingFor('found', 0, true).body).toContain('Refresh');
    expect(headingFor('found', 0, false).body).not.toContain('Refresh');
  });

  it('offers a real alternative when Refresh is unavailable', () => {
    expect(headingFor('found', 0, false).body).toContain('restart Vicoa');
  });

  it('never names the button by its old label', () => {
    // The button reads "Refresh"; copy pointing at "Rescan" would name a
    // control that does not exist on screen.
    for (const canRefresh of [true, false]) {
      expect(headingFor('found', 0, canRefresh).body).not.toMatch(/Rescan/i);
    }
  });

  it('explains that the agents live on the user\'s own machine', () => {
    // The load-bearing idea: Vicoa drives agents you install, it does not bring
    // its own. Without it, a list of eight greyed-out names is meaningless.
    // Asserted on the concept, not on an exact sentence — the wording is the
    // author's to change.
    expect(headingFor('found', 0, true).body).toMatch(/installed on your computer/i);
  });

  it('matches singular and plural to the count', () => {
    expect(headingFor('found', 1, true).body).toMatch(/with this agent/i);
    expect(headingFor('found', 3, true).body).toMatch(/with these agents/i);
  });

  it('uses the product\'s own "agent" wording, not an invented synonym', () => {
    // The sign-in screen sells "Run a team of coding agents" — the scan step
    // must not rename the same concept to "tool" halfway through onboarding.
    expect(headingFor('found', 0, true).title).toBe('Install an AI agent to get started');
    for (const phase of ['scanning', 'found'] as const) {
      for (const count of [0, 2]) {
        expect(headingFor(phase, count, true).body, `${phase}/${count}`).not.toMatch(
          /coding tool|AI tool/i
        );
      }
    }
  });

  it('never blames the user for a daemon that is still booting', () => {
    // The user is sitting AT this computer; "couldn't reach it" reads as broken.
    const { title, body } = headingFor('empty', 0, false);
    expect(`${title} ${body}`).not.toMatch(/couldn't reach|failed|error/i);
    expect(title).toBe('Getting things ready');
  });

  it('anchors "agent" to named products so it never floats as jargon', () => {
    expect(headingFor('scanning', 0, false).body).toContain('Claude Code');
    expect(headingFor('found', 0, false).body).toContain('Claude Code');
  });

  it('gives every state a non-empty title and body', () => {
    for (const phase of ['scanning', 'found', 'empty'] as const) {
      for (const count of [0, 1, 5]) {
        for (const canRefresh of [true, false]) {
          const { title, body } = headingFor(phase, count, canRefresh);
          expect(title.trim(), `${phase}/${count}`).not.toBe('');
          expect(body.trim(), `${phase}/${count}`).not.toBe('');
        }
      }
    }
  });
});
