"""Export canonical API dialogue; keep auth/real-family/backup material out.

Run after both HTTPS scenarios and independent audits have finished.
The whitelist includes synthetic API journals, not registration/login responses.
"""
from pathlib import Path
from html import escape
from html.parser import HTMLParser
import argparse,hashlib,json,re,shutil,zipfile

parser=argparse.ArgumentParser()
parser.add_argument('--artifacts',type=Path,required=True)
parser.add_argument('--private',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();A=args.artifacts;P=args.private;O=args.output
O.mkdir(parents=True,exist_ok=True)
RAW=O/'原始记录';RAW.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text())
write=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sections=[];checks=[]
order=['C03_childhood','C03_work','C03_family','C02_partial','C02_empty']+['C01_module_'+str(i) for i in range(4)]+['C01_skeleton_'+str(i) for i in range(4)]+['full_skeleton','C03_content_and_end']
titles={'C03_childhood':'C03 · 童年：补充与无补充收口','C03_work':'C03 · 工作：补充与无补充收口','C03_family':'C03 · 家庭：补充与无补充收口','C02_partial':'C02 · 已答后不想展开','C02_empty':'C02 · 整题无内容的拒答','full_skeleton':'完整骨架顺序、暂停继续、更正与确认','C03_content_and_end':'C03 · 同时补充并表示结束'}
for env,priv,label in [('production-https','production','正式 HTTPS'),('candidate-https','candidate','隔离候选 HTTPS')]:
 summary=read(A/env/'summary.json');audit=read(A/env/'independent-audit.json')
 assert summary['all_passed'] and audit['passed'] and audit['all_provider_calls_successful']
 dest=RAW/env;dest.mkdir(exist_ok=True)
 for path in sorted((A/env).glob('*.json')):shutil.copy2(path,dest/path.name)
 shutil.copytree(P/priv/'operations',dest/'http-journals',dirs_exist_ok=True)
 for name in order:
  path=A/env/(name+'.json')
  if not path.exists():continue
  case=read(path);assert case['passed'];final=case['responses'][-1]
  turns=[]
  if case['module']:
   opening=read(P/priv/'operations'/name/'select-module.json')['response']
   start=next(m['id'] for m in reversed(opening['messages']) if m['role']=='assistant' and m.get('type')!='notice')
   messages=final['messages'];index=next(i for i,m in enumerate(messages) if m['id']==start)
   for m in messages[index:]:
    if m['role'] in ('user','assistant') and m.get('type')!='notice':turns.append({'role':m['role'],'text':m['content']})
   guide=final['session']['information']['guided_interview'];phase=guide['phase']
   natural=phase=='review';cutoff=not natural
   state={'phase':phase,'topic_index':guide['topic_index'],'generation_offer':final.get('generation_offer') is not None}
  else:
   for m in final['life_overview']['turns']:
    if m['role'] in ('user','assistant'):turns.append({'role':m['role'],'text':m['content']})
   life=final['life_overview'];natural=life['status']=='confirmed';cutoff=not natural
   state={k:life.get(k) for k in ('status','question_id','paused','version')}
  assert turns and all(isinstance(t['text'],str) for t in turns)
  events=[e for e in case['events'] if e['role']=='respondent']
  for e in events:assert any(t['role']=='user' and t['text']==e['text'] for t in turns)
  sections.append({'id':env+'/'+name,'environment':label,'case':name,'title':titles.get(name,name),'turns':turns,'backend_state':state,
   'sample_cutoff':cutoff,'natural_completion':natural,'completion_scope':'question reached review; no generation/save' if natural and case['module'] else ('overview confirmed' if natural else 'bounded acceptance test; backend state retained'),
   'input_method':case['input_method'],'setup':case['setup']})
write(O/'逐字问答.json',sections)
intro='C01–C03 云端双层采访问答 · 2026-10-23'
notes='正式生产代码 ed38ab2；v3j/v4d；DeepSeek deepseek-v4-pro，thinking disabled。老人输入为固定验收原话或上轮公开材料 AI 回答的逐字重放，并非真人实时访谈；判定与说话层均为本轮新真实调用。未使用 gold/holdout 调参，未调用回忆生成或保存。候选通过带证书校验的 SSH 转发 HTTPS，生产通过正式公网 HTTPS。模块正文从选择模块开始；骨架准备与所有按钮操作保留在原始 HTTP journals。C02 保留原草稿固定句中的可选补充问句，停止的是目标追问。到核对不等于已确认保存。'
html=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+intro+'</title><style>body{margin:0;background:#f5f3ef;color:#262a29;font:16px/1.75 system-ui,sans-serif}main{max-width:920px;margin:auto;padding:36px 20px}h1{font-size:28px}h2{font-size:22px;margin:0 0 12px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}a{color:#225e52}article{background:white;border:1px solid #deded6;border-radius:16px;padding:24px;margin:24px 0}.meta{color:#59615e;font-size:13px}.turn{margin:18px 0;padding:12px 16px;border-left:3px solid #b9cec5;background:#f4f8f6}.user{background:#faf6ed;border-color:#d4bb8d}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin:4px 0}b{font-size:13px}details{font-size:14px}</style><main><h1>'+intro+'</h1><p>'+notes+'</p><nav>']
for i,s in enumerate(sections):html.append('<a href="#case'+str(i)+'">'+escape(s['environment']+' · '+s['title'])+'</a>')
html.append('</nav>');txt=[intro,notes,'']
expected=[]
for i,s in enumerate(sections):
 meta=json.dumps({k:s[k] for k in ('backend_state','sample_cutoff','natural_completion')},ensure_ascii=False)
 html.append('<article id="case'+str(i)+'"><div class="meta">'+escape(s['environment'])+'</div><h2>'+escape(s['title'])+'</h2><p class="meta">'+escape(meta)+'</p>')
 txt.extend([s['environment']+' · '+s['title'],meta])
 for j,t in enumerate(s['turns']):
  who='受访者' if t['role']=='user' else '采访者'
  html.append('<div class="turn '+('user' if t['role']=='user' else '')+'"><b>'+who+'</b><pre data-turn="'+str(i)+'-'+str(j)+'">'+escape(t['text'])+'</pre></div>')
  txt.extend([who+'：',t['text'],'']);expected.append(t['text'])
 html.append('<details><summary>采样与准备方式</summary><p>'+escape(s['input_method'])+'</p><p>'+escape(s['setup'])+'</p></details></article>')
 txt.append('')
