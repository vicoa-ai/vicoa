'use client';

/**
 * Sign-in / sign-up for a self-hosted deployment running the backend's built-in
 * auth provider (`AUTH_PROVIDER=builtin`).
 *
 * A deliberately small counterpart to `supabase-login.tsx`: no social
 * providers, no server actions, no desktop OAuth handshake — just email and
 * password against `/api/v1/auth/builtin/*`, plus the emailed-code password
 * reset that provider supports. Rendered instead of `SupabaseLogin` when
 * `NEXT_PUBLIC_AUTH_PROVIDER=builtin`.
 */

import Link from 'next/link';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  builtinForgotPassword,
  builtinResetPassword,
  builtinSignIn,
  builtinSignUp,
} from '@/lib/auth/builtin-client';

type View = 'credentials' | 'forgot' | 'reset';

const FIELD_CLASS =
  'w-full max-w-xs px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none';
const BUTTON_CLASS =
  'w-full max-w-xs flex justify-center items-center py-5 px-4 border border-input rounded-lg shadow-sm text-sm font-medium text-foreground bg-background hover:bg-accent focus:outline-none focus:ring-[1px] focus:ring-offset-0 focus:ring-foreground';

export function BuiltinLogin({ mode = 'signin' }: { mode?: 'signin' | 'signup' }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect');

  const [view, setView] = useState<View>('credentials');
  const [email, setEmail] = useState(searchParams.get('email') ?? '');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const run = async (action: () => Promise<void>) => {
    setPending(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setPending(false);
    }
  };

  const submitCredentials = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      if (mode === 'signup') {
        await builtinSignUp(email, password);
      } else {
        await builtinSignIn(email, password);
      }
      // A full navigation, not router.push: the session cookie was just set
      // client-side and the middleware has to see it on the next request.
      window.location.href = redirect || '/dashboard';
    });
  };

  const submitForgot = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const message = await builtinForgotPassword(email);
      setNotice(message);
      setView('reset');
    });
  };

  const submitReset = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await builtinResetPassword(email, code, password);
      setNotice('Password updated. You can sign in now.');
      setPassword('');
      setCode('');
      setView('credentials');
    });
  };

  return (
    <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Image
            src="/images/vicoa-light.webp"
            alt="Vibe Code Anywhere Logo"
            width={0}
            height={0}
            sizes="100vw"
            className="h-12 w-auto opacity-90"
          />
        </div>
        <h2 className="mt-6 text-center text-3xl text-foreground">
          {view !== 'credentials'
            ? 'Reset your password'
            : mode === 'signin'
              ? 'Sign in to Vicoa'
              : 'Welcome to Vicoa'}
        </h2>
        <p className="mt-2 text-center text-base text-muted-foreground">
          Run a team of coding agents. Anywhere. Any Device.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        {view === 'credentials' && (
          <form className="space-y-6" onSubmit={submitCredentials}>
            <div className="flex flex-col items-center">
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                maxLength={100}
                className={FIELD_CLASS}
                placeholder="Enter your email"
              />
            </div>

            <div className="flex flex-col items-center">
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                maxLength={100}
                className={FIELD_CLASS}
                placeholder="Enter your password"
              />
            </div>

            {mode === 'signin' && (
              <div className="flex flex-col items-center">
                <div className="w-full max-w-xs flex justify-end text-sm">
                  <button
                    type="button"
                    onClick={() => {
                      setView('forgot');
                      setError(null);
                      setNotice(null);
                    }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Forgot password?
                  </button>
                </div>
              </div>
            )}

            <Feedback error={error} notice={notice} />
            <SubmitButton pending={pending} label="Continue" />
          </form>
        )}

        {view === 'forgot' && (
          <form className="space-y-6" onSubmit={submitForgot}>
            <div className="flex flex-col items-center">
              <Input
                id="reset_email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className={FIELD_CLASS}
                placeholder="Enter your email"
              />
            </div>
            <Feedback error={error} notice={notice} />
            <SubmitButton pending={pending} label="Send reset code" />
          </form>
        )}

        {view === 'reset' && (
          <form className="space-y-6" onSubmit={submitReset}>
            <div className="flex flex-col items-center">
              <Input
                id="code"
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                className={FIELD_CLASS}
                placeholder="6-digit code"
              />
            </div>
            <div className="flex flex-col items-center">
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className={FIELD_CLASS}
                placeholder="New password"
              />
            </div>
            <Feedback error={error} notice={notice} />
            <SubmitButton pending={pending} label="Set new password" />
          </form>
        )}

        <div className="mt-6 flex justify-center text-sm text-muted-foreground">
          {view === 'credentials' ? (
            <>
              <span>
                {mode === 'signin'
                  ? "Don't have an account?"
                  : 'Already have an account?'}
              </span>
              <Link
                href={`${mode === 'signin' ? '/sign-up' : '/sign-in'}${
                  redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
                }`}
                className="ml-1 text-foreground hover:underline"
              >
                {mode === 'signin' ? 'Sign up' : 'Sign in'}
              </Link>
            </>
          ) : (
            <button
              type="button"
              onClick={() => {
                setView('credentials');
                setError(null);
              }}
              className="text-foreground hover:underline"
            >
              Back to sign in
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Feedback({ error, notice }: { error: string | null; notice: string | null }) {
  if (!error && !notice) return null;
  return (
    <div className="flex flex-col items-center">
      <div
        className={`w-full max-w-xs text-sm ${error ? 'text-red-500' : 'text-green-500'}`}
      >
        {error ?? notice}
      </div>
    </div>
  );
}

function SubmitButton({ pending, label }: { pending: boolean; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <Button type="submit" variant="outline" className={BUTTON_CLASS} disabled={pending}>
        {pending ? (
          <>
            <Loader2 className="animate-spin mr-2 h-4 w-4" />
            Loading...
          </>
        ) : (
          label
        )}
      </Button>
    </div>
  );
}
