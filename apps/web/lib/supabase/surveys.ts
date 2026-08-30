import { createClient } from '@/lib/auth/supabase-client';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';

/**
 * Store an onboarding survey answer in Supabase.
 *
 * Supabase-only: `surveys` is a table in Vicoa's own project, not part of the
 * self-hostable schema, so a built-in-provider deployment simply has nowhere to
 * put this and skips it.
 */
export async function uploadSurveyAnswer(question: string, answer: string) {
  if (isBuiltinAuth()) return;
  const supabase = createClient();
  const { data: { user } } = await supabase.auth.getUser();

  await supabase.from('surveys').upsert(
    {
      question,
      answers: [answer],
      created_at: new Date().toISOString(),
      ...(user?.id ? { user_id: user.id } : {}),
    },
    { onConflict: user?.id ? 'user_id,question' : undefined }
  );
}
