# Vicoa CLI installer — Windows (PowerShell).
#
#   irm https://vicoa.ai/install.ps1 | iex
#
# Downloads the self-contained `vicoa` daemon (a frozen binary — no Python, pip,
# or npm required) from the PUBLIC npm registry, verifies its sha512 against the
# registry's signed integrity metadata, and installs it under %LOCALAPPDATA%\Vicoa
# with a launcher on your PATH. Re-run any time to upgrade.
#
# Env overrides:
#   VICOA_VERSION       pin a version (e.g. 1.7.6); default: the npm `latest` tag
#   VICOA_NPM_REGISTRY  registry base (e.g. https://registry.npmmirror.com);
#                       default: https://registry.npmjs.org
#   VICOA_INSTALL_DIR   install root; default: %LOCALAPPDATA%\Vicoa
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'  # IWR's progress bar cripples large-file throughput

function Info($m) { Write-Host $m -ForegroundColor Cyan }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }

$registry = $env:VICOA_NPM_REGISTRY
if ([string]::IsNullOrWhiteSpace($registry)) { $registry = 'https://registry.npmjs.org' }
$registry = $registry.TrimEnd('/')
$pkgEnc = '@vicoa%2Fcli'

$installDir = $env:VICOA_INSTALL_DIR
if ([string]::IsNullOrWhiteSpace($installDir)) { $installDir = Join-Path $env:LOCALAPPDATA 'Vicoa' }
$binDir = Join-Path $installDir 'bin'

# Only a win32-x64 binary is published. Windows-on-ARM runs it under x64 emulation.
$key = 'win32-x64'
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
  Warn 'Windows on ARM detected — installing the x64 build (runs under emulation).'
}
if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
  throw 'tar.exe not found (needs Windows 10 build 17063+). Update Windows or install a tar.'
}

# --- resolve version + artifact ----------------------------------------------
if (-not [string]::IsNullOrWhiteSpace($env:VICOA_VERSION)) {
  $ver = $env:VICOA_VERSION.TrimStart('v')
} else {
  Info 'Resolving latest Vicoa version…'
  $ver = (Invoke-RestMethod -UseBasicParsing "$registry/$pkgEnc/latest").version
}
if ([string]::IsNullOrWhiteSpace($ver)) { throw "could not resolve a version from $registry" }
Info "Installing Vicoa $ver ($key)…"

$manifest = Invoke-RestMethod -UseBasicParsing "$registry/$pkgEnc/$ver-$key"
$tarball = $manifest.dist.tarball
$integrity = $manifest.dist.integrity
if ([string]::IsNullOrWhiteSpace($tarball)) { throw "registry manifest for $key has no tarball URL" }

# --- download + verify + install ---------------------------------------------
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("vicoa-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
  $tgz = Join-Path $tmp 'vicoa.tgz'
  Info 'Downloading…'
  Invoke-WebRequest -UseBasicParsing -Uri $tarball -OutFile $tgz

  if (-not [string]::IsNullOrWhiteSpace($integrity)) {
    $sha = [System.Security.Cryptography.SHA512]::Create()
    $fs = [System.IO.File]::OpenRead($tgz)
    try { $hash = $sha.ComputeHash($fs) } finally { $fs.Dispose() }
    $got = 'sha512-' + [Convert]::ToBase64String($hash)
    if ($got -ne $integrity) { throw "checksum mismatch — refusing to install (expected $integrity, got $got)" }
    Info 'Checksum verified.'
  }

  Info 'Extracting…'
  $extract = Join-Path $tmp 'x'
  New-Item -ItemType Directory -Force -Path $extract | Out-Null
  & tar.exe -xf $tgz -C $extract
  if ($LASTEXITCODE -ne 0) { throw 'tar extraction failed' }
  $stagedBin = Join-Path $extract 'package\bin'
  if (-not (Test-Path (Join-Path $stagedBin 'vicoa.exe'))) { throw 'archive did not contain bin\vicoa.exe' }

  $runtime = Join-Path (Join-Path $installDir 'runtime') $ver
  if (Test-Path $runtime) { Remove-Item -Recurse -Force $runtime }
  New-Item -ItemType Directory -Force -Path (Split-Path $runtime) | Out-Null
  Move-Item $stagedBin $runtime

  # Prune other installed versions to reclaim disk.
  Get-ChildItem (Split-Path $runtime) -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $ver } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

  # Launcher on PATH — a .cmd shim so the onedir exe runs in place next to _internal.
  New-Item -ItemType Directory -Force -Path $binDir | Out-Null
  $shim = Join-Path $binDir 'vicoa.cmd'
  "@echo off`r`n`"$runtime\vicoa.exe`" %*" | Set-Content -Path $shim -Encoding ASCII

  Info "Installed vicoa $ver -> $shim"
} finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

# --- PATH --------------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $binDir) {
  [Environment]::SetEnvironmentVariable('Path', ((($userPath, $binDir) -join ';').TrimStart(';')), 'User')
  Warn "Added $binDir to your PATH (persisted for new terminals)."
}
# Always refresh THIS session's PATH too. `irm | iex` runs in-process, so this
# makes `vicoa` resolve immediately — even on a re-install where the persisted
# User PATH already contained $binDir and the block above was skipped.
if (($env:Path -split ';') -notcontains $binDir) {
  $env:Path = ($env:Path.TrimEnd(';') + ';' + $binDir)
}
Info "Done. Run 'vicoa --help' to get started."
