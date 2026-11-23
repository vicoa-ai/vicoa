"""Agent CLI builds this daemon release may download. Generated; do not edit.

Regenerate with ``scripts/pin_agent_releases.py`` when bumping a version.
Each asset is the vendor's own build with the SHA-256 and size its release
metadata publishes, so a download is accepted only if it is exactly that build.
"""

from __future__ import annotations

from vicoa.agent_release_types import PinnedRelease, ReleaseAsset

PINNED_RELEASES: dict[str, PinnedRelease] = {
    "claude": PinnedRelease(
        agent="claude",
        version="2.1.330",
        assets={
            "darwin-arm64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/darwin-arm64/claude",
                sha256="f7c5093b9dd6560d08af28bc27b123fb55091deae3180ac39df199522da86815",
                size=363855808,
                archive="raw",
                binary="claude",
            ),
            "darwin-x64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/darwin-x64/claude",
                sha256="bbed99bb8a39bb3f94389c5c99d3d02cb75f3f983b5d1bc40b1b0d1efca84713",
                size=378707584,
                archive="raw",
                binary="claude",
            ),
            "linux-arm64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/linux-arm64/claude",
                sha256="6016f90cac783e367fb1aa97c768a2efb94a0128a5b46b70fb3d8fcbbd9dd444",
                size=379971000,
                archive="raw",
                binary="claude",
            ),
            "linux-arm64-musl": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/linux-arm64-musl/claude",
                sha256="986b83557cbd428273c37f35fc08a44fc786077deeb391660884833bc581348a",
                size=365065160,
                archive="raw",
                binary="claude",
            ),
            "linux-x64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/linux-x64/claude",
                sha256="f390eaa0814e6a1bff74cbb47acb74cb9c89d30ced809fe0af5af00c7bfe8ebb",
                size=381121040,
                archive="raw",
                binary="claude",
            ),
            "linux-x64-musl": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/linux-x64-musl/claude",
                sha256="510d57bbf077b49288b9f3b53b11324048f4c2da5dcb980563be82534980d621",
                size=367484168,
                archive="raw",
                binary="claude",
            ),
            "win32-arm64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/win32-arm64/claude.exe",
                sha256="782519c6241a2bedfd4c0d225d59d5095b895037ae7cd2a14a12f5bc5dcba1c3",
                size=369760416,
                archive="raw",
                binary="claude.exe",
            ),
            "win32-x64": ReleaseAsset(
                url="https://downloads.claude.ai/claude-code-releases/2.1.330/win32-x64/claude.exe",
                sha256="fa797c1bc7d4a3511da42622bae53a2b7f1276ae328c668f2bfef44635301caa",
                size=387754656,
                archive="raw",
                binary="claude.exe",
            ),
        },
    ),
    "codex": PinnedRelease(
        agent="codex",
        version="0.153.4",
        assets={
            "aarch64-apple-darwin": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-aarch64-apple-darwin.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-aarch64-apple-darwin.tar.gz",
                sha256="35438da1fbf7a6db7ddb3bcec84448fa6015ba188461472a97d9d1da7d9c4353",
                size=111554884,
                archive="tar.gz",
                binary="bin/codex",
            ),
            "x86_64-apple-darwin": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-x86_64-apple-darwin.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-x86_64-apple-darwin.tar.gz",
                sha256="3ee638d7155c856ef31f3f4a85cb2195de1939962d3924c935b24f0514564a3d",
                size=121093282,
                archive="tar.gz",
                binary="bin/codex",
            ),
            "aarch64-unknown-linux-musl": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-aarch64-unknown-linux-musl.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-aarch64-unknown-linux-musl.tar.gz",
                sha256="fc395cb043a1093ab0db34f44aba3199bfaa9ce640cd9be7fd588f44b0da64a4",
                size=117238842,
                archive="tar.gz",
                binary="bin/codex",
            ),
            "x86_64-unknown-linux-musl": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-x86_64-unknown-linux-musl.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-x86_64-unknown-linux-musl.tar.gz",
                sha256="a822187e1a2420c61c5926721bfbd878701ed95547c9bb0d4de4498a16ba1821",
                size=126196303,
                archive="tar.gz",
                binary="bin/codex",
            ),
            "aarch64-pc-windows-msvc": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-aarch64-pc-windows-msvc.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-aarch64-pc-windows-msvc.tar.gz",
                sha256="ac51b1a5932e07dffcaa6e98f4801f13b25192094739b732fc8b40ddb41bbda2",
                size=126141441,
                archive="tar.gz",
                binary="bin/codex.exe",
            ),
            "x86_64-pc-windows-msvc": ReleaseAsset(
                url="https://releases.openai.com/codex/releases/0.153.4/codex-package-x86_64-pc-windows-msvc.tar.gz",
                fallback_url="https://github.com/openai/codex/releases/download/rust-v0.153.4/codex-package-x86_64-pc-windows-msvc.tar.gz",
                sha256="a6ef3442cb12766a88b39311d79244289e4f9763e2c53ff4fbebc2cb653cc5f3",
                size=136067504,
                archive="tar.gz",
                binary="bin/codex.exe",
            ),
        },
    ),
    "opencode": PinnedRelease(
        agent="opencode",
        version="1.18.18",
        assets={
            "darwin-arm64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-darwin-arm64.zip",
                sha256="7d668bf26496fec8686d4e51ebb1ac2bd2e393f0c1620aa696c4c242a9e5806a",
                size=46059142,
                archive="zip",
                binary="opencode",
            ),
            "darwin-x64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-darwin-x64.zip",
                sha256="9581bd7683a7528456179fb11e3377d9ef568e10a935611a2c6722e349454d83",
                size=48261294,
                archive="zip",
                binary="opencode",
            ),
            "darwin-x64-baseline": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-darwin-x64-baseline.zip",
                sha256="c029941795f9cf55cfdbc5b0e105db4300413718d489e8e47c950d1a2e126eed",
                size=48261294,
                archive="zip",
                binary="opencode",
            ),
            "linux-arm64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-arm64.tar.gz",
                sha256="dcb1b5ec5687b43f87749560021f9203f3809e0ce5ae44ff9be8ae17083fe4ba",
                size=60199312,
                archive="tar.gz",
                binary="opencode",
            ),
            "linux-arm64-musl": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-arm64-musl.tar.gz",
                sha256="38a7504dab35007c70d2cdf89870b4be63faa60667318a90338798d34f53eab1",
                size=62324509,
                archive="tar.gz",
                binary="opencode",
            ),
            "linux-x64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-x64.tar.gz",
                sha256="0cddc222418b8553669905a8980c0cda7088f00da24d83d6ac76b01c9fdb2aaf",
                size=60386126,
                archive="tar.gz",
                binary="opencode",
            ),
            "linux-x64-baseline": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-x64-baseline.tar.gz",
                sha256="05914655854c1dab48f0d52a8af8f74967e4e26daf87dfe6534f57e799a853d7",
                size=60386127,
                archive="tar.gz",
                binary="opencode",
            ),
            "linux-x64-baseline-musl": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-x64-baseline-musl.tar.gz",
                sha256="f5fe814ac3f94daa4374b7e882b9f0dabe492f63e6b3bbbe7d1e23c95c149a2b",
                size=62749109,
                archive="tar.gz",
                binary="opencode",
            ),
            "linux-x64-musl": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-linux-x64-musl.tar.gz",
                sha256="60279c62d2182aa4279cea4d5a84d23437f8074042cbbed4a2bfa70e5acbd193",
                size=62749124,
                archive="tar.gz",
                binary="opencode",
            ),
            "windows-arm64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-windows-arm64.zip",
                sha256="0d34d837ea3b5e10349d8550318083040a8b4c061d3faaa4eabd339984aa49b0",
                size=58669300,
                archive="zip",
                binary="opencode.exe",
            ),
            "windows-x64": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-windows-x64.zip",
                sha256="c6d265376fdb93164013671b0cf402410184f73c34fc15d82d40a16a745b15f4",
                size=60504740,
                archive="zip",
                binary="opencode.exe",
            ),
            "windows-x64-baseline": ReleaseAsset(
                url="https://github.com/anomalyco/opencode/releases/download/v1.18.18/opencode-windows-x64-baseline.zip",
                sha256="66ad3d31bdc48d7cf16e212da21449bdfe34656cf83a56f682a211c8b78d30ba",
                size=60504745,
                archive="zip",
                binary="opencode.exe",
            ),
        },
    ),
}
