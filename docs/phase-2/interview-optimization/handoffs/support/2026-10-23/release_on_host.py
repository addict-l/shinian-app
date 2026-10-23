"""Protected release operations; run only on the authorized Shinian cloud host.

No credentials or business rows printed. Backups/config remain server-side.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

os.umask(0o077)
R = Path('/opt/shinian-releases/interview-v3j-v4d-770f841-20261023')
B = Path('/opt/ai-memories/backend')
TAG = 'shinian-api:interview-v3j-v4d-770f841-20261023'
CANDIDATE = 'shinian-v3j-v4d-isolated-770f841-20261023'
PIN = '8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f'
NEW = {'INTERVIEW_PIPELINE': 'v3j_v4d', 'INTERVIEW_V3J_RUNTIME_DIR': '/app/app/ai/interview_runtime_v3j_v4d',
       'INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256': PIN}


def call(args, **kw):
    return subprocess.run(args, check=True, **kw)


def output(args, **kw):
    return subprocess.check_output(args, **kw)


def inspect(name='backend-api-1'):
    return json.loads(output(['docker', 'inspect', name]))[0]


def env(data):
    return dict(x.split('=', 1) for x in data['Config']['Env'])


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def health(port=8000):
    for _ in range(80):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as f:
                d = json.load(f)
            if d.get('database') == 'ok':
                return d
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError('health_failed')


def compose(path):
    return ['docker', 'compose', '--project-name', 'backend', '--env-file', '.env.production',
            '-f', 'docker-compose.demo.yml', '-f', str(path), 'up', '-d', '--no-deps', '--no-build', 'api']


SNAPSHOT = r'''import json,hashlib
from pathlib import Path
from sqlalchemy import text,inspect
from app.db.database import engine
out={}
tables=['families','family_members','chat_sessions','chat_messages','memories','memory_drafts','media_assets','memory_people','memoir_settings']
with engine.connect() as c:
 existing=set(inspect(engine).get_table_names())
 for table in tables:
  if table not in existing:continue
  rows=[dict(r._mapping) for r in c.execute(text('SELECT * FROM '+table))]
  values=sorted(json.dumps(row,sort_keys=True,default=str,ensure_ascii=False) for row in rows)
  out[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
media={str(p.relative_to('/data/media')):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/data/media').rglob('*') if p.is_file()}
out['media_files']={'count':len(media),'sha256':hashlib.sha256(json.dumps(media,sort_keys=True).encode()).hexdigest()}
print(json.dumps(out))
'''


def snapshot_running():
    return json.loads(output(['docker', 'exec', '-i', 'backend-api-1', 'python', '-'], input=SNAPSHOT.encode()))


def snapshot_stopped():
    image = (R / 'before-image').read_text().strip()
    return json.loads(output(['docker', 'run', '--rm', '-i', '--memory=256m', '--memory-swap=384m',
                             '--network', 'backend_default', '--env-file', str(R / 'before.env'),
                             '-v', 'backend_media_data:/data/media:ro', '--entrypoint', 'python', image, '-'],
                            input=SNAPSHOT.encode()))


def prepare():
    assert not R.exists(), 'release_exists_inspect_before_resume'
    before = inspect()
    assert any(m.get('Name') == 'backend_media_data' and m.get('Destination') == '/data/media' for m in before['Mounts']), 'unexpected_media_mount'
    assert 'backend_default' in before['NetworkSettings']['Networks'], 'unexpected_network'
    assert all('\n' not in v and '\r' not in v for v in env(before).values()), 'unsupported_env_newline'
    R.mkdir(mode=0o700)
    (R / 'before-image').write_text(before['Image'])
    write(R / 'before-inspect.json', before)
    current_files = before['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
    current = Path(current_files[-1])
    assert current.is_file() and current.suffix == '.json'
    shutil.copy2(current, R / 'rollback-override.json')
    shutil.copy2(B / '.env.production', R / 'env.production.backup')
    original_env = env(before)
    (R / 'before.env').write_text(''.join(k + '=' + v + '\n' for k, v in original_env.items()))
    with tarfile.open('/tmp/shinian-v3j-cloud-770f841.tar.gz') as archive:
        members = archive.getmembers()
        assert all(not m.issym() and not m.islnk() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in members)
        archive.extractall(R / 'patch')
    manifest = json.loads((R / 'patch/source-manifest.json').read_text())
    names = [x['path'] for x in manifest['existing_changed']]
    probe = 'from pathlib import Path;import hashlib,json;names=' + repr(names) + ';print(json.dumps({n:hashlib.sha256(Path("/app",n).read_bytes()).hexdigest() for n in names}))'
    actual = json.loads(output(['docker', 'exec', 'backend-api-1', 'python', '-c', probe]))
    assert all(actual[x['path']] == x['base_sha256'] for x in manifest['existing_changed']), 'production_base_file_mismatch'
    for name, digest in manifest['patch_sha256'].items():
        assert hashlib.sha256((R / 'patch' / name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((R / 'patch/app/ai/interview_runtime_v3j_v4d/manifest.json').read_bytes()).hexdigest() == PIN
    parent = 'shinian-api:interview-v3j-parent-20261023'
    call(['docker', 'tag', before['Image'], parent])
    (R / 'patch/Dockerfile').write_text('FROM ' + parent + '\nCOPY app /app/app\nCOPY tests /app/tests\n'
        + 'LABEL org.opencontainers.image.revision="770f8419c76e1edc7205c76e88c97100dbdf17b1"\n'
        + 'LABEL shinian.interview.pipeline="v3j_v4d"\nLABEL shinian.interview.manifest="' + PIN + '"\n')
    with (R / 'build.log').open('w') as log:
        call(['docker', 'build', '-t', TAG, str(R / 'patch')], stdout=log, stderr=subprocess.STDOUT)
    config = json.loads(current.read_text())
    config['services']['api']['image'] = TAG
    config['services']['api']['environment'] = {k: v.replace('$', '$$') for k, v in {**original_env, **NEW}.items()}
    write(R / 'production-override.json', config)
    fallback = deepcopy(config)
    fallback['services']['api']['environment']['INTERVIEW_PIPELINE'] = 'v2'
    write(R / 'fallback-v2-override.json', fallback)
    # Runtime env for temporary test processes. Never output this file.
    run_env = {**original_env, **NEW}
    (R / 'runtime.env').write_text(''.join(k + '=' + v + '\n' for k, v in run_env.items()))
    with (R / 'candidate-unittest.log').open('w') as log:
        call(['docker', 'run', '--rm', '--memory=320m', '--memory-swap=448m', '--network', 'none',
              '--env-file', str(R / 'runtime.env'), '-e', 'DATABASE_URL=sqlite://', '-e', 'ALLOWED_HOSTS=testserver',
              '--entrypoint', 'python', TAG, '-c', "import pathlib,shutil,subprocess,sys; p=pathlib.Path('/validation/cloud-deployment/backend'); p.mkdir(parents=True); shutil.copytree('/app/tests',p/'tests'); (p/'app').symlink_to('/app/app',target_is_directory=True); r=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py','-q'],cwd=p); raise SystemExit(r.returncode)"],
             stdout=log, stderr=subprocess.STDOUT)
    dbname = 'shinian_v3j_20261023_770f841'
    call(['docker', 'exec', 'backend-db-1', 'sh', '-c',
          'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE ' + dbname + ' CHARACTER SET utf8mb4"'],
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    db_env = env(inspect('backend-db-1'))
    # The temporary candidate uses only its own database and a private media directory.
    from urllib.parse import quote
    run_env['DATABASE_URL'] = 'mysql+pymysql://root:' + quote(db_env['MYSQL_ROOT_PASSWORD'], safe='') + '@db:3306/' + dbname + '?charset=utf8mb4'
    run_env['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,testserver'
    (R / 'candidate.env').write_text(''.join(k + '=' + v + '\n' for k, v in run_env.items()))
    (R / 'candidate-media').mkdir()
    write(R / 'candidate-metadata.json', {'name': CANDIDATE, 'database': dbname, 'port': 18011})
    call(['docker', 'run', '-d', '--name', CANDIDATE, '--memory=256m', '--memory-swap=384m', '--network', 'backend_default',
          '--env-file', str(R / 'candidate.env'), '-p', '127.0.0.1:18011:8000',
          '-v', str(R / 'candidate-media') + ':/data/media', TAG], stdout=subprocess.DEVNULL)
    h = health(18011)
    write(R / 'prepared.json', {'prepared': True, 'candidate_health': h, 'image': inspect(CANDIDATE)['Image'],
          'production_unchanged': inspect()['Image'] == before['Image'], 'pin': PIN})
    print(json.dumps({'prepared': True, 'release': str(R), 'candidate_health': h, 'production_unchanged': True}), flush=True)


def activate():
    assert json.loads((R / 'candidate-verification.json').read_text())['passed'], 'candidate_verification_required'
    before = inspect()
    assert before['Image'] == (R / 'before-image').read_text().strip(), 'production_changed_since_prepare'
    call(['docker', 'stop', CANDIDATE], stdout=subprocess.DEVNULL)
    activated = False
    try:
        call(['docker', 'stop', 'backend-api-1'], stdout=subprocess.DEVNULL)
        with (R / 'database.sql').open('wb') as f:
            call(['docker', 'exec', 'backend-db-1', 'sh', '-c',
                  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --no-tablespaces ai_memories'],
                 stdout=f, stderr=subprocess.DEVNULL)
        with (R / 'media.tar.gz').open('wb') as f:
            call(['docker', 'run', '--rm', '--memory=64m', '-v', 'backend_media_data:/backup:ro',
                  '--entrypoint', 'tar', before['Image'], '-C', '/backup', '-czf', '-', '.'], stdout=f)
        with tarfile.open(R / 'source-before.tar.gz', 'w:gz') as archive:
            for p in (B / 'app').rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:
                    archive.add(p, arcname=str(p.relative_to(B)))
        with tarfile.open(R / 'nginx-before.tar.gz', 'w:gz') as archive:
            archive.add('/etc/nginx', arcname='nginx')
        assert (R / 'database.sql').stat().st_size > 100
        with tarfile.open(R / 'media.tar.gz') as archive:
            archive.getmembers()
        before_data = snapshot_stopped()
        write(R / 'data-before.json', before_data)
        activated = True
        call(compose(R / 'production-override.json'), cwd=B, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        h = health()
        after = inspect()
        expected_env = {**env(before), **NEW}
        assert env(after) == expected_env, 'environment_changed_unexpectedly'
        assert after['Mounts'] == before['Mounts'] and after['HostConfig']['PortBindings'] == before['HostConfig']['PortBindings'], 'ports_or_volumes_changed'
        after_data = snapshot_running()
        assert before_data == after_data, 'business_data_changed_during_deployment'
        for p in (R / 'patch/app').rglob('*'):
            if p.is_file():
                dest = B / p.relative_to(R / 'patch')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
        result = {'activated': True, 'health': h, 'commit': '770f8419c76e1edc7205c76e88c97100dbdf17b1',
                  'pipeline': 'v3j_v4d', 'manifest_sha256': PIN, 'image': after['Image'], 'release': str(R),
                  'business_data_unchanged': True, 'ports_volumes_other_env_preserved': True,
                  'business_counts': {k: v['count'] for k, v in after_data.items()},
                  'backup_verified': True, 'known_flow_issues_accepted_for_user_testing': True,
                  'formal_three_round_acceptance': False}
        write(R / 'deployment.json', result)
        (B / 'CLOUD_VERSION.md').write_text('Interview v3j + v4d\nSource commit: 770f8419c76e1edc7205c76e88c97100dbdf17b1\nPipeline: v3j_v4d\nRelease: ' + str(R) + '\n')
        print(json.dumps(result), flush=True)
    except Exception:
        if activated:
            call(compose(R / 'fallback-v2-override.json'), cwd=B, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            call(['docker', 'start', 'backend-api-1'], stdout=subprocess.DEVNULL)
        health()
        raise


if __name__ == '__main__':
    {'prepare': prepare, 'activate': activate}[sys.argv[1]]()
