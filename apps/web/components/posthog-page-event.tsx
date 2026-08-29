'use client'

import { useEffect } from 'react'
import posthog from 'posthog-js'

export function PostHogPageEvent({ event, properties }: { event: string; properties?: Record<string, unknown> }) {
  useEffect(() => {
    posthog.capture(event, properties)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
