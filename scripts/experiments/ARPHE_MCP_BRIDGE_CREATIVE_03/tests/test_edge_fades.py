from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.edge_fade_tools import apply_audio_edge_fades  # noqa: E402


class EdgeFadeTests(unittest.TestCase):
    def test_audio_fades_reach_silence_and_preserve_middle(self):
        source = np.full((12, 2), 1000, dtype=np.int16)
        result = apply_audio_edge_fades(source, 3, 4)
        self.assertEqual(0, result[0, 0])
        self.assertEqual(1000, result[2, 0])
        self.assertEqual(1000, result[6, 0])
        self.assertEqual(1000, result[-4, 0])
        self.assertEqual(0, result[-1, 0])
        self.assertTrue(np.array_equal(source, np.full((12, 2), 1000, dtype=np.int16)))


if __name__ == "__main__":
    unittest.main()
