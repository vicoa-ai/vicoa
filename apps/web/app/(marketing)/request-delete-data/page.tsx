import type { Metadata } from 'next';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata('/request-delete-data', {
  title: 'Request Delete Data | Vicoa',
  description: 'Request deletion of your data by contacting Vicoa support.',
});

export default function RequestDeleteDataPage() {
  return (
    <main className="bg-background">
      <div className="bg-muted/30">
        <div className="container mx-auto px-4 pt-16 pb-8 max-w-7xl text-center">
          <h1 className="text-4xl md:text-5xl">Request Delete Data</h1>
        </div>
      </div>

      <div className="container mx-auto px-4 pt-12 pb-48 max-w-7xl">
        <div className="max-w-3xl mx-auto rounded-2xl border border-border bg-card p-8 md:p-10 shadow-sm">
          <p className="text-base md:text-lg text-muted-foreground leading-8">
            You can delete your account directly in the mobile apps or the web application.
          </p>
          <p className="text-base md:text-lg text-muted-foreground leading-8 mt-6">
            You can also request to delete your data by emailing us at{' '}
            <a href="mailto:hi@vicoa.ai" className="text-foreground underline underline-offset-4">
              hi@vicoa.ai
            </a>
            , as stated in the privacy policy. Please include the specific details of the data you wish to delete, or
            mention if you would like to delete all of your data.
          </p>
        </div>
      </div>

    </main>
  );
}
