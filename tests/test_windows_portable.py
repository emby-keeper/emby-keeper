import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("portable_pack", ROOT / "windows" / "portable" / "pack.py")
PACKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKER)


class ArchivedApplicationTests(unittest.TestCase):
    def test_archived_application_preserves_site_catalog_and_source_options(self):
        probe = """
import asyncio
import json
asyncio.set_event_loop(asyncio.new_event_loop())
from embykeeper.api import sites
from embykeeper.telegram.dynamic import get_names
print(json.dumps({
    'origin': sites.__file__,
    'types': {
        kind: {
            'names': sorted(get_names(kind, allow_ignore=True)),
            'templates': sites._template_kinds(kind),
            'options': sites._template_options(kind, 'a'),
            'catalog': sites._builtin_catalog(kind),
        }
        for kind in ('checkiner', 'monitor', 'messager', 'registrar')
    }
}, ensure_ascii=False))
"""
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            site_packages = runtime / "Lib" / "site-packages"
            site_packages.mkdir(parents=True)
            for package in ("embykeeper", "embykeeperapi"):
                shutil.copytree(
                    ROOT / package,
                    site_packages / package,
                    ignore=shutil.ignore_patterns("__pycache__", "static"),
                )
            (runtime / "python._pth").write_text(".\nLib/site-packages\nimport site\n", encoding="ascii")
            report = PACKER.compact_runtime(runtime)
            self.assertLess(report["after"]["files"], report["before"]["files"] // 10)
            with self.assertRaises(FileExistsError):
                PACKER.compact_runtime(runtime)
            archive = runtime / "packages.zip"

            results = []
            for path in (ROOT, archive):
                result = subprocess.run(
                    [sys.executable, "-c", probe],
                    cwd=directory,
                    env={**os.environ, "PYTHONPATH": str(path)},
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                results.append(json.loads(result.stdout))
            self.assertIn("packages.zip", results[1]["origin"])
            self.assertTrue(results[0]["types"]["checkiner"]["templates"])
            for kind, expected in results[0]["types"].items():
                for key, value in expected.items():
                    self.assertEqual(value, results[1]["types"][kind][key], f"{kind}: {key}")
