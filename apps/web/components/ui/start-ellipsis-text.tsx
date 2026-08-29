'use client';

import { useLayoutEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export function StartEllipsisText({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const textRef = useRef<HTMLSpanElement | null>(null);
  const [displayValue, setDisplayValue] = useState(value);

  useLayoutEffect(() => {
    const node = textRef.current;
    if (!node) return;

    const updateDisplayValue = () => {
      const availableWidth = node.clientWidth;
      if (availableWidth <= 0) {
        setDisplayValue(value);
        return;
      }

      const computedStyle = window.getComputedStyle(node);
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');

      if (!context) {
        setDisplayValue(value);
        return;
      }

      context.font = computedStyle.font;

      const measure = (text: string) => context.measureText(text).width;
      if (measure(value) <= availableWidth) {
        setDisplayValue(value);
        return;
      }

      const ellipsis = '...';
      let left = 0;
      let right = value.length;
      let best = value.slice(-1);

      while (left <= right) {
        const middle = Math.floor((left + right) / 2);
        const candidateTail = value.slice(-middle);
        const candidate = `${ellipsis}${candidateTail}`;

        if (measure(candidate) <= availableWidth) {
          best = candidateTail;
          left = middle + 1;
        } else {
          right = middle - 1;
        }
      }

      setDisplayValue(`${ellipsis}${best}`);
    };

    updateDisplayValue();

    const observer = new ResizeObserver(() => {
      updateDisplayValue();
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [value]);

  return (
    <span
      ref={textRef}
      className={cn(
        'block w-full min-w-0 overflow-hidden whitespace-nowrap text-left',
        className
      )}
      title={value}
    >
      {displayValue}
    </span>
  );
}
