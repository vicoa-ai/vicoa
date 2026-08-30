'use client'

import { useEffect } from 'react'
import posthog from 'posthog-js'
import useSWR from 'swr'
import { createClient } from '@/lib/auth/supabase-client'
import { isBuiltinAuth } from '@/lib/auth/auth-provider'
import { identifyDesktopUser, resetIdentity } from '@/lib/desktop-telemetry'

const fetcher = (url: string) => fetch(url).then(r => r.ok ? r.json() : null)

// Compile-time constant so the SWR key is stably null on desktop (no hydration
// mismatch).
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1'

/**
 * Attach PostHog events to the signed-in user, by whichever route this surface
 * actually has a session on.
 *
 * **Web** asks the server (`/api/supabase-user`) — it holds the session cookie.
 *
 * **Desktop** reads the session client-side instead. `/api/supabase-user` 401s
 * there because the Next standalone server the renderer loads from has no
 * cookie: the renderer keeps its session in localStorage. That 401 is exactly
 * the noise this component was gated away from producing, so re-enabling the
 * *fetch* would bring it straight back — reading the session locally will not.
 *
 * (The old "desktop-local has no Supabase session" rationale is stale: it
 * predates vicoa-backend@08d14c4, which disabled local-only mode and made the
 * app login-required. In cloud mode the renderer holds a real session.)
 */
export function PostHogIdentify() {
  const { data: user } = useSWR(IS_DESKTOP ? null : '/api/supabase-user', fetcher)

  useEffect(() => {
    if (user?.id) {
      posthog.identify(user.id, { email: user.email })
    }
  }, [user?.id, user?.email])

  useEffect(() => {
    if (!IS_DESKTOP) return
    // The built-in provider emits no auth-state events; the SWR path above
    // already covers identification everywhere it applies.
    if (isBuiltinAuth()) return

    // onAuthStateChange fires INITIAL_SESSION on subscribe carrying the current
    // session, so an already-signed-in launch identifies without a separate
    // getSession() race.
    const { data: { subscription } } = createClient().auth.onAuthStateChange((event, session) => {
      if (session?.user) {
        // Also fires on TOKEN_REFRESHED; identifyDesktopUser no-ops on an
        // unchanged id, so a refresh doesn't emit an hourly $set per user.
        identifyDesktopUser(session.user.id, session.user.email)
      } else if (event === 'SIGNED_OUT') {
        // Load-bearing on desktop in a way it isn't on mobile: a Mac is shared
        // physical hardware, so without this the next person to sign in
        // inherits the previous user's PostHog person.
        resetIdentity()
      }
    })
    return () => subscription.unsubscribe()
  }, [])

  return null
}
