'use client';

import { useState, useEffect } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

type TerminalProps = {
  commands?: string[];
  className?: string;
  showRunComment?: boolean;
};

const defaultCommands = ['npm i -g @vicoa/cli && vicoa'];

export function Terminal({
  commands = defaultCommands,
  className,
  showRunComment = false,
}: TerminalProps) {
  const [terminalStep, setTerminalStep] = useState(0);
  const [copied, setCopied] = useState(false);
  const terminalSteps = commands.length ? commands : defaultCommands;

  useEffect(() => {
    const timer = setTimeout(() => {
      setTerminalStep((prev) =>
        prev < terminalSteps.length - 1 ? prev + 1 : prev
      );
    }, 500);

    return () => clearTimeout(timer);
  }, [terminalStep, terminalSteps.length]);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(terminalSteps.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        'max-w-sm rounded-xl shadow-lg overflow-hidden bg-secondary text-secondary-foreground font-mono text-sm relative',
        className
      )}
    >
      <div className="px-5 py-2">
        <div className="space-y-2">
          {terminalSteps.map((step, index) => (
            <div
              key={index}
              className={`${index > terminalStep ? 'opacity-0' : 'opacity-100'} transition-opacity duration-300 flex justify-between items-center relative`}
            >
              <div>
                <span className="text-green-400">$</span> {step}
                {showRunComment ? (
                  <span className="ml-2 text-muted-foreground/60"> # Run in terminal</span>
                ) : null}
              </div>
              <button
                onClick={copyToClipboard}
                className="text-muted-foreground hover:text-blue-400 dark:hover:bg-blue-900/20 transition-colors ml-4 p-1 rounded"
                aria-label="Copy to clipboard"
              >
                {copied ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
