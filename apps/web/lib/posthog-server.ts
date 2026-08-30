import { PostHog } from 'posthog-node'

export async function captureServerEvent(
  distinctId: string,
  event: string,
  properties?: Record<string, unknown>
) {
  try {
    const client = new PostHog(process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN!, {
      host: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    })
    client.capture({ distinctId, event, properties })
    await client.shutdown()
  } catch {
    // don't let analytics failures affect the user
  }
}
