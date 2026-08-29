'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { createClient } from '@/lib/auth/supabase-client';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { getBuiltinClaims } from '@/lib/auth/builtin-client';
import { Button } from '@/components/ui/button';
import posthog from 'posthog-js';
import { CheckCircle, AlertTriangle, ExternalLink, Copy, Eye, EyeOff } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';
import { MobileDownloadCta } from '@/components/landing/cta/mobile-download-cta';

/** The signed-in user, from whichever auth provider this deployment runs. */
type CliAuthIdentity = { id: string; email?: string };

function builtinIdentity(): CliAuthIdentity | null {
  const claims = getBuiltinClaims();
  return claims ? { id: claims.sub, email: claims.email } : null;
}

async function supabaseIdentity(): Promise<CliAuthIdentity | null> {
  const { data: { session } } = await createClient().auth.getSession();
  return session ? { id: session.user.id, email: session.user.email } : null;
}

function AuthPageLogo() {
  return (
    <div className="flex justify-center mb-8">
      <Link href="/">
        <Image
          src="/images/vicoa-light.webp"
          alt="Vicoa Logo"
          width={0}
          height={0}
          sizes="100vw"
          priority
          className="h-12 w-auto opacity-90 hover:opacity-100 transition-opacity"
        />
      </Link>
    </div>
  );
}

