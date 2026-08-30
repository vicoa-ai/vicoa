#!/usr/bin/env bash
set -euo pipefail

echo "[cibw_before_build] Starting pre-build for Codex binary"

# Detect OS/ARCH first, so we can early-exit if a reused binary already exists
OS="${OS:-$(uname -s)}"
ARCH="${ARCH:-$(uname -m)}"

ARCH_TAG=""
BIN_EXT=""
case "$OS" in
  Darwin)
    if [[ "$ARCH" == "arm64" || "$ARCH" == "aarch64" ]]; then
      ARCH_TAG="darwin-arm64"
    else
      ARCH_TAG="darwin-x64"
    fi
    ;;
  Linux)
    ARCH_TAG="linux-x64"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    ARCH_TAG="win-x64"
    BIN_EXT=".exe"
    ;;
  *)
    echo "[cibw_before_build] Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

PACKAGE_ROOT="vicoa"
if [[ -d "src/vicoa" ]]; then
  PACKAGE_ROOT="src/vicoa"
fi

DEST_DIR="${PACKAGE_ROOT}/_bin/codex/${ARCH_TAG}"
DEST="${DEST_DIR}/codex${BIN_EXT}"

# If a binary is already present (e.g., fetched from a previous release), reuse it
if [[ -f "$DEST" ]]; then
  echo "[cibw_before_build] Reusing pre-populated Codex binary at ${DEST}"
  if [[ -z "$BIN_EXT" ]]; then
    chmod +x "${DEST}" || true
  fi
  echo "[cibw_before_build] Done (reused)"
  exit 0
fi

# Ensure curl exists (manylinux images typically have it; add fallback)
if ! command -v curl >/dev/null 2>&1; then
  echo "[cibw_before_build] curl not found; attempting to install (yum/apk)" >&2
  if command -v yum >/dev/null 2>&1; then
    yum -y install curl || true
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache curl || true
  fi
fi

# Install Rust toolchain (if not already present)
if [ ! -x "$HOME/.cargo/bin/cargo" ]; then
  echo "[cibw_before_build] Installing Rust via rustup"
  curl https://sh.rustup.rs -sSf | sh -s -- -y
fi
source "$HOME/.cargo/env"
rustc -V || true
cargo -V || true

RUST_TOOLCHAIN=""
if [[ -f "src/integrations/cli_wrappers/codex/codex-rs/rust-toolchain.toml" ]]; then
  RUST_TOOLCHAIN="$(sed -n 's/^channel = "\(.*\)"/\1/p' src/integrations/cli_wrappers/codex/codex-rs/rust-toolchain.toml | head -n1 || true)"
fi

if [[ -n "$RUST_TOOLCHAIN" ]]; then
  echo "[cibw_before_build] Ensuring Rust toolchain ${RUST_TOOLCHAIN}"
  rustup toolchain install "${RUST_TOOLCHAIN}" --profile minimal
fi

# On Linux, ensure OpenSSL headers and pkg-config are available
if [[ "$OS" == "Linux" ]]; then
  echo "[cibw_before_build] Installing OpenSSL, pkg-config, and libcap dev headers on Linux"
  if command -v yum >/dev/null 2>&1; then
    yum -y install openssl openssl-libs openssl-devel pkgconfig zlib-devel libcap-devel || true
  elif command -v microdnf >/dev/null 2>&1; then
    microdnf -y install openssl openssl-libs openssl-devel pkgconfig zlib-devel libcap-devel || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf -y install openssl openssl-libs openssl-devel pkgconfig zlib-devel libcap-devel || true
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y libssl-dev pkg-config zlib1g-dev libcap-dev || true
  fi

  # codex-rs/linux-sandbox build.rs requires libcap via pkg-config.
  if ! pkg-config --exists libcap; then
    echo "[cibw_before_build] ERROR: libcap pkg-config metadata not found (pkg-config --exists libcap failed)." >&2
    echo "[cibw_before_build] Install libcap development headers before cargo build." >&2
    exit 1
  fi
fi

# Build codex-cli (Rust) in release mode as a fallback
echo "[cibw_before_build] Building codex-cli (fallback build)"
pushd src/integrations/cli_wrappers/codex/codex-rs >/dev/null

# Pass through the externally selected Codex version, and use CI-friendly release
# overrides so manylinux builds stay within memory limits.
if [[ -n "${CODEX_BUILD_VERSION:-}" ]]; then
  export CODEX_BUILD_VERSION
  echo "[cibw_before_build] Using CODEX_BUILD_VERSION=${CODEX_BUILD_VERSION}"
fi
export CARGO_NET_GIT_FETCH_WITH_CLI="${CARGO_NET_GIT_FETCH_WITH_CLI:-true}"
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
export CARGO_PROFILE_RELEASE_LTO="${CARGO_PROFILE_RELEASE_LTO:-off}"
export CARGO_PROFILE_RELEASE_CODEGEN_UNITS="${CARGO_PROFILE_RELEASE_CODEGEN_UNITS:-16}"

if [[ -n "$RUST_TOOLCHAIN" ]]; then
  cargo +"${RUST_TOOLCHAIN}" build --release -p codex-cli
else
  cargo build --release -p codex-cli
fi

popd >/dev/null

# Compute path to built binary. When cross-compiling (CARGO_BUILD_TARGET set,
# e.g. macos-15 ARM runner producing x86_64-apple-darwin), cargo writes output
# under target/${CARGO_BUILD_TARGET}/release/; otherwise it's target/release/.
if [[ -n "${CARGO_BUILD_TARGET:-}" ]]; then
  SRC="src/integrations/cli_wrappers/codex/codex-rs/target/${CARGO_BUILD_TARGET}/release/codex${BIN_EXT}"
else
  SRC="src/integrations/cli_wrappers/codex/codex-rs/target/release/codex${BIN_EXT}"
fi

# Install built binary into wheel payload
echo "[cibw_before_build] Installing Codex binary to ${DEST}"
mkdir -p "${DEST_DIR}"
cp "${SRC}" "${DEST}"
if [[ -z "$BIN_EXT" ]]; then
  chmod +x "${DEST}"
fi

echo "[cibw_before_build] Done"
