'use client';

import { useActionState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { supabaseRequestPasswordReset } from '../supabase-actions';
import { ActionState } from '@/lib/auth/supabase-helpers';

export default function ForgotPasswordPage() {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    supabaseRequestPasswordReset,
    { error: '' }
  );

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
          Reset your password
        </h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          Enter the email linked to your account and we will send a reset link.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <form className="space-y-6" action={formAction}>
          <div className="flex flex-col items-center">
            <div className="mt-1 w-full max-w-xs">
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                defaultValue={state.email}
                required
                maxLength={50}
                className="w-full px-4 py-6 rounded-lg bg-background text-foreground placeholder:text-muted-foreground border-0 focus:outline-none"
                placeholder="Enter your email"
              />
            </div>
          </div>

          {state?.error && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs text-red-500 text-sm">{state.error}</div>
            </div>
          )}

          {state?.success && (
            <div className="flex flex-col items-center">
              <div className="w-full max-w-xs text-green-500 text-sm">{state.success}</div>
            </div>
          )}

          <div className="flex flex-col items-center">
            <Button
              type="submit"
              className="w-full max-w-xs flex justify-center items-center py-5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-background bg-foreground hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-foreground"
              disabled={pending}
            >
              {pending ? (
                <>
                  <Loader2 className="animate-spin mr-2 h-4 w-4" />
                  Sending...
                </>
              ) : (
                'Send reset link'
              )}
            </Button>
          </div>
        </form>

        <div className="mt-6 text-center">
          <Link href="/sign-in" className="text-sm text-muted-foreground hover:text-foreground">
            Back to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
