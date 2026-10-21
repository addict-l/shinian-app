"""A finite, evidence-based outline. No story expansion or implied life chronology."""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from fastapi import HTTPException
from app.db.database import SessionLocal
from app.models.family_member import FamilyMemberModel
from app.schemas.life_overview import LifeOverview, LifeField, LifeAction, LifeExtraction
from app.ai.llm_client import LLMResponseFormatError

QUESTIONS = (
    ('home', '成长的地方', '您小时候主要在哪里长大？'),
    ('learning', '读书或学艺', '您读书或学手艺的经历，大致是怎样的？'),
    ('early_work', '年轻时的工作与生活', '年轻时，您主要忙些什么事情？'),
    ('later_work', '后来的工作与生活', '再往后，您主要做的事情有没有变化？'),
    ('family', '重要家人', '您这一生，有哪些重要的家人或一起生活的人？'),
    ('changes', '记得的生活变化', '回头看，有哪些生活上的变化是您一直记得的？'),
    ('present', '如今的生活', '现在您的日子主要是怎么过的？'),
)
INTRO = '我们先聊几个简单的问题，了解您大致经历过哪些日子。记不清或暂时不想讲的，可以先跳过。之后您再选一段最想聊的，我们慢慢讲。'
PROMPT = '''你只记录人生骨架，不采访具体故事，不生成回复或新问题。输出fields必须列出全部七个话题，每话题恰好一次，逐项检查是否被本次回答覆盖。未涉及的话题输出pending和空evidence，不能遗漏检查。每条evidence必须逐字引用current_source及其message_id，不能改写。
七个topic_id对应人工预设问题。当前问题的简短答案足以记录，例如地名、没上学、做农活。不要求两个求学经历、不要求精确年份、婚姻、退休或成就。不把未提供、未知或不愿讲当作没有经历。
一次回答明确涉及后续话题时记录以免重复提问，但不能凭一般人生规律推算先后、日期、地点、关系或性格。early_work和later_work只在原文有相应阶段依据时分别记录；只有一个不带阶段的工作回答时只归当前被问的工作话题。不能把工作变化自动当作本人一直记得的生活转折。unknown和declined必须引用明确的记不清或不想讲。单独说“记不清”或“不想讲”只处理当前问题，其他六项仍为pending，不能扩展成拒绝全部话题。不能输出skipped。例如“年轻时给邻居修门，后来自己开了修理铺”同时明确覆盖early_work和later_work，两项分别引用原文；不能因为当前只问成长地点就漏记后续人生阶段。本人主动长讲完整原文已保留，只用原话摘录重要线索。语句不能回答当前问题时不冒充已答。'''

def new_data(required=True):
    from app.services.contract_interview_state import enabled
    if enabled():
        from app.services.contract_life_overview import new_data as contract_new
        return contract_new(required)
    now=datetime.now(timezone.utc).isoformat()
    return {'version':1,'status':'collecting','required':required,'paused':False,
        'fields':[LifeField(topic_id=k).model_dump(mode='json') for k,_,_ in QUESTIONS],
        'turns':[{'id':str(uuid4()),'role':'assistant','content':INTRO+'\n'+QUESTIONS[0][2],'created_at':now}],
        'requests':{},'pending':None,'confirmed_version':None}

def view(data):
    if data and data.get('schema_version') == 2:
        from app.services.contract_life_overview import view as contract_view
        return contract_view(data)
    if not data:return LifeOverview()
    fields=[LifeField.model_validate(f) for f in data['fields']]
    pending=next((i for i,f in enumerate(fields) if f.status=='pending'),None)
    return LifeOverview(version=data['version'],status=data['status'],required=data['required'],
        paused=data.get('paused',False),fields=fields,turns=data['turns'],
        question_id=QUESTIONS[pending][0] if pending is not None else None,
        question=QUESTIONS[pending][2] if pending is not None else None,
        question_number=pending+1 if pending is not None else 7,
        confirmed_version=data.get('confirmed_version'),
        pending_request_id=data['pending']['request_id'] if data.get('pending') else None,
        pending_action=data['pending'].get('request') if data.get('pending') else None)

