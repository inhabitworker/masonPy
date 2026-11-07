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
