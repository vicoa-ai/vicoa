from setuptools import setup
from setuptools.dist import Distribution

try:
    # setuptools >= 70.1 vendors bdist_wheel; older toolchains only have it in
    # the standalone `wheel` package. Prefer the setuptools copy, fall back.
    try:
        from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel  # type: ignore
    except Exception:  # pragma: no cover - older setuptools
        from wheel.bdist_wheel import bdist_wheel as _bdist_wheel  # type: ignore

    class bdist_wheel(_bdist_wheel):  # type: ignore
        def finalize_options(self):
            super().finalize_options()
            # Mark wheel as non-pure so it gets a platform tag and can carry binaries.
            self.root_is_pure = False

        def get_tag(self):
            # The only non-pure payload is the bundled codex binary — a
            # standalone executable, NOT a CPython C-extension — so the wheel is
            # valid for every Python 3.x on this platform. Emit a
            # `py3-none-<platform>` tag (one wheel per arch) instead of a
            # `cp3XX-cp3XX-<platform>` tag (four byte-identical wheels per arch).
            # This keeps the platform tag (OS/arch/glibc/macOS-min gating intact)
            # while collapsing the redundant per-Python-version copies that were
            # filling PyPI's 10 GB per-project storage quota.
            _python, _abi, plat = super().get_tag()
            return "py3", "none", plat
except Exception:  # pragma: no cover - wheel may not be available in some envs
    bdist_wheel = None  # type: ignore


class BinaryDistribution(Distribution):
    def has_ext_modules(self):  # type: ignore[override]
        # Tell setuptools/wheel that this distribution contains non-pure (binary) artifacts.
        return True


setup(
    distclass=BinaryDistribution,
    cmdclass={"bdist_wheel": bdist_wheel} if bdist_wheel else {},
)
