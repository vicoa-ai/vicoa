import { Monitor, Smartphone, History, RefreshCw, Bell, Rocket } from 'lucide-react';

export function BenefitsSection() {
  const benefitsTitle = "Why builders choose Vicoa";
  const benefitsDescription = "Get more done with your coding agents.";

  const features = [
    {
      title: "Vibe Code Anywhere",
      description: "Recover hours lost waiting at your desk, orchestrate coding agents on the go.",
      icon: Smartphone,
      color: "blue"
    },
    {
      title: "Real-time Sync",
      description: "Start a task on your laptop, pick it up on your phone, zero context lost.",
      icon: RefreshCw,
      color: "blue"
    },
    {
      title: "Instant Notifications",
      description: "Never miss a beat. Get alerted the moment your agent needs your input.",
      icon: Bell,
      color: "blue"
    },
    {
      title: "UI for Coding Agents",
      description: "Escape terminal chaos with a visual workspace to manage your agents.",
      icon: Monitor,
      color: "blue"
    },
    {
      title: "Visual Session History",
      description: "Find any past session in seconds, no more digging through terminal history.",
      icon: History,
      color: "blue"
    },
    {
      title: "Setup in Seconds",
      description: "One command to install, or download the desktop app for an even easier start. Start coding immediately.",
      icon: Rocket,
      color: "blue"
    }
  ];

  const getColorClasses = (color: string) => {
    const colorMap: Record<string, { bg: string; text: string }> = {
      blue: { bg: 'bg-blue-100 dark:bg-blue-900/20', text: 'text-blue-600 dark:text-blue-400' },
      purple: { bg: 'bg-purple-100 dark:bg-purple-900/20', text: 'text-purple-600 dark:text-purple-400' },
      green: { bg: 'bg-green-100 dark:bg-green-900/20', text: 'text-green-600 dark:text-green-400' },
      cyan: { bg: 'bg-cyan-100 dark:bg-cyan-900/20', text: 'text-cyan-600 dark:text-cyan-400' },
      orange: { bg: 'bg-orange-100 dark:bg-orange-900/20', text: 'text-orange-600 dark:text-orange-400' },
      pink: { bg: 'bg-pink-100 dark:bg-pink-900/20', text: 'text-pink-600 dark:text-pink-400' },
    };
    return colorMap[color] || colorMap.blue;
  };

  return (
    <section className="py-12 sm:py-16 lg:py-20 bg-background">
      <div className="max-w-7xl mx-auto px-4 mb-16 sm:mb-20 lg:mb-24 sm:px-6 lg:px-8">
        <div className="text-center mb-10 sm:mb-12 lg:mb-16">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-4 sm:mb-6">
            {benefitsTitle}
          </h2>
          <p className="text-base sm:text-lg lg:text-xl text-muted-foreground max-w-3xl mx-auto">
            {benefitsDescription}
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8 lg:gap-12 mb-16">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            const colors = getColorClasses(feature.color);
            return (
              <div key={index} className="bg-card rounded-2xl p-6 sm:p-8 shadow-sm hover:shadow-md transition-shadow border">
                <div className={`flex items-center justify-center h-12 w-12 sm:h-16 sm:w-16 rounded-2xl ${colors.bg} ${colors.text} mb-4 sm:mb-6 mx-auto`}>
                  <Icon className="h-6 w-6 sm:h-8 sm:w-8" />
                </div>
                <h3 className="text-lg sm:text-xl lg:text-2xl text-card-foreground mb-3 sm:mb-4 text-center">{feature.title}</h3>
                <p className="text-sm sm:text-base text-muted-foreground text-center leading-relaxed">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}