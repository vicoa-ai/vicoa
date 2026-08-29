'use server';

import { z } from 'zod';
import { redirect } from 'next/navigation';
import { headers } from 'next/headers';
import { createClient } from '@/lib/auth/supabase-server';
import { validatedAction } from '@/lib/auth/supabase-helpers';
import { getBackendAPI } from '@/lib/backend-api';
import { captureServerEvent } from '@/lib/posthog-server';

const signInSchema = z.object({
  email: z.string().email().min(3).max(255),
  password: z.string().min(8).max(100),
  redirect: z.string().optional(),
  priceId: z.string().optional(),
  inviteId: z.string().optional(),
});

const signUpSchema = z.object({
  email: z.string().email().min(3).max(255),
  password: z.string().min(8).max(100),
  redirect: z.string().optional(),
  priceId: z.string().optional(),
  inviteId: z.string().optional(),
});

const resetPasswordSchema = z.object({
  email: z.string().email().min(3).max(255),
});

export const supabaseSignIn = validatedAction(signInSchema, async (data) => {
  const supabase = await createClient();

  const { data: authData, error } = await supabase.auth.signInWithPassword({
    email: data.email,
    password: data.password,
  });

  if (error) {
    return {
      error: error.message,
      email: data.email,
      password: data.password
    };
  }

  if (authData.user) {
    await captureServerEvent(authData.user.id, 'login_completed', { method: 'email' });
  }

  const redirectTo = data.redirect || '/dashboard';
  redirect(redirectTo);
});

export const supabaseSignUp = validatedAction(signUpSchema, async (data) => {
  const supabase = await createClient();

  // When email confirmation is on, the confirmation link must return the
  // user to their pending flow (e.g. the desktop handoff's /desktop-auth
  // URL), not the Supabase site root — otherwise the desktop app waits on
  // its sign-in screen forever. Routed through /api/auth/callback, which
  // exchanges the code and forwards to `next`.
  let emailRedirectTo: string | undefined;
  if (data.redirect) {
    const origin = await resolveOrigin();
    emailRedirectTo = `${origin}/api/auth/callback?next=${encodeURIComponent(data.redirect)}`;
  }

  const { data: authData, error } = await supabase.auth.signUp({
    email: data.email,
    password: data.password,
    options: emailRedirectTo ? { emailRedirectTo } : undefined,
  });

  if (error) {
    // User already registered — try signing them in with the provided password
    if (
      error.message.toLowerCase().includes('user already registered') ||
      error.message.toLowerCase().includes('already been registered') ||
      error.status === 422
    ) {
      const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
        email: data.email,
        password: data.password,
      });

      if (!signInError) {
        if (signInData.user) {
          await captureServerEvent(signInData.user.id, 'login_completed', { method: 'email' });
        }
        const redirectTo = data.redirect || '/dashboard';
        redirect(redirectTo);
      }

      return {
        error: 'An account with this email already exists. Please sign in instead.',
        email: data.email,
        password: data.password,
      };
    }

    return {
      error: error.message,
      email: data.email,
      password: data.password
    };
  }

  // Supabase silently returns a fake user with no identities when the email is already registered
  // (happens when email confirmation is enabled). Try signing in instead.
  if (authData.user && authData.user.identities?.length === 0) {
    const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
      email: data.email,
      password: data.password,
    });

    if (!signInError) {
      if (signInData.user) {
        await captureServerEvent(signInData.user.id, 'login_completed', { method: 'email' });
      }
      const redirectTo = data.redirect || '/dashboard';
      redirect(redirectTo);
    }

    return {
      error: 'An account with this email already exists. Please sign in instead.',
      email: data.email,
      password: data.password,
    };
  }

  if (authData.user && !authData.session) {
    await captureServerEvent(authData.user.id, 'signup_completed', {
      method: 'email',
      pending_confirmation: true,
      $set_once: { signup_origin: 'web' },
    });
    return {
      success: 'Check your email to confirm your account before signing in.',
      email: data.email,
      password: data.password
    };
  }

  const backendAPI = getBackendAPI(false);
  if (authData.user && authData.session) {
    // Subscribe user to ConvertKit
    try {
      await backendAPI.subscribeToConvertKit({
        email: authData.user.email || data.email,
        name: authData.user.user_metadata?.name || undefined
      });
    } catch (error) {
      console.error('Failed to subscribe user to ConvertKit:', error);
      // Don't fail the signup if ConvertKit subscription fails
    }

    // User was created and automatically signed in
    await captureServerEvent(authData.user.id, 'signup_completed', {
      method: 'email',
      $set_once: { signup_origin: 'web' },
    });
    const dest = data.redirect || '/dashboard';
    redirect(dest + (dest.includes('?') ? '&' : '?') + 'new_user=1');
  }

  // For email confirmation flow, also try to subscribe
  if (authData.user && !authData.session) {
    try {
      await backendAPI.subscribeToConvertKit({ 
        email: authData.user.email || data.email,
        name: authData.user.user_metadata?.name || undefined
      });
    } catch (error) {
      console.error('Failed to subscribe user to ConvertKit:', error);
      // Don't fail the signup if ConvertKit subscription fails
    }
  }

  return { 
    success: 'Account created successfully!',
    email: data.email,
    password: data.password 
  };
});

export const supabaseRequestPasswordReset = validatedAction(
  resetPasswordSchema,
  async (data) => {
    const supabase = await createClient();

    const redirectTo = `${process.env.BASE_URL}/reset-password`;

    const { error } = await supabase.auth.resetPasswordForEmail(data.email, {
      redirectTo,
    });

    if (error) {
      return {
        error: error.message,
        email: data.email,
      };
    }

    return {
      success: 'Check your email for a reset link.',
      email: data.email,
    };
  }
);

export async function supabaseSignOut() {
  const supabase = await createClient();
  // scope 'local': sign out THIS browser only. The default ('global')
  // revokes every session the user has — including the desktop app's —
  // so signing out of the website used to break the app.
  await supabase.auth.signOut({ scope: 'local' });
  redirect('/');
}

async function resolveOrigin() {
  if (process.env.NODE_ENV !== 'development' && process.env.BASE_URL) {
    return process.env.BASE_URL;
  }
  const headersList = await headers();
  const headerOrigin =
    headersList.get('origin') ||
    (headersList.get('x-forwarded-host') || headersList.get('host')
      ? `${headersList.get('x-forwarded-proto') || 'http'}://${headersList.get('x-forwarded-host') || headersList.get('host')}`
      : '');
  return process.env.BASE_URL || headerOrigin || 'http://localhost:3000';
}

export async function supabaseSignInWithGoogle(redirectPath?: string) {
  const supabase = await createClient();
  const origin = await resolveOrigin();

  const next = redirectPath || '/dashboard';
  const redirectTo = `${origin}/api/auth/callback?next=${encodeURIComponent(next)}`;

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo,
    },
  });

  if (error) {
    return { error: error.message };
  }

  if (data.url) {
    redirect(data.url);
  }

  return { error: 'Failed to initiate Google sign in' };
}

export async function supabaseSignInWithApple(redirectPath?: string) {
  const supabase = await createClient();
  const origin = await resolveOrigin();

  const next = redirectPath || '/dashboard';
  const redirectTo = `${origin}/api/auth/callback?next=${encodeURIComponent(next)}`;

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'apple',
    options: {
      redirectTo,
    },
  });

  if (error) {
    return { error: error.message };
  }

  if (data.url) {
    redirect(data.url);
  }

  return { error: 'Failed to initiate Apple sign in' };
}
