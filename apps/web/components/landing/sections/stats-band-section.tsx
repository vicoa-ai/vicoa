// Loom-style "by the numbers" proof, but with defensible capability facts (not
// vanity metrics): what the product actually spans. Numbers map to /vs/happy +
// /features (8+ agents, 300+ models, cross-device, scheduled automations).
const stats = [
  {
    stat: '8+',
    label: 'coding agents',
    detail: 'Claude Code, Codex, OpenCode, Gemini, Cursor, Copilot & more',
    accent: 'from-blue-500 to-cyan-400',
    glow: 'bg-blue-500/15',
    border: 'border-blue-500/25',
  },
  {
    stat: '300+',
    label: 'models',
    detail: 'via OpenRouter, plus bring your own key',
    accent: 'from-violet-500 to-fuchsia-400',
    glow: 'bg-violet-500/15',
    border: 'border-violet-500/25',
  },
  {
    stat: '4',
    label: 'apps, one workspace',
    detail: 'iOS, Android, Web & Desktop, synced in real time',
    accent: 'from-emerald-500 to-teal-400',
    glow: 'bg-emerald-500/15',
    border: 'border-emerald-500/25',
  },
  {
    stat: '24/7',
    label: 'automations',
    detail: 'Schedule recurring agent runs that work unattended',
    accent: 'from-amber-500 to-orange-400',
    glow: 'bg-amber-500/15',
    border: 'border-amber-500/25',
  },
];

export function StatsBandSection() {
  return (
    <section className="py-12 sm:py-16 bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((item) => (
            <div
              key={item.label}
              className={`relative overflow-hidden rounded-2xl border ${item.border} bg-card p-6 text-center`}
            >
              <div
                aria-hidden
                className={`pointer-events-none absolute -top-10 left-1/2 h-28 w-40 -translate-x-1/2 rounded-full ${item.glow} blur-2xl`}
              />
              <div
                className={`relative bg-gradient-to-r ${item.accent} bg-clip-text text-4xl font-bold text-transparent md:text-5xl`}
              >
                {item.stat}
              </div>
              <div className="relative mt-1 text-sm font-medium text-foreground">
                {item.label}
              </div>
              <p className="relative mt-2 text-sm text-muted-foreground">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
