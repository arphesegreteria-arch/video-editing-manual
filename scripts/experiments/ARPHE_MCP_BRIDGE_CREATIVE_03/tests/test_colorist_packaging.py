from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]


def powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        raise unittest.SkipTest("PowerShell is required for packaging tests")
    return executable


def windows_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


class ColoristPackagingTests(unittest.TestCase):
    def run_installer(self, root: Path, config_path: Path) -> Path:
        destination = root / "installed-creative"
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(root / "local-app-data")
        environment["USERPROFILE"] = str(root / "user-profile")
        result = subprocess.run(
            [
                powershell(),
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(PACKAGE_ROOT / "install_on_segreteria.ps1"),
                "-WorkstationId",
                "PC_PERSONALE",
                "-Destination",
                str(destination),
                "-AssetRoot",
                str(root / "assets"),
                "-RenderRoot",
                str(root / "renders"),
                "-RuntimeLogRoot",
                str(root / "logs"),
                "-ConfigPath",
                str(config_path),
                "-Confirm:$false",
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return destination

    def test_installer_copies_colorist_presets_into_package(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            destination = self.run_installer(root, root / "config" / "creative.json")

            installed = json.loads(
                (destination / "colorist_presets.json").read_text(encoding="utf-8")
            )
            expected = json.loads(
                (PACKAGE_ROOT / "colorist_presets.json").read_text(encoding="utf-8")
            )
            self.assertEqual(expected, installed)

    def test_installer_migrates_existing_config_with_disabled_colorist_flag(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            config_path = root / "config" / "creative.json"
            config_path.parent.mkdir(parents=True)
            config = json.loads(
                (PACKAGE_ROOT / "creative_config.example.json").read_text(encoding="utf-8")
            )
            config["workstation_id"] = "PC_PERSONALE"
            config["feature_flags"].pop("CAP_COLORIST")
            config_path.write_text(json.dumps(config), encoding="utf-8")

            self.run_installer(root, config_path)

            migrated = json.loads(config_path.read_text(encoding="utf-8-sig"))
            self.assertIs(False, migrated["feature_flags"]["CAP_COLORIST"])

    def test_feature_flag_script_enables_colorist_in_isolated_profile(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            install_root = root / "runtime"
            profile_root = install_root / "runtime-configs" / "PC_PERSONALE"
            profile_root.mkdir(parents=True)
            creative_config_path = profile_root / "creative_config.json"
            creative_config_path.write_text(
                json.dumps(
                    {
                        "workstation_id": "PC_PERSONALE",
                        "feature_flags": {"CAP_COLORIST": False},
                    }
                ),
                encoding="utf-8",
            )
            (profile_root / "bridge_config.json").write_text(
                json.dumps(
                    {
                        "workstation_id": "PC_PERSONALE",
                        "creative_config_path": windows_path(creative_config_path),
                    }
                ),
                encoding="utf-8",
            )
            profile_path = root / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "workstation_id": "PC_PERSONALE",
                        "tunnel_name": "ARPHE-RESOLVE-PERSONALE",
                        "tunnel_id": "tunnel_test_colorist",
                        "python_path": windows_path(Path(sys.executable)),
                        "pythonw_path": windows_path(Path(sys.executable)),
                        "python_version": "3.12.10",
                        "tunnel_client_path": windows_path(root / "cloudflared.exe"),
                        "install_root": windows_path(install_root),
                        "log_dir": windows_path(root / "logs"),
                        "creative_destination": windows_path(root / "creative"),
                        "mcp_entrypoint": windows_path(root / "creative" / "entry.py"),
                        "safe_write_entrypoint": windows_path(root / "safe" / "entry.py"),
                        "requirements_path": windows_path(root / "requirements.txt"),
                        "venv_root": windows_path(root / "venv"),
                        "feature_flags": {"CAP_COLORIST": False},
                    }
                ),
                encoding="utf-8",
            )
            command = (
                f"& '{PACKAGE_ROOT / 'set_feature_flag.ps1'}' "
                f"-WorkstationId PC_PERSONALE -ProfilePath '{profile_path}' "
                "-Name CAP_COLORIST -Enabled $true -Confirm:$false"
            )
            environment = os.environ.copy()
            environment["LOCALAPPDATA"] = str(root / "local-app-data")
            result = subprocess.run(
                [powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr or result.stdout)
            updated = json.loads(creative_config_path.read_text(encoding="utf-8-sig"))
            self.assertIs(True, updated["feature_flags"]["CAP_COLORIST"])


if __name__ == "__main__":
    unittest.main()
