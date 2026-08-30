'use client';

import { Button } from '@/components/ui/button';
import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import posthog from 'posthog-js';

export function CTASection({
  heading,
  subheading = 'Set up your fleet on the desktop, then steer them from any device.',
  badge = '🚀 Join 17,000+ developers',
}: {
  /** Override the H2. Defaults to the homepage two-line gradient headline. */
  heading?: React.ReactNode;
  subheading?: string;
  badge?: string;
} = {}) {
  const benefits = ["Easy setup", "Works on any device", "No credit card required"];

  return (
    <section className="relative py-24 overflow-hidden bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900">
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZGVmcz48cGF0dGVybiBpZD0iYSIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSIgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBwYXR0ZXJuVHJhbnNmb3JtPSJyb3RhdGUoNDUpIj48cmVjdCB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIGZpbGw9Im5vbmUiLz48cGF0aCBkPSJNLTEwIDMwbDIwLTIwTTEwIDcwbDIwLTIwTTMwIDUwbDIwLTIwTTUwIDMwbDIwLTIwTTcwIDEwbDIwLTIwTTkwIDMwbDIwLTIwIiBzdHJva2U9InJnYmEoMjU1LDI1NSwyNTUsMC4xKSIgc3Ryb2tlLXdpZHRoPSIxIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] opacity-20"></div>
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl"></div>
      <div className="absolute bottom-0 right-1/4 w-64 h-64 bg-indigo-500/20 rounded-full blur-3xl"></div>

      <div className="relative max-w-4xl mx-auto text-center px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <div className="inline-flex items-center px-4 py-2 bg-white/10 backdrop-blur-sm rounded-full text-blue-100 text-sm font-medium mb-6 border border-white/20">
            {badge}
          </div>
        </div>

        <h2 className="text-3xl sm:text-4xl lg:text-6xl text-white mb-6 leading-tight">
          {heading ?? (
            <>
              Run a team of coding agents,
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400">
                from anywhere
              </span>
            </>
          )}
        </h2>

        <p className="text-xl lg:text-2xl text-slate-200 mb-10 max-w-3xl mx-auto leading-relaxed">
          {subheading}
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-8">
          <Link href="/sign-up" className="w-full sm:w-auto" onClick={() => posthog.capture('cta_section_clicked', { location: 'bottom' })}>
            <Button className="group text-lg sm:text-xl !px-6 sm:!px-8 !py-5 sm:!py-6 bg-white text-slate-900 hover:bg-slate-100 hover:shadow-2xl shadow-lg transform hover:scale-105 transition-all duration-300 ease-out rounded-full border-0 w-full sm:w-auto">
              Get Vicoa for free
              {/* <ArrowRight className="ml-2 h-5 sm:h-6 w-5 sm:w-6 group-hover:translate-x-1 transition-transform duration-300" /> */}
            </Button>
          </Link>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-8 text-blue-200 text-sm">
          {benefits.map((benefit, index) => (
            <div key={index} className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-400 rounded-full"></div>
              <span>{benefit}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}