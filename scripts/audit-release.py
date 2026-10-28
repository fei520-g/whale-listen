"""Inspect a proposed release directory; never prints matched secret values.

This is a preflight, not a guarantee. It does not scan Git history or establish
copyright/licensing. Publication still requires human review and authorization.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import re

DENIED_DIRS={'private','.git','node_modules','official-client-audit','room-api-audit'}
DENIED_SUFFIXES={'.apk','.jks','.dpapi','.p12','.pfx','.pem','.key','.keystore'}
PRIVATE_KEY=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')
INVITE=re.compile(rb'h5\.kugou\.com/sharepage/v-96be9ea4/index\.html\?[^\s"\x27]*code=([a-fA-F0-9]{32})')
IP=re.compile(rb'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])')
SECRET=re.compile(rb'(?i)(?:["\x27]?(?:api[_-]?key|access[_-]?token|password|private[_-]?key)["\x27]?\s*[:=]\s*["\x27])([^"\x27\r\n]{16,})')

def check(root):
 root=Path(root).resolve(strict=True)
 if not root.is_dir():raise ValueError('需要文件夹')
 issues=[];count=0
 for p in root.rglob('*'):
  rel=p.relative_to(root).as_posix()
  if p.is_symlink():issues.append((rel,'symlink'));continue
  if p.is_dir():
   if p.name in DENIED_DIRS:issues.append((rel,'private_directory'))
   continue
  count+=1
  if any(part in DENIED_DIRS for part in p.relative_to(root).parts):continue
  if p.suffix.lower() in DENIED_SUFFIXES or p.name.lower() in {'authorized_keys','credentials.json','id_rsa','id_ed25519'}:
   issues.append((rel,'sensitive_file_type'));continue
  if p.stat().st_size>2*1024*1024:issues.append((rel,'oversize_requires_manual_review'));continue
  raw=p.read_bytes()
  if PRIVATE_KEY.search(raw):issues.append((rel,'private_key_material'))
  if b'/home/admin/whale-cloud' in raw or re.search(rb'(?i)C:[/\\]Users[/\\][^/\\\s]+',raw):issues.append((rel,'personal_path'))
  for match in INVITE.finditer(raw):
   if len(set(match.group(1).lower()))>1:issues.append((rel,'room_invitation'));break
  for match in IP.finditer(raw):
   try:address=ipaddress.ip_address(match.group().decode('ascii'))
   except ValueError:continue
   if str(address) not in {'127.0.0.1','0.0.0.0'} and not any(address in ipaddress.ip_network(n) for n in ('192.0.2.0/24','198.51.100.0/24','203.0.113.0/24')):
    issues.append((rel,'nonexample_ip_address'));break
  for match in SECRET.finditer(raw):
   value=match.group(1).lower()
   if not any(marker in value for marker in (b'example',b'placeholder',b'fake',b'test-only',b'your_',b'<')):
    issues.append((rel,'possible_secret'));break
 return {'files_checked':count,'issues':[{'path':p,'kind':k} for p,k in issues],
         'git_history_checked':False,'licenses_verified':False,'safe_to_publish':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);args=parser.parse_args()
 report=check(args.directory);print(json.dumps(report,ensure_ascii=False,indent=2));return 1 if report['issues'] else 0
if __name__=='__main__':raise SystemExit(main())
