import Image from 'next/image';
import { Shield, Github, Linkedin, Bell, Mail } from 'lucide-react';

// Discord Icon Component
const DiscordIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0a12.64 12.64 0 0 0-.617-1.25a.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.078.078 0 0 0 .084-.028a14.09 14.09 0 0 0 1.226-1.994a.076.076 0 0 0-.041-.106a13.107 13.107 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10.2 10.2 0 0 0 .372-.292a.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127a12.299 12.299 0 0 1-1.873.892a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028a19.839 19.839 0 0 0 6.002-3.03a.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418z"/>
  </svg>
);

// X (Twitter) Icon Component
const XIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
);

export function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-8 mb-12">
          {/* Brand */}
          <div className="md:col-span-1">
            <div className="flex items-center mb-4">
              <Image
                src="/images/vicoa-logo-text.webp"
                alt="Vicoa Logo"
                width={100}
                height={100}
                className="mr-3"
              />
              {/* <span className="text-2xl font-semibold text-white font-mono">vicoa</span> */}
            </div>
            <p className="text-gray-400 mb-6 text-sm leading-relaxed">
              Code with AI. Anywhere. Any device.
            </p>
            {/* <div className="mb-6">
              <a href="https://www.producthunt.com/products/vibe-code-anywhere-vicoa?embed=true&utm_source=badge-featured&utm_medium=badge&utm_source=badge-vibe&#0045;code&#0045;anywhere&#0045;vicoa" target="_blank">
                <img src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1014571&theme=dark&t=1757494713017" alt="Vibe&#0032;Code&#0032;Anywhere&#0032;&#0040;Vicoa&#0041; - Ship&#0032;faster&#0032;with&#0032;Claude&#0032;Code&#0032;anytime&#0044;&#0032;anywhere | Product Hunt" style={{width: '200px', height: '43px'}} width={200} height={43} />
              </a>
            </div> */}
          </div>

          {/* Product */}
          <div>
            <h3 className="text-white mb-4">Product</h3>
            <ul className="space-y-3 text-sm">
              <li><a href="/download" className="hover:text-blue-400 transition-colors">Download</a></li>
              <li><a href="http://apps.apple.com/sg/app/id6751626168" className="hover:text-blue-400 transition-colors">iOS App</a></li>
              <li><a href="https://play.google.com/store/apps/details?id=app.vicoa" className="hover:text-blue-400 transition-colors">Android App</a></li>
              <li><a href="/dashboard" className="hover:text-blue-400 transition-colors">Web App</a></li>
            </ul>
          </div>

          {/* Resources & Support */}
          <div>
            <h3 className="text-white mb-4">Resources</h3>
            <ul className="space-y-3 text-sm">
              <li><a href="/#features" className="hover:text-blue-400 transition-colors">Features</a></li>
              <li><a href="/docs" className="hover:text-blue-400 transition-colors">Documentation</a></li>
              <li><a href="/blog" className="hover:text-blue-400 transition-colors">Blog</a></li>
              <li><a href="/updates" className="hover:text-blue-400 transition-colors">Updates</a></li>
              <li><a href="/coding-agents" className="hover:text-blue-400 transition-colors">Coding agents</a></li>
              <li><a href="/pricing" className="hover:text-blue-400 transition-colors">Pricing</a></li>
            </ul>
          </div>

          {/* Compare */}
          <div>
            <h3 className="text-white mb-4">Compare</h3>
            <ul className="space-y-3 text-sm">
              <li><a href="/vs/happy" className="hover:text-blue-400 transition-colors">Vicoa vs Happy</a></li>
              <li><a href="/vs/codex" className="hover:text-blue-400 transition-colors">Vicoa vs Codex</a></li>
              <li><a href="/vs/conductor" className="hover:text-blue-400 transition-colors">Vicoa vs Conductor</a></li>
              <li><a href="/vs/claude-code-remote-control" className="hover:text-blue-400 transition-colors">Vicoa vs Claude Code Remote</a></li>
              <li><a href="/vs/superset" className="hover:text-blue-400 transition-colors">Vicoa vs Superset.sh</a></li>
            </ul>
          </div>

          {/* Use Cases + Support */}
          <div>
            <h3 className="text-white mb-4">Use Cases</h3>
            <ul className="space-y-3 text-sm mb-8">
              <li><a href="/use-cases/researchers" className="hover:text-blue-400 transition-colors">For researchers</a></li>
            </ul>
            <h3 className="text-white mb-4">Support</h3>
            <ul className="space-y-3 text-sm">
              <li><a href="/contact" className="hover:text-blue-400 transition-colors">Contact us</a></li>
              <li><a href="https://github.com/vicoa-ai/vicoa-open" className="hover:text-blue-400 transition-colors">Feature request</a></li>
            </ul>
          </div>

        </div>

        {/* Bottom Bar */}
        <div className="border-t border-gray-800 pt-8">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="flex items-center space-x-6 text-sm text-gray-400 mb-4 md:mb-0">
              <p>&copy; 2026 Vicoa. All rights reserved.</p>
              <a href="/privacy" className="hover:text-blue-400 transition-colors">Privacy Policy</a>
              <a href="/terms" className="hover:text-blue-400 transition-colors">Terms of Service</a>
            </div>
            <div className="flex items-center space-x-4">
              <a
                href="https://discord.gg/mqz4qRPV4j"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="Join our Discord community"
              >
                <DiscordIcon className="h-5 w-5" />
              </a>
              <a
                href="https://updates.vicoa.ai/"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="Subscribe to our newsletter"
              >
                <Bell className="h-5 w-5" />
              </a>
              <a
                href="mailto:hi@vicoa.ai"
                className="hover:text-blue-400 transition-colors"
                aria-label="Contact us via email"
              >
                <Mail className="h-5 w-5" />
              </a>
              <a
                href="https://github.com/vicoa-ai/vicoa-open"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="View on GitHub"
              >
                <Github className="h-5 w-5" />
              </a>
              <a
                href="https://www.linkedin.com/company/vicoa"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="Follow us on LinkedIn"
              >
                <Linkedin className="h-5 w-5" />
              </a>
              <a
                href="https://x.com/vicoaai"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="Follow us on X"
              >
                <XIcon className="h-5 w-5" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
