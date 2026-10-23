"""Resume the recorded preparation stages; production remains untouched."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import socket
import subprocess
import tarfile

spec = importlib.util.spec_from_file_location('prepared_release', '/home/admin/prepare-c01-c03-ed38ab2.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
R = p.R
assert p.inspect()['Image'] == (R / 'before-image').read_text(), 'production_changed'
with tarfile.open('/home/admin/c01-c03-validation-tools.tar.gz') as archive:
    assert all(not item.issym() and not item.islnk() and not item.name.startswith('/') and '..' not in Path(item.name).parts for item in archive)
    archive.extractall(R, filter='data')
additions = json.loads((R / 'validation-additions.json').read_text())
for name, digest in additions['sha256'].items():
    assert hashlib.sha256((R / 'source' / name).read_bytes()).hexdigest() == digest
with (R / 'candidate-unittest-resumed.log').open('w') as log:
    result = subprocess.run(['docker','run','--rm','--network','none','--memory=384m','--memory-swap=512m',
        '--env-file',str(R/'unittest.env'),'-v',str(R/'source')+':/validation:ro',
        '-v',str(R/'replay/interview-eval')+':/evaluation:ro','-w','/validation/cloud-deployment/backend',
        '--entrypoint','python',p.IMAGE,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],stdout=log,stderr=subprocess.STDOUT)
p.write('unittest-result-resumed.json',{'exit_code':result.returncode,'network':'none','fixed_sha':p.SHA,'validation_additions':additions['integration_sha']})
p.progress('container_tests_resumed',exit_code=result.returncode)
assert result.returncode == 0, 'cloud_unit_tests_failed'
old = p.inspect(p.NAME)
assert old['State']['Status'] == 'created' and old['Config']['Image'] == p.IMAGE, 'inspect_candidate_before_replacing'
p.write('created-container-port-conflict.json',{'name':p.NAME,'status':old['State']['Status'],'ports':old['HostConfig']['PortBindings']})
p.call(['docker','rm',p.NAME],stdout=subprocess.DEVNULL)
p.call(['docker','run','-d','--name',p.NAME,'--memory=384m','--memory-swap=512m','--network','backend_default',
    '--env-file',str(R/'candidate.env'),'-p','127.0.0.1::8000','-v',str(R/'candidate-media')+':/data/media',p.IMAGE],stdout=subprocess.DEVNULL)
candidate = p.inspect(p.NAME)
http_port = int(candidate['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort'])
health = p.health(http_port)
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0)); tls_port = sock.getsockname()[1]
nginx_dir = R/'candidate-nginx'
nginx_dir.mkdir(exist_ok=True)
(nginx_dir/'client-body').mkdir(exist_ok=True)
shutil.chown(nginx_dir/'client-body',user='www-data',group='www-data')
conf = '''user www-data;
worker_processes 1;
pid %(root)s/nginx.pid;
error_log %(root)s/error.log warn;
events { worker_connections 128; }
http {
 access_log %(root)s/access.log;
 client_body_temp_path %(root)s/client-body;
 client_body_buffer_size 128k;
 server {
  listen 127.0.0.1:%(tls)s ssl;
  server_name %(host)s;
  ssl_certificate /etc/letsencrypt/live/%(host)s/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/%(host)s/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  location / {
   proxy_pass http://127.0.0.1:%(http)s;
   proxy_set_header Host $host;
   proxy_set_header X-Forwarded-Proto https;
   proxy_read_timeout 600s;
  }
 }
}
''' % {'root':nginx_dir,'tls':tls_port,'host':p.HOST,'http':http_port}
(R/'candidate-nginx.conf').write_text(conf)
with (R/'candidate-nginx-check.log').open('w') as log:
    p.call(['nginx','-p',str(nginx_dir)+'/', '-c',str(R/'candidate-nginx.conf'),'-t'],stdout=log,stderr=subprocess.STDOUT)
    p.call(['nginx','-p',str(nginx_dir)+'/', '-c',str(R/'candidate-nginx.conf')],stdout=log,stderr=subprocess.STDOUT)
report={'prepared':True,'integration_sha':p.SHA,'candidate':p.NAME,'image':candidate['Image'],'candidate_database':p.DB,
    'pipeline':'v3j_v4d','runtime_pin':p.PIN,'candidate_health':health,'http_port':http_port,'https_loopback_port':tls_port,
    'https_identity':p.HOST,'https_transport':'verified certificate over separate loopback TLS listener and SSH forwarding',
    'production_image_unchanged':p.inspect()['Image']==(R/'before-image').read_text(),
    'production_nginx_modified_or_reloaded':False,'container_unittest_exit_code':result.returncode,
    'candidate_media_storage':'local_isolated','production_data_writes':False,'fallback_prepared_pipeline':'v2'}
assert report['production_image_unchanged']
p.write('prepared.json',report)
p.progress('prepared',**report)
