from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = MODULE_DIR / "profile_config.py"
PROFILES = MODULE_DIR / "profiles"


def load_profile_module():
    if not MODULE_PATH.is_file():
        raise AssertionError(f"missing production module: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("profile_config", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_personal_profile(**overrides):
    profile = {
        "schema_version": 1,
        "workstation_id": "PC_PERSONALE",
        "tunnel_name": "ARPHE-RESOLVE-PERSONALE",
        "tunnel_id": "tunnel_personal_test",
        "python_path": "C:/Program Files/Python312/python.exe",
        "pythonw_path": "C:/Program Files/Python312/pythonw.exe",
        "python_version": "3.12.10",
        "tunnel_client_path": "C:/ARPHE/MCP/tunnel client/tunnel-client.exe",
        "install_root": "C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1",
        "log_dir": "C:/ARPHE/MCP/logs/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1",
        "creative_destination": "C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_CREATIVE_03",
        "mcp_entrypoint": "C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_CREATIVE_03/ARPHE_MCP_BRIDGE_CREATIVE_03.py",
        "requirements_path": "C:/ARPHE/video-editing-manual/scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/requirements.txt",
        "venv_root": "C:/ARPHE/MCP/runtimes/PC_PERSONALE/venv",
        "feature_flags": {"CAP_PROJECT": True, "CAP_TIMELINE": True},
    }
    profile.update(overrides)
    return profile


class ProfileConfigTests(unittest.TestCase):
    def test_profiles_have_distinct_workstations_and_tunnel_names(self):
        module = load_profile_module()
        personal = module.load_profile(PROFILES / "pc_personale.example.json", allow_placeholder_tunnel=True)
        office = module.load_profile(PROFILES / "pc_segreteria.example.json", allow_placeholder_tunnel=True)
        self.assertEqual("PC_PERSONALE", personal["workstation_id"])
        self.assertEqual("PC_SEGRETERIA", office["workstation_id"])
        self.assertNotEqual(personal["tunnel_name"], office["tunnel_name"])

    def test_personal_profile_rejects_legacy_office_tunnel(self):
        module = load_profile_module()
        profile = valid_personal_profile(tunnel_name="ARPHE-RESOLVE-HOME")
        with self.assertRaisesRegex(ValueError, "reserved for PC_SEGRETERIA"):
            module.validate_profile(profile, allow_placeholder_tunnel=False)

    def test_profile_rejects_api_key_material(self):
        module = load_profile_module()
        profile = valid_personal_profile(runtime_api_key="sk-proj-test-value")
        with self.assertRaisesRegex(ValueError, "secret"):
            module.validate_profile(profile, allow_placeholder_tunnel=False)

    def test_profile_rejects_windowsapps_python_alias(self):
        module = load_profile_module()
        profile = valid_personal_profile(
            python_path="C:/Users/test/AppData/Local/Microsoft/WindowsApps/python.exe"
        )
        with self.assertRaisesRegex(ValueError, "WindowsApps"):
            module.validate_profile(profile, allow_placeholder_tunnel=False)

    def test_real_install_rejects_placeholder_tunnel_id(self):
        module = load_profile_module()
        profile = valid_personal_profile(tunnel_id="tunnel_REPLACE_PERSONAL")
        with self.assertRaisesRegex(ValueError, "placeholder"):
            module.validate_profile(profile, allow_placeholder_tunnel=False)

    def test_load_profile_returns_normalized_forward_slash_paths(self):
        module = load_profile_module()
        profile = valid_personal_profile(python_path=r"C:\Program Files\Python312\python.exe")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            loaded = module.load_profile(path, allow_placeholder_tunnel=False)
        self.assertEqual("C:/Program Files/Python312/python.exe", loaded["python_path"])


if __name__ == "__main__":
    unittest.main()
