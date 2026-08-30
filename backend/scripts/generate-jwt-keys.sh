#!/usr/bin/env bash
# Generate the RS256 keypair Vicoa signs agent API keys with.
#
#   ./backend/scripts/generate-jwt-keys.sh [output-dir]     # default: selfhost/keys
#
# The backend mints agent JWTs with the private key and every process verifies
# with the public one, so both must be present and must match. Point the backend
# at them with JWT_PRIVATE_KEY_FILE / JWT_PUBLIC_KEY_FILE (what
# docker-compose.selfhost.yml does), or paste the PEM contents into
# JWT_PRIVATE_KEY / JWT_PUBLIC_KEY.
#
# Rotating these invalidates every issued API key — clients have to re-auth.
set -euo pipefail

out_dir="${1:-selfhost/keys}"
private="$out_dir/jwt_private.pem"
public="$out_dir/jwt_public.pem"

if [[ -e "$private" || -e "$public" ]]; then
  echo "Refusing to overwrite existing keys in $out_dir" >&2
  echo "Delete them first if you really mean to rotate." >&2
  exit 1
fi

mkdir -p "$out_dir"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$private" >/dev/null 2>&1
openssl rsa -in "$private" -pubout -out "$public" >/dev/null 2>&1
chmod 600 "$private"
chmod 644 "$public"

echo "Wrote:"
echo "  $private  (secret — never commit)"
echo "  $public"
