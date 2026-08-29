'use client';

import { useMemo, useState, useEffect, type FormEvent, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { Loader2, LogOut, Trash2, PlayCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { createClient } from '@/lib/auth/supabase-client';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { signOutBrowser } from '@/lib/auth/sign-out';
import { getBackendAPI } from '@/lib/backend-api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog';
import { BillingSettingsSection } from './billing-settings-section';
import { OnboardingModal, ONBOARDING_KEY } from '@/components/dashboard/onboarding-modal';
import { DesktopSettings } from '@/components/dashboard/desktop-settings';
import { ProvidersSettingsSection } from '@/components/dashboard/providers-settings-section';
import { MachinesSettingsSection } from '@/components/dashboard/machines-settings-section';

// Desktop builds swap the whole settings surface: the shell renders the
// settings nav in the left panel and this page renders only the tab content.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error('Failed to fetch');
  }
  return res.json();
});

type SupabaseUser = {
  id: string;
  name: string;
  email: string;
  createdAt: string;
  role?: string;
};

const tabs = [
  { id: 'profile', label: 'Profile' },
  { id: 'providers', label: 'Providers' },
  { id: 'machines', label: 'Machines' },
  { id: 'billing', label: 'Billing' },
  { id: 'account', label: 'Account' }
] as const;

const defaultTab = tabs[0].id;

function SettingsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: supabaseUser } = useSWR<SupabaseUser | null>('/api/supabase-user', fetcher);

  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showOnboarding, setShowOnboarding] = useState(false);

  const handleReplayOnboarding = () => {
    localStorage.removeItem(ONBOARDING_KEY);
    setShowOnboarding(true);
  };

  const activeTab = useMemo(() => {
    const tabFromParams = searchParams.get('tab');
    return tabs.some((tab) => tab.id === tabFromParams) ? tabFromParams! : defaultTab;
  }, [searchParams]);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await signOutBrowser();
      router.push('/');
    } catch (error) {
      console.error('Failed to sign out', error);
    } finally {
      setIsLoggingOut(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (isDeletingAccount) return;
    setIsDeletingAccount(true);
    setDeleteError(null);
    try {
      const backendAPI = getBackendAPI(true);
      await backendAPI.deleteUserAccount();

      await signOutBrowser();
      setIsDeleteDialogOpen(false);
      router.push('/');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete account.';
      setDeleteError(message);
    } finally {
      setIsDeletingAccount(false);
    }
  };

  const getNavHref = (tabId: string) => {
    if (tabId === defaultTab) {
      return '/dashboard/settings';
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', tabId);
    return `/dashboard/settings?${params.toString()}`;
  };


  return (
    <>
      {showOnboarding && <OnboardingModal forceShow isOnboard={false} onClose={() => setShowOnboarding(false)} />}
    <div className="flex-1 font-mono">
      <div className="w-full max-w-5xl mx-auto px-4 lg:px-6 py-6 lg:py-10">
        <div className="mb-8">
          <h1 className="text-2xl tracking-tight text-foreground">
            Settings
          </h1>
          {/* <p className="text-sm text-muted-foreground mt-2">
            Manage your profile, account access, and billing information.
          </p> */}
        </div>
        <div className="flex flex-col lg:flex-row gap-8">
          <nav className="lg:w-48 shrink-0">
            <div className="rounded-xl border border-border/70 bg-card p-1">
              {tabs.map((tab) => (
                <Link
                  key={tab.id}
                  href={getNavHref(tab.id)}
                  className={cn(
                    'block rounded-lg px-4 py-2 text-sm transition-colors',
                    activeTab === tab.id
                      ? 'bg-muted text-foreground font-medium'
                      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                  )}
                  scroll={false}
                >
                  {tab.label}
                </Link>
              ))}
            </div>
          </nav>
          <div className="flex-1 space-y-8">
            {activeTab === 'profile' && (
              <Card>
                <CardHeader>
                  <CardTitle>Profile</CardTitle>
                </CardHeader>
                <CardContent>
                  {typeof supabaseUser === 'undefined' ? (
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading profile information...
                    </div>
                  ) : supabaseUser ? (
                    <SupabaseProfileForm
                      user={supabaseUser}
                      onRefresh={() => mutate('/api/supabase-user')}
                    />
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      Profile information is unavailable.
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {activeTab === 'account' && (
              <Card>
                <CardHeader>
                  <CardTitle>Account</CardTitle>
                </CardHeader>
                <CardContent className="space-y-8">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <p className="text-sm text-foreground">Show feature tour</p>
                    <Button onClick={handleReplayOnboarding} variant="outline">
                      <PlayCircle className="mr-2 h-4 w-4" />
                      Show
                    </Button>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <p className="text-sm text-foreground">Log out of current device</p>
                    <Button onClick={handleLogout} variant="outline" disabled={isLoggingOut}>
                      {isLoggingOut ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Logging out
                        </>
                      ) : (
                        <>
                          <LogOut className="mr-2 h-4 w-4" />
                          Log out
                        </>
                      )}
                    </Button>
                  </div>


                  <div className="space-y-4 pt-2">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                          <div className="space-y-1">
                            <p className="text-sm text-foreground">Delete your account</p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            className="text-foreground"
                            aria-label="Delete account"
                            onClick={() => {
                              setDeleteError(null);
                              setIsDeleteDialogOpen(true);
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>

                        <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
                          <DialogContent>
                            <DialogHeader>
                              <DialogTitle>Delete account</DialogTitle>
                              <DialogDescription>
                                This action is permanent and cannot be undone. Are you sure you want
                                to continue?
                              </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-4">
                              {deleteError && (
                                <p className="text-sm text-destructive">{deleteError}</p>
                              )}
                              <DialogFooter>
                                <Button
                                  type="button"
                                  variant="outline"
                                  onClick={() => {
                                    if (!isDeletingAccount) {
                                      setDeleteError(null);
                                      setIsDeleteDialogOpen(false);
                                    }
                                  }}
                                  disabled={isDeletingAccount}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  type="button"
                                  variant="destructive"
                                  onClick={handleDeleteAccount}
                                  disabled={isDeletingAccount}
                                >
                                  {isDeletingAccount ? (
                                    <>
                                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                      Deleting
                                    </>
                                  ) : (
                                    'Delete account'
                                  )}
                                </Button>
                              </DialogFooter>
                            </div>
                          </DialogContent>
                        </Dialog>
                  </div>
                </CardContent>
              </Card>
            )}

            {activeTab === 'providers' && <ProvidersSettingsSection />}

            {activeTab === 'machines' && <MachinesSettingsSection />}

            {activeTab === 'billing' && (
              <BillingSettingsSection checkoutSuccess={searchParams.get('checkout') === 'success'} />
            )}
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

export default function SettingsPage() {
  if (IS_DESKTOP) {
    return (
      <Suspense fallback={null}>
        <DesktopSettings />
      </Suspense>
    );
  }
  return (
    <Suspense fallback={
      <div className="flex-1 font-mono">
        <div className="w-full max-w-5xl mx-auto px-4 lg:px-6 py-6 lg:py-10">
          <div className="mb-8">
            <h1 className="text-2xl tracking-tight text-foreground">
              Settings
            </h1>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading settings...
          </div>
        </div>
      </div>
    }>
      <SettingsContent />
    </Suspense>
  );
}

type SupabaseProfileFormProps = {
  user: SupabaseUser;
  onRefresh: () => Promise<unknown>;
};

function SupabaseProfileForm({ user, onRefresh }: SupabaseProfileFormProps) {
  const [name, setName] = useState(user.name ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    setName(user.name ?? '');
  }, [user.name]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('Name is required.');
      setSuccess(null);
      return;
    }

    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      // The `profiles` table is Supabase's copy of the display name. A
      // built-in-provider deployment has no Supabase at all — the backend
      // `syncUser` call below is the only write it needs.
      if (!isBuiltinAuth()) {
        const supabase = createClient();
        const timestamp = new Date().toISOString();

        const { error: upsertError } = await supabase
          .from('profiles')
          .upsert(
            { id: user.id, display_name: trimmedName, updated_at: timestamp },
            { onConflict: 'id' }
          );

        if (upsertError) {
          const message = upsertError.message.toLowerCase();
          if (message.includes('column') && message.includes('id')) {
            const { error: fallbackError } = await supabase
              .from('profiles')
              .upsert(
                { user_id: user.id, display_name: trimmedName, updated_at: timestamp },
                { onConflict: 'user_id' }
              );
            if (fallbackError) {
              throw new Error(fallbackError.message);
            }
          } else {
            throw new Error(upsertError.message);
          }
        }
      }

      const backendAPI = getBackendAPI(true);
      try {
        await backendAPI.syncUser({
          id: user.id,
          email: user.email,
          display_name: trimmedName
        });
      } catch (apiError) {
        const detail =
          apiError instanceof Error && apiError.message
            ? apiError.message
            : 'Failed to sync account.';
        throw new Error(detail);
      }

      try {
        await onRefresh();
      } catch (refreshError) {
        console.error('Failed to refresh Supabase user cache:', refreshError);
      }
      setName(trimmedName);
      setSuccess('Profile updated successfully.');
    } catch (syncError) {
      const message = syncError instanceof Error ? syncError.message : 'Failed to save changes.';
      setError(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid gap-4">
        <div className="space-y-2">
          <Label htmlFor="supabase-name">Full name</Label>
          <Input
            id="supabase-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Enter your name"
            required
            className="border-transparent bg-muted focus-visible:border-border focus-visible:ring-0 shadow-none"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="supabase-email">Email</Label>
          <Input
            id="supabase-email"
            value={user.email}
            disabled
            className="border-0 bg-muted focus-visible:ring-0 focus-visible:border-0 shadow-none"
          />
        </div>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-500">{success}</p>}
      <Button type="submit" disabled={isSaving}>
        {isSaving ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Saving
          </>
        ) : (
          'Save changes'
        )}
      </Button>
    </form>
  );
}
