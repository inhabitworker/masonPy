"""Install a built extension ZIP and run Blender integration tests in a temporary profile."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


BOOTSTRAP = """
from pathlib import Path
import os
import bpy
expected = Path(os.environ["BLENDER_USER_CONFIG"]).resolve()
actual = Path(bpy.utils.user_resource("CONFIG")).resolve()
assert actual == expected, (actual, expected)
bpy.ops.wm.read_factory_userpref()
repos = bpy.context.preferences.extensions.repos
for repo in list(repos):
    repos.remove(repo)
repos.new(name="Masonry Test", module="masonry_test",
          custom_directory=str(Path(os.environ["BLENDER_USER_EXTENSIONS"]) / "masonry_test"))
bpy.ops.wm.save_userpref()
print("Verified isolated Blender profile:", actual)
"""


def main():
    """Create directories before launching Blender and verify paths before saving preferences."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--blender", default="/Applications/Blender.app/Contents/MacOS/Blender"
    )
    parser.add_argument(
        "--zip", type=Path, default=ROOT / "dist/blender/masonpy_blender-0.1.0.zip"
    )
    args = parser.parse_args()
    if not args.zip.is_file():
        parser.error("Build the extension ZIP first")
    with tempfile.TemporaryDirectory(prefix="masonpy-blender-test-") as directory:
        directory = Path(directory)
        config, extensions = directory / "config", directory / "extensions"
        config.mkdir()
        (extensions / "masonry_test").mkdir(parents=True)
        environment = dict(
            os.environ,
            BLENDER_USER_CONFIG=str(config),
            BLENDER_USER_EXTENSIONS=str(extensions),
        )
        setup = directory / "setup.py"
        setup.write_text(BOOTSTRAP)
        subprocess.run(
            [
                args.blender,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(setup),
            ],
            env=environment,
            check=True,
        )
        assert (config / "userpref.blend").is_file()
        subprocess.run(
            [
                args.blender,
                "--command",
                "extension",
                "install-file",
                "--repo",
                "masonry_test",
                "--enable",
                str(args.zip.resolve()),
            ],
            env=environment,
            check=True,
        )
        subprocess.run(
            [
                args.blender,
                "--background",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "tests/blender/test_masonry.py"),
            ],
            env=environment,
            check=True,
        )


if __name__ == "__main__":
    main()
