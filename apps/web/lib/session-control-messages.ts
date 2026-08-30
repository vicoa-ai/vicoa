import { MessageResponse } from '@/lib/backend-api';
import type { PermissionModeValue, OpencodeAgentModeValue } from '@/components/chat-input';
import { CONTROL_COMMAND_JSON_REGEX, isControlEnvelope, parseControlCommand } from '@/lib/control-messages';

// Parsing + building of the in-band `{type:'control', ...}` command messages the
// chat uses to drive permission mode, agent mode, thinking, model, and effort.
// Extracted from the agent instance page so the page and its message-rendering
// components can share one implementation.

const permissionModeMatchers: { value: PermissionModeValue; keywords: string[] }[] = [
  { value: 'bypassPermissions', keywords: ['bypass permissions', 'bypass-permissions', 'bypass_permissions', 'bypasspermissions', 'yolo mode', 'yolo'] },
  { value: 'plan', keywords: ['plan mode', 'plan'] },
  { value: 'acceptEdits', keywords: ['accept edits', 'accept-edits', 'acceptedits', 'auto accept'] },
  { value: 'auto', keywords: ['auto mode', 'auto'] },
  { value: 'default', keywords: ['default', 'manual approval', 'shortcuts'] },
];

const permissionModeLabels: Record<PermissionModeValue, string> = {
  default: 'default mode',
  plan: 'plan mode',
  acceptEdits: 'accept edits',
  bypassPermissions: 'bypass permissions',
  auto: 'auto mode',
};

const PERMISSION_MODE_COMMAND_REGEX = /(?:,?\s*)permission-mode(?:=set)?[:=\-][a-z-]+/gi;

type ControlSetting = 'permission_mode' | 'thinking' | 'interrupt' | 'agent_type' | 'model' | 'effort';

export function shouldHideControlMessage(message: MessageResponse): boolean {
  const senderType = message.sender_type?.toLowerCase() ?? '';
  const isUser = senderType === 'user' || senderType === 'human';
  if (!isUser) {
    return false;
  }

  const content = message.content || '';
  // Only hide messages that ARE a control directive. A user message that merely
  // quotes/pastes control JSON amid prose must stay in the transcript.
  if (!isControlEnvelope(content)) return false;
  const matches = content.match(CONTROL_COMMAND_JSON_REGEX) || [];
  for (const match of matches) {
    const parsed = parseControlCommand(match);
    if (parsed?.setting === 'ask_user_question') {
      return true;
    }
  }
  return false;
}

export function extractControlSettingValue(content: string, setting: ControlSetting): string | null {
  if (!content) return null;
  // Don't derive settings from control JSON a user merely pasted into prose.
  if (!isControlEnvelope(content)) return null;
  const matches = content.match(CONTROL_COMMAND_JSON_REGEX) || [];
  for (const match of matches) {
    const parsed = parseControlCommand(match);
    if (parsed?.setting === setting && typeof parsed.value === 'string') {
      return parsed.value;
    }
  }
  return null;
}

export function getPermissionModeLabel(mode: PermissionModeValue): string {
  return permissionModeLabels[mode] || mode;
}

function buildControlMessage(setting: ControlSetting, value: string): string {
  return JSON.stringify({ type: 'control', setting, value });
}

export function buildPermissionModeRequestMessage(mode: PermissionModeValue): string {
  const label = getPermissionModeLabel(mode);
  const humanReadable = `Change the permission mode to ${label}.`;
  return `${humanReadable} ${buildControlMessage('permission_mode', mode)}`;
}

export function buildAgentTypeControlMessage(mode: OpencodeAgentModeValue): string {
  const humanReadable = `Switch agent to ${mode}.`;
  return `${humanReadable} ${buildControlMessage('agent_type', mode)}`;
}

