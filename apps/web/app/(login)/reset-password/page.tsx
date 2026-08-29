'use client';

import { FormEvent, useEffect, useMemo, useState, Suspense } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { createClient } from '@/lib/auth/supabase-client';

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const supabase = useMemo(() => createClient(), []);
  const [checkingSession, setCheckingSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const cleanQueryParams = () => {
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.delete('access_token');
      currentUrl.searchParams.delete('refresh_token');
      currentUrl.searchParams.delete('expires_in');
      currentUrl.searchParams.delete('token_type');
      currentUrl.searchParams.delete('type');
      window.history.replaceState({}, '', `${currentUrl.pathname}${currentUrl.search ? `?${currentUrl.searchParams.toString()}` : ''}`);
    };

    const ensureSession = async () => {
      const accessToken = searchParams.get('access_token');
      const refreshToken = searchParams.get('refresh_token');

      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });

        if (isMounted) {
          if (error) {
            setSessionError('This reset link has expired or is invalid.');
          } else {
            cleanQueryParams();
            setSessionError(null);
          }
          setCheckingSession(false);
        }
        return;
      }

      const { data, error } = await supabase.auth.getSession();
      if (!isMounted) return;

      if (error || !data.session) {
        setSessionError('Request a fresh password reset link to continue.');
      } else {
        setSessionError(null);
      }

      setCheckingSession(false);
    };

    ensureSession();

    return () => {
      isMounted = false;
    };
  }, [searchParams, supabase]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    if (password.length < 8) {
      setFormError('Password must be at least 8 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setFormError('Passwords do not match.');
      return;
    }

    setSubmitting(true);

    const { error } = await supabase.auth.updateUser({ password });

    if (error) {
      setFormError(error.message);
      setSubmitting(false);
      return;
    }

    setFormSuccess('Password updated. Redirecting you to sign in...');
    setSubmitting(false);
    setTimeout(() => {
      router.replace('/sign-in');
    }, 1500);
  };

  const disabled = checkingSession || !!sessionError;

  return (
    <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Image
            src="/images/vicoa-light.webp"
            alt="Vicoa logo"
            width={0}
            height={0}
            sizes="100vw"
            className="h-12 w-auto opacity-90"
          />
        </div>
        <h2 className="mt-6 text-center text-3xl text-foreground">
          Reset password
        </h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          Create a strong password to secure your account.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="flex flex-col items-center">
            <div className="mt-1 w-full max-w-xs">
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={8}
                maxLength={100}
                required
                className="w-full px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none"
                placeholder="Enter a new password"
                disabled={disabled || submitting}
              />
            </div>
          </div>

          <div className="flex flex-col items-center">
            <div className="mt-1 w-full max-w-xs">
              <Input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                minLength={8}
                maxLength={100}
                required
                className="w-full px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none"
                placeholder="Re-enter your new password"
                disabled={disabled || submitting}
              />
            </div>
          </div>

          {checkingSession && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs flex items-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Verifying reset link...
              </div>
            </div>
          )}

          {sessionError && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs text-red-500 text-sm">{sessionError}</div>
            </div>
          )}

          {formError && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs text-red-500 text-sm">{formError}</div>
            </div>
          )}

          {formSuccess && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs text-green-500 text-sm">{formSuccess}</div>
            </div>
          )}

          <div className="flex flex-col items-center">
            <Button
              type="submit"
              className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-background bg-foreground hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-foreground"
              disabled={disabled || submitting}
            >
              {submitting ? (
                <>
                  <Loader2 className="animate-spin mr-2 h-4 w-4" />
                  Updating...
                </>
              ) : (
                'Update password'
              )}
            </Button>
          </div>
        </form>

        <div className="mt-6 text-center">
          <Link href="/sign-in" className="text-sm text-muted-foreground hover:text-foreground">
            Return to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}

function LoadingFallback() {
  return (
    <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Image
            src="/images/vicoa-light.webp"
            alt="Vicoa logo"
            width={0}
            height={0}
            sizes="100vw"
            className="h-12 w-auto opacity-90"
          />
        </div>
        <div className="mt-6 flex justify-center">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
