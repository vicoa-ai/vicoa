import { createClient } from './supabase-client';
import { createClient as createServerClient } from '@/lib/auth/supabase-server'
import { isBuiltinAuth } from '@/lib/auth/auth-provider'
import { getBuiltinClaimsFromCookies, getBuiltinTokenFromCookies } from '@/lib/auth/builtin-server'
import { redirect } from 'next/navigation'
import { z } from 'zod'

export type ActionState = {
  error?: string
  success?: string
  [key: string]: any
}

type ValidatedActionFunction<S extends z.ZodType<any, any>, T> = (
  data: z.infer<S>,
  formData: FormData
) => Promise<T>

export function validatedAction<S extends z.ZodType<any, any>, T>(
  schema: S,
  action: ValidatedActionFunction<S, T>
) {
  return async (prevState: ActionState, formData: FormData) => {
    const result = schema.safeParse(Object.fromEntries(formData))
    if (!result.success) {
      return { error: result.error.errors[0].message }
    }

    return action(result.data, formData)
  }
}

type ValidatedActionWithUserFunction<S extends z.ZodType<any, any>, T> = (
  data: z.infer<S>,
  formData: FormData,
  user: any
) => Promise<T>

export function validatedActionWithUser<S extends z.ZodType<any, any>, T>(
  schema: S,
  action: ValidatedActionWithUserFunction<S, T>
) {
  return async (prevState: ActionState, formData: FormData) => {
    const supabase = await createServerClient()
    const { data: { user }, error } = await supabase.auth.getUser()
    
    if (error || !user) {
      throw new Error('User is not authenticated')
    }

    const result = schema.safeParse(Object.fromEntries(formData))
    if (!result.success) {
      return { error: result.error.errors[0].message }
    }

    return action(result.data, formData, user)
  }
}

/**
 * The signed-in user, server-side, from whichever provider is configured.
 *
 * The built-in provider has no user directory to call — its session token
 * already carries the identity — so the claims are reshaped into the same
 * `{ id, email, user_metadata }` form every caller already reads.
 */
export async function getSupabaseUser() {
  if (isBuiltinAuth()) {
    const claims = await getBuiltinClaimsFromCookies()
    if (!claims) {
      return null
    }
    return {
      id: claims.sub,
      email: claims.email ?? null,
      user_metadata: { display_name: claims.name, name: claims.name },
    } as any
  }

  const supabase = await createServerClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  
  if (error || !user) {
    return null
  }
  
  return user
}

export async function requireAuth() {
  const user = await getSupabaseUser()
  if (!user) {
    redirect('/sign-in')
  }
  return user
}

/** The caller's bearer token for backend calls, whichever provider issued it. */
export async function getSupabaseToken(isServerSide = false): Promise<string | null> {
  try {
    if (isBuiltinAuth()) {
      if (isServerSide) {
        return await getBuiltinTokenFromCookies();
      }
      const { getBuiltinToken } = await import('@/lib/auth/builtin-client');
      return getBuiltinToken();
    }
    if (isServerSide) {
      const supabase = await createServerClient();
      const { data: { session } } = await supabase.auth.getSession();
      return session?.access_token || null;
    } else {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      return session?.access_token || null;
    }
  } catch (error) {
    console.error('Error getting Supabase token:', error);
    return null;
  }
}