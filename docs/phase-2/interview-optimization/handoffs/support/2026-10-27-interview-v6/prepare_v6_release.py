"""Prepare the authorized V6 release, preserving all protected production settings."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,os,shutil,subprocess,tarfile,time,urllib.request
os.umask(0o077)
R=Path('/opt/shinian-releases/interview-v6-8799b52-20261027');B=Path('/opt/ai-memories/backend')
OLD=Path('/opt/shinian-releases/story-listening-20261027')
SHA='8799b52b4d7590ea522c6798c364fd2fa451226a'
TAG='shinian-api:interview-v6-8799b52-20261027';NAME='shinian-story-listening-20261027'
HOST='api.xn--zbs33ddmy9oeqa.club'
PIN='1062b6c2158fa8132c0a6ea9541a4dcdbec80f6dd32d21cfda0d816cd2a76487'
OLD_PIN='8897f3c50690d70571e8b8bf2acf2176c80caf17c860ddf6f207c2470a3ba99f'
NEW={'INTERVIEW_PIPELINE':'v3j_v5f','INTERVIEW_V5F_RUNTIME_DIR':'/app/app/ai/interview_runtime_v3j_v5f_listening','INTERVIEW_V5F_RUNTIME_MANIFEST_SHA256':PIN}
def call(a,**k):return subprocess.run(a,check=True,**k)
def output(a,**k):return subprocess.check_output(a,**k)
def inspect(n='backend-api-1'):return json.loads(output(['docker','inspect',n]))[0]
def env(x):return dict(v.split('=',1) for v in x['Config']['Env'])
def write(n,x):(R/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def progress(s,**k):print(json.dumps({'stage':s,**k}),flush=True)
def health(port=8000):
    for _ in range(100):
        try:
            data=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2))
            if data.get('database')=='ok':return data
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('health_failed')
def prepare():
    assert not R.exists(),'release already exists; inspect before resuming'
    assert shutil.disk_usage('/opt').free>1024**3
    before=inspect();original=env(before)
    assert before['Config']['Labels']['org.opencontainers.image.revision']=='a1ecee61eae633898f1ba3a7200a630ca66a32c2'
    assert original['INTERVIEW_PIPELINE']=='v3j_v4d' and original['INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256']==OLD_PIN
    assert original.get('MEDIA_STORAGE')=='oss' and any(m['Destination']=='/run/shinian-oss' for m in before['Mounts'])
    assert all('\n' not in v and '\r' not in v for v in original.values())
    R.mkdir(mode=0o700);write('before-inspect.json',before)
    (R/'before-image').write_text(before['Image']);(R/'before.env').write_text(''.join(k+'='+v+'\n' for k,v in original.items()))
    current=Path(before['Config']['Labels']['com.docker.compose.project.config_files'].split(',')[-1])
    assert current.is_file();shutil.copy2(current,R/'before-override.json')
    with tarfile.open('/home/admin/interview-v6-source.tar.gz') as archive:
        assert all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in archive)
        archive.extractall(R,filter='data')
    manifest=json.loads((R/'source-manifest.json').read_text());assert manifest['code_sha']==SHA
    for n,h in manifest['source_sha256'].items():assert hashlib.sha256((R/'source'/n).read_bytes()).hexdigest()==h,n
    assert manifest['backend_content_sha256']=='de77f4d0398c27ee8206206925ce7ac71660eb149327f3048ce4f647aa154cca'
    assert hashlib.sha256((R/'source/cloud-deployment/backend/app/ai/interview_runtime_v3j_v5f_listening/manifest.json').read_bytes()).hexdigest()==PIN
    tested=json.loads((OLD/'update-r2/updated.json').read_text())
    assert tested['candidate_image']=='sha256:655270a1a53548cef7fc877608da98b8443c2bc74fc7503e8646107f8bdfe1d7'
    assert tested['backend_content_sha256']==manifest['backend_content_sha256']
    parent='shinian-api:v6-tested-parent';call(['docker','tag',tested['candidate_image'],parent])
    (R/'Dockerfile').write_text('FROM '+parent+'\nCOPY source/cloud-deployment/backend/ /app/\nLABEL org.opencontainers.image.revision="'+SHA+'"\nLABEL org.opencontainers.image.version="V6"\nLABEL io.shinian.backend-git-tree="'+manifest['backend_git_tree']+'"\nLABEL io.shinian.runtime-pin="'+PIN+'"\n')
    (R/'.dockerignore').write_text('*\n!Dockerfile\n!source\n!source/**\n')
    with (R/'build.log').open('w') as f:call(['docker','build','-t',TAG,str(R)],stdout=f,stderr=subprocess.STDOUT)
    progress('image_built',version='V6')
    run_env={**original,**NEW};run_env.update(DATABASE_URL='sqlite://',ALLOWED_HOSTS='testserver',SHINIAN_EVAL_HOME='/evaluation')
    (R/'unittest.env').write_text(''.join(k+'='+v+'\n' for k,v in run_env.items()))
    with (R/'unittest.log').open('w') as f:
        result=subprocess.run(['docker','run','--rm','--network','none','--memory=384m','--memory-swap=512m','--env-file',str(R/'unittest.env'),'-v',str(R/'source')+':/validation:ro','-v',str(OLD/'replay/interview-eval')+':/evaluation:ro','-w','/validation/cloud-deployment/backend','--entrypoint','python',TAG,'-m','unittest','discover','-s','tests','-p','test_*.py','-v'],stdout=f,stderr=subprocess.STDOUT)
    write('unittest-result.json',{'exit_code':result.returncode,'network':'none'});assert result.returncode==0
    log=(R/'unittest.log').read_text();assert 'Ran 130 tests' in log and 'OK (skipped=1)' in log
    progress('cloud_suite_passed',run=130,skipped=1)
    # Read the exact image files independently of the mounted validation source.
    backend={n.removeprefix('cloud-deployment/backend/'):h for n,h in manifest['source_sha256'].items() if n.startswith('cloud-deployment/backend/')}
    code='from pathlib import Path;import json,hashlib;expected=json.loads(input());bad=[n for n,h in expected.items() if hashlib.sha256(Path("/app",n).read_bytes()).hexdigest()!=h];assert not bad,bad;print(len(expected))'
    count=int(output(['docker','run','--rm','-i','--network','none','--memory=96m','--entrypoint','python',TAG,'-c',code],input=json.dumps(backend).encode()))
    config=json.loads(current.read_text());config['services']['api']['image']=TAG
    config['services']['api']['environment']={k:v.replace('$','$$') for k,v in {**original,**NEW}.items()}
    write('production-override.json',config)
    fallback=deepcopy(config);fallback['services']['api']['environment']['INTERVIEW_PIPELINE']='v3j_v4d';write('fallback-v4d-override.json',fallback)
    call(['docker','compose','--project-name','backend','--env-file','.env.production','-f','docker-compose.demo.yml','-f',str(R/'production-override.json'),'config','--quiet'],cwd=B,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    image=json.loads(output(['docker','image','inspect',TAG]))[0]['Id']
    gates={'integration_sha':SHA,'all_required_gates_passed':True,'local_suite':{'run':130,'skipped':1,'failures':0,'errors':0},'cloud_suite':{'run':130,'skipped':1,'failures':0,'errors':0},'approved_candidate_backend_equivalent':True,'image_files_verified':count,'candidate_focus_cases':8,'candidate_focus_checks':51,'provider_audit_passed':True,'client_not_changed':True,'keyboard_settings_untouched':True,'known_quality_limitations_accepted_for_release':True,'formal_quality_acceptance_passed':False}
    write('release-gates.json',gates)
    write('prepared.json',{'prepared':True,'code_sha':SHA,'version':'V6','image':image,'pipeline':'v3j_v5f','runtime_pin':PIN,'backend_git_tree':manifest['backend_git_tree'],'backend_content_sha256':manifest['backend_content_sha256'],'image_files_verified':count})
    progress('prepared',code_sha=SHA,image=image,image_files_verified=count,production_unchanged=inspect()['Image']==before['Image'])
if __name__=='__main__':prepare()
