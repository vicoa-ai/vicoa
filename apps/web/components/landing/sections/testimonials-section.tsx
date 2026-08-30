'use client';

import { Star } from 'lucide-react';
import { useState, useEffect } from 'react';

export interface Testimonial {
  text: string;
  author: string;
  role: string;
}

const defaultTestimonials: Testimonial[] = [
  {
    text: "Vibe coding on mobile felt impossible until Vicoa. Now I fix bugs during lunch breaks and ship features from anywhere. Total game changer.",
    author: "Alex Chen",
    role: "Full Stack Engineer",
  },
  {
    text: "I can finally code during my 2-hour daily commute. Set up tasks on desktop, continue on mobile. My productivity doubled overnight.",
    author: "Priya Shah",
    role: "React Developer",
  },
  {
    text: "Perfect for indie devs like me. I code at coffee shops, on trains, even waiting in line. Every moment becomes productive time.",
    author: "Marcus Tan",
    role: "Indie Hacker",
  },
  {
    text: "The mobile coding experience is surprisingly smooth. Touch interface works great, and I can actually get real work done on my phone.",
    author: "Sarah Kemp",
    role: "Frontend Developer",
  },
  {
    text: "I didn't realize how much dead time I had until Vicoa. Now every coffee break, commute, and wait becomes coding time.",
    author: "David Lee",
    role: "Software Engineer",
  },
  {
    text: "The notifications are perfect. No more waiting and checking progress constantly. I get pinged when my AI needs input and can respond instantly.",
    author: "Tom Reed",
    role: "DevOps Engineer",
  },
];

function TestimonialCard({ testimonial }: { testimonial: Testimonial }) {
  return (
    <div className="bg-card rounded-2xl p-8 shadow-sm border flex flex-col">
      <div className="flex text-yellow-400 mb-6">
        {[...Array(5)].map((_, i) => (
          <Star key={i} className="h-5 w-5 fill-current" />
        ))}
      </div>
      <p className="text-sm sm:text-base text-card-foreground mb-6 italic leading-relaxed flex-1">
        "{testimonial.text}"
      </p>
      <div>
        <div className="text-sm sm:text-base text-card-foreground font-medium">{testimonial.author}</div>
        <div className="text-xs sm:text-sm text-muted-foreground">{testimonial.role}</div>
      </div>
    </div>
  );
}

export function TestimonialsSection({
  title = 'Loved by developers',
  testimonials = defaultTestimonials,
}: {
  title?: string;
  testimonials?: Testimonial[];
} = {}) {
  const [displayedTestimonials, setDisplayedTestimonials] = useState<Testimonial[]>([]);

  useEffect(() => {
    const shuffled = [...testimonials].sort(() => Math.random() - 0.5);
    setDisplayedTestimonials(shuffled);
  }, [testimonials]);

  return (
    <section className="py-20 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-24">
        <div className="text-center mb-16">
          <h2 className="text-2xl sm:text-3xl lg:text-5xl text-foreground mb-6">
            {title}
          </h2>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
          {displayedTestimonials.map((testimonial, index) => (
            <TestimonialCard key={index} testimonial={testimonial} />
          ))}
        </div>
      </div>
    </section>
  );
}