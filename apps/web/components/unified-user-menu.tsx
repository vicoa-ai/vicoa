'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { LogOut, Home, Key, ChevronDown, User as UserIcon } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { signOutBrowser } from '@/lib/auth/sign-out';
import { useRouter } from 'next/navigation';
import type { AuthUser } from '@/lib/auth/user';
import useSWR, { mutate } from 'swr';

const fetcher = (url: string) => fetch(url).then((res) => {
  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error('Failed to fetch');
  }
  return res.json();
});

interface UnifiedUserMenuProps {
  variant?: 'avatar' | 'button';
}

export function UnifiedUserMenu({ variant = 'avatar' }: UnifiedUserMenuProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  
  const { data: user } = useSWR<AuthUser>('/api/supabase-user', fetcher);

  const router = useRouter();

  async function handleSignOut() {
    setIsSigningOut(true);
    try {
      await signOutBrowser();
      mutate('/api/supabase-user');
      router.push('/');
    } catch (error) {
      console.error('Sign out error:', error);
    } finally {
      setIsSigningOut(false);
    }
  }

  if (!user) {
    return (
      <div className="flex items-center gap-3">
        {/* <Link
          href="/pricing"
          className="text-sm font-medium text-foreground/80 hover:text-foreground"
        >
          Pricing
        </Link> */}
        <Button asChild className="rounded-full h-10">
          <Link href="/sign-up">Get Started</Link>
        </Button>
      </div>
    );
  }

  const getUserDisplayName = (user: any) => {
    return user?.email || user?.name || 'User';
  };

  const getUserInitials = (user: any) => {
    const name = getUserDisplayName(user);
    return name.split(' ').map((n: string) => n[0]).join('').substring(0, 2).toUpperCase();
  };

  if (variant === 'button') {
    return (
      <Button asChild variant="outline" className="rounded-full h-10">
        <Link href="/dashboard">Dashboard</Link>
      </Button>
    );
  }

  return (
    <DropdownMenu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
      <DropdownMenuTrigger asChild>
        <Avatar className="cursor-pointer size-9">
          <AvatarImage 
            src={`https://avatar.vercel.sh/${user.email}`} 
            alt={getUserDisplayName(user)} 
          />
          <AvatarFallback>
            {getUserInitials(user)}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="flex flex-col gap-1">
        <div className="px-2 py-1.5 text-sm text-muted-foreground border-b">
          <div className="font-medium text-foreground">{getUserDisplayName(user)}</div>
        </div>
        <DropdownMenuItem className="cursor-pointer">
          <Link href="/dashboard" className="flex w-full items-center">
            <Home className="mr-2 h-4 w-4" />
            <span>Dashboard</span>
          </Link>
        </DropdownMenuItem>        
        <DropdownMenuItem className="cursor-pointer">
          <Link href="/dashboard/api-keys" className="flex w-full items-center">
            <Key className="mr-2 h-4 w-4" />
            <span>API Keys</span>
          </Link>
        </DropdownMenuItem>
        <form action={handleSignOut} className="w-full">
          <button type="submit" className="flex w-full" disabled={isSigningOut}>
            <DropdownMenuItem className="w-full flex-1 cursor-pointer">
              <LogOut className="mr-2 h-4 w-4" />
              <span>{isSigningOut ? 'Signing out...' : 'Sign out'}</span>
            </DropdownMenuItem>
          </button>
        </form>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
