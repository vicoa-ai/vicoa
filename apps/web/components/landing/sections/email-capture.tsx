'use client';

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight } from 'lucide-react';

export function EmailCapture() {
  const [email, setEmail] = useState('');
  const router = useRouter();

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (email) {
      router.push(`/sign-up?email=${encodeURIComponent(email)}`);
    }
  };

  return (
    <div className="max-w-lg mx-auto mb-12 px-4">
      <form onSubmit={handleSubmit} className="flex items-center gap-1.5 bg-background/80 backdrop-blur-sm rounded-full p-1 shadow-xl border-2 border-foreground/20 hover:border-foreground/40 transition-all duration-300">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email address"
          required
          className="flex-1 px-4 py-2 bg-transparent text-foreground text-sm placeholder:text-muted-foreground/60 focus:outline-none"
        />
        <button
          type="submit"
          className="flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-gray-50 text-black rounded-full transition-all duration-300 ease-out whitespace-nowrap shadow-md hover:cursor-pointer"
        >
          Start now
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  );
}
