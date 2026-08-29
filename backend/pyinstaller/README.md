# PyInstaller Binary Distribution

This directory contains the PyInstaller configuration for building standalone Vicoa CLI binaries.

## Quick Start

### Prerequisites

```bash
# Install PyInstaller (in your conda/virtualenv)
pip install pyinstaller
```

### Build Binary

```bash
cd pyinstaller/
pyinstaller vicoa.spec
```

The binary will be created at `dist/vicoa` (macOS/Linux) or `dist/vicoa.exe` (Windows).

### Test Binary

```bash
./dist/vicoa --version
./dist/vicoa --help
./dist/vicoa --auth
```

## Files

- **`vicoa.spec`** - PyInstaller specification file with all dependencies and configuration
- **`vicoa_entry.py`** - Entry point wrapper that ensures proper module loading in frozen environment
- **`build/`** - Build artifacts (gitignored)
- **`dist/`** - Final binary output (gitignored)

## Platform-Specific Builds

### macOS (Apple Silicon)
```bash
# Build on M1/M2/M3 Mac
pyinstaller vicoa.spec
# Output: dist/vicoa (arm64)
```

### macOS (Intel)
```bash
# Build on Intel Mac or use macOS-13 runner in CI
pyinstaller vicoa.spec
# Output: dist/vicoa (x86_64)
```

### Linux
```bash
# Build on Linux machine
pyinstaller vicoa.spec
# Output: dist/vicoa (x86_64 ELF)
```

### Windows
```bash
# Build on Windows machine
pyinstaller vicoa.spec
# Output: dist\vicoa.exe
```

## Configuration Details

### Hidden Imports

The spec file includes hidden imports for:
- `aiohttp` and related web server components
- `websocket` for WebSocket client
- `fastmcp` for MCP protocol
- `anthropic` SDK
- `pydantic` for data validation
- All `vicoa` submodules

### Data Files

Collects data files from the vicoa package (e.g., binaries in `_bin/` directory).

### Binary Size

Expected sizes:
- macOS: ~25-30 MB
- Linux: ~25-30 MB  
- Windows: ~25-30 MB

(Smaller than the 60-80MB estimate due to efficient bundling)

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError` when running the binary:

1. Add the missing module to `hidden_imports` in `vicoa.spec`
2. Rebuild with `pyinstaller --clean vicoa.spec`

### "Invalid Choice" Error on Other Machines

If you see `argument command: invalid choice: ...` when running on a different machine:

This happens when PyInstaller's `collect_submodules()` doesn't detect dynamically imported modules (via `importlib.import_module()`). The fix:

1. Explicitly add the module to `hidden_imports` in `vicoa.spec`
2. Common culprits are CLI wrappers and headless modules
3. Rebuild with `pyinstaller --clean vicoa.spec`

**Example**: If `vicoa codex` fails, ensure `integrations.headless.codex_acp` is in `hidden_imports`.

### Data Files Missing

If data files are not included:

1. Check the `datas` collection in `vicoa.spec`
2. Manually add files: `datas=[('path/to/file', 'destination')]`

### macOS Gatekeeper Issues

If macOS blocks the binary:

```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine dist/vicoa

# Or sign the binary (requires Apple Developer Account)
codesign --force --options runtime --sign "Developer ID Application: Your Name" dist/vicoa
```

## CI/CD Integration

`.github/workflows/backend-build-binaries.yml` builds binaries for all platforms:

### Automated Builds

**Trigger on tag push**:
```bash
git tag v1.3.11
git push origin v1.3.11
```

**Manual trigger**:
1. Go to GitHub Actions tab
2. Select "Build Binaries" workflow
3. Click "Run workflow"

### What Gets Built

- **macOS arm64** (Apple Silicon)
- **macOS x64** (Intel)
- **Linux x64** - Standard ELF binary
- **Windows x64** - .exe executable

Binaries are published to npm as `@vicoa/cli` platform packages and to PyPI as
`vicoa` (see `backend/scripts/build_npm_package.py`); the CLI does **not** cut a
GitHub release (the desktop app is the only GitHub release, and it pulls the
frozen daemon from these npm platform packages). npm publish uses OIDC Trusted
Publishing (no token). macOS builds are not currently signed/notarized, so macOS
users need to run `xattr -d com.apple.quarantine vicoa` once (see Troubleshooting
above).
