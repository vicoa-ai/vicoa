import posthog from 'posthog-js'
import { SURFACE } from '@/lib/desktop-telemetry'

const posthogToken = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN

// Guard the init on a present token. NEXT_PUBLIC_* values are inlined at
// `next build` time, so a build that doesn't have the token in its env (e.g. a
// CI-produced desktop renderer that was only handed the Supabase vars) would
// otherwise call posthog.init('') and log "PostHog was initialized without a
// token" on every launch. When the token is absent we skip init entirely;
// capture()/identify() elsewhere already no-op while PostHog is uninitialized.
if (posthogToken) {
  posthog.init(posthogToken, {
    api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    defaults: '2026-01-30',
  })

  // Tag every event with the surface it came from, so the shared PostHog
  // project can split desktop-vs-web funnels (the mobile app registers
  // source='app'). This bundle ships as both apps — `build-renderer.mjs` bakes
  // NEXT_PUBLIC_VICOA_DESKTOP=1 into the desktop renderer — so without this the
  // desktop app's events are indistinguishable from web's and the desktop
  // funnel is unanswerable.
  //
  // `register` sets a SUPER property, and event properties override it. That is
  // why the hardcoded `source: 'web'` event props had to be deleted from
  // `new-session/page.tsx` outright: left in place they would shadow this and
  // keep counting desktop activations as web ones.
  posthog.register({ source: SURFACE })
}
