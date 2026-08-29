'use client';

import { useEffect, useState } from 'react';

const locations = [
  'from anywhere',
  'from your phone',
  'on your desktop',
  'from the couch',
  'on your commute',
  'while waiting',
  'in a taxi',
  'on the train',
  'at the airport',
  'on the bus',
  'during breaks',
  'at the park',
  'on the go',
  'during chores',
  'at the café',
  'while traveling',
  'on the bed',
  'during errands',
];

export function DynamicPhrase({ phrases = locations }: { phrases?: string[] } = {}) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const displayDuration = 3000;

    const timeout = setTimeout(() => {
      setIsVisible(false);
      setTimeout(() => {
        setCurrentIndex((prevIndex) => (prevIndex + 1) % phrases.length);
        setIsVisible(true);
      }, 600);
    }, displayDuration);

    return () => clearTimeout(timeout);
  }, [currentIndex, phrases.length]);

  return (
    <span
      className={`inline-block whitespace-nowrap text-transparent bg-clip-text bg-gradient-to-br font-semibold from-blue-400 via-blue-600 to-purple-600 transition-all duration-700 ease-in-out ${
        isVisible ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {phrases[currentIndex]}
    </span>
  );
}
