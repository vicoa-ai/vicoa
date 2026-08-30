import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Vitest setup for vicoa-web (websocket-migration plan §4 Phase 0 item 11).
// Unblocks the WebSocket client merge/dedupe unit tests, which are written as
// pure functions so they need no DOM — `node` environment is sufficient.
export default defineConfig({
  resolve: {
    // Mirror the tsconfig `@/*` -> `./*` path alias.
    alias: {
      '@': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['**/*.test.ts', '**/*.test.tsx'],
    // The web suite lives in lib/ and components/ only.
    exclude: ['**/node_modules/**', '.next/**'],
  },
});
