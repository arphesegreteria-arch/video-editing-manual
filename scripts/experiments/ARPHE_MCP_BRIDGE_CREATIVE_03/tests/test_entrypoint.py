from pathlib import Path
import subprocess
import sys
import unittest


BRIDGE_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = BRIDGE_ROOT / "ARPHE_MCP_BRIDGE_CREATIVE_03.py"


class EntrypointTests(unittest.TestCase):
    def test_entrypoint_imports_when_python_omits_the_script_directory(self):
        code = f"import runpy; runpy.run_path({str(ENTRYPOINT)!r}, run_name='entrypoint_test')"
        result = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
