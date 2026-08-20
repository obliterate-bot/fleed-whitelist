from __future__ import annotations

from setuptools import Distribution, setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
from packaging.tags import sys_tags

class BinaryDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        return True


class PlatformWheel(_bdist_wheel):
    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        platform = next(sys_tags()).platform
        return "py3", "none", platform


setup(
    distclass=BinaryDistribution,
    cmdclass={"bdist_wheel": PlatformWheel},
    data_files=[
        ("share/o_bfuscate/vendor/luau", ["vendor/luau/LICENSE.txt"]),
        ("share/o_bfuscate/vendor/luau/linux-x86_64", [
            "vendor/luau/linux-x86_64/luau",
            "vendor/luau/linux-x86_64/luau-compile",
        ]),
        ("share/o_bfuscate/vendor/luau/source", ["vendor/luau/source/luau-master.zip"]),
    ],
)
