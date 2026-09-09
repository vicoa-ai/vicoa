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
  /** Backend `users.avatar_image_uri` — null when the user has no stored image. */
  avatarImageUri?: string | null;
  /** Backend `users.avatar_emoji` — shown when there is no stored image. */
  avatarEmoji?: string | null;
  /** Backend `users.updated_at` — cache-buster for the stable avatar URL. */
  updatedAt?: string | null;
};
