let cachedConfig: { clientId: string } | null | undefined;

export function getGoogleOAuthConfig() {
  if (cachedConfig !== undefined) {
    return cachedConfig;
  }

  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  if (!clientId) {
    cachedConfig = null;
    return cachedConfig;
  }

  cachedConfig = { clientId };
  return cachedConfig;
}
