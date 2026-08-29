import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/terms', {
  title: 'Terms of Use | Vicoa',
  description: 'These Terms of Use apply to your use of Vicoa mobile application, web application, and other services.',
});

const paragraphClassName = 'text-muted-foreground leading-relaxed';
const listClassName = 'list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2';

export default function TermsPage() {
  return (
    <main>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto prose prose-gray max-w-none">
          <h1 className="text-4xl text-foreground mb-8">Terms of Use and License Agreement</h1>

          <p className={`text-sm mb-8 ${paragraphClassName}`}>Last Updated: February 18, 2026</p>
          <p className={`font-semibold ${paragraphClassName}`}>
            IMPORTANT: PLEASE READ THESE TERMS OF USE ("TERMS") CAREFULLY BEFORE USING THE VICOA APPLICATION.
          </p>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">1. Acceptance of Terms</h2>
            <p className={paragraphClassName}>
              By downloading, installing, or using the Vicoa mobile application ("App") and related services (collectively, the "Service"), you agree to be
              bound by these Terms. If you do not agree to these Terms, do not use the Service.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">2. Description of Service</h2>
            <p className={paragraphClassName}>
              Vicoa provides a platform that enables real-time communication between users and their AI agents through various AI service providers. The Service
              includes:
            </p>
            <ul className={listClassName}>
              <li>Mobile application for iOS and Android</li>
              <li>Web application</li>
              <li>Real-time messaging with AI agents</li>
              <li>Conversational voice agent for coding</li>
              <li>Agent status monitoring and management</li>
              <li>Subscription-based premium features</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">3. Account Registration</h2>
            <p className={paragraphClassName}>To use the Service, you must:</p>
            <ul className={listClassName}>
              <li>Provide accurate and complete registration information</li>
              <li>Maintain the security of your account credentials</li>
              <li>Be responsible for all activities under your account</li>
              <li>Notify us immediately of any unauthorized use</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">4. Subscription and Payment Terms</h2>
            <h3 className="text-xl text-foreground mb-3 mt-6">Free Tier</h3>
            <ul className={listClassName}>
              <li>Limited to 50 prompts</li>
              <li>Basic features as described in the App</li>
            </ul>
            <h3 className="text-xl text-foreground mb-3 mt-6">Pro Subscription</h3>
            <ul className={listClassName}>
              <li>Unlimited messages</li>
              <li>Unlimited agents</li>
              <li>Priority support</li>
              <li>Advanced features as they become available</li>
              <li>Billed monthly through your app store account or Stripe</li>
            </ul>
            <h3 className="text-xl text-foreground mb-3 mt-6">Billing</h3>
            <ul className={listClassName}>
              <li>Subscriptions automatically renew unless canceled 24 hours before the current period ends</li>
              <li>Your account will be charged for renewal within 24 hours before the current period ends</li>
              <li>You can manage subscriptions in your app store account settings</li>
              <li>No refunds for partial months</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">5. Use of Service</h2>
            <p className={paragraphClassName}>You may use our Service for any lawful purpose. You agree NOT to:</p>
            <ul className={listClassName}>
              <li>Use the Service for illegal purposes</li>
              <li>Transmit malware or harmful code</li>
              <li>Interfere with or disrupt the Service</li>
              <li>Attempt unauthorized access to other users' accounts</li>
              <li>Impersonate others or provide false information</li>
              <li>Harass or harm other users</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">6. Content and Ownership</h2>
            <ul className={listClassName}>
              <li>You retain ownership of content you create through the Service</li>
              <li>You grant us a license to store and display your content as necessary to provide the Service</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">7. Privacy</h2>
            <p className={paragraphClassName}>
              Your use of the Service is subject to our <a href="/privacy" className="text-primary">Privacy Policy</a>, which is incorporated into these Terms by reference.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">8. Third-Party Services</h2>
            <ul className={listClassName}>
              <li>The Service integrates with third-party AI providers</li>
              <li>Your use of these integrations is subject to their terms and policies</li>
              <li>We are not responsible for third-party services or content</li>
              <li>API keys and credentials you provide are your responsibility</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">9. Disclaimers</h2>
            <p className={paragraphClassName}>
              THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A
              PARTICULAR PURPOSE, NON-INFRINGEMENT, OR ACCURACY OF INFORMATION.
            </p>
            <p className={`mt-4 ${paragraphClassName}`}>WE DO NOT WARRANT THAT:</p>
            <ul className={listClassName}>
              <li>The Service will be uninterrupted or error-free</li>
              <li>Defects will be corrected</li>
              <li>The Service is free of viruses or harmful components</li>
              <li>AI responses will be accurate, appropriate, or suitable for your purposes</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">10. Limitation of Liability</h2>
            <p className={paragraphClassName}>TO THE MAXIMUM EXTENT PERMITTED BY LAW:</p>
            <ul className={listClassName}>
              <li>We are not liable for indirect, incidental, special, or consequential damages</li>
              <li>Our total liability shall not exceed the amount you paid for the Service in the past 12 months</li>
            </ul>
            <p className={`mt-4 ${paragraphClassName}`}>We are not responsible for losses resulting from:</p>
            <ul className={listClassName}>
              <li>Your use or inability to use the Service</li>
              <li>Unauthorized access to your account or data</li>
              <li>Data breaches, hacks, or security incidents</li>
              <li>Loss, corruption, or disclosure of your data</li>
              <li>AI-generated content or recommendations</li>
              <li>Third-party services or content</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">11. Indemnification</h2>
            <p className={paragraphClassName}>
              You agree to indemnify and hold harmless Vicoa, its affiliates, and their respective officers, directors, employees, and agents from any claims,
              damages, losses, liabilities, costs, and expenses arising from your violation of these Terms, your use of the Service, your content or AI
              interactions, or your violation of any rights of another party.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">12. Termination</h2>
            <ul className={listClassName}>
              <li>Either party may terminate these Terms at any time</li>
              <li>We may suspend or terminate your access for violations</li>
              <li>Upon termination, your license to use the Service ends</li>
              <li>Provisions that should survive termination will remain in effect</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">13. Modifications</h2>
            <p className={paragraphClassName}>
              We may modify these Terms at any time. We will notify you of material changes through the App or email. Continued use after changes constitutes
              acceptance.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">14. Governing Law and Jurisdiction</h2>
            <p className={paragraphClassName}>
              These Terms and any action related thereto will be governed and interpreted by and under the laws of Singapore, without giving effect to any
              principles that provide for the application of the law of another jurisdiction. The United Nations Convention on Contracts for the International Sale
              of Goods does not apply to the Agreement.
            </p>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">15. Apple App Store Additional Terms</h2>
            <p className={paragraphClassName}>For iOS users:</p>
            <ul className={listClassName}>
              <li>Apple has no obligation to provide maintenance or support for the App</li>
              <li>Apple is not responsible for any product warranties</li>
              <li>Apple is not responsible for addressing claims relating to the App</li>
              <li>Apple is not responsible for third-party intellectual property claims</li>
              <li>Apple and its subsidiaries are third-party beneficiaries of these Terms</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">16. Google Play Store Additional Terms</h2>
            <p className={paragraphClassName}>For Android users:</p>
            <ul className={listClassName}>
              <li>You acknowledge that these Terms are between you and Vicoa, not Google</li>
              <li>Google has no responsibility for the App or its content</li>
              <li>Your use must comply with Google Play's Terms of Service</li>
            </ul>
          </section>

          <section className="mb-8">
            <h2 className="text-2xl text-foreground mb-4">17. Contact Information</h2>
            <p className={paragraphClassName}>For questions about these Terms, contact us at:</p>
            <p className={`mt-4 ${paragraphClassName}`}>Email: hi@vicoa.ai</p>
            <p className={paragraphClassName}>Website: https://vicoa.ai</p>
            <p className={`mt-4 ${paragraphClassName}`}>
              BY USING THE SERVICE, YOU ACKNOWLEDGE THAT YOU HAVE READ, UNDERSTOOD, AND AGREE TO BE BOUND BY THESE TERMS OF USE.
            </p>
          </section>
        </div>
      </div>

    </main>
  );
}
