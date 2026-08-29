let cachedConfig: { clientId: string } | null | undefined;

export function getAppleOAuthConfig() {
  if (cachedConfig !== undefined) {
    return cachedConfig;
  }

  const clientId = process.env.NEXT_PUBLIC_APPLE_CLIENT_ID;

  if (!clientId) {
    cachedConfig = null;
    return cachedConfig;
  }

  cachedConfig = { clientId };
  return cachedConfig;
}
