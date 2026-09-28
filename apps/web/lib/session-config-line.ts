/**
 * The display subset of `session_config` as one "model · effort · mode" line,
 * for anyone watching a session they do not own: the public share viewer and
 * a signed-in grantee's read-only view. Both receive only the display keys
 * (the backend strips the rest), so this never has more to show than that.
 */
export function describeSessionConfig(
  config: Record<string, unknown> | null | undefined,
): string | null {
  if (!config) return null;
  const parts: string[] = [];
  const str = (key: string) =>
    typeof config[key] === 'string' && config[key] ? String(config[key]) : null;
  const model = str('model');
  const effort = str('thinking_effort') ?? str('reasoning_effort');
  const mode = str('permission_mode') ?? str('opencode_mode');
  if (model) parts.push(model);
  if (effort) parts.push(`${effort} effort`);
  if (mode) parts.push(mode);
  return parts.length ? parts.join(' · ') : null;
}