export function buildThinkingControlMessage(enabled: boolean): string {
  const humanReadable = enabled ? 'Turn thinking on.' : 'Turn thinking off.';
  return `${humanReadable} ${buildControlMessage('thinking', enabled ? 'on' : 'off')}`;
}

export function buildInterruptControlMessage(): string {
  const humanReadable = 'Stop current task.';
  return `${humanReadable} ${JSON.stringify({ type: 'control', setting: 'interrupt' })}`;
}

export function stripPermissionModeCommandTokens(content: string): string {
  if (!content) {
    return '';
  }
  let cleaned = content.replace(PERMISSION_MODE_COMMAND_REGEX, '');
  // Only strip the control token when the message IS a control directive, so a
  // user message that quotes control JSON in prose keeps its text intact.
  if (isControlEnvelope(content)) {
    cleaned = cleaned.replace(CONTROL_COMMAND_JSON_REGEX, '');
  }
  return cleaned
    .replace(/[ \t]{2,}/g, ' ')  // Only collapse multiple spaces/tabs, not newlines
    .trim();
}

export function extractPermissionModeFromMessage(content: string): PermissionModeValue | null {
  const controlValue = extractControlSettingValue(content, 'permission_mode');
  if (controlValue) {
    if (controlValue === 'bypass_permissions' || controlValue === 'bypass-permissions') {
      return 'bypassPermissions';
    }
    if (['default', 'plan', 'acceptEdits', 'bypassPermissions', 'auto'].includes(controlValue)) {
      return controlValue as PermissionModeValue;
    }
  }

  const normalized = content?.toLowerCase().trim() ?? '';
  if (!normalized.startsWith('permission mode')) {
    return null;
  }

  const [, afterPrefix = ''] = normalized.split(':', 2);
  const searchBlock = (afterPrefix || normalized).trim();

  for (const matcher of permissionModeMatchers) {
    if (matcher.keywords.some((keyword) => searchBlock.includes(keyword))) {
      return matcher.value;
    }
  }

  return null;
}

export function findLatestPermissionMode(messages: MessageResponse[]): PermissionModeValue | null {
  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const detected = extractPermissionModeFromMessage(messages[idx].content);
    if (detected) {
      return detected;
    }
  }
  return null;
}

export function findInitialPermissionMode(messages: MessageResponse[]): PermissionModeValue | null {
  for (let idx = 0; idx < messages.length; idx += 1) {
    const detected = extractPermissionModeFromMessage(messages[idx].content);
    if (detected) {
      return detected;
    }
  }
  return null;
}

export function extractAgentModeFromMessage(content: string): OpencodeAgentModeValue | null {
  const controlValue = extractControlSettingValue(content, 'agent_type');
  if (controlValue && ['build', 'plan'].includes(controlValue.toLowerCase())) {
    return controlValue.toLowerCase() as OpencodeAgentModeValue;
  }
  return null;
}

export function findLatestAgentMode(messages: MessageResponse[]): OpencodeAgentModeValue | null {
  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const detected = extractAgentModeFromMessage(messages[idx].content);
    if (detected) {
      return detected;
    }
  }
  return null;
}

export function extractThinkingSettingFromMessage(content: string): boolean | null {
  const controlValue = extractControlSettingValue(content, 'thinking');
  if (controlValue === 'on') return true;
  if (controlValue === 'off') return false;
  return null;
}

export function findLatestThinkingSetting(messages: MessageResponse[]): boolean | null {
  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const detected = extractThinkingSettingFromMessage(messages[idx].content);
    if (detected !== null) {
      return detected;
    }
  }
  return null;
}

export function findLatestModel(messages: MessageResponse[]): string | null {
  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const value = extractControlSettingValue(messages[idx].content, 'model');
    if (value) return value;
  }
  return null;
}

export function findLatestEffort(messages: MessageResponse[]): string | null {
  for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
    const value = extractControlSettingValue(messages[idx].content, 'effort');
    if (value) return value;
  }
  return null;
}
