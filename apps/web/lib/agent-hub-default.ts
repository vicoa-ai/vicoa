export const AGENT_HUB_DEFAULT_THRESHOLD = 3;
export const AGENT_HUB_DEFAULT_FLAG = 'vicoa-agent-hub-default';
const ONE_YEAR_IN_SECONDS = 60 * 60 * 24 * 365;

export function hasAgentHubDefaultCookie(cookieHeader: string | undefined): boolean {
  if (!cookieHeader) {
    return false;
  }

  return cookieHeader
    .split(';')
    .map((part) => part.trim())
    .includes(`${AGENT_HUB_DEFAULT_FLAG}=1`);
}

export function hasAgentHubDefaultCookieStoreFlag(cookieStore: {
  get: (name: string) => { value?: string } | undefined;
}): boolean {
  return cookieStore.get(AGENT_HUB_DEFAULT_FLAG)?.value === '1';
}

export function persistAgentHubDefaultFlag() {
  if (typeof document === 'undefined') {
    return;
  }

  const hasCookieFlag = hasAgentHubDefaultCookie(document.cookie);
  let hasLocalStorageFlag = false;

  try {
    hasLocalStorageFlag = window.localStorage.getItem(AGENT_HUB_DEFAULT_FLAG) === '1';
  } catch {
    hasLocalStorageFlag = false;
  }

  if (hasCookieFlag && hasLocalStorageFlag) {
    return;
  }

  try {
    if (!hasLocalStorageFlag) {
      window.localStorage.setItem(AGENT_HUB_DEFAULT_FLAG, '1');
    }
  } catch (error) {
    console.warn('Failed to persist agent hub default flag:', error);
  }

  if (!hasCookieFlag) {
    document.cookie = `${AGENT_HUB_DEFAULT_FLAG}=1; path=/; max-age=${ONE_YEAR_IN_SECONDS}; samesite=lax`;
  }
}
