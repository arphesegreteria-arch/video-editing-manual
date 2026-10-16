import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bridge.v11_caption_extension import place_v11_caption_carrier
from bridge.safety import ValidationError
class Item:
 def __init__(self,start=108177,end=108574,comp=True):self.start=start;self.end=end;self.comp=comp
 def GetStart(self):return self.start
 def GetEnd(self):return self.end
 def SetName(self,n):return True
 def AddFusionComp(self):return object() if self.comp else None
class Timeline:
 def __init__(self, fusion_item=None):self.deleted=[];self.deleted_track=[];self.fusion_item=fusion_item
 def GetName(self):return 'ARPHE_BIORIVITALIZZAZIONE_V11_KARAOKE_UPPER_SAMPLE_20261016'
 def GetTrackCount(self,k):return 2
 def AddTrack(self,k):return True
 def CreateFusionClip(self,x):return self.fusion_item if self.fusion_item is not None else x[0]
 def DeleteClips(self,x,r):self.deleted=x;return True
 def DeleteTrack(self,k,i):self.deleted_track.append((k,i));return True
class Pool:
 def __init__(self,item=None):self.payload=None;self.item=item or Item()
 def ImportMedia(self,x):return [object()]
 def AppendToTimeline(self,x):self.payload=x[0];return [self.item]
class Project:
 def __init__(self,p):self.p=p
 def GetName(self):return 'ARPHE_BIORIVITALIZZAZIONE_ADV_20261013_PERSONALE'
 def GetMediaPool(self):return self.p
class T(unittest.TestCase):
 def test_places_exact_record_frame(self):
  pool=Pool(); cfg=SimpleNamespace(asset_root=ROOT/'assets')
  with patch('bridge.v11_caption_extension.Path.is_file',return_value=True):place_v11_caption_carrier(Project(pool),Timeline(),cfg,108177,108574)
  self.assertEqual(108177,pool.payload['recordFrame']);self.assertEqual(3,pool.payload['trackIndex']);self.assertEqual(1,pool.payload['mediaType'])
 def test_rejects_any_other_range_without_write(self):
  with self.assertRaises(ValidationError):place_v11_caption_carrier(Project(Pool()),Timeline(),SimpleNamespace(asset_root=ROOT),1,2)
 def test_rolls_back_wrapper_and_fresh_track_when_fusion_setup_fails(self):
  item=Item(); wrapper=Item(comp=False); pool=Pool(item); timeline=Timeline(wrapper)
  with patch('bridge.v11_caption_extension.Path.is_file',return_value=True):
   with self.assertRaises(ValidationError):place_v11_caption_carrier(Project(pool),timeline,SimpleNamespace(asset_root=ROOT/'assets'),108177,108574)
  self.assertEqual([wrapper],timeline.deleted);self.assertEqual([('video',3)],timeline.deleted_track)
 def test_rolls_back_bad_readback_without_touching_audio_or_existing_tracks(self):
  item=Item(start=108178);pool=Pool(item);timeline=Timeline()
  with patch('bridge.v11_caption_extension.Path.is_file',return_value=True):
   with self.assertRaises(ValidationError):place_v11_caption_carrier(Project(pool),timeline,SimpleNamespace(asset_root=ROOT/'assets'),108177,108574)
  self.assertEqual([item],timeline.deleted);self.assertEqual([('video',3)],timeline.deleted_track)
  self.assertEqual(1,pool.payload['mediaType'])
 def test_wrong_project_rejects_before_any_write(self):
  pool=Pool();timeline=Timeline(); project=Project(pool);project.GetName=lambda:'OTHER'
  with self.assertRaises(ValidationError):place_v11_caption_carrier(project,timeline,SimpleNamespace(asset_root=ROOT),108177,108574)
  self.assertIsNone(pool.payload);self.assertEqual([],timeline.deleted)
if __name__=='__main__':unittest.main()
