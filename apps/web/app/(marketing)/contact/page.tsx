import { FAQSection, type FAQItem } from '@/components/faq-section';
import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/contact', {
  title: 'Contact Us | Vicoa',
  description: 'Get in touch with the Vicoa team for support, bug reports, feature requests, or general feedback.',
});

const paragraphClassName = 'text-muted-foreground leading-relaxed';

const contactFaqs: FAQItem[] = [
  {
    question: 'How do I report a bug?',
    answer: (
      <>
        You can report the issue in the mobile app's Profile page, or website. You can also email us at{' '}
        <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a>{' '}
        with your device type and a description of the issue.
      </>
    ),
    answerText: 'You can report the issue in the mobile and website. You can also email us with your device type and a description of the issue.',
  },
  {
    question: 'How do I request a feature?',
    answer: (
      <>
        Send your suggestions to{' '}
        <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a>, or open a request on our{' '}
        <a href="https://github.com/vicoa-ai/vicoa-open" className="text-primary" target="_blank" rel="noopener noreferrer">
          GitHub.
        </a>
        .
      </>
    ),
    answerText: 'Send your suggestions to hi@vicoa.ai, or open a request on our GitHub.',
  },
  {
    question: 'How do I cancel my subscription?',
    answer: (
      <>
        See{' '}
        <a href="/help/cancel-subscription" className="text-primary">cancel your subscription</a>{' '}
        for iOS, Android, and web instructions.
      </>
    ),
    answerText: 'See the Cancel your subscription page for iOS, Android, and web instructions.',
  },
  {
    question: 'How do I request a refund?',
    answer: (
      <>
        See{' '}
        <a href="/help/refund-requests" className="text-primary">refund requests</a>{' '}
        for how to request one, depending on where you subscribed.
      </>
    ),
    answerText: 'See the refund requests page for how to request one, depending on where you subscribed.',
  },
  {
    question: 'How do I delete my account?',
    answer: (
      <>
        Delete it directly from the app or web dashboard under Settings → Account, or see{' '}
        <a href="/request-delete-data" className="text-primary">request delete data</a>{' '}
        to have us delete it for you.
      </>
    ),
    answerText: 'Delete it in Settings → Account, or see the request delete data page to have us delete it for you.',
  },
];

export default function ContactPage() {
  return (
    <main>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="max-w-3xl mx-auto prose prose-gray max-w-none">
          <h1 className="text-4xl text-foreground mb-8">Contact Us</h1>

          <p className={paragraphClassName}>
            Thank you for using Vicoa. If you have any questions, encounter any issues, or would like to provide
            feedback, we&apos;re here to help.
          </p>

          <p className={`mt-6 ${paragraphClassName}`}>
            Email: <a href="mailto:hi@vicoa.ai" className="text-primary">hi@vicoa.ai</a>. 
          </p>
          <p className={`mt-6 ${paragraphClassName}`}>
            We typically respond within
            1–2 business days.
          </p>
        </div>
      </div>

      <FAQSection
        title="Frequently Asked Questions"
        faqs={contactFaqs}
        idPrefix="contact-faq"
        sectionClassName="py-8 bg-background mt-12 mb-12"
        containerClassName="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8"
        headerClassName="mb-8"
        titleClassName="text-2xl sm:text-3xl text-foreground mb-2"
      />

    </main>
  );
}
