# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Collect all vicoa and integrations submodules
# Match pyproject.toml package includes
hidden_imports = (
    collect_submodules('vicoa') +
    collect_submodules('integrations') +
    collect_submodules('protocol') +
    collect_submodules('servers.mcp') +
    collect_submodules('servers.shared') +
    collect_submodules('fastmcp') +
    # Desktop local server (vicoa.local_server): FastAPI app served by uvicorn.
    # uvicorn and websockets pick protocol/loop implementations via dynamic
    # imports (uvicorn.loops.*, uvicorn.protocols.*, websockets negotiation),
    # so static analysis misses them without explicit collection. The
    # vicoa.local_server / vicoa.terminal packages themselves are covered by
    # collect_submodules('vicoa') above.
    collect_submodules('uvicorn') +
    collect_submodules('websockets') +
    [
        'fastapi',
        # Web & network dependencies
        'aiohttp',
        'aiohttp.web',
        'aiohttp.client',
        'websocket',
        'fastmcp',
        'anthropic',
        'pydantic',
        'pydantic_core',
        'requests',
        'urllib3',
        'certifi',
        'pathspec',
        'claude_agent_sdk',

        # Explicitly include modules used in frozen mode direct imports
        'integrations.cli_wrappers.claude_code.wrapper',
        'integrations.cli_wrappers.claude_code.__main__',
        'servers.mcp.stdio_server',
    ]
)

# Collect data files (binaries in _bin/, any config files)
# copy_metadata('fastmcp') is required because fastmcp.__init__ calls
# importlib.metadata.version("fastmcp") which needs the dist-info directory.
datas = collect_data_files('vicoa') + collect_data_files('integrations') + copy_metadata('fastmcp')

# The vendored Codex CLI Rust workspace (integrations/cli_wrappers/codex/
# codex-rs) is dev-only source: the daemon never reads it at runtime, and
# collect_data_files sweeps in whatever is on disk — including its target/
# build directory, which reaches tens of GB after a cargo build and once
# ballooned the desktop dmg from ~300 MB to 8 GB.
datas = [
    (src, dest)
    for src, dest in datas
    if 'codex-rs' not in str(src).replace('\\', '/')
]

a = Analysis(
    ['vicoa_entry.py'],
    pathex=['../src'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Defense in depth: the tests dir under integrations/headless/ is a
        # non-package (no __init__.py) so collect_submodules('integrations')
        # already skips it. Listing it here keeps the build green even if
        # someone later adds an __init__.py.
        'integrations.headless.tests',
        'integrations.headless.tests.*',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# onedir mode: files live in dist/vicoa/, no extraction on every startup
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='vicoa',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='vicoa',
)
