from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from artifact_log_handler import ArtifactRotatingFileHandler  # noqa: E402
from arphe_bridge_runtime import SecretRedactor, configure_logging  # noqa: E402


class ArtifactLogHandlerTests(unittest.TestCase):
    def _logger(self, root: Path, *, secret: str = "") -> tuple[logging.Logger, ArtifactRotatingFileHandler]:
        logger = logging.getLogger(f"artifact-log-test-{id(root)}")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = ArtifactRotatingFileHandler(root / "runtime.log", "PC_PERSONALE", max_bytes=80)
        handler.addFilter(SecretRedactor(secret))
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        return logger, handler

    def test_rotation_creates_unique_non_shifting_directories_with_verified_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logger, handler = self._logger(root)
            for index in range(12):
                logger.info("event-%02d-%s", index, "x" * 30)
            handler.close()

            producer_dirs = sorted((root / "rotated").iterdir())
            self.assertGreaterEqual(len(producer_dirs), 2)
            self.assertEqual(len(producer_dirs), len({path.name for path in producer_dirs}))
            self.assertFalse(any(root.glob("runtime.log.*")))
            for producer_dir in producer_dirs:
                log_path = producer_dir / "runtime.log"
                metadata = json.loads((producer_dir / "artifact.json").read_text(encoding="utf-8"))
                payload = log_path.read_bytes()
                self.assertEqual(1, metadata["schema_version"])
                self.assertEqual("PC_PERSONALE", metadata["workstation_id"])
                self.assertEqual("ROTATED_LOG", metadata["category"])
                self.assertEqual("runtime.log", metadata["log_file"])
                self.assertEqual(len(payload), metadata["size_bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), metadata["sha256"])
                self.assertTrue(metadata["created_at"].endswith("+00:00"))

    def test_redaction_happens_before_any_content_is_rotated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "sk-secret-value-123456789"
            logger, handler = self._logger(root, secret=secret)
            for _ in range(6):
                logger.info("CONTROL_PLANE_API_KEY=%s filler=%s", secret, "x" * 30)
            handler.close()
            combined = b"".join(path.read_bytes() for path in root.rglob("runtime.log"))
            self.assertNotIn(secret.encode(), combined)
            self.assertIn(b"[REDACTED]", combined)

    def test_runtime_logging_uses_artifact_handler_and_workstation_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            logger, _ = configure_logging(Path(directory), "secret", "PC_PERSONALE")
            try:
                self.assertIsInstance(logger.handlers[0], ArtifactRotatingFileHandler)
                self.assertEqual("PC_PERSONALE", logger.handlers[0].workstation_id)
                self.assertEqual(2_000_000, logger.handlers[0].max_bytes)
            finally:
                for handler in list(logger.handlers):
                    handler.close()
                logger.handlers.clear()


if __name__ == "__main__":
    unittest.main()
