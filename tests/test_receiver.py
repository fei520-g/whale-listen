import importlib.util,unittest,time,tempfile,json,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('receiver',Path(__file__).parents[1]/'server/receiver.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ReceiverTest(unittest.TestCase):
 def setUp(self):
  self.now=1800000000000;self.state={'version':1,'active':True,'package':'com.kugou.android','state':'playing','title':'测试曲目','artist':'歌手','album':'专辑','positionMs':1000,'durationMs':200000,'speed':1,'observedAtMs':self.now}
 def test_valid_state(self):
  r=m.validate(self.state,'phone-1',self.now);self.assertEqual(r['title'],'测试曲目');self.assertEqual(r['receivedAtMs'],self.now)
 def test_reject_chat_or_unknown_fields(self):
  for field in ['notificationText','instructions','url','command']:
   with self.assertRaises(ValueError):m.validate({**self.state,field:'secret'},'phone-1',self.now)
 def test_only_allowed_player(self):
  with self.assertRaises(ValueError):m.validate({**self.state,'package':'com.tencent.mobileqq'},'phone-1',self.now)
 def test_stale_phone_clock(self):
  with self.assertRaises(ValueError):m.validate(self.state,'phone-1',self.now+1000000)
 def test_position_and_metadata_bounds(self):
  for change in [{'positionMs':float('nan')},{'speed':float('inf')},{'title':'a'*241},{'durationMs':-1},{'positionMs':300000}]:
   with self.assertRaises(ValueError):m.validate({**self.state,**change},'phone-1',self.now)
 def test_unknown_position_stays_unknown(self):self.assertIsNone(m.validate({**self.state,'positionMs':None},'phone-1',self.now)['positionMs'])
 def test_disconnect_clears_metadata(self):
  r=m.validate({**self.state,'active':False},'phone-1',self.now);self.assertEqual(r['title'],'');self.assertIsNone(r['positionMs'])
 @unittest.skipIf(os.name=='nt','Atomic POSIX permissions are tested on the Linux receiver')
 def test_atomic_snapshot_no_history(self):
  with tempfile.TemporaryDirectory() as d:
   a=m.validate(self.state,'phone-1',self.now);m.write_state(d,a);m.write_state(d,{**a,'title':'第二首'});self.assertEqual(json.loads((Path(d)/'current.json').read_text(encoding='utf8'))['title'],'第二首');self.assertEqual(len(list(Path(d).iterdir())),1)
if __name__=='__main__':unittest.main()
