'use client';

import { useState } from 'react';
import { Minus, Plus } from 'lucide-react';

export interface FAQItem {
  question: string;
  answer: string | React.ReactNode;
  answerText?: string;
}

type FAQSectionProps = {
  title?: string;
  subtitle?: string;
  faqs: FAQItem[];
  idPrefix?: string;
  sectionClassName?: string;
  containerClassName?: string;
  headerClassName?: string;
  titleClassName?: string;
  subtitleClassName?: string;
};

export function FAQSection({
  title,
  subtitle,
  faqs,
  idPrefix = 'faq',
  sectionClassName = 'py-20 bg-background',
  containerClassName = 'max-w-3xl mx-auto px-4 sm:px-6 lg:px-8',
  headerClassName = 'text-center mb-16',
  titleClassName = 'text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6',
  subtitleClassName = 'text-base sm:text-lg lg:text-xl text-muted-foreground max-w-2xl mx-auto'
}: FAQSectionProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const faqSchema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((faq) => ({
      '@type': 'Question',
      name: faq.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: faq.answerText || (typeof faq.answer === 'string' ? faq.answer : '')
      }
    }))
  };

  const toggleFAQ = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <section className={sectionClassName}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />

      <div className={containerClassName}>
        {title || subtitle ? (
          <div className={headerClassName}>
            {title ? <h2 className={titleClassName}>{title}</h2> : null}
            {subtitle ? <p className={subtitleClassName}>{subtitle}</p> : null}
          </div>
        ) : null}

        <div className="space-y-0">
          {faqs.map((faq, index) => (
            <div key={faq.question} className="border-b border-border/50 last:border-b-0">
              <button
                onClick={() => toggleFAQ(index)}
                className="w-full py-6 text-left flex items-start justify-between gap-6 group"
                aria-expanded={openIndex === index}
                aria-controls={`${idPrefix}-answer-${index}`}
              >
                <h3 className="text-base sm:text-lg text-foreground group-hover:text-foreground/80 transition-colors">
                  {faq.question}
                </h3>
                <div className="flex-shrink-0 mt-1">
                  {openIndex === index ? (
                    <Minus className="h-5 w-5 text-muted-foreground" />
                  ) : (
                    <Plus className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
              </button>
              <div
                id={`${idPrefix}-answer-${index}`}
                className={`grid transition-all duration-300 ease-in-out ${
                  openIndex === index
                    ? 'grid-rows-[1fr] opacity-100'
                    : 'grid-rows-[0fr] opacity-0'
                }`}
              >
                <div className="overflow-hidden">
                  <div className="pb-6 text-sm sm:text-base text-muted-foreground leading-relaxed">
                    {faq.answer}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
