import { Star, Users, Code } from 'lucide-react';

export function SocialProofSection() {

  return (
    <section className="py-10 bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-6">
          <p className="text-muted-foreground text-xl mb-8">Trusted by builders running coding agents everywhere</p>
          <div className="flex flex-col items-center space-y-6">
            <div className="flex flex-wrap justify-center items-center gap-4 sm:gap-8 opacity-60">
              <div className="flex items-center space-x-2">
                <Star className="h-6 w-6 text-yellow-400 fill-current" />
                <span className="text-lg">4.9/5</span>
                {/* <span className="text-muted-foreground text-base">rating</span> */}
              </div>
              <div className="flex items-center space-x-2">
                <Users className="h-6 w-6 text-blue-500" />
                <span className="text-lg">17,000+</span>
                <span className="text-muted-foreground text-lg">developers</span>
              </div>
              {/* <div className="flex items-center space-x-2">
                <Code className="h-6 w-6 text-green-500" />
                <span className="text-lg">45,000+</span>
                <span className="text-muted-foreground text-lg">projects built</span>
              </div> */}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
