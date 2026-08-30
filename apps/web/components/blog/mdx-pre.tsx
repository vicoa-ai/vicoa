"use client";

import React, { useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';

interface MdxPreProps extends React.HTMLAttributes<HTMLPreElement> {
  children: React.ReactNode;
  className?: string;
}

interface CodeElementProps {
  className?: string;
  children?: React.ReactNode;
}

export function MdxPre({ children, className = '', ...props }: MdxPreProps) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  let codeClassName = className;
  let languageLabel: string | undefined;
  let codeChildren = children;

  if (!codeClassName && React.isValidElement(children)) {
    const childProps = children.props as CodeElementProps;
    if (typeof childProps.className === 'string') {
      codeClassName = childProps.className;
    }
  }

  const match = codeClassName.match(/language-([\w-]+)/);
  languageLabel = match?.[1];

  if (React.isValidElement(children)) {
    const childProps = children.props as CodeElementProps;
    codeChildren = React.cloneElement(children, {
      className: childProps.className || codeClassName,
    } as Partial<CodeElementProps>);
  }

  const handleCopy = async () => {
    const text = preRef.current?.innerText;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (error) {
      console.error('Failed to copy code', error);
    }
  };

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background/90 text-muted-foreground shadow-sm backdrop-blur transition hover:text-primary opacity-0 group-hover:opacity-100"
        aria-label={copied ? 'Copied' : 'Copy code'}
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </button>
      {languageLabel && (
        <span className="absolute left-3 top-3 z-10 rounded-sm bg-background/80 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground border border-border shadow-sm">
          {languageLabel}
        </span>
      )}
      <pre ref={preRef} className={codeClassName} {...props}>
        {codeChildren}
      </pre>
    </div>
  );
}
