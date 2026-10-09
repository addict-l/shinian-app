"""Manage task-owned MySQL and FastAPI services through macOS launchd."""
from pathlib import Path
import os,sys,subprocess,plistlib,time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
UID = os.getuid()
SERVICES = {
    'mysql': ['com.aimemories.local.mysql', ['/usr/local/mysql/bin/mysqld', '--no-defaults',
        '--basedir=/usr/local/mysql', f'--datadir={RUNTIME / "mysql"}', '--bind-address=127.0.0.1',
        '--port=3307', f'--socket={RUNTIME / "mysql.sock"}', f'--pid-file={RUNTIME / "mysql.pid"}',
        '--mysqlx=OFF', '--character-set-server=utf8mb4', '--collation-server=utf8mb4_unicode_ci']],
    'api': ['com.aimemories.local.api', [str(ROOT / '.venv/bin/python'), '-m', 'uvicorn',
        'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1', '--timeout-keep-alive', '10']],
}

def manage(action, name):
    label,args=SERVICES[name]
    directory=Path.home()/'Library/LaunchAgents'
    directory.mkdir(parents=True,exist_ok=True)
    plist=directory/(label+'.plist')
    (RUNTIME/'logs').mkdir(parents=True,exist_ok=True)
    target=f'gui/{UID}/{label}'
    if action in ['start','restart']:
        if action=='restart':
            subprocess.run(['launchctl','bootout',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(50):
                if subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
                    break
                time.sleep(0.1)
            else:
                raise SystemExit('Service did not stop: '+name)
        data={'Label':label,'ProgramArguments':args,'WorkingDirectory':str(ROOT),
              'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
              'StandardOutPath':str(RUNTIME/'logs'/f'{name}.log'),
              'StandardErrorPath':str(RUNTIME/'logs'/f'{name}-error.log'),
              'EnvironmentVariables':{'PATH':'/usr/bin:/bin:/usr/local/mysql/bin','PYTHONUNBUFFERED':'1'}}
        with plist.open('wb') as f:plistlib.dump(data,f)
        result=subprocess.run(['launchctl','bootstrap',f'gui/{UID}',str(plist)],capture_output=True)
        if result.returncode and subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            raise SystemExit('launchd could not start '+name)
        print(name+': service started')
    elif action=='stop':
        subprocess.run(['launchctl','bootout',target],check=False)
        print(name+': service stopped')
    elif action=='status':
        p=subprocess.run(['launchctl','print',target],capture_output=True,text=True)
        print(name+': '+('loaded' if p.returncode==0 else 'stopped'))
    else:raise SystemExit('Use start, stop, restart, status')

if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    names=[sys.argv[2]] if len(sys.argv)>2 else ['mysql','api']
    if action=='stop':names.reverse()
    for name in names:manage(action,name)