def read(person_id):
    with SessionLocal() as db:
        person=db.get(FamilyMemberModel,str(person_id))
        if not person:raise HTTPException(404,'人物不存在')
        return view(person.life_interview)

def blocks(session, overview):
    guide=session.information.guided_interview
    return bool(guide and not guide.module_selected and overview.required and overview.status in ('collecting','review'))

def background(person_id):
    o=read(person_id)
    if o.status!='confirmed':return []
    return list({(q.message_id,q.quote):q for f in o.fields for q in f.evidence}.values())

def refresh_background(guide, person_id):
    """Checkpoint restoration must never revive a superseded outline quote."""
    if guide.version == 3:
        guide.background_sources = []
        return guide
    overview=read(person_id)
    outline_ids={t.id for t in overview.turns if t.role=='user'}
    current=background(person_id)
    guide.background_sources=[q for q in guide.background_sources if q.message_id not in outline_ids]+current
    facts=[]
    for fact in guide.facts:
        old=list(fact.evidence)
        fact.evidence=[q for q in old if q.message_id not in outline_ids or
            any(q.message_id==live.message_id and q.quote in live.quote for live in current)]
        if old and not fact.evidence:continue
        facts.append(fact)
    guide.facts=facts
    return guide


def perform(person_id, action: LifeAction, client):
    """Caller holds the person lock. Save raw input before any fallible model request."""
    with SessionLocal() as lookup:
        person = lookup.get(FamilyMemberModel, str(person_id))
        existing = person.life_interview if person else None
    from app.services.contract_interview_state import enabled
    if (existing and existing.get('schema_version') == 2) or (existing is None and enabled()):
        from app.services.contract_life_overview import perform as contract_perform
        return contract_perform(person_id, action, client)
    fingerprint=hashlib.sha256(action.model_dump_json().encode()).hexdigest()
    rid=str(action.client_request_id)
    with SessionLocal.begin() as db:
        person=db.get(FamilyMemberModel,str(person_id),with_for_update=True)
        if person is None:raise HTTPException(404,'人物不存在')
        data=json.loads(json.dumps(person.life_interview)) if person.life_interview else None
        requests=data.get('requests',{}) if data else {}
        if rid in requests:
            if requests[rid]!=fingerprint:raise HTTPException(409,'同一个请求标识不能更改操作内容')
            return view(data)
        pending=data.get('pending') if data else None
        if pending:
            if pending['request_id']!=rid or pending['hash']!=fingerprint:
                raise HTTPException(409,'上次回答已保留，请先重试完成该回答')
        else:
            if (data['version'] if data else 0)!=action.expected_version:
                raise HTTPException(409,'人生概览已更新，请重新读取后核对')
            if action.action=='begin':
                if data is None:data=new_data(required=False)
                data['paused']=False
            elif data is None:raise HTTPException(409,'请先开始了解人生骨架')
            elif action.action in ('answer','correct'):
                text=action.text.strip()
                if not text:raise HTTPException(422,'请填写回答或选择跳过')
                if action.action=='answer' and data['status']!='collecting':raise HTTPException(409,'请在概览中选择需要更正的内容')
                if action.action=='correct' and action.topic_id is None:raise HTTPException(422,'请选择要更正的话题')
                topic=action.topic_id if action.action=='correct' else view(data).question_id
                data['turns'].append({'id':rid,'role':'user','content':text,'created_at':datetime.now(timezone.utc).isoformat()})
                data['pending']={'request_id':rid,'hash':fingerprint,'topic_id':topic,'action':action.action,'text':text,'request':action.model_dump(mode='json')}
                # A correction invalidates confirmation immediately, even if extraction needs retry.
                data['confirmed_version']=None
                if action.action=='correct':data['status']='review'
            elif action.action=='confirm':
                if data['status']!='review':raise HTTPException(409,'请先完成或跳过骨架问题，再核对概览')
                data['status']='confirmed';data['confirmed_version']=data['version']+1
            elif action.action in ('pause','resume'):data['paused']=action.action=='pause'
            if not data.get('pending'):
                data['requests'][rid]=fingerprint;data['version']+=1
            person.life_interview=data
    if not data.get('pending'):return view(data)
    pending=data['pending']; text=pending['text']; topic=pending['topic_id']
    pause = bool(re.fullmatch(r'(?:先休息|暂停|先暂停|今天先不聊|暂时不想聊)[。！!\s]*', text))
    resume = data.get('paused') and bool(re.fullmatch(r'(?:继续|继续聊|接着讲)[。！!\s]*', text))
    if pending['action']=='answer' and (pause or resume):
        data['paused']=pause;data['pending']=None;data['requests'][rid]=fingerprint;data['version']+=1
        reply='好，先休息。您的回答和采访位置都已保留。' if pause else '好，我们接着聊。'+view(data).question
        data['turns'].append({'id':str(uuid5(NAMESPACE_URL,'life-reply:'+rid)),'role':'assistant','content':reply,'created_at':datetime.now(timezone.utc).isoformat()})
        with SessionLocal.begin() as db:db.get(FamilyMemberModel,str(person_id)).life_interview=data
        return view(data)
    skip=bool(re.fullmatch(r'(?:跳过|跳过这题|暂时跳过|先跳过)[。！!\s]*',text))
    if skip:
        extraction=LifeExtraction(fields=[LifeField(topic_id=k,status='skipped' if k==topic else 'pending') for k,_,_ in QUESTIONS])
    else:
        def validate(value):
            keys=[f.topic_id for f in value.fields]
            if set(keys)!={k for k,_,_ in QUESTIONS} or len(keys)!=7:raise LLMResponseFormatError('Check each of the seven outline topics exactly once')
            for f in value.fields:
                if f.status=='pending' and not f.evidence:continue
                if f.status not in ('known','unknown','declined') or not f.evidence:
                    raise LLMResponseFormatError('Outline facts require current original evidence')
                for q in f.evidence:
                    if str(q.message_id)!=rid or q.quote not in text:raise LLMResponseFormatError('Outline evidence must quote current answer')
                if f.status in ('unknown','declined'):
                    pattern='记不清|记不得|不记得|不知道|忘了|想不起|不清楚|说不准' if f.status=='unknown' else '不想|不愿|不说|不讲|不谈|先别|不要问'
                    if not any(re.search(pattern,q.quote) for q in f.evidence):raise LLMResponseFormatError('Unavailable topic requires explicit user words')
            return value
        extraction=(client() if callable(client) else client)._structured(PROMPT,{'questions':QUESTIONS,'current_topic':topic,
            'current_source':{'message_id':rid,'content':text}},LifeExtraction,validate)
    if pending['action']=='correct' and not any(f.topic_id==topic and f.status!='pending' for f in extraction.fields):
        raise LLMResponseFormatError('Correction must address the selected outline topic')
    fields={f['topic_id']:f for f in data['fields']}
    for f in extraction.fields:
        if f.status=='pending':continue
        # Corrections only change the explicitly selected topic. Other raw details remain saved.
        if pending['action']=='correct' and f.topic_id!=topic:continue
        if fields[f.topic_id]['status']=='pending' or f.topic_id==topic:
            fields[f.topic_id]=f.model_dump(mode='json')
    data['fields']=list(fields.values());data['pending']=None;data['paused']=False
    data['requests'][rid]=fingerprint;data['version']+=1
    if pending['action']=='answer':
        data['status']='collecting' if any(f['status']=='pending' for f in data['fields']) else 'review'
    reply=('我记下了。'+view(data).question if data['status']=='collecting' else '这些是您提供的人生线索。请先核对，有需要更正的地方可以告诉我；确认后再选想聊的部分。')
    data['turns'].append({'id':str(uuid5(NAMESPACE_URL,'life-reply:'+rid)),'role':'assistant','content':reply,'created_at':datetime.now(timezone.utc).isoformat()})
    with SessionLocal.begin() as db:
        person=db.get(FamilyMemberModel,str(person_id),with_for_update=True)
        person.life_interview=data
    return view(data)
