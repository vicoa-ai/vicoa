import { createClient } from './supabase-client';

// Client-side utilities for Supabase auth
export const supabaseAuthUtils = {
  // Sign in with email and password
  async signIn(email: string, password: string) {
    const supabase = createClient();
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    
    return { data, error };
  },

  // Sign up with email and password
  async signUp(email: string, password: string) {
    const supabase = createClient();
    const { data, error } = await supabase.auth.signUp({
      email,
      password
    });
    
    return { data, error };
  },

  // Sign out. 'local': this browser only — the default ('global') revokes
  // every session the user has, including the desktop app's.
  async signOut() {
    const supabase = createClient();
    const { error } = await supabase.auth.signOut({ scope: 'local' });
    return { error };
  },

  // Get current session
  async getSession() {
    const supabase = createClient();
    const { data: { session }, error } = await supabase.auth.getSession();
    return { session, error };
  },

  // Get current user
  async getUser() {
    const supabase = createClient();
    const { data: { user }, error } = await supabase.auth.getUser();
    return { user, error };
  },

  // Listen to auth state changes
  onAuthStateChange(callback: (event: string, session: any) => void) {
    const supabase = createClient();
    return supabase.auth.onAuthStateChange(callback);
  }
};

// Note: Server-side utilities should be used directly in API routes or server components
// Import createClient from './supabase-server' in those contexts