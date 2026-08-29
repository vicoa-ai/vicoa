import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/help/refund-requests', {
  title: 'Refund Requests | Vicoa',
  description:
    'How to request a refund for your Vicoa Pro subscription on iPhone or iPad (App Store), Android (Google Play), or online on the web (Stripe).',
});

const paragraphClassName = 'text-muted-foreground leading-relaxed';
const listClassName = 'list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2';
const stepsClassName = 'list-decimal list-inside text-muted-foreground leading-relaxed mt-4 space-y-2 marker:text-foreground/60';

export default function RefundRequestsPage() {
  return (
    <main>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto prose prose-gray max-w-none">
          <h1 className="text-4xl text-foreground mb-8">Refund requests</h1>

          <p className={paragraphClassName}>
            We want you to be happy with Vicoa. 
            While most in-app purchases are nonrefundable, some exceptions apply. If you need help with a purchase made in the last 14 days, we’re here to help. You’ll find the info you need below, depending on where you made your purchase.
          </p>
          {/* <p className={`mt-4 ${paragraphClassName}`}>
            Not sure where you subscribed? Check the receipt you received when you upgraded — it will be from Apple,
            Google, or Stripe (web). You can also open{' '}
            <a href="/dashboard/settings?tab=billing" className="text-primary">Settings → Billing</a> in your Vicoa dashboard,
            which shows where your current plan is managed.
          </p> */}

          <section className="mb-8 mt-10">
            <h2 className="text-2xl text-foreground mb-4">iOS Purchases (Apple App Store)</h2>
            <p className={paragraphClassName}>
              If you subscribed through your iPhone or iPad, your purchase is handled by Apple. You'll need to contact Apple directly for assistance with a refund.
            </p>
            <p className={paragraphClassName}>
              To request a refund from Apple, visit {' '}
              <a href="https://support.apple.com/billing" className="text-primary" target="_blank" rel="noopener noreferrer">
                Apple Support
              </a>.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Android Purchases (Google Play Store)</h2>
            <p className={paragraphClassName}>
              If you subscribed through an Android device, your purchase is handled by Google. You'll need to contact Google directly for assistance with a refund. 
            </p>
            <p className={paragraphClassName}>
              To request a refund from Google, visit{' '}
              <a href="https://support.google.com/googleplay" className="text-primary" target="_blank" rel="noopener noreferrer">
                Google Play Support
              </a>.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Web Purchases</h2>
            <p className={paragraphClassName}>
              If you subscribed on the web at vicoa.ai, your payment is processed by Stripe and we can review refund
              requests directly.
            </p>
            <p className={paragraphClassName}>
              To request a refund for a web purchase:
            </p>
            <ol className={stepsClassName}>
              <li>Email us at{' '}
                <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a> from the address on your Vicoa account.
              </li>
              <li>Include the date of the charge and order number (if you have them handy).</li>
              <li>Let us know briefly why you&apos;re requesting a refund.</li>
            </ol>
            <p className={`mt-4 ${paragraphClassName}`}>
              Approved refunds are returned to your original payment method and typically appear within 5–10 business days,
              depending on your bank.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Things to keep in mind</h2>
            <ul className={listClassName}>
              <li>
                Submitting a refund request does not automatically cancel your subscription. To stop future charges, see{' '}
                <a href="/help/cancel-subscription" className="text-primary">Cancel your subscription</a>.
              </li>
              <li>
                Apple and Google have final say over refunds for purchases made through the App Store and Google Play. Vicoa
                can&apos;t override their decisions.
              </li>
              <li>
                For full details, see our{' '}
                <a href="/terms" className="text-primary">Terms of Use</a>.
              </li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">Need help?</h2>
            <p className={paragraphClassName}>
              Still have questions? Email us at{' '}
              <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a> and we&apos;ll help you sort it out.
            </p>
          </section>
        </div>
      </div>

    </main>
  );
}