function CliAuthContent() {
  const scrollbarHiddenStyle = `
    .scrollbar-hidden::-webkit-scrollbar {
      display: none;
    }
    .scrollbar-hidden {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }
  `;
  
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [connected, setConnected] = useState(false);
  const [copyingKey, setCopyingKey] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [generatedApiKey, setGeneratedApiKey] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  
  const port = searchParams.get('port');
  const state = searchParams.get('state');

  const maskApiKey = (apiKey: string) => {
    if (apiKey.length <= 8) return '*'.repeat(apiKey.length);
    return apiKey.slice(0, 4) + '*'.repeat(apiKey.length - 8) + apiKey.slice(-4);
  };

  useEffect(() => {
    checkAuthentication();

    // If this is a new sign-up arriving via CLI auth, preserve the onboarding flag
    // so the dashboard shows it after CLI auth completes.
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('new_user') === '1') {
      sessionStorage.setItem('vicoa_show_onboarding', 'true');
      urlParams.delete('new_user');
      const newSearch = urlParams.toString();
      window.history.replaceState({}, '', window.location.pathname + (newSearch ? '?' + newSearch : ''));
    }
  }, []);

  const checkAuthentication = async () => {
    let hasSession = false;
    try {
      const identity = isBuiltinAuth()
        ? builtinIdentity()
        : await supabaseIdentity();

      if (identity) {
        hasSession = true;
        // Identify with the user's UUID before firing the page-view event so it
        // is attributed to the identified person (and merges cross-surface with the
        // mobile app), instead of an anonymous distinct_id.
        posthog.identify(identity.id, { email: identity.email });
        setAuthenticated(true);
      } else {
        setAuthenticated(false);
      }
    } catch (err) {
      setError('Failed to check authentication status');
    } finally {
      posthog.capture('cli_auth_page_viewed', { has_port: !!port, authenticated: hasSession });
      setLoading(false);
    }
  };

  const handleAuthenticateLocalCLI = async () => {
    if (!port || !state) {
      setError('Missing port or state parameters');
      return;
    }

    posthog.capture('cli_connect_clicked', { method: 'auto' });

    try {
      setLoading(true);
      
      // Generate API key for the CLI
      const response = await fetch('/api/cli-auth/generate-key', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to generate API key');
      }

      const { apiKey } = await response.json();

      // Notify local CLI server with the API key
      const callbackUrl = `http://127.0.0.1:${port}?api_key=${encodeURIComponent(apiKey)}&state=${encodeURIComponent(state)}`;
      await fetch(callbackUrl, { mode: 'no-cors' }).catch(() => {});

      setConnected(true);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to authenticate CLI');
      setLoading(false);
    }
  };

  const handleSignIn = () => {
    // Redirect to sign-in page, then return here
    const returnUrl = encodeURIComponent(window.location.href);
    window.location.href = `/sign-in?redirect=${returnUrl}`;
  };

  const handleGenerateApiKey = async () => {
    posthog.capture('cli_connect_clicked', { method: 'manual' });
    try {
      setCopyingKey(true);
      
      const response = await fetch('/api/cli-auth/generate-key', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to generate API key');
      }

      const { apiKey } = await response.json();
      setGeneratedApiKey(apiKey);
      
    } catch (err) {
      setError('Failed to generate API key');
    } finally {
      setCopyingKey(false);
    }
  };

  const handleCopyApiKey = async () => {
    if (!generatedApiKey) return;
    
    try {
      await navigator.clipboard.writeText(generatedApiKey);
      setCopiedKey(true);
      
      setTimeout(() => setCopiedKey(false), 2000);
      
    } catch (err) {
      setError('Failed to copy API key to clipboard');
    }
  };

  if (connected) {
    return (
      <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-8 lg:px-16 bg-background">
        <div className="mx-auto w-full max-w-4xl text-center">
          <AuthPageLogo />
          <p className="text-foreground text-3xl mt-10">
            Your Vicoa CLI should be connected.
          </p>
          <p className="text-foreground text-3xl mt-5">
            Open <a href="/dashboard" className="text-primary underline">dashboard</a> to view your connected sessions.
          </p>
          <MobileDownloadCta
            title="Download Vicoa on Your Phone"
            text="Login with the same account to run a team of coding agents on the go."
          />
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
        <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
          <AuthPageLogo />
          <div className="flex items-center justify-center space-x-2 mt-4">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
            <span className="text-sm text-muted-foreground">Verifying...</span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
        <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
          <AuthPageLogo />
          <h2 className="text-xl text-destructive mb-2">Authentication Failed</h2>
          <p className="text-sm text-muted-foreground mb-6">There was a problem with the authentication process</p>
          <div className="bg-destructive/5 border border-destructive/20 rounded-lg p-4 mb-6 text-left">
            <p className="text-sm text-destructive/90">{error}</p>
          </div>
          <div className="flex flex-col gap-2 max-w-xs mx-auto">
            <Button onClick={() => window.location.reload()} className="w-full">
              Try Again
            </Button>
            <Button onClick={() => window.location.href = '/'} variant="outline" className="w-full">
              Return to Home
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: scrollbarHiddenStyle }} />
      <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
        <div className="sm:mx-auto sm:w-full sm:max-w-lg">
          <AuthPageLogo />
          <h2 className="text-center text-3xl text-foreground mb-2">Connect Vicoa CLI</h2>
          <p className="text-center text-base text-muted-foreground mb-8">
            Connect Vicoa CLI to securely remote control your coding agents
          </p>
        </div>

        <div className="sm:mx-auto sm:w-full sm:max-w-md">
            {!authenticated ? (
              <div className="text-center space-y-6">
                <Button onClick={handleSignIn} className="w-full h-12 text-base">
                  <ExternalLink className="h-5 w-5 mr-2" />
                  Sign In to Continue
                </Button>
                
                <p className="text-xs text-muted-foreground">
                  You'll be redirected back here after signing in
                </p>
              </div>
            ) : (
              <div className="space-y-8">
              
              {/* Permissions List */}
              {/* <div className="space-y-4">
                <div className="mb-6">
                  <h3 className="text-lg text-muted-foreground uppercase tracking-wide mb-6">
                    Your Account Will Be Used To:
                  </h3>
                </div>
                
                <div className="space-y-4">
                  <div className="flex items-start space-x-4">
                    <div className="flex-shrink-0 mt-1">
                      <CheckCircle className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-foreground font-medium">Access your Vicoa profile information</p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-4">
                    <div className="flex-shrink-0 mt-1">
                      <CheckCircle className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-foreground font-medium">Execute commands on your behalf</p>
                    </div>
                  </div>
                  
                  <div className="flex items-start space-x-4">
                    <div className="flex-shrink-0 mt-1">
                      <CheckCircle className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-foreground font-medium">Your privacy settings apply to CLI sessions</p>
                    </div>
                  </div>
                </div>
              </div> */}

              {/* Action Buttons */}
              <div className="space-y-4 pt-4">
                {port ? (
                  <>
                    <Button 
                      onClick={handleAuthenticateLocalCLI}
                      className="w-full h-12 text-base font-medium"
                      disabled={loading}
                    >
                      {loading ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Connecting...
                        </>
                      ) : (
                        'Connect'
                      )}
                    </Button>
                    
                    {generatedApiKey ? (
                      <div className="space-y-3 pt-4">
                        <p className="text-sm text-muted-foreground text-left">
                          Copy this API key and paste it in your terminal:
                        </p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 font-mono text-sm bg-muted rounded-md overflow-x-auto scrollbar-hidden h-12 flex items-center px-3">
                            <div className="whitespace-nowrap">
                              {showApiKey ? generatedApiKey : maskApiKey(generatedApiKey)}
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowApiKey(!showApiKey)}
                            className="h-12 w-12"
                          >
                            {showApiKey ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleCopyApiKey}
                            className="h-12 w-12"
                          >
                            {copiedKey ? (
                              <CheckCircle className="h-4 w-4 text-green-500" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                        {/* <p className="text-sm text-muted-foreground text-left">
                          Or use CLI: <code className="px-1 py-0.5 bg-muted rounded">vicoa auth --api-key [YOUR_KEY]</code>
                        </p> */}
                      </div>
                    ) : (
                      <Button 
                        onClick={handleGenerateApiKey}
                        variant="outline"
                        className="w-full h-12 text-base font-medium"
                        disabled={copyingKey}
                      >
                        {copyingKey ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current mr-2"></div>
                            Generating...
                          </>
                        ) : (
                          <>
                            <Copy className="h-4 w-4 mr-2" />
                            Generate API Key
                          </>
                        )}
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    {generatedApiKey ? (
                      <div className="space-y-3">
                        <p className="text-sm text-muted-foreground text-left">
                          Copy this API key and paste it in your terminal
                        </p>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 font-mono text-sm bg-muted rounded-md overflow-x-auto scrollbar-hidden h-12 flex items-center px-3">
                            <div className="whitespace-nowrap">
                              {showApiKey ? generatedApiKey : maskApiKey(generatedApiKey)}
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowApiKey(!showApiKey)}
                            className="h-12 w-12"
                          >
                            {showApiKey ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleCopyApiKey}
                            className="h-12 w-12"
                          >
                            {copiedKey ? (
                              <CheckCircle className="h-4 w-4 text-green-500" />
                            ) : (
                              <Copy className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                        <p className="text-xs text-muted-foreground text-left">
                          Or use CLI: <code className="px-1 py-0.5 bg-muted rounded">vicoa auth --api-key [YOUR_KEY]</code>
                        </p>
                      </div>
                    ) : (
                      <Button 
                        onClick={handleGenerateApiKey}
                        className="w-full h-12 text-base font-medium"
                        disabled={copyingKey}
                      >
                        {copyingKey ? (
                          <>
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                            Generating...
                          </>
                        ) : (
                          'Generate API Key'
                        )}
                      </Button>
                    )}
                  </>
                )}
                
                {!generatedApiKey && (
                  <Button 
                    onClick={() => window.close()}
                    variant="ghost" 
                    className="w-full h-12 text-base text-muted-foreground hover:text-foreground"
                  >
                    Decline
                  </Button>
                )}
              </div>

              {/* Help text for manual usage */}
              {!port && (
                <div className="text-center pt-4 border-t border-border">
                  <p className="text-sm text-muted-foreground mb-2">
                    For manual setup or remote usage
                  </p>
                  <p className="text-xs text-muted-foreground">
                    The API key will be copied to your clipboard. Use it with: 
                    <code className="ml-1 px-1 py-0.5 bg-muted rounded text-xs">vicoa auth --api-key [YOUR_KEY]</code>
                  </p>
                </div>
              )}
              </div>
            )}
        </div>
      </div>
    </>
  );
}

export default function CliAuthPage() {
  return (
    <Suspense fallback={
      <div className="min-h-[100dvh] flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-background">
        <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
          <AuthPageLogo />
          <div className="flex items-center justify-center space-x-2 mt-4">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
            <span className="text-sm text-muted-foreground">Loading...</span>
          </div>
        </div>
      </div>
    }>
      <CliAuthContent />
    </Suspense>
  );
}
