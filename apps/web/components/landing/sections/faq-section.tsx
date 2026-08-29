import { FAQSection as BaseFAQSection } from '@/components/faq-section';

export function FAQSection() {
  const faqs = [
    {
      question: "What is Vicoa?",
      answer:
        "Vicoa is an agentic IDE for you to run a team of coding agents like Claude Code and Codex from any device. Start coding on your laptop, continue seamlessly on your phone or tablet, and get instant notifications when your AI agent needs input."
    },
    {
      question: "Do I need coding experience to use Vicoa?",
      answer:
        "Nope. You don't need traditional coding experience. Vicoa is made for people who uses AI agents. If you can type ideas, tweak prompts, and run simple commands, you're good to go."
    },
    {
      question: "Can I run several agents at once?",
      answer:
        "Yes. That's the point. Run Claude Code, Codex, OpenCode, and more agents in parallel, and watch every agent's live status on one board. A push notification pulls you to whichever one is blocked or done, so you never juggle terminal tabs again."
    },
    {
      question: "Does my code leave my machine?",
      answer:
        "No. Vicoa runs your coding agents on your own machine and your code stays there. Your phone, tablet, and browser act as a remote control that talks to your machine through a secure relay. Vicoa relays the conversation, not your codebase."
    },
    {
      question: "Which agents and models does Vicoa support?",
      answer:
        "Claude Code, Codex, OpenCode, Gemini, Cursor, GitHub Copilot, Kimi, and Hermes, plus 300+ models from 60+ providers through OpenRouter. Bring your own key. There's no lock-in and no usage markup."
    },
    {
      question: "Do I need git or worktrees?",
      answer:
        "No. Vicoa works in any project folder. Git worktrees are optional. They're what let agents run in parallel without stepping on each other, but you can run an agent anywhere you'd normally work."
    },
    {
      question: "Can I get banned for using Vicoa?",
      answer:
        "We can't make promises on behalf of the agent providers. That said, Vicoa launches each provider's own CLI (Claude Code, Codex, OpenCode, and others) locally on your machine using your own credentials. It doesn't extract tokens or call inference APIs directly, so from the provider's side usage through Vicoa looks the same as running the agent yourself."
    },
    {
      question: "How long does it take to set up Vicoa?",
      answer:
        "You can go from installation to your agents in minutes. Simply download the desktop app or run 'npm i -g @vicoa/cli' and launch with 'vicoa'."
    },
    {
      question: "What devices does Vicoa support?",
      answer: (
        <span>
          Vicoa works on iOS (
          <a
            href="http://apps.apple.com/sg/app/id6751626168"
            className="text-blue-600 hover:text-blue-700 underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            App Store
          </a>
          ), Android (
          <a
            href="https://play.google.com/store/apps/details?id=app.vicoa"
            className="text-blue-600 hover:text-blue-700 underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            Google Play
          </a>
          ), 
          web app at{' '}
          <a
            href="https://vicoa.ai"
            className="text-blue-600 hover:text-blue-700 underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            vicoa.ai
          </a> and CLI on macOS, Linux, and Windows.
        </span>
      ),
      answerText:
        "Vicoa works on iOS (App Store), Android (Google Play), web browsers at vicoa.ai, and CLI on macOS, Linux, and Windows."
    },
    {
      question: "Is Vicoa free to use?",
      answer:
        "Vicoa offers a free tier to get started. You'll need your Claude/Codex subscription or API keys. For advanced features and higher usage limits, check our pricing page for details."
    },
    {
      question: "Can I use Vicoa with my existing projects?",
      answer:
        "Absolutely. Vicoa works with any project that Claude Code or Codex can work with. Just start a new session from desktop app in the project or navigate to your project directory and run 'vicoa' to start a session."
    }
  ];

  return (
    <BaseFAQSection
      title="Frequently Asked Questions"
      subtitle="Find answers to common questions about Vicoa"
      faqs={faqs}
    />
  );
}
