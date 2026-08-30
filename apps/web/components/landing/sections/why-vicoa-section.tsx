import { X, CheckCircle, ArrowRight } from 'lucide-react';

interface BenefitsSectionProps {
  variant?: 'default' | 'vicoa';
}

export function BenefitsSection({ variant = 'default' }: BenefitsSectionProps) {
  const problems = [
    {
      title: "Leave your desk?",
      description: "Your coding session stops dead"
    },
    {
      title: "Mobile AI chatbots?",
      description: "Can't replace a real development environment"
    },
    {
      title: "SSH on mobile?",
      description: "Clunky, limited, and frustrating to use"
    }
  ];

  const solutions = [
    {
      title: "Full coding environment",
      description: "Access Claude Code and your entire dev setup from anywhere"
    },
    {
      title: "Flexible AI providers",
      description: "Bring your own API keys or use multiple AI agents"
    },
    {
      title: "Seamless continuity",
      description: "Pick up exactly where you left off, any device, anytime"
    }
  ];

  return (
    <section className="py-20 bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 mb-24 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-4">
            Why Vicoa?
          </h2>
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            Stop losing momentum when you step away from your desk
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8 lg:gap-12 items-start">
          {/* Problems Column */}
          <div className="relative">
            <div className="absolute -inset-1 bg-gradient-to-br from-red-500/20 to-orange-500/20 rounded-2xl blur-xl opacity-30" />
            <div className="relative bg-background/80 backdrop-blur-sm border border-red-500/20 rounded-2xl p-8 shadow-xl">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                  <X className="w-6 h-6 text-red-500" />
                </div>
                <h3 className="text-xl sm:text-2xl text-foreground">The Problem</h3>
              </div>
              <div className="space-y-5">
                {problems.map((problem, index) => (
                  <div
                    key={index}
                    className="group flex items-start gap-4 p-4 rounded-xl hover:bg-red-500/5 transition-all duration-300"
                  >
                    <div className="flex-shrink-0 mt-1.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-red-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-base text-foreground mb-1">
                        {problem.title}
                      </div>
                      <div className="text-sm text-muted-foreground leading-relaxed">
                        {problem.description}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Solutions Column */}
          <div className="relative">
            <div className="absolute -inset-1 bg-gradient-to-br from-blue-500/20 to-purple-500/20 rounded-2xl blur-xl opacity-30" />
            <div className="relative bg-background/80 backdrop-blur-sm border border-blue-500/20 rounded-2xl p-8 shadow-xl">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                  <CheckCircle className="w-6 h-6 text-blue-500" />
                </div>
                <h3 className="text-xl sm:text-2xl text-foreground">The Solution</h3>
              </div>
              <div className="space-y-5">
                {solutions.map((solution, index) => (
                  <div
                    key={index}
                    className="group flex items-start gap-4 p-4 rounded-xl hover:bg-blue-500/5 transition-all duration-300"
                  >
                    <div className="flex-shrink-0 mt-1">
                      <ArrowRight className="w-5 h-5 text-blue-500 group-hover:translate-x-1 transition-transform duration-300" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-base text-foreground mb-1">
                        {solution.title}
                      </div>
                      <div className="text-sm text-muted-foreground leading-relaxed">
                        {solution.description}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}