import { Suspense } from 'react';
import type { Metadata } from 'next';
import { SupabaseLogin } from '../supabase-login';
import { BuiltinLogin } from '../builtin-login';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { getGoogleOAuthConfig } from '@/lib/auth/google-oauth';
import { getAppleOAuthConfig } from '@/lib/auth/apple-oauth';
import { redirectAuthenticatedUser } from '../redirect-authenticated-user';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/sign-in', {
  title: 'Sign In | Vicoa',
  description: 'Sign in to Vicoa to run and manage your AI coding agents from any device.',
});

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect?: string }>;
}) {
  const { redirect } = await searchParams;
  await redirectAuthenticatedUser(redirect);

  // A self-hosted deployment on the built-in provider has no social sign-in
  // and no Supabase client to talk to — it gets its own small email/password
  // form instead.
  if (isBuiltinAuth()) {
    return (
      <Suspense>
        <BuiltinLogin mode="signin" />
      </Suspense>
    );
  }

  const googleConfig = getGoogleOAuthConfig();
  const appleConfig = getAppleOAuthConfig();
  return (
    <Suspense>
      <SupabaseLogin
        mode="signin"
        googleClientId={googleConfig?.clientId}
        appleClientId={appleConfig?.clientId}
      />
    </Suspense>
  );
}
