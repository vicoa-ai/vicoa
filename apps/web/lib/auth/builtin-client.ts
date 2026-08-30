'use client';

/**
 * Browser-side session handling for the built-in auth provider.
 *
 * The token lives in a plain cookie rather than localStorage so that the Next
 * middleware and server components can read it on the very first request —
 * which is what keeps route protection working without a round-trip. It is
 * deliberately not httpOnly: the same token is the bearer for direct
 * backend/WebSocket calls from the browser, exactly as the Supabase session is.
 */

import {
  BUILTIN_SESSION_COOKIE,
  decodeBuiltinToken,
  readSessionCookie,
  type BuiltinClaims,
} from './auth-provider';
import { getCloudApiBase } from '@/lib/runtime-config';

export type BuiltinSession = {
  access_token: string;
  expires_at: string;
  user: { id: string; email: string; display_name: string | null };
};

export function getBuiltinToken(): string | null {
  if (typeof document === 'undefined') return null;
  const token = readSessionCookie(document.cookie);
  // An expired token is worse than none: it would be sent, rejected, and read
  // as "the server is broken" rather than "sign in again".
  return decodeBuiltinToken(token) ? token : null;
}

export function getBuiltinClaims(): BuiltinClaims | null {
  return decodeBuiltinToken(getBuiltinToken());
}

export function setBuiltinSession(session: BuiltinSession): void {
  const expires = new Date(session.expires_at);
  const maxAge = Math.max(
    0,
    Math.floor((expires.getTime() - Date.now()) / 1000)
  );
  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie =
    `${BUILTIN_SESSION_COOKIE}=${encodeURIComponent(session.access_token)}` +
    `; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

export function clearBuiltinSession(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${BUILTIN_SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${getCloudApiBase()}/api/v1/auth/builtin${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.detail || 'Something went wrong. Please try again.');
  }
  return payload as T;
}

export async function builtinSignIn(
  email: string,
  password: string
): Promise<BuiltinSession> {
  const session = await post<BuiltinSession>('/sign-in', { email, password });
  setBuiltinSession(session);
  return session;
}

export async function builtinSignUp(
  email: string,
  password: string,
  displayName?: string
): Promise<BuiltinSession> {
  const session = await post<BuiltinSession>('/sign-up', {
    email,
    password,
    display_name: displayName || null,
  });
  setBuiltinSession(session);
  return session;
}

export async function builtinForgotPassword(email: string): Promise<string> {
  const result = await post<{ message: string }>('/forgot-password', { email });
  return result.message;
}

export async function builtinResetPassword(
  email: string,
  code: string,
  newPassword: string
): Promise<void> {
  await post('/reset-password', { email, code, new_password: newPassword });
}
