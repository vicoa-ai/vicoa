#!/bin/sh
# Vicoa CLI installer — macOS & Linux.
#
#   curl -fsSL https://vicoa.ai/install.sh | sh
#
# Downloads the self-contained `vicoa` daemon (a frozen PyInstaller binary — no
# Python, pip, or npm required) from the PUBLIC npm registry, verifies its
# sha512 against the registry's signed integrity metadata, and installs it under
# ~/.vicoa with a launcher on your PATH. Re-run any time to upgrade.
#
# Env overrides:
#   VICOA_VERSION       pin a version (e.g. 1.7.6); default: the npm `latest` tag
#   VICOA_NPM_REGISTRY  registry base (e.g. https://registry.npmmirror.com for a
#                       China-friendly mirror); default: https://registry.npmjs.org
#   VICOA_INSTALL_DIR   install root; default: $HOME/.vicoa
set -eu

PKG_ENC='@vicoa%2Fcli'
REGISTRY="${VICOA_NPM_REGISTRY:-https://registry.npmjs.org}"
REGISTRY="${REGISTRY%/}"
INSTALL_DIR="${VICOA_INSTALL_DIR:-$HOME/.vicoa}"
BIN_DIR="$HOME/.local/bin"

info() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- tooling -----------------------------------------------------------------
if command -v curl >/dev/null 2>&1; then
  http_get() { curl -fL --proto '=https' --tlsv1.2 -o "$2" "$1"; }
  http_read() { curl -fsSL --proto '=https' --tlsv1.2 "$1"; }
elif command -v wget >/dev/null 2>&1; then
  http_get() { wget -qO "$2" "$1"; }
  http_read() { wget -qO- "$1"; }
else
  die "need curl or wget"
fi
command -v tar >/dev/null 2>&1 || die "need tar"

# Pull one "field":"value" string out of a SINGLE-version registry manifest.
json_str() { grep -o "\"$1\":\"[^\"]*\"" | head -1 | sed "s/.*\":\"//;s/\"$//"; }

# --- platform ----------------------------------------------------------------
os="$(uname -s)"; arch="$(uname -m)"
case "$os" in
  Darwin) plat=darwin ;;
  Linux)  plat=linux ;;
  *) die "unsupported OS: $os (Windows: use install.ps1)" ;;
esac
case "$arch" in
  arm64|aarch64) cpu=arm64 ;;
  x86_64|amd64)  cpu=x64 ;;
  *) die "unsupported CPU: $arch" ;;
esac
KEY="$plat-$cpu"
case "$KEY" in
  darwin-arm64|darwin-x64|linux-x64) : ;;
  *) die "no Vicoa binary published for $KEY yet" ;;
esac

# --- resolve version + artifact ----------------------------------------------
if [ -n "${VICOA_VERSION:-}" ]; then
  VER="${VICOA_VERSION#v}"
else
  info "Resolving latest Vicoa version…"
  VER="$(http_read "$REGISTRY/$PKG_ENC/latest" | json_str version)"
  [ -n "$VER" ] || die "could not resolve the latest version from $REGISTRY"
fi
info "Installing Vicoa $VER ($KEY)…"

MANIFEST="$(http_read "$REGISTRY/$PKG_ENC/$VER-$KEY")" || die "no published binary for $VER-$KEY"
TARBALL="$(printf '%s' "$MANIFEST" | json_str tarball)"
INTEGRITY="$(printf '%s' "$MANIFEST" | json_str integrity)"
[ -n "$TARBALL" ] || die "registry manifest for $KEY has no tarball URL"

# --- download + verify + install ---------------------------------------------
tmp="$(mktemp -d "${TMPDIR:-/tmp}/vicoa.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT INT TERM
tgz="$tmp/vicoa.tgz"

info "Downloading…"
http_get "$TARBALL" "$tgz"

if [ -n "$INTEGRITY" ] && command -v openssl >/dev/null 2>&1; then
  got="sha512-$(openssl dgst -sha512 -binary "$tgz" | openssl base64 -A)"
  [ "$got" = "$INTEGRITY" ] || die "checksum mismatch — refusing to install (expected $INTEGRITY, got $got)"
  info "Checksum verified."
else
  warn "openssl not found — skipping checksum verification (download was over HTTPS)."
fi

info "Extracting…"
tar -xzf "$tgz" -C "$tmp"
[ -x "$tmp/package/bin/vicoa" ] || die "archive did not contain bin/vicoa"

runtime="$INSTALL_DIR/runtime/$VER"
rm -rf "$runtime"
mkdir -p "$INSTALL_DIR/runtime"
mv "$tmp/package/bin" "$runtime"
chmod +x "$runtime/vicoa" 2>/dev/null || true
# `current` symlink so the launcher survives version bumps (PyInstaller resolves
# _internal against the real dir, so a dir symlink is fine).
ln -sfn "$VER" "$INSTALL_DIR/runtime/current"

# Launcher on PATH — a wrapper (not a symlink) so the onedir exe always runs in
# place next to its _internal/.
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/vicoa" <<EOF
#!/bin/sh
exec "$INSTALL_DIR/runtime/current/vicoa" "\$@"
EOF
chmod +x "$BIN_DIR/vicoa"

info "Installed vicoa $VER -> $BIN_DIR/vicoa"

case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *)
    warn "$BIN_DIR is not on your PATH. Add this to your shell profile:"
    warn "  export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

info "Done. Run 'vicoa --help' to get started."
