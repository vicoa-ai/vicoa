"use client"

import * as React from "react"
import { CircleAlert, CircleCheck, X } from "lucide-react"
import { Toast as ToastPrimitive } from "radix-ui"
import { NO_DRAG } from "@/lib/app-region"
import { getToasts, subscribeToasts, toast, type ToastItem, type ToastKind } from "@/lib/toast"
import { cn } from "@/lib/utils"

const NO_TOASTS: ToastItem[] = []

// Hovering or focusing a toast pauses its timer, and so does leaving the window.
const DURATION_MS: Record<ToastKind, number> = { error: 6000, success: 4000 }

/**
 * Draws the toasts queued through `toast.*` (lib/toast.ts): a themed card in
 * the bottom-right corner, above dialogs, that leaves on its own and never
 * blocks the page. On a phone-width screen it sits at the top centre instead,
 * because there the bottom is the full-width composer and the keyboard.
 * Mounted once, last in the root layout's body.
 */
function Toaster() {
  const toasts = React.useSyncExternalStore(subscribeToasts, getToasts, () => NO_TOASTS)

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {toasts.map((t) => (
        <ToastPrimitive.Root
          key={t.id}
          open={t.open}
          onOpenChange={(open) => {
            if (!open) toast.dismiss(t.id)
          }}
          duration={DURATION_MS[t.kind]}
          // A screen reader reads an error out at once; a success waits its turn.
          type={t.kind === "error" ? "foreground" : "background"}
          // A narrow desktop window puts the toast on the title-bar drag
          // strip; without this a click on it would grab the window instead.
          style={NO_DRAG}
          className={cn(
            // Full width at the top of a phone; on a wider screen as wide as its text.
            "pointer-events-auto relative flex w-full items-start gap-2.5 rounded-lg border border-menu-border bg-menu py-3 pl-3 pr-9 text-menu-foreground sm:w-auto",
            // It sits over the composer, which is the same bg-menu. Anchored at
            // the bottom, a shadow cast downward would fall off the screen, so
            // it spreads up and around instead; in dark, where a black shadow
            // barely shows, the card is also a step lighter than the composer.
            "shadow-[0_0_0_1px_rgb(0_0_0/0.04),0_-2px_28px_rgb(0_0_0/0.16),0_2px_8px_rgb(0_0_0/0.08)]",
            "dark:bg-[color-mix(in_srgb,hsl(var(--menu))_94%,white)] dark:shadow-[0_0_0_1px_rgb(0_0_0/0.5),0_-4px_36px_rgb(0_0_0/0.7),0_2px_10px_rgb(0_0_0/0.5)]",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2 sm:data-[state=open]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
            "data-[swipe=move]:translate-x-(--radix-toast-swipe-move-x) data-[swipe=cancel]:translate-x-0 data-[swipe=cancel]:transition-transform data-[swipe=end]:translate-x-(--radix-toast-swipe-end-x)"
          )}
        >
          {t.kind === "error" ? (
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          ) : (
            <CircleCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          )}
          <div className="min-w-0 flex-1 space-y-0.5">
            <ToastPrimitive.Title className="text-sm font-medium leading-5">{t.title}</ToastPrimitive.Title>
            {t.description ? (
              <ToastPrimitive.Description className="text-sm break-words text-muted-foreground">
                {t.description}
              </ToastPrimitive.Description>
            ) : null}
          </div>
          <ToastPrimitive.Close
            aria-label="Dismiss"
            className="absolute right-2 top-2 cursor-pointer rounded-sm p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-3.5" />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      {/* The newest toast sits nearest the edge it is anchored to. On a wider
          screen each toast hugs its text, right-aligned, and wraps at 24rem. */}
      <ToastPrimitive.Viewport className="pointer-events-none fixed left-1/2 top-3 z-[100] flex w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2 flex-col-reverse gap-2 outline-none sm:bottom-4 sm:left-auto sm:right-4 sm:top-auto sm:w-max sm:max-w-[min(24rem,calc(100vw-2rem))] sm:translate-x-0 sm:flex-col sm:items-end" />
    </ToastPrimitive.Provider>
  )
}

export { Toaster }
