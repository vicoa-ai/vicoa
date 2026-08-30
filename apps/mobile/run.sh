#!/usr/bin/env sh
# Run the app with Supabase config injected as dart-defines, so you don't have
# to pass --dart-define=SUPABASE_URL=... on the command line every time.
#
#   ./run.sh                 # like `flutter run`
#   ./run.sh -d chrome       # extra args pass straight through to flutter run
#   ./run.sh build apk       # or any other flutter subcommand
#
# Config is read from env.json (copy env.example.json and fill it in). If that
# file is absent, it falls back to the shared secrets file used by CI/release.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$DIR/env.json"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$DIR/../../../secrets/mobile-supabase.json"
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "No Supabase config found. Copy env.example.json to env.json and fill" >&2
  echo "in your SUPABASE_URL / SUPABASE_ANON_KEY (see SELF_HOSTING.md)." >&2
  exit 1
fi

# Default to `run` unless an explicit flutter subcommand (build, test, ...) is
# given. A leading -flag is treated as an argument to `run`.
SUB=run
case "${1:-}" in
  "" | -* ) : ;;
  * ) SUB="$1"; shift ;;
esac

exec flutter "$SUB" --dart-define-from-file="$ENV_FILE" "$@"
