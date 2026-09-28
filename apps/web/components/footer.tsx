import Image from 'next/image';
import { Shield, Linkedin, Bell, Mail, Star } from 'lucide-react';

import { DiscordIcon } from '@/components/discord-icon';
import { GithubIcon } from '@/components/github-icon';
import { DISCORD_INVITE_URL, GITHUB_ISSUES_URL, GITHUB_REPO_URL } from '@/lib/constants/links';

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
            <p className="text-gray-400 mb-4 text-sm leading-relaxed">
              Code with AI. Anywhere.
            </p>
            <a
              href={GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 mb-6 rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-300 hover:border-gray-500 hover:text-white transition-colors"
            >
              <GithubIcon className="h-4 w-4" />
              <span>Star on Github</span>
              <Star className="h-3.5 w-3.5" />
            </a>
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
              <li><a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer" className="hover:text-blue-400 transition-colors">Source code</a></li>
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
              <li><a href="/vs/paseo" className="hover:text-blue-400 transition-colors">Vicoa vs Paseo</a></li>
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
              <li><a href={GITHUB_ISSUES_URL} target="_blank" rel="noopener noreferrer" className="hover:text-blue-400 transition-colors">Feature request</a></li>
              <li><a href={GITHUB_ISSUES_URL} target="_blank" rel="noopener noreferrer" className="hover:text-blue-400 transition-colors">Report a bug</a></li>
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
                href={DISCORD_INVITE_URL}
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
                href={GITHUB_REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-400 transition-colors"
                aria-label="View on GitHub"
              >
                <GithubIcon className="h-5 w-5" />
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
