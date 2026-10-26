"""Export only synthetic test captures and non-secret deployment evidence."""
from pathlib import Path
import http.client,json,socket,ssl,subprocess,sys,tarfile
R=Path('/opt/shinian-releases/interview-v6-8799b52-20261027')
x=json.loads(subprocess.check_output(['docker','inspect','backend-api-1']))[0]
env=dict(v.split('=',1) for v in x['Config']['Env'])
before=json.loads((R/'before-inspect.json').read_text())
assert x['Config']['Labels']['org.opencontainers.image.revision']=='8799b52b4d7590ea522c6798c364fd2fa451226a'
assert x['Config']['Labels']['org.opencontainers.image.version']=='V6'
assert env['INTERVIEW_PIPELINE']=='v3j_v5f' and env['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']=='1062b6c2158fa8132c0a6ea9541a4dcdbec80f6dd32d21cfda0d816cd2a76487'
metadata={'version':'V6','code_sha':x['Config']['Labels']['org.opencontainers.image.revision'],'image':x['Image'],
 'pipeline':env['INTERVIEW_PIPELINE'],'runtime_pin':env['INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256'],
 'v4d_pin':env['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'],'mounts_unchanged':x['Mounts']==before['Mounts'],
 'ports_unchanged':x['HostConfig']['PortBindings']==before['HostConfig']['PortBindings'],
 'unrelated_environment_preserved':{k:v for k,v in env.items() if k not in ['INTERVIEW_PIPELINE','INTERVIEW_V5F_RUNTIME_DIR','INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']}=={k:v for k,v in dict(v.split('=',1) for v in before['Config']['Env']).items() if k not in ['INTERVIEW_PIPELINE','INTERVIEW_V5F_RUNTIME_DIR','INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256']},
 'checks':[]}
for host in ['api.xn--zbs33ddmy9oeqa.club','aimemory.47-82-83-74.nip.io']:
 class TLS(http.client.HTTPSConnection):
  def connect(self):
   raw=socket.create_connection(('127.0.0.1',443),timeout=15)
   self.sock=self._context.wrap_socket(raw,server_hostname=host)
 c=TLS(host,context=ssl.create_default_context(),timeout=30);c.request('GET','/health');r=c.getresponse();body=json.loads(r.read());c.close()
 assert r.status==200 and body['database']=='ok'
 c=TLS(host,context=ssl.create_default_context(),timeout=30);c.request('GET','/api/v1/auth/me');u=c.getresponse();u.read();c.close();assert u.status==401
 metadata['checks'].append({'host':host,'https_health_status':r.status,'database':body['database'],'unauthenticated_business_status':u.status})
assert metadata['mounts_unchanged'] and metadata['ports_unchanged'] and metadata['unrelated_environment_preserved']
(R/'final-runtime-verification.json').write_text(json.dumps(metadata,indent=2)+'\n')
verification=json.loads((R/'production-verification.json').read_text())
deployment=json.loads((R/'deployment.json').read_text())
deployment['production_postrelease_scenarios']=verification
(R/'deployment.json').write_text(json.dumps(deployment,indent=2)+'\n')
fixed=['source-manifest.json','unittest.log','unittest-result.json','prepared.json','release-gates.json','deployment.json','backup-verification.json','data-before.json','data-after.json','preactivation-pending.json','quiesced-pending.json','postrelease-database-observation.json','production-verification.json','final-runtime-verification.json']
paths=[R/n for n in fixed if (R/n).is_file()]+list((R/'production-records').glob('*.json'))+list((R/'initial-attempts').glob('*.json'))
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tar:
 for p in paths:
  assert p.is_file() and not p.is_symlink();tar.add(p,arcname=str(p.relative_to(R)),recursive=False)
