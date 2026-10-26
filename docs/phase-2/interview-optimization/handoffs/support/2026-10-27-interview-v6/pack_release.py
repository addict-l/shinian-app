from pathlib import Path
import hashlib,io,json,subprocess,tarfile
W=Path('/Users/student03/Desktop/shinian-validation/worktrees/story-listening-20261027')
A=Path(__file__).resolve().parent
release=json.loads((A/'release-code.json').read_text());sha=release['code_sha']
def git(*a):return subprocess.check_output(['git',*a],cwd=W)
names=git('ls-tree','-r','--name-only',sha).decode().splitlines()
names=[n for n in names if n.startswith(('cloud-deployment/backend/','docs/prototypes/full-interview-','tools/')) or n=='docs/question-bank-freeze-v2.json']
names=[n for n in names if not (Path(n).name.startswith('.env') and Path(n).name!='.env.production.example')]
files={n:git('show',sha+':'+n) for n in names}
digests={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
backend={n:h for n,h in digests.items() if n.startswith('cloud-deployment/backend/')}
digest=hashlib.sha256(json.dumps(backend,sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert digest==release['tested_backend_content_sha256'],digest
manifest={**release,'source_sha256':digests,'backend_content_sha256':digest}
raw=(json.dumps(manifest,indent=2)+'\n').encode();(A/'source-manifest.json').write_bytes(raw)
with tarfile.open(A/'interview-v6-source.tar.gz','w:gz') as tar:
    for n,b in [('source-manifest.json',raw),*[(f'source/{n}',b) for n,b in files.items()]]:
        t=tarfile.TarInfo(n);t.size=len(b);t.mode=0o600;tar.addfile(t,io.BytesIO(b))
result={'archive_sha256':hashlib.sha256((A/'interview-v6-source.tar.gz').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256(raw).hexdigest(),'files':len(files),'backend_content_sha256':digest}
(A/'archive-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
