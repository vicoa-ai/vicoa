'use client';

/**
 * A plugin page: `/dashboard/plugin/<machine>/<plugin>/<surface>`. The shell
 * and every state live in `PluginPageView`; this route only reads the params.
 */

import { Suspense } from 'react';
import { useParams } from 'next/navigation';
import { PluginPageView } from '@/components/plugins/plugin-page-view';

export default function PluginSurfaceRoute() {
  const params = useParams<{ machineId: string; pluginId: string; surfaceId: string }>();
  const decode = (v: string | undefined) => {
    try {
      return decodeURIComponent(v ?? '');
    } catch {
      return '';
    }
  };
  // useSearchParams (inside the view) needs a Suspense boundary for prerender.
  return (
    <Suspense fallback={null}>
      <PluginPageView
        machineId={decode(params?.machineId)}
        pluginId={decode(params?.pluginId)}
        surfaceId={decode(params?.surfaceId)}
      />
    </Suspense>
  );
}
