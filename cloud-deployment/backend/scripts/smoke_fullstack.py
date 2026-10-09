"""Real HTTP, MySQL and configured LLM; an isolated, clearly named test family."""
import io,json,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import httpx
from PIL import Image
BASE='http://127.0.0.1:8000'
client=httpx.Client(base_url=BASE,timeout=120,follow_redirects=True,trust_env=False)
results=[]
def check(name,condition):
    assert condition,name
    results.append(name)
    print('PASS: '+name,flush=True)
def call(method,path,status=200,**kwargs):
    r=client.request(method,path,**kwargs)
    assert r.status_code==status,(path,r.status_code,r.text[:300])
    return r.json() if r.content else None

def main():
    started=time.time()
    check('health and database',call('GET','/health')['database']=='ok')
    local=call('POST','/api/v1/local/bootstrap')['id']
    check('bootstrap replay',call('POST','/api/v1/local/bootstrap')['id']==local)
    family=call('POST','/api/v1/families/',201,json={'name':'自动联调测试家庭 '+str(uuid4())[:8]})['id']
    person_body={'family_id':family,'client_request_id':str(uuid4()),'name':'联调爷爷张建国','relationship':'爷爷','birth_date':'1940-05-12'}
    person=call('POST','/api/v1/family-members/',201,json=person_body)['id']
    check('member persisted and replay',call('POST','/api/v1/family-members/',201,json=person_body)['id']==person)
    call('POST','/api/v1/family-members/',409,json={**person_body,'name':'different'})
    check('conflicting request rejected',True)
    call('POST','/api/v1/family-members/',422,json={**person_body,'birth_date':'2999-01-01'})
    check('future birthday rejected',True)
    session_body={'family_id':family,'primary_person_id':person,'title':'爷爷教我骑自行车','client_request_id':str(uuid4())}
    session=call('POST','/api/v1/chat/sessions',201,json=session_body)['id']
    check('session replay',call('POST','/api/v1/chat/sessions',201,json=session_body)['id']==session)
    path='/api/v1/chat/sessions/'+session
    call('POST',path+'/draft',400)
    check('empty conversation cannot generate',True)
    opening=call('POST',path+'/start')
    check('real AI opening',len(opening['messages'])==1 and opening['messages'][0]['role']=='assistant')
    check('opening replay',call('POST',path+'/start')['messages']==opening['messages'])
    body={'content':'2010年5月1日，爷爷张建国在家门口的小广场教我骑自行车。他一直扶着车后座，告诉我看前方别害怕。那天我终于学会了，爷爷笑得特别开心。','client_request_id':str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:call('POST',path+'/messages',201,json=body),range(2)))
    check('concurrent message retry creates one user and one reply',len(replies[0]['messages'])==3 and replies[0]==replies[1])
    check('message chronology',[m['role'] for m in replies[0]['messages']]==['assistant','user','assistant'])
    check('generation available',replies[0]['can_generate'])
    draft=call('POST',path+'/draft')
    check('draft preserves raw user words',draft['memory']['raw_content']==body['content'])
    check('correct extracted date',draft['memory']['memory_date']=='2010-05-01')
    check('draft cache',call('POST',path+'/draft')==draft)
    check('preview not saved yet',call('GET','/api/v1/memories/',params={'family_id':family})==[])
    call('POST',path+'/messages',201,json={'content':'补充一下，当时只有我和爷爷，没有其他家人。','client_request_id':str(uuid4())})
    call('POST','/api/v1/memory-drafts/'+draft['id']+'/confirm',409,json={'revision':draft['revision']})
    check('stale preview rejected',True)
    fresh=call('POST',path+'/draft')
    check('revision changes with conversation',fresh['revision']!=draft['revision'])
    call('POST',path+'/media',415,params={'client_request_id':str(uuid4())},files={'file':('bad.jpg',b'not a photo','image/jpeg')})
    check('invalid image rejected',True)
    buf=io.BytesIO();Image.new('RGB',(32,32),'blue').save(buf,format='PNG');image=buf.getvalue()
    def upload(id):return call('POST',path+'/media',201,params={'client_request_id':id},files={'file':('test.png',image,'image/png')})
    upload_id=str(uuid4());media=upload(upload_id)
    check('image replay',upload(upload_id)==media)
    call('DELETE',path+'/media',204);call('GET',media['url'],404)
    check('image removal',True)
    media=upload(str(uuid4()));replacement=upload(str(uuid4()));call('GET',media['url'],404)
    check('single image replacement',True)
    confirm_path='/api/v1/memory-drafts/'+fresh['id']+'/confirm'
    with ThreadPoolExecutor(max_workers=3) as pool:
        memories=list(pool.map(lambda _:call('POST',confirm_path,json={'revision':fresh['revision']}),range(3)))
    check('concurrent confirmation saves once',len({m['id'] for m in memories})==1)
    saved=memories[0]
    check('saved member and photo association',saved['person_ids']==[person] and saved['media_urls']==[replacement['url']])
    r=client.get(replacement['url'])
    check('downloaded photo is JPEG',r.status_code==200 and Image.open(io.BytesIO(r.content)).format=='JPEG')
    check('fresh HTTP client reads persisted memory',httpx.get(BASE+'/api/v1/memories/'+saved['id'],trust_env=False).json()['id']==saved['id'])
    check('family has exactly one memory',len(call('GET','/api/v1/memories/',params={'family_id':family}))==1)
    check('family isolation',all(m['id']!=saved['id'] for m in call('GET','/api/v1/memories/',params={'family_id':local})))
    call('POST',path+'/messages',409,json={'content':'不允许追加','client_request_id':str(uuid4())})
    check('completed conversation protected',True)
    check('completed message retry is safe',len(call('POST',path+'/messages',201,json=body)['messages'])==5)
    result={'checks':results,'count':len(results),'elapsed_seconds':round(time.time()-started,2),'family_id':family,'person_id':person,'session_id':session,'memory_id':saved['id'],'media_url':replacement['url']}
    (Path(__file__).resolve().parents[1]/'.runtime/logs/real-integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('All '+str(len(results))+' real integration checks passed.',flush=True)
if __name__=='__main__':main()
