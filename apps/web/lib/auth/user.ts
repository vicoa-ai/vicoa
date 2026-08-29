/**
 * Shape returned by `GET /api/supabase-user` — the app's single source of
 * user identity now that the next-saas-starter Drizzle/JWT template is gone.
 * Components only read `email` / `name` plus truthiness, so this stays minimal.
 */
export type AuthUser = {
  id?: string;
  email?: string | null;
  name?: string | null;
  createdAt?: string;
  role?: string;
};
