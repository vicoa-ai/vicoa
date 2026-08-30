# Web dashboard image for self-hosting (docker-compose.selfhost.yml).
#
# Next inlines every NEXT_PUBLIC_* value into the browser bundle at BUILD time,
# so the backend/WebSocket/Supabase endpoints are build args, not runtime env.
# Change one and you have to rebuild: `docker compose -f docker-compose.selfhost.yml build web`.
FROM node:22-alpine AS builder

WORKDIR /app

# Pin pnpm to the major that generated pnpm-lock.yaml (lockfileVersion 9.0).
# Corepack's "latest" pulls pnpm 11, which ignores dependency build scripts by
# default and fails the install with ERR_PNPM_IGNORED_BUILDS (sharp,
# @tailwindcss/oxide, esbuild need to compile native binaries) — a build that
# works locally on pnpm 9 would break only in this image.
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

# Dependencies first, so a source-only change reuses this layer.
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG NEXT_PUBLIC_BACKEND_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_VICOA_WS_URL=ws://localhost:8080/ws
# Which sign-in screen ships in the bundle: `builtin` (this stack's own
# email/password) or `supabase`. Must match the backend's AUTH_PROVIDER.
ARG NEXT_PUBLIC_AUTH_PROVIDER=builtin
ARG NEXT_PUBLIC_SUPABASE_URL=
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY=
ARG BASE_URL=http://localhost:3000
ENV NEXT_PUBLIC_BACKEND_API_URL=$NEXT_PUBLIC_BACKEND_API_URL \
    NEXT_PUBLIC_VICOA_WS_URL=$NEXT_PUBLIC_VICOA_WS_URL \
    NEXT_PUBLIC_AUTH_PROVIDER=$NEXT_PUBLIC_AUTH_PROVIDER \
    NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    BASE_URL=$BASE_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

# `output: 'standalone'` (next.config.ts) emits a self-contained server plus the
# minimal node_modules it needs, so the runtime stage carries no build tooling.
FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