html.append('</main></html>')
(O/'云端双层采访问答.html').write_text(''.join(html));(O/'云端双层采访问答.txt').write_text('\n'.join(txt))
class Parse(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.values=[]
 def handle_starttag(self,tag,attrs):
  if tag=='pre' and 'data-turn' in dict(attrs):self.active=True;self.values.append('')
 def handle_data(self,data):
  if self.active:self.values[-1]+=data
 def handle_endtag(self,tag):
  if tag=='pre':self.active=False
p=Parse();p.feed((O/'云端双层采访问答.html').read_text());assert p.values==expected
assert read(O/'逐字问答.json')==sections
for s in sections:
 for t in s['turns']:assert t['text'] in (O/'云端双层采访问答.txt').read_text()
# Safe, aggregate release metadata and complete helper sources. No server configuration is copied.
meta=O/'核验与工具';meta.mkdir(exist_ok=True)
allow=['deployment.json','post-release-summary.json','production-final-preflight.json','cloud_preflight.py','candidate-independent-audit-rerun.json','backup-verification.json','preactivation-pending.json','quiesced-pending.json','public-health-auth-check.json','release-gates.json','intake.json','replay-data-intake.json','source-manifest.json','preactivation-image-config-check.log','backend-all-tests.log','backend-all-tests-with-replay.log','cloud-tests-attempt-1.log','cloud-tests-final.log','cloud-prepare.log','cloud-resume.log','activation.log','candidate-https-attempt-0-transport.log','candidate-https.log','production-https.log','audit-attempt-1.log','prepare_candidate.py','resume_candidate.py','legacy_setup.py','activate_release.py','verify_candidate_https.py','audit_live_records.py','extract_test_family_records.py','export_verbatim.py']
for name in allow:shutil.copy2(A/name,meta/name)
for name in ['result.json','provenance.json','build.log']:
 if (A/'ios-display-probe'/name).exists():shutil.copy2(A/'ios-display-probe'/name,meta/('ios-'+name))
for name in ['LifeOverview.swift','SummaryProjection.swift','main.swift']:
 shutil.copy2(A/'ios-display-probe'/name,meta/('ios-'+name))
secret_values=[]
def find_secrets(v,key=''):
 if isinstance(v,dict):
  for k,x in v.items():find_secrets(x,k)
 elif isinstance(v,list):
  for x in v:find_secrets(x,key)
 elif isinstance(v,str) and key.lower() in ('token','password','access_token','refresh_token','api_key') and len(v)>=8:secret_values.append(v)
for env in ('candidate','production'):find_secrets(read(P/env/'auth.json'))
keyfile=Path('/Users/student03/Documents/ChatGPT/ai memory/exports/DeepSeek_API_Key.txt')
if keyfile.exists():
 content=keyfile.read_text();secret_values.extend(re.findall(r'sk-[A-Za-z0-9_-]{12,}',content))
files=[p for p in O.rglob('*') if p.is_file() and p.suffix!='.zip']
for file in files:
 content=file.read_text()
 assert not any(v in content for v in secret_values),'actual_credential_value_in_'+str(file.relative_to(O))
 assert not re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',content)
 assert not re.search(r'(?i)"(?:token|password|access_token|refresh_token|api_key)"\s*:\s*"[^"\s]{8,}"',content),'credential_field_in_'+str(file.relative_to(O))
report={'passed':True,'dialogue_sections':len(sections),'verbatim_turns':len(expected),'html_roundtrip_exact':True,'txt_contains_each_original_turn':True,'canonical_dialogue_json_exact':True,'actual_credential_values_scanned':True,'private_key_headers_scanned':True,'auth_files_excluded':True,'real_family_data_or_database_backup_included':False,'formal_three_round_quality_acceptance':False}
write(O/'导出核验.json',report)
manifest={str(p.relative_to(O)):sha(p) for p in sorted(O.rglob('*')) if p.is_file() and p.suffix!='.zip' and p.name!='附件清单.json'}
write(O/'附件清单.json',manifest)
zipname=O/'C01-C03问答与原始核验.zip'
with zipfile.ZipFile(zipname,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(O.rglob('*')):
  if p.is_file() and p.suffix!='.zip':z.write(p,str(p.relative_to(O)))
with zipfile.ZipFile(zipname) as z:
 assert z.testzip() is None
 for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
write(A/'delivery-summary.json',{'export':str(O),'zip':zipname.name,'sha256':sha(zipname),'zip_bytes':zipname.stat().st_size,**report})
print(json.dumps(read(A/'delivery-summary.json'),ensure_ascii=False,indent=2))
