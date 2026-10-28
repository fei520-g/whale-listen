import importlib.util
from pathlib import Path
import tempfile,unittest
spec=importlib.util.spec_from_file_location('audit_release',Path(__file__).resolve().parents[1]/'scripts/audit-release.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReleaseAuditTests(unittest.TestCase):
 def setUp(self):
  base=Path(__file__).resolve().parents[1]/'testing/tmp';base.mkdir(parents=True,exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_private_files_keys_and_real_invites_are_flagged_without_printing_values(self):
  (self.root/'private').mkdir();(self.root/'private/account').write_text('secret')
  (self.root/'keys.txt').write_text('-----BEGIN '+'RSA PRIVATE KEY-----\n')
  (self.root/'invite.txt').write_text('https://h5.kugou.com/sharepage/v-96be9ea4/index.html?code='+'0123456789abcdef'*2)
  out=m.check(self.root);kinds={x['kind'] for x in out['issues']}
  self.assertTrue({'private_directory','private_key_material','room_invitation'}<=kinds)
  self.assertNotIn('0123456789abcdef'*2,str(out));self.assertFalse(out['safe_to_publish'])
 def test_documentation_ips_and_synthetic_invites_are_allowed(self):
  (self.root/'example.txt').write_text('http://127.0.0.1 and 203.0.113.8\nhttps://h5.kugou.com/sharepage/v-96be9ea4/index.html?code='+'a'*32)
  self.assertEqual(m.check(self.root)['issues'],[])
 def test_personal_paths_and_other_addresses_are_flagged(self):
  (self.root/'bad.txt').write_text('C:/Users/example/secret\n198.18.0.1')
  self.assertEqual({x['kind'] for x in m.check(self.root)['issues']},{'personal_path','nonexample_ip_address'})

if __name__=='__main__':unittest.main()
