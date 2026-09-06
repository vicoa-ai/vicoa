import { describe, expect, test } from 'vitest';
import {
  AGENT_CATALOG_FALLBACK,
  agentById,
  defaultsFor,
  toSpawnMetadata,
} from './agent-catalog';
import { getAgentLogoSrc } from '@/components/dashboard/agent-type-icon';
import { agentSessionHandle, resumeAgentSlug } from './session-resume';

describe('pi / omp catalog entries', () => {
  test('both agents are in the fallback catalog', () => {
    expect(agentById(AGENT_CATALOG_FALLBACK, 'omp')?.label).toBe('Oh My Pi');
    expect(agentById(AGENT_CATALOG_FALLBACK, 'pi')?.label).toBe('Pi');
  });

  test('omp offers the three approval modes; pi offers none', () => {
    // omp maps these to `--approval-mode always-ask|write|yolo`; pi has no
    // approval flag at all, so rendering a mode picker for it would be a lie.
    expect(
      agentById(AGENT_CATALOG_FALLBACK, 'omp')?.permission_modes?.map((m) => m.id)
    ).toEqual(['default', 'acceptEdits', 'bypassPermissions']);
    expect(agentById(AGENT_CATALOG_FALLBACK, 'pi')?.permission_modes).toBeUndefined();
  });

  test('both start on the "let the agent choose" model sentinel', () => {
    // The real per-machine list arrives live from get_available_models; the
    // catalog only needs a defer-to-the-agent default.
    expect(defaultsFor(AGENT_CATALOG_FALLBACK, 'omp').model).toBe('default');
    expect(defaultsFor(AGENT_CATALOG_FALLBACK, 'pi').model).toBe('default');
  });

  test('the thinking picker omits levels that would widen the shared enum', () => {
    // `minimal` (both) and `auto` (omp) are real CLI levels, deliberately not
    // offered so THINKING_EFFORTS stays the same set for every agent.
    const ids = agentById(AGENT_CATALOG_FALLBACK, 'omp')?.thinking_efforts?.map((e) => e.id);
    expect(ids).toEqual(['max', 'xhigh', 'high', 'medium', 'low', 'off']);
  });
});

describe('toSpawnMetadata for the pi family', () => {
  test('sends model, thinking effort and permission mode', () => {
    expect(
      toSpawnMetadata({
        agent: 'omp',
        model: 'anthropic/claude-haiku-4-5',
        thinking_effort: 'high',
        permission_mode: 'acceptEdits',
      })
    ).toEqual({
      model: 'anthropic/claude-haiku-4-5',
      thinking_effort: 'high',
      permission_mode: 'acceptEdits',
    });
  });

  test('does not dual-write claude\'s legacy enable_thinking flag', () => {
    const metadata = toSpawnMetadata({ agent: 'pi', thinking_effort: 'off' });
    expect(metadata).not.toHaveProperty('enable_thinking');
  });

  test('the defer sentinel sends no model, so the agent keeps its own', () => {
    expect(toSpawnMetadata({ agent: 'omp', model: 'default' })).toEqual({});
    expect(toSpawnMetadata({ agent: 'pi', model: 'auto' })).toEqual({});
  });
});

describe('the "pi" substring hazard', () => {
  // Both clients resolve an icon with `name.includes(match)` over an ordered
  // array, and 'copilot' contains 'pi'. A bare 'pi' entry placed before
  // Copilot would silently swallow it.
  test('Copilot still resolves to the Copilot mark', () => {
    expect(getAgentLogoSrc('Copilot')?.alt).toBe('Copilot');
    expect(getAgentLogoSrc('Copilot CLI')?.alt).toBe('Copilot');
  });

  test('Pi and Oh My Pi each resolve to their own mark', () => {
    expect(getAgentLogoSrc('Pi')?.src).toBe('/images/integrations/pi.svg');
    expect(getAgentLogoSrc('Oh My Pi')?.src).toBe('/images/integrations/omp.svg');
    expect(getAgentLogoSrc('omp')?.src).toBe('/images/integrations/omp.svg');
  });

  test('every other agent keeps the mark it had', () => {
    expect(getAgentLogoSrc('Claude Code')?.alt).toBe('Claude');
    expect(getAgentLogoSrc('OpenCode')?.alt).toBe('OpenCode');
    expect(getAgentLogoSrc('Gemini CLI')?.alt).toBe('Gemini');
    expect(getAgentLogoSrc('Kimi CLI')?.alt).toBe('Kimi');
    expect(getAgentLogoSrc('Hermes')?.alt).toBe('Hermes');
  });
});

describe('resume', () => {
  test('the agent slug survives the same substring hazard', () => {
    const byName = (agent_type_name: string) =>
      resumeAgentSlug({ id: 'x', status: 'COMPLETED', agent_type_name });
    expect(byName('Copilot')).toBe('copilot');
    expect(byName('Oh My Pi')).toBe('omp');
    expect(byName('Pi')).toBe('pi');
  });

  test('session_config.agent still wins over the display name', () => {
    expect(
      resumeAgentSlug({
        id: 'x',
        status: 'COMPLETED',
        agent_type_name: 'My Renamed Agent',
        session_config: { agent: 'omp' },
      })
    ).toBe('omp');
  });

  test('the pi conversation handle is carried into the relaunch', () => {
    expect(
      agentSessionHandle({
        id: 'x',
        status: 'COMPLETED',
        instance_metadata: { pi_session_id: '01a06fcb-fe9a-71e6' },
      })
    ).toBe('01a06fcb-fe9a-71e6');
  });
});
