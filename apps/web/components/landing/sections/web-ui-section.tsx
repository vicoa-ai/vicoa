import Image from 'next/image';

export function WebUISection() {
  return (
    <section className="py-20 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-4">
            Desktop UI Interface
          </h2>
          <p className="text-base sm:text-lg text-muted-foreground max-w-3xl mx-auto">
            Orchestrate coding agents in parallel, manage tasks, schedule automations, and more.
          </p>
        </div>
        <div className="rounded-3xl p-4 shadow-lg">
          <Image
            src="/images/features/desktop-ui.webp"
            alt="Vicoa Desktop UI Interface"
            width={1508}
            height={851}
            className="w-full h-auto rounded-2xl"
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 90vw, (max-width: 1536px) 1200px, 1400px"
            priority
            quality={95}
          />
        </div>
      </div>
    </section>
  );
}
