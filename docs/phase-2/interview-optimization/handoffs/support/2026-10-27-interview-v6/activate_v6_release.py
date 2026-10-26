"""Authorized conditional cutover. Backups stay on host; never restores data.

Preserves the complete OSS/runtime configuration. After replacement starts,
recovery uses the new v3-capable image with only PIPELINE changed to v2.
"""
from pathlib import Path
import gzip
import hashlib
import http.client
import importlib.util
import json
import ssl
import subprocess
import tarfile

spec=importlib.util.spec_from_file_location('candidate','/home/admin/interview-v6-tools/prepare_v6_release.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
R=p.R;B=Path('/opt/ai-memories/backend')

SNAPSHOT=r'''import json,hashlib
from pathlib import Path
from sqlalchemy import text,inspect
from app.db.database import engine
out={}
with engine.connect() as c:
 for table in sorted(inspect(engine).get_table_names()):
  assert table.replace('_','').isalnum()
  rows=[dict(r._mapping) for r in c.execute(text('SELECT * FROM `'+table+'`'))]
  values=sorted(json.dumps(row,sort_keys=True,default=str,ensure_ascii=False) for row in rows)
  out[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
media={str(path.relative_to('/data/media')):hashlib.sha256(path.read_bytes()).hexdigest() for path in Path('/data/media').rglob('*') if path.is_file()}
out['media_files']={'count':len(media),'sha256':hashlib.sha256(json.dumps(media,sort_keys=True).encode()).hexdigest()}
print(json.dumps(out))'''

PENDING=r'''import json
from sqlalchemy import inspect,text
from app.db.database import engine
out={'pending':0,'speaker':0,'preexisting_v5f_states':0}
def walk(value):
 if isinstance(value,dict):
  if value.get('pipeline')=='v3j_v5f':out['preexisting_v5f_states']+=1
  pending=value.get('pending')
  if isinstance(pending,dict):
   out['pending']+=1
   if (pending.get('calls') or {}).get('speaker'):out['speaker']+=1
  for item in value.values():walk(item)
 elif isinstance(value,list):
  for item in value:walk(item)
with engine.connect() as c:
 for table in ['family_members','chat_sessions']:
  for col in inspect(engine).get_columns(table):
   if str(col['type']).upper()!='JSON':continue
   name=col['name'];assert name.replace('_','').isalnum()
   for row in c.execute(text('SELECT `'+name+'` FROM `'+table+'` WHERE `'+name+'` IS NOT NULL')):
    value=row[0]
    if isinstance(value,(str,bytes)):value=json.loads(value)
    walk(value)
print(json.dumps(out))'''

class LocalTLS(http.client.HTTPSConnection):
    def connect(self):
        import socket
        raw=socket.create_connection(('127.0.0.1',443),timeout=10)
        self.sock=self._context.wrap_socket(raw,server_hostname=p.HOST)


def compose(path):
    return ['docker','compose','--project-name','backend','--env-file','.env.production',
            '-f','docker-compose.demo.yml','-f',str(path),'up','-d','--no-deps','--no-build','api']


def running_probe(code):
    return json.loads(p.output(['docker','exec','-i','backend-api-1','python','-'],input=code.encode()))


def stopped_probe(image,code):
    return json.loads(p.output(['docker','run','--rm','-i','--network','backend_default','--memory=256m','--memory-swap=384m',
        '--env-file',str(R/'before.env'),'-v','backend_media_data:/data/media:ro','--entrypoint','python',image,'-'],input=code.encode()))


def main():
    gates=json.loads((R/'release-gates.json').read_text())
    assert gates['integration_sha']==p.SHA and gates['all_required_gates_passed']
    assert gates['local_suite']=={'run':130,'skipped':1,'failures':0,'errors':0}
    assert gates['cloud_suite']==gates['local_suite']
    assert gates['approved_candidate_backend_equivalent'] and gates['provider_audit_passed']
    assert gates['known_quality_limitations_accepted_for_release'] and gates['client_not_changed']
    assert gates['candidate_focus_cases']==8 and gates['candidate_focus_checks']==51
    assert not (R/'deployment.json').exists(),'already_deployed_inspect_first'
    before=p.inspect();original=p.env(before)
    assert before['Image']==(R/'before-image').read_text(),'production_changed_after_candidate'
    assert original==dict(line.split('=',1) for line in (R/'before.env').read_text().splitlines())
    assert original['INTERVIEW_PIPELINE']=='v3j_v4d' and original['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256']==p.OLD_PIN
    pending=running_probe(PENDING);p.write('preactivation-pending.json',pending)
    assert pending['preexisting_v5f_states']==0 and pending['speaker']==0 and pending['pending']==0,'pending_requests_need_attention'
    for name in [p.NAME]:
        p.call(['docker','stop',name],stdout=subprocess.DEVNULL)
    for prefix in ['candidate']:
        directory=R/(prefix+'-nginx')
        if (directory/'nginx.pid').exists():
            p.call(['nginx','-p',str(directory)+'/', '-c',str(R/(prefix+'-nginx.conf')),'-s','quit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    p.call(['nginx','-t'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    p.call(['systemctl','is-active','--quiet','nginx'])
    # Back up the actual executing source, rather than the historical Compose working directory.
    with (R/'source-before.tar').open('wb') as stream:
        p.call(['docker','cp','backend-api-1:/app','-'],stdout=stream)
    for name,directory in [('nginx-before.tar.gz','/etc/nginx'),('tls-before.tar.gz','/etc/letsencrypt'),('oss-config-before.tar.gz',next(m['Source'] for m in before['Mounts'] if m['Destination']=='/run/shinian-oss'))]:
        with tarfile.open(R/name,'w:gz') as archive:archive.add(directory,arcname=Path(directory).name)
    (R/'env.production.backup').write_bytes((B/'.env.production').read_bytes())
    p.progress('preactivation_verified',pending_speaker_calls=0)
    switched=False;nginx_stopped=False;old_stopped=False
    try:
        # Close the public entry during the data snapshot so user writes cannot race the comparison.
        nginx_stopped=True;p.call(['systemctl','stop','nginx'])
        pending=running_probe(PENDING);p.write('quiesced-pending.json',pending)
        assert pending['preexisting_v5f_states']==0 and pending['pending']==0 and pending['speaker']==0,'request_started_during_maintenance_entry'
        old_stopped=True;p.call(['docker','stop','backend-api-1'],stdout=subprocess.DEVNULL)
        with gzip.open(R/'database.sql.gz','wb') as stream:
            process=subprocess.Popen(['docker','exec','backend-db-1','sh','-c',
                'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces ai_memories'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            for block in iter(lambda:process.stdout.read(1024*1024),b''):stream.write(block)
            assert process.wait()==0,'database_backup_failed'
        with (R/'media.tar.gz').open('wb') as stream:
            p.call(['docker','run','--rm','--memory=64m','-v','backend_media_data:/backup:ro','--entrypoint','tar',before['Image'],'-C','/backup','-czf','-','.'],stdout=stream)
        with gzip.open(R/'database.sql.gz','rb') as stream:
            dump=stream.read()
            assert len(dump)>100 and b'Dump completed on' in dump,'database_archive_incomplete'
        for name in ['media.tar.gz','source-before.tar','nginx-before.tar.gz','tls-before.tar.gz','oss-config-before.tar.gz']:
            with tarfile.open(R/name) as archive:assert archive.getmembers(),name
        before_data=stopped_probe(before['Image'],SNAPSHOT);p.write('data-before.json',before_data)
        backups={name:{'bytes':(R/name).stat().st_size,'sha256':hashlib.sha256((R/name).read_bytes()).hexdigest()}
            for name in ['database.sql.gz','media.tar.gz','source-before.tar','nginx-before.tar.gz','tls-before.tar.gz','oss-config-before.tar.gz','env.production.backup']}
        p.write('backup-verification.json',{'readable':True,'files':backups})
        p.progress('backups_verified')
        switched=True  # Compose can partially replace a container before returning an error.
        p.call(compose(R/'production-override.json'),cwd=B,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        health=p.health(8000);after=p.inspect()
        assert p.env(after)=={**original,**p.NEW},'production_environment_changed'
        assert after['Mounts']==before['Mounts'],'production_mounts_changed'
        assert after['HostConfig']['PortBindings']==before['HostConfig']['PortBindings'],'production_ports_changed'
        after_data=running_probe(SNAPSHOT);p.write('data-after.json',after_data)
        assert after_data==before_data,'business_data_changed_during_cutover'
        (B/'CLOUD_VERSION.md').write_text('Current production interview V6\nSource commit: '+p.SHA+'\nVersion: V6\nPipeline: v3j_v5f\nRuntime pin: '+p.PIN+'\nRelease: '+str(R)+'\nAuthoritative source: '+str(R/'source/cloud-deployment/backend')+'\n')
        p.call(['systemctl','start','nginx']);nginx_stopped=False
        connection=LocalTLS(p.HOST,context=ssl.create_default_context(),timeout=15)
        connection.request('GET','/health');response=connection.getresponse();public=json.loads(response.read());connection.close()
        assert response.status==200 and public['database']=='ok','https_health_failed'
        result={'activated':True,'integration_sha':p.SHA,'image':after['Image'],'version':'V6','pipeline':p.NEW['INTERVIEW_PIPELINE'],
            'runtime_pin':p.PIN,'release':str(R),'health':health,'https_health':public,
            'business_data_unchanged_during_cutover':True,'backup_verified':True,
            'business_counts_at_cutover':{key:value['count'] for key,value in after_data.items()},
            'ports_mounts_full_environment_preserved':True,'oss_preserved':original.get('MEDIA_STORAGE')=='oss',
            'pending_speaker_calls_before_cutover':0,'fallback':'same new image and runtime settings; INTERVIEW_PIPELINE=v3j_v4d',
            'formal_three_round_quality_acceptance':False,'production_postrelease_scenarios':'pending'}
        p.write('deployment.json',result);p.progress('activated',**result)
    except Exception as exc:
        recovery='old_service';recovery_errors=[]
        try:
            if switched:
                p.call(compose(R/'fallback-v4d-override.json'),cwd=B,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                recovery='new_image_compatible_v4d_fallback'
            elif old_stopped:p.call(['docker','start','backend-api-1'],stdout=subprocess.DEVNULL)
            p.health(8000)
        except Exception as recovery_exc:
            recovery_errors.append(type(recovery_exc).__name__)
        finally:
            if nginx_stopped:
                try:p.call(['systemctl','start','nginx'])
                except Exception as nginx_exc:recovery_errors.append(type(nginx_exc).__name__)
        actual=p.inspect()
        failure={'activated':False,'error_type':type(exc).__name__,'message':str(exc),'recovery':recovery,
            'recovery_errors':recovery_errors,'actual_image':actual['Image'],
            'actual_pipeline':p.env(actual).get('INTERVIEW_PIPELINE'),'data_restore_performed':False}
        p.write('activation-failure.json',failure);p.progress('activation_failed',**failure)
        raise


if __name__=='__main__':main()
