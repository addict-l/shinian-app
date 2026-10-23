"""A v2-only sidecar for API skeleton setup and v2-to-v3 continuity checks.

Uses the candidate's isolated DB/media. Never touches production; explicit
skeleton skips use v2 fixed replies and spend no model calls.
"""
import importlib.util
from pathlib import Path
import json
import socket
import shutil

spec=importlib.util.spec_from_file_location('candidate','/home/admin/prepare-c01-c03-ed38ab2.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
R=p.R
prepared=json.loads((R/'prepared.json').read_text())
name=p.NAME+'-v2-setup'
environment=dict(line.split('=',1) for line in (R/'candidate.env').read_text().splitlines())
environment['INTERVIEW_PIPELINE']='v2'
(R/'legacy-setup.env').write_text(''.join(k+'='+v+'\n' for k,v in environment.items()))
p.call(['docker','run','-d','--name',name,'--network','backend_default','--memory=256m','--memory-swap=384m',
    '--env-file',str(R/'legacy-setup.env'),'-p','127.0.0.1::8000','-v',str(R/'candidate-media')+':/data/media',p.IMAGE],stdout=p.subprocess.DEVNULL)
info=p.inspect(name);http_port=int(info['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort'])
p.health(http_port)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));tls_port=sock.getsockname()[1]
directory=R/'legacy-setup-nginx';directory.mkdir();(directory/'client-body').mkdir();shutil.chown(directory/'client-body',user='www-data',group='www-data')
conf=(R/'candidate-nginx.conf').read_text().replace(str(R/'candidate-nginx'),str(directory)).replace('127.0.0.1:'+str(prepared['https_loopback_port'])+' ssl','127.0.0.1:'+str(tls_port)+' ssl').replace('127.0.0.1:'+str(prepared['http_port'])+';','127.0.0.1:'+str(http_port)+';')
(R/'legacy-setup-nginx.conf').write_text(conf)
with (R/'legacy-setup-nginx-check.log').open('w') as log:
 p.call(['nginx','-p',str(directory)+'/', '-c',str(R/'legacy-setup-nginx.conf'),'-t'],stdout=log,stderr=p.subprocess.STDOUT)
 p.call(['nginx','-p',str(directory)+'/', '-c',str(R/'legacy-setup-nginx.conf')],stdout=log,stderr=p.subprocess.STDOUT)
report={'name':name,'http_port':http_port,'https_loopback_port':tls_port,'pipeline':'v2','same_isolated_database':prepared['candidate_database'],'purpose':'v2 skeleton explicit-skip setup; module answers continue through v3j_v4d candidate','production_modified':False}
p.write('legacy-setup.json',report);print(json.dumps(report))
