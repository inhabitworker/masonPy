"""Package/module contracts that make a source-layout refactor auditable."""

import ast
from importlib.resources import files
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

from masonpy.app.server import MasonPyRequestHandler

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_core_import_does_not_load_the_optional_app(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import masonpy, sys; assert 'masonpy.app' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_recipe_and_basic_geometry_need_no_host_or_clipping_engine(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import importlib.abc
import sys

class BlockHostImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"bpy", "pyclipper", "masonpy.app", "masonpy.exporting"}:
            raise ImportError("Blocked dependency: " + fullname)

sys.meta_path.insert(0, BlockHostImports())
from masonpy import Wall, WallGeometry, shape_wall
from masonpy.configuration import configuration, DEFAULT_SHAPE_SETTINGS
from masonpy.generators.catalog import get_generator_definition

recipe = configuration(dict(generator="running_bond", width=12, height=4,
                            parameters={}))
recipe["shape"]["distortion"] = 0.5
assert DEFAULT_SHAPE_SETTINGS["distortion"] == 0
assert configuration(dict(generator="running_bond", width=12, height=4,
                          parameters={}))['shape']['distortion'] == 0
generator, _ = get_generator_definition(recipe["generator"]).create(recipe["parameters"])
wall = Wall(recipe["width"], recipe["height"])
generator.generate(wall)
shape = shape_wall(wall, joint_width=0.2)
assert WallGeometry(shape, depth=0.25).to_dict()["stones"]
try:
    shape_wall(wall, corner_softening=0.5)
except ValueError as error:
    assert "Pyclipper" in str(error)
else:
    raise AssertionError("Active softening must report its missing dependency")
""",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_library_does_not_import_host_or_serialization_layers_upstream(self):
        for path in (ROOT / "src/masonpy").rglob("*.py"):
            if "app" in path.relative_to(ROOT / "src/masonpy").parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    self.assertFalse(module == "bpy" or module.startswith("bpy."), path)
                    self.assertFalse(module.startswith("masonpy.app"), path)
                    if "geometry" in path.relative_to(ROOT / "src/masonpy").parts:
                        self.assertNotEqual(module, "masonpy.exporting", path)

    def test_packaged_static_inventory_covers_every_local_module_import(self):
        static = files("masonpy.app").joinpath("static")
        served = set(MasonPyRequestHandler.static_files.values())
        for name in served:
            self.assertTrue(static.joinpath(name).is_file(), name)
            if name.endswith(".js"):
                text = static.joinpath(name).read_text()
                for dependency in re.findall(r'["\']\./([^"\']+\.js)["\']', text):
                    self.assertIn(dependency, served)
        shell = static.joinpath("index.html").read_text()
        self.assertIn('type="module" src="/startup.js"', shell)
        self.assertEqual(shell.count("three@0.180.0"), 2)

    def test_library_classes_and_methods_explain_their_purpose(self):
        for path in (ROOT / "src/masonpy").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    with self.subTest(path=path, name=node.name):
                        self.assertIsNotNone(ast.get_docstring(node))

    @unittest.skipUnless(
        shutil.which("node"),
        "Node is optional; browser workbench has no Node runtime dependency",
    )
    def test_pure_browser_component_contracts(self):
        result = subprocess.run(
            [
                shutil.which("node"),
                "--test",
                str(ROOT / "tests/browser_modules.test.mjs"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
