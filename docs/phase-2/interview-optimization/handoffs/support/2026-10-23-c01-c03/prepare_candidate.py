"""Prepare an isolated candidate from a fixed Git archive; never switches production.

Run on the authorized cloud host as root. Secret configuration remains on host.
The HTTPS listener is a separate loopback Nginx instance, not a production reload.
"""
from pathlib import Path
from copy import deepcopy
from urllib.parse import quote
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
import stat

os.umask(0o077)
SHA = 'ed38ab2c4738874d01b4470a10a8826c1c3da90d'
PIN = '8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f'
R = Path('/opt/shinian-releases/interview-c01-c03-ed38ab2-20261023')
ARCHIVE = Path('/home/admin/shinian-c01-c03-ed38ab2-20261023.tar.gz')
REPLAY_ARCHIVE = Path('/home/admin/claude-interview-replay-data-20261023-f8b3914.zip')
NAME = 'shinian-c01-c03-ed38ab2-20261023'
IMAGE = 'shinian-api:c01-c03-ed38ab2-20261023'
DB = 'shinian_c01_c03_ed38ab2_20261023'
HOST = 'aimemory.47-82-83-74.nip.io'
HTTP_PORT = 18012
TLS_PORT = 18444


def call(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(args, **kwargs):
    return subprocess.check_output(args, **kwargs)


def inspect(name='backend-api-1'):
    return json.loads(output(['docker', 'inspect', name]))[0]


def env(data):
    return dict(item.split('=', 1) for item in data['Config']['Env'])


def write(name, value):
    (R / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def progress(stage, **details):
    print(json.dumps({'stage': stage, **details}, ensure_ascii=False), flush=True)


def health(port):
    for _ in range(90):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
                value = json.load(response)
            if value.get('database') == 'ok':
                return value
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError('candidate_health_failed')


def main():
    assert not R.exists(), 'release_exists_inspect_before_resume'
    before = inspect()
    original = env(before)
    assert original['INTERVIEW_PIPELINE'] == 'v3j_v4d'
    assert original['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'] == PIN
    assert not any(m['Destination'] == '/app' or m['Destination'].startswith('/app/') for m in before['Mounts'])
    assert 'backend_default' in before['NetworkSettings']['Networks']
    assert all('\n' not in value and '\r' not in value for value in original.values())
    R.mkdir(mode=0o700)
    write('before-inspect.json', before)  # protected on host; never exported
    (R / 'before.env').write_text(''.join(key + '=' + value + '\n' for key, value in original.items()))
    (R / 'before-image').write_text(before['Image'])
    config_path = Path(before['Config']['Labels']['com.docker.compose.project.config_files'].split(',')[-1])
    config = json.loads(config_path.read_text())
    shutil.copy2(config_path, R / 'before-override.json')
    with tarfile.open(ARCHIVE) as archive:
        members = archive.getmembers()
        assert all(not m.issym() and not m.islnk() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in members)
        archive.extractall(R, filter='data')
    manifest = json.loads((R / 'source-manifest.json').read_text())
    assert manifest['integration_sha'] == SHA
    for name, digest in manifest['source_sha256'].items():
        assert hashlib.sha256((R / 'source' / name).read_bytes()).hexdigest() == digest, name
    app = R / 'source/cloud-deployment/backend/app'
    assert hashlib.sha256((app / 'ai/interview_runtime_v3j_v4d/manifest.json').read_bytes()).hexdigest() == PIN
    expected = manifest['production_backend_sha256']
    probe = 'from pathlib import Path;import json,hashlib; names=' + repr(list(expected)) + '; print(json.dumps({n:hashlib.sha256(Path("/app",n).read_bytes()).hexdigest() for n in names}))'
    actual = json.loads(output(['docker', 'exec', 'backend-api-1', 'python', '-c', probe]))
    assert actual == expected, 'production_source_changed_since_reference'
    assert hashlib.sha256(REPLAY_ARCHIVE.read_bytes()).hexdigest() == 'f8b39141903954ad7d52415b9e84f724e57bb93a841a1493e6d3828749b3f8b7'
    with zipfile.ZipFile(REPLAY_ARCHIVE) as archive:
        assert archive.testzip() is None
        assert all(not Path(item.filename).is_absolute() and '..' not in Path(item.filename).parts
                   and not stat.S_ISLNK(item.external_attr >> 16) for item in archive.infolist())
        archive.extractall(R / 'replay')
    write('replay-data-verification.json', {'archive_sha256': 'f8b39141903954ad7d52415b9e84f724e57bb93a841a1493e6d3828749b3f8b7',
         'holdout_used_for_tuning': False, 'evaluation_home': 'replay/interview-eval'})
    progress('source_verified', fixed_sha=SHA, production_files=len(expected))
    parent = 'shinian-api:c01-c03-parent-ed38ab2'
    call(['docker', 'tag', before['Image'], parent])
    (R / 'Dockerfile').write_text('FROM ' + parent + '\nCOPY source/cloud-deployment/backend/ /app/\n'
        + 'LABEL org.opencontainers.image.revision="' + SHA + '"\n'
        + 'LABEL io.shinian.backend-tree="' + manifest['backend_tree'] + '"\n'
        + 'LABEL io.shinian.source-manifest-sha256="' + hashlib.sha256((R / 'source-manifest.json').read_bytes()).hexdigest() + '"\n'
        + 'LABEL shinian.source_base="649b5b900244fd3742f3226f8e2b6d9d07387992"\n'
        + 'LABEL shinian.release_mode="interview-c01-c03-integration"\n'
        + 'LABEL shinian.interview.pipeline="v3j_v4d"\n'
        + 'LABEL shinian.interview.manifest="' + PIN + '"\n')
    (R / '.dockerignore').write_text('*\n!Dockerfile\n!source\n!source/**\n')
    with (R / 'build.log').open('w') as log:
        call(['docker', 'build', '-t', IMAGE, str(R)], stdout=log, stderr=subprocess.STDOUT)
    progress('image_built')
    # Complete repository-shaped validation input. Tests use SQLite and cannot reach a provider.
    unit_env = dict(original)
    unit_env['DATABASE_URL'] = 'sqlite://'
    unit_env['ALLOWED_HOSTS'] = 'testserver'
    unit_env['MEDIA_STORAGE'] = 'local'
    unit_env['SHINIAN_EVAL_HOME'] = '/evaluation'
    (R / 'unittest.env').write_text(''.join(key + '=' + value + '\n' for key, value in unit_env.items()))
    with (R / 'candidate-unittest.log').open('w') as log:
        tests = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--memory=384m', '--memory-swap=512m',
            '--env-file', str(R / 'unittest.env'), '-v', str(R / 'source') + ':/validation:ro',
            '-v', str(R / 'replay/interview-eval') + ':/evaluation:ro',
            '-w', '/validation/cloud-deployment/backend', '--entrypoint', 'python', IMAGE,
            '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'], stdout=log, stderr=subprocess.STDOUT)
    write('unittest-result.json', {'exit_code': tests.returncode, 'network': 'none', 'source': SHA})
    progress('container_tests_finished', exit_code=tests.returncode)
    # Only image/env references are changed in future production/fallback configurations.
    new = deepcopy(config)
    new['services']['api']['image'] = IMAGE
    new['services']['api']['environment'] = {key: value.replace('$', '$$') for key, value in original.items()}
    write('production-override.json', new)
    fallback = deepcopy(new)
    fallback['services']['api']['environment']['INTERVIEW_PIPELINE'] = 'v2'
    write('fallback-v2-override.json', fallback)
    # A separate DB and local-only media make candidate writes independent of production and OSS.
    call(['docker', 'exec', 'backend-db-1', 'sh', '-c',
          'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE ' + DB + ' CHARACTER SET utf8mb4"'],
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    db_environment = env(inspect('backend-db-1'))
    candidate_env = dict(original)
    candidate_env['DATABASE_URL'] = 'mysql+pymysql://root:' + quote(db_environment['MYSQL_ROOT_PASSWORD'], safe='') + '@db:3306/' + DB + '?charset=utf8mb4'
    candidate_env['MEDIA_STORAGE'] = 'local'
    candidate_env['MEDIA_ROOT'] = '/data/media'
    candidate_env['ALLOWED_HOSTS'] = HOST + ',localhost,127.0.0.1,testserver'
    (R / 'candidate.env').write_text(''.join(key + '=' + value + '\n' for key, value in candidate_env.items()))
    (R / 'candidate-media').mkdir()
    call(['docker', 'run', '-d', '--name', NAME, '--memory=384m', '--memory-swap=512m', '--network', 'backend_default',
          '--env-file', str(R / 'candidate.env'), '-p', '127.0.0.1:' + str(HTTP_PORT) + ':8000',
          '-v', str(R / 'candidate-media') + ':/data/media', IMAGE], stdout=subprocess.DEVNULL)
    candidate_health = health(HTTP_PORT)
    progress('candidate_http_healthy', health=candidate_health)
    # Separate Nginx master with its own pid/config; production Nginx is neither changed nor reloaded.
    nginx_dir = R / 'candidate-nginx'
    nginx_dir.mkdir()
    (nginx_dir / 'client-body').mkdir()
    shutil.chown(nginx_dir / 'client-body', user='www-data', group='www-data')
    conf = '''worker_processes 1;
pid %(root)s/nginx.pid;
error_log %(root)s/error.log warn;
events { worker_connections 128; }
http {
 access_log %(root)s/access.log;
 client_body_temp_path %(root)s/client-body;
 server {
  listen 127.0.0.1:%(tls_port)s ssl;
  server_name %(host)s;
  ssl_certificate /etc/letsencrypt/live/%(host)s/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/%(host)s/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  client_max_body_size 9m;
  location / {
   proxy_pass http://127.0.0.1:%(http_port)s;
   proxy_set_header Host $host;
   proxy_set_header X-Forwarded-Proto https;
   proxy_connect_timeout 5s;
   proxy_read_timeout 600s;
  }
 }
}
''' % {'root': nginx_dir, 'tls_port': TLS_PORT, 'host': HOST, 'http_port': HTTP_PORT}
    (R / 'candidate-nginx.conf').write_text(conf)
    with (R / 'candidate-nginx-check.log').open('w') as log:
        call(['nginx', '-p', str(nginx_dir) + '/', '-c', str(R / 'candidate-nginx.conf'), '-t'], stdout=log, stderr=subprocess.STDOUT)
        call(['nginx', '-p', str(nginx_dir) + '/', '-c', str(R / 'candidate-nginx.conf')], stdout=log, stderr=subprocess.STDOUT)
    result = {'prepared': True, 'integration_sha': SHA, 'candidate': NAME, 'image': inspect(NAME)['Image'],
              'pipeline': original['INTERVIEW_PIPELINE'], 'runtime_pin': PIN,
              'candidate_health': candidate_health, 'candidate_database': DB, 'http_port': HTTP_PORT,
              'https_loopback_port': TLS_PORT, 'https_identity': HOST,
              'https_transport': 'verified production certificate on separate loopback Nginx, reached over SSH forwarding',
              'production_image_unchanged': inspect()['Image'] == before['Image'],
              'production_nginx_modified_or_reloaded': False,
              'container_unittest_exit_code': tests.returncode, 'production_data_writes': False,
              'candidate_media_storage': 'local_isolated', 'fallback_prepared_pipeline': 'v2'}
    assert result['production_image_unchanged']
    write('prepared.json', result)
    progress('prepared', **result)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if R.exists():
            write('prepare-failure.json', {'error_type': type(exc).__name__, 'message': str(exc), 'production_switch_attempted': False})
        progress('prepare_failed', error_type=type(exc).__name__)
        raise
