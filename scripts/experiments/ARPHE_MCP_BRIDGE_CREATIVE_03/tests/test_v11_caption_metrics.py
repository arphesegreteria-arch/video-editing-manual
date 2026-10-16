import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bridge.v11_caption_metrics import layout_width,phrase_word_slots_measured

class Metrics(unittest.TestCase):
 def test_long_words_receive_measured_width_not_legacy_fixed_width(self):
  self.assertGreater(layout_width('COSTRUIAMO'),.30)
  self.assertGreater(layout_width('TRATTAMENTO'),.32)
  self.assertGreater(layout_width('VALUTAZIONE'),.30)
 def test_measured_slots_keep_each_word_in_its_own_container(self):
  slots=phrase_word_slots_measured(['ACCURATA','COSTRUIAMO','IL','PERCORSO'])
  self.assertEqual(4,len(slots))
  self.assertGreater(slots[1][3],.30)
  self.assertNotEqual(slots[0][2],slots[2][2])
if __name__=='__main__':unittest.main()
