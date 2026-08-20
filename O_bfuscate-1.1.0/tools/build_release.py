from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.0"
DIST = ROOT / "dist"
WHEEL_NAME = f"o_bfuscate-{VERSION}-py3-none-linux_x86_64.whl"
SOURCE_NAME = f"O_bfuscate-{VERSION}-full-luau-source.zip"
DIST_INFO = f"o_bfuscate-{VERSION}.dist-info"
DATA_ROOT = f"o_bfuscate-{VERSION}.data/data/share/o_bfuscate/vendor/luau"


def digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def build_wheel() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / WHEEL_NAME
    records: list[tuple[str, str, int]] = []
    payloads: list[tuple[str, bytes, bool]] = []
    package = ROOT / "src/o_bfuscate"
    for path in sorted(package.iterdir()):
        if path.is_file() and path.suffix in {".py", ".luau"}:
            payloads.append((f"o_bfuscate/{path.name}", path.read_bytes(), False))

    vendor = ROOT / "vendor/luau"
    payloads.extend([
        (f"{DATA_ROOT}/LICENSE.txt", (vendor / "LICENSE.txt").read_bytes(), False),
        (f"{DATA_ROOT}/linux-x86_64/luau", (vendor / "linux-x86_64/luau").read_bytes(), True),
        (f"{DATA_ROOT}/linux-x86_64/luau-compile", (vendor / "linux-x86_64/luau-compile").read_bytes(), True),
        (f"{DATA_ROOT}/source/luau-master.zip", (vendor / "source/luau-master.zip").read_bytes(), False),
    ])

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    metadata = f"""Metadata-Version: 2.4
Name: o-bfuscate
Version: {VERSION}
Summary: A deterministic, Luau-aware source protection CLI
Author: O_bfuscate contributors
License: MIT
Keywords: luau,lua,obfuscator,roblox,minifier
Classifier: Programming Language :: Python :: 3
Classifier: License :: OSI Approved :: MIT License
Requires-Python: >=3.11
Description-Content-Type: text/markdown
License-File: LICENSE

{readme}
""".encode()
    wheel = b"""Wheel-Version: 1.0
Generator: O_bfuscate release builder
Root-Is-Purelib: false
Tag: py3-none-linux_x86_64
"""
    entry_points = b"""[console_scripts]
o-bfuscate = o_bfuscate.cli:main
o-bfuscate-license = o_bfuscate.license_cli:main
"""
    payloads.extend([
        (f"{DIST_INFO}/METADATA", metadata, False),
        (f"{DIST_INFO}/WHEEL", wheel, False),
        (f"{DIST_INFO}/entry_points.txt", entry_points, False),
        (f"{DIST_INFO}/top_level.txt", b"o_bfuscate\n", False),
        (f"{DIST_INFO}/licenses/LICENSE", (ROOT / "LICENSE").read_bytes(), False),
    ])

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data, executable in payloads:
            archive.writestr(zip_info(name, executable), data)
            records.append((name, digest(data), len(data)))
        record_name = f"{DIST_INFO}/RECORD"
        record_lines = [f"{name},{sha},{size}" for name, sha, size in records]
        record_lines.append(f"{record_name},,")
        archive.writestr(zip_info(record_name), ("\n".join(record_lines) + "\n").encode())
    return out


def build_source() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / SOURCE_NAME
    excluded = {"dist", "__pycache__", ".pytest_cache", "build", "*.egg-info"}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in {"dist", "__pycache__", ".pytest_cache", "build"} or part.endswith(".egg-info") for part in rel.parts):
                continue
            arcname = f"O_bfuscate-{VERSION}/{rel.as_posix()}"
            archive.write(path, arcname)
    return out


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    wheel = build_wheel()
    source = build_source()
    checksums = DIST / f"O_bfuscate-{VERSION}-SHA256SUMS.txt"
    lines = []
    for path in (source, wheel):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(wheel)
    print(source)
    print(checksums)


if __name__ == "__main__":
    main()
