import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/help/cancel-subscription', {
  title: 'Cancel Your Subscription | Vicoa',
  description:
    'How to cancel your Vicoa Pro subscription on iPhone or iPad (App Store), Android (Google Play), or online on the web (Stripe).',
});

const paragraphClassName = 'text-muted-foreground leading-relaxed';
const listClassName = 'list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2';
const stepsClassName = 'list-decimal list-inside text-muted-foreground leading-relaxed mt-4 space-y-2 marker:text-foreground/60';

export default function CancelSubscriptionPage() {
  return (
    <main>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto prose prose-gray max-w-none">
          <h1 className="text-4xl text-foreground mb-8">Cancel your subscription</h1>

          <p className={paragraphClassName}>
            Whether you are not using coding agents or just need a break, here's how you can cancel your subscription and avoid future charges.
          </p>

          <section className="mb-8 mt-10">
            <h2 className="text-2xl text-foreground mb-4">iOS Purchases (Apple App Store)</h2>
            <p className={paragraphClassName}>
              If you purchased Vicoa subscription via iPhone or iPad, it is billed by Apple and must be
              canceled through the App Store. Vicoa is unable to cancel it for you.
            </p>
            <p className={paragraphClassName}>
              To cancel on your Apple device:
            </p>
            <ol className={stepsClassName}>
              <li>Open your <strong>Settings</strong>.</li>
              <li>Tap your <strong>name</strong> at the top.</li>
              <li>Tap <strong>Subscriptions</strong>.</li>
              <li>Find and select the subscription you want to cancel.</li>
              <li>Tap <strong>Cancel Subscription</strong>. (If you don&apos;t see this option, the subscription is already canceled and won&apos;t renew.)</li>
            </ol>
            <p className={`mt-4 ${paragraphClassName}`}>
              You can also manage it from any device at{' '}
              <a href="https://apps.apple.com/account/subscriptions" className="text-primary" target="_blank" rel="noopener noreferrer">
                apps.apple.com/account/subscriptions
              </a>
              .
            </p>
            <p className={`mt-4 ${paragraphClassName}`}>
              If you need any extra help, don&apos;t hesitate to reach out to{' '}
              <a href="https://support.apple.com/billing" className="text-primary" target="_blank" rel="noopener noreferrer">
                Apple Support
              </a>{' '}
              for more info.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Android Purchases (Google Play Store)</h2>
            <p className={paragraphClassName}>
              If you purchased Vicoa subscription via Android phones, it is billed by Google and must be
              canceled through Google Play Store. Vicoa is unable to cancel it for you.
            </p>
            <p className={`mt-4 ${paragraphClassName}`}>
              To cancel on your Android device:
            </p>
            <ol className={stepsClassName}>
              <li>Open the <strong>Google Play Store</strong> app.</li>
              <li>Tap your <strong>profile icon</strong> in the top right.</li>
              <li>Tap <strong>Payments &amp; subscriptions</strong>, then <strong>Subscriptions</strong>.</li>
              <li>Select the subscription you want to cancel.</li>
              <li>Tap <strong>Cancel subscription</strong>.</li>
            </ol>
            <p className={`mt-4 ${paragraphClassName}`}>
              You can also manage it from a browser at{' '}
              <a href="https://play.google.com/store/account/subscriptions" className="text-primary" target="_blank" rel="noopener noreferrer">
                play.google.com/store/account/subscriptions
              </a>
              .
            </p>
            <p className={`mt-4 ${paragraphClassName}`}>
              If you have more questions, please contact{' '}
              <a href="https://support.google.com/googleplay" className="text-primary" target="_blank" rel="noopener noreferrer">
                Google Play Support
              </a>{' '}
              for more help.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Web Purchases</h2>
            <p className={paragraphClassName}>
              If you subscribed on the web at vicoa.ai, your can cancel it from Vicoa dashboard.
            </p>
            <ol className={stepsClassName}>
              <li>Sign in to your account.</li>
              <li>Click your <strong>profile avatar</strong> at the bottom-left of the sidebar, then choose <strong>Settings</strong>.</li>
              <li>Open the <strong>Billing</strong> tab.</li>
              <li>Click <strong>Manage subscription</strong> to open the Stripe billing portal.</li>
              <li>Select <strong>Cancel plan</strong> and confirm.</li>
            </ol>
            <p className={`mt-4 ${paragraphClassName}`}>
              Shortcut: go straight to{' '}
              <a href="/dashboard/settings?tab=billing" className="text-primary">
                Settings → Billing
              </a>
              .
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">What happens after you cancel</h2>
            <ul className={listClassName}>
              <li>Your subscription won&apos;t renew, and you won&apos;t be charged again.</li>
              <li>You keep Pro access until the end of your current billing period.</li>
              <li>After that, your account automatically moves to the Free plan.</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Looking for a refund?</h2>
            <p className={paragraphClassName}>
              Canceling stops future charges but doesn&apos;t automatically refund past ones. If you&apos;d like to request a refund for a recent charge, see{' '}
              <a href="/help/refund-requests" className="text-primary">Refund Requests</a>.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Need help?</h2>
            <p className={paragraphClassName}>
              If you can&apos;t find your subscription or need a hand, email us at{' '}
              <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a> and we&apos;ll help you out.
            </p>
          </section>
        </div>
      </div>

    </main>
  );
}
