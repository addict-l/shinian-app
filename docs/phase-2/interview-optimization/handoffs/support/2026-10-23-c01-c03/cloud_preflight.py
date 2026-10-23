"""Read-only deployment preflight. Prints counts and non-secret metadata only."""
from pathlib import Path
import json
import re
import subprocess


def output(args):
    return subprocess.check_output(args)


data = json.loads(output(['docker', 'inspect', 'backend-api-1']))[0]
environment = dict(item.split('=', 1) for item in data['Config']['Env'])
scan = r'''import json
from sqlalchemy import inspect,text
from app.db.database import engine
result={'documents':0,'pending_holders':0,'pending_speaker_calls':0,'by_column':{}}
def walk(value, counts):
 if isinstance(value,dict):
  pending=value.get('pending')
  if isinstance(pending,dict):
   counts['pending_holders']+=1
   if (pending.get('calls') or {}).get('speaker'): counts['pending_speaker_calls']+=1
  for child in value.values():walk(child,counts)
 elif isinstance(value,list):
  for child in value:walk(child,counts)
with engine.connect() as connection:
 for table in ['family_members','chat_sessions']:
  for column in inspect(engine).get_columns(table):
   if str(column['type']).upper()!='JSON':continue
   name=column['name']
   assert name.replace('_','').isalnum()
   counts={'documents':0,'pending_holders':0,'pending_speaker_calls':0}
   for row in connection.execute(text('SELECT `'+name+'` FROM `'+table+'` WHERE `'+name+'` IS NOT NULL')):
    value=row[0]
    if isinstance(value,(str,bytes)):value=json.loads(value)
    counts['documents']+=1
    walk(value,counts)
   result['by_column'][table+'.'+name]=counts
   for key in counts:result[key]+=counts[key]
print(json.dumps(result))'''
pending = json.loads(output(['docker', 'exec', 'backend-api-1', 'python', '-c', scan]))
nginx = output(['nginx', '-T']).decode()
certificates = re.findall(r'^\s*ssl_certificate\s+([^;]+);', nginx, re.M)
keys = re.findall(r'^\s*ssl_certificate_key\s+([^;]+);', nginx, re.M)
report = {
    'image': data['Image'],
    'revision': (data['Config'].get('Labels') or {}).get('org.opencontainers.image.revision'),
    'pipeline': environment.get('INTERVIEW_PIPELINE'),
    'runtime_pin': environment.get('INTERVIEW_V3J_RUNTIME_MANIFEST_SHA256'),
    'media_storage': environment.get('MEDIA_STORAGE', 'local'),
    'compose_configs': (data['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files'),
    'mounts': [{'type': m['Type'], 'destination': m['Destination'], 'read_write': m['RW']} for m in data['Mounts']],
    'code_mount_present': any(m['Destination'] == '/app' or m['Destination'].startswith('/app/') for m in data['Mounts']),
    'pending_scan': pending,
    'tls_certificate_paths': certificates,
    'tls_key_paths': keys,
    'read_only': True,
}
print(json.dumps(report, ensure_ascii=False))
