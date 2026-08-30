import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/privacy', {
  title: 'Privacy Policy | Vicoa',
  description: 'This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our mobile application and services.',
});

export default function PrivacyPage() {
  return (
    <main>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto prose prose-gray max-w-none">
        <h1 className="text-4xl text-foreground mb-8">Privacy Policy</h1>

        <p className="text-sm text-muted-foreground mb-8">Last Updated: February 18, 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">1. Introduction</h2>
          <p className="text-muted-foreground leading-relaxed">
            Vicoa, provided by BETTERBIT PTE. LTD. ("BetterBit," "we," "our," or "us"), is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our mobile application, web application, and services
            (collectively, the "Service").
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">2. Information We Collect</h2>

          <h3 className="text-xl text-foreground mb-3 mt-6">Personal Information</h3>
          <p className="text-muted-foreground leading-relaxed">Account Information: Email address, name, and profile information you provide during registration</p>
          <p className="text-muted-foreground leading-relaxed mt-2">
            Payment Information: Processed securely through Apple App Store/Google Play Store/Stripe (we do not store payment details)
          </p>
          <p className="text-muted-foreground leading-relaxed mt-2">Usage Data: Information about how you interact with AI agents and use our Service</p>
          <p className="text-muted-foreground leading-relaxed">
            Message Content: Your conversations with AI agents are securely stored to enable seamless access across all your devices
          </p>

          <h3 className="text-xl text-foreground mb-3 mt-6">Automatically Collected Information</h3>
          <p className="text-muted-foreground leading-relaxed">Device Information: Device type, operating system, unique device identifiers</p>
          <p className="text-muted-foreground leading-relaxed mt-2">Log Data: IP address, access times, app features accessed, and crashes</p>
          <p className="text-muted-foreground leading-relaxed mt-2">Analytics: App performance metrics and usage patterns</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">3. How We Use Your Information</h2>
          <p className="text-muted-foreground leading-relaxed">We use the information we collect to:</p>
          <ul className="list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2">
            <li>Provide, maintain, and improve our Service</li>
            <li>Process transactions and manage subscriptions</li>
            <li>Facilitate communication between you and your AI agents</li>
            <li>Send notifications about AI agent activities</li>
            <li>Respond to customer service requests</li>
            <li>Monitor and analyze usage patterns to improve user experience</li>
            <li>Comply with legal obligations</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">4. Data Sharing and Disclosure</h2>
          <p className="text-muted-foreground leading-relaxed">We do not sell or share your personal information. We disclose information as follows:</p>
          <ul className="list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2">
            <li>Limited account information with service providers who assist in operating our Service (e.g., authentication, analytics)</li>
            <li>
              Aggregated or de-identified information for analytics, research, or business purposes, including with partners or in connection with a business
              transaction
            </li>
            <li>Any information as required to comply with legal obligations or respond to lawful requests</li>
            <li>Information necessary to protect our rights, privacy, safety, or property</li>
            <li>With your explicit consent or at your direction</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">5. Your Data Privacy</h2>
          <p className="text-muted-foreground leading-relaxed">
            We respect your privacy and handle your data with care:
          </p>
          <ul className="list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2">
            <li>Your conversations are securely stored to sync across your devices and maintain your chat history</li>
            <li>
              We do not disclose your message content to third parties except as described in this Policy (including service providers under contract or legal
              requirements)
            </li>
            <li>You can delete your account to permanently delete your data (including messages and chats). Email hi@vicoa.ai to request account deletion.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">6. Data Security</h2>
          <p className="text-muted-foreground leading-relaxed">
            We implement appropriate technical and organizational security measures to protect your personal information against unauthorized access, alteration,
            disclosure, or destruction. However, no method of transmission over the Internet or electronic storage is 100% secure. We cannot guarantee absolute
            security of your data and are not liable for any data breach, unauthorized access, or security incident beyond our reasonable control. You use the
            Service at your own risk.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">7. Data Retention</h2>
          <p className="text-muted-foreground leading-relaxed">
            We retain your personal information for as long as necessary to provide our Service and fulfill the purposes outlined in this Privacy Policy, unless a
            longer retention period is required by law. Message content that you delete is immediately and permanently removed from our servers.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">8. Your Rights</h2>
          <p className="text-muted-foreground leading-relaxed">Subject to applicable law, you have the right to:</p>
          <ul className="list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2">
            <li>Know and access the categories and specific pieces of personal information we collect, use, and disclose</li>
            <li>Request deletion of personal information, subject to legal exceptions</li>
            <li>Correct inaccurate personal information</li>
            <li>Receive your information in a portable format where applicable</li>
            <li>
              Opt out of the sale or sharing of personal information and cross-context behavioral advertising (we do not currently sell or share personal
              information)
            </li>
            <li>Limit the use and disclosure of sensitive personal information, where applicable</li>
            <li>Be free from discrimination for exercising these rights</li>
          </ul>
          <p className="text-muted-foreground leading-relaxed mt-4">
            To exercise these rights or submit an opt-out request if our practices change, contact us at hi@vicoa.ai.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">9. Third-Party Services</h2>
          <p className="text-muted-foreground leading-relaxed">
            Our Service may contain links to third-party websites or services. We are not responsible for the privacy practices of these third parties. We
            encourage you to review their privacy policies.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">10. Subscription and Payment Processing</h2>
          <ul className="list-disc list-inside text-muted-foreground leading-relaxed mt-4 space-y-2">
            <li>iOS: Payments are processed by Apple through the App Store</li>
            <li>Android: Payments are processed by Google through Google Play Store</li>
            <li>Web: Payments are processed by Stripe</li>
            <li>We do not have access to your payment card details</li>
            <li>Mobile subscription management is handled through your app store account</li>
            <li>Web subscription management is handled through your account settings</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">11. Push Notifications</h2>
          <p className="text-muted-foreground leading-relaxed">
            With your consent, we may send push notifications about AI agent activities, updates, and important service information. You can disable these in
            your device settings.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">12. Changes to This Privacy Policy</h2>
          <p className="text-muted-foreground leading-relaxed">
            We may update this Privacy Policy from time to time. We will notify you of changes by posting the new Privacy Policy in the app and updating the
            "Last Updated" date.
          </p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">13. Contact Us</h2>
          <p className="text-muted-foreground leading-relaxed">
            If you have questions about this Privacy Policy or our privacy practices, please contact us at:
          </p>
          <p className="text-muted-foreground leading-relaxed mt-4">Email: hi@vicoa.ai</p>
          <p className="text-muted-foreground leading-relaxed">Website: https://vicoa.ai</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl text-foreground mb-4">14. Data Protection Inquiries</h2>
          <p className="text-muted-foreground leading-relaxed">For data protection inquiries, please contact us at: hi@vicoa.ai</p>
        </section>
        </div>
      </div>

    </main>
  );
}
