"""Build a self-contained Blender 5.1/macOS Apple Silicon extension from this checkout."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PYCLIPPER_WHEEL = "pyclipper-1.4.0-cp313-cp313-macosx_10_13_universal2.whl"


def main():
    """Stage extension source and wheels; let Blender validate and package the ZIP."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--blender", default="/Applications/Blender.app/Contents/MacOS/Blender"
    )
    parser.add_argument("--pyclipper-wheel", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.pyclipper_wheel.resolve()
    if wheel.name != PYCLIPPER_WHEEL or not wheel.is_file():
        parser.error(f"Provide the unmodified {PYCLIPPER_WHEEL} wheel")
    stage = ROOT / "build/blender/masonpy_blender"
    stage.parent.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(
        ROOT / "blender/masonpy_blender",
        stage,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "wheels"),
    )
    wheels = stage / "wheels"
    wheels.mkdir()
    shutil.copy2(wheel, wheels / wheel.name)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(ROOT),
            "--no-deps",
            "--no-build-isolation",
            "--no-index",
            "--wheel-dir",
            str(wheels),
        ],
        check=True,
    )
    subprocess.run(
        [args.blender, "--command", "extension", "validate", str(stage)], check=True
    )
    output = ROOT / "dist/blender"
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            args.blender,
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(stage),
            "--output-dir",
            str(output),
        ],
        check=True,
    )
    print(f"Install ZIP from {output}; local repository development source: {stage}")


if __name__ == "__main__":
    main()
