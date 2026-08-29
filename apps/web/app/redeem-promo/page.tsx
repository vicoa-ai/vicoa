'use client';

import Image from 'next/image';

import { Footer } from '@/components/footer';
import { NavigationHeader } from '@/components/navigation-header';

const steps = [
  {
    title: 'Step 1: Open the App Store',
    description: 'On your iPhone, tap the App Store icon to open it.',
    image: '/images/redeem-promo/step1.png'
  },
  {
    title: 'Step 2: Go to Your Profile',
    description: 'Tap your profile icon in the top right corner of the App Store.',
    image: '/images/redeem-promo/step2.png'
  },
  {
    title: 'Step 3: Redeem Gift Card or Code',
    description: "Scroll down and tap 'Redeem Gift Card or Code'.",
    image: '/images/redeem-promo/step3.png'
  },
  {
    title: 'Step 4: Enter the Promo Code',
    description: "Enter your promo code in the field provided and tap 'Redeem' in the top right corner.",
    image: '/images/redeem-promo/step4.png'
  },
  {
    title: 'Step 5: Sit back, Relax, and Start Coding Anywhere',
    description: 'Confirm the redemption and the Vicoa app will begin downloading automatically. Open the app and start vibing code anywhere with Claude Code and Codex!',
    image: '/images/redeem-promo/step5.png'
  }
];

export default function RedeemPromoPage() {
  return (
    <section className="flex min-h-screen flex-col bg-background text-foreground">
      <NavigationHeader />
      <main className="flex-1 bg-background px-8 pt-12 pb-16 md:pt-16 md:pb-24">
        <div className="container mx-auto grid h-full min-h-[50vh] w-full grid-cols-1 place-items-center gap-y-10 px-4 py-8">
          <div className="max-w-3xl lg:col-span-1 lg:row-auto">
            <h1 className="mb-6 text-center text-4xl">
              How to Redeem a Promo Code on your iPhone for Vicoa Pro
            </h1>

            <p className="mb-10 text-center text-muted-foreground">
              Here is a simple step-by-step instruction of how to redeem your fresh promo code and get the app for free from Apple&apos;s App Store. All you need is the promo code and sign in to your Apple ID.
            </p>

            <div className="space-y-16">
              {steps.map((step, index) => (
                <div key={index} className="flex flex-col items-center gap-8 md:flex-row md:items-start">
                  <div className="order-1 md:flex-1">
                    <h2 className="mb-2 text-2xl">
                      {step.title}
                    </h2>
                    <p className="text-muted-foreground">
                      {step.description}
                    </p>
                  </div>
                  <Image
                    src={step.image}
                    alt={step.title}
                    width={256}
                    height={256}
                    className="order-2 h-auto w-64 rounded-lg shadow-md"
                  />
                </div>
              ))}
            </div>

            <a className="text-background cursor-default" href='https://karmalinks.io/?verificationId=69c2baa486498dfc75195bb1'>l</a>
          </div>
        </div>
      </main>
      <Footer />
    </section>
  );
}
