"""Real MySQL + FastAPI; only AI is replaced to deterministically inject failures."""
from uuid import uuid4
from sqlalchemy import delete
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.chat import workflow
from app.api.workflow import workflow as draft_workflow
from app.ai.llm_client import LLMServiceError, LLMResponseFormatError
from app.schemas.memory import MemoryExtraction
from app.db.database import SessionLocal
from app.models.family import FamilyModel

class AIStub:
    def chat(self, messages):
        return '后来发生了什么？'
    def extract_memory(self, raw):
        return MemoryExtraction(title='爷爷的故事', summary=raw, memory_date=None, people=['爷爷'])

@pytest.fixture
def context(monkeypatch):
    fake=AIStub()
    monkeypatch.setattr(workflow.chat,'_get_llm_client',lambda:fake)
    monkeypatch.setattr(draft_workflow.memories,'_get_llm_client',lambda:fake)
    monkeypatch.setattr(workflow.memories,'_get_llm_client',lambda:fake)
    client=TestClient(app)
    family=client.post('/api/v1/families/',json={'name':'异常注入测试家庭'}).json()['id']
    person=client.post('/api/v1/family-members/',json={'family_id':family,'name':'测试爷爷','relationship':'爷爷','birth_date':'1940-05-12'}).json()['id']
    session=client.post('/api/v1/chat/sessions',json={'family_id':family,'primary_person_id':person,'title':'测试'}).json()['id']
    yield client,fake,family,session
    # This fixture deletes only its own disposable test family and cascade children.
    with SessionLocal.begin() as db:
        db.execute(delete(FamilyModel).where(FamilyModel.id==family))

def test_ai_failure_preserves_user_and_retry_is_idempotent(context,monkeypatch):
    client,fake,_,session=context
    path=f'/api/v1/chat/sessions/{session}'
    client.post(path+'/start')
    body={'content':'爷爷教我骑车。','client_request_id':str(uuid4())}
    def fail(_):raise LLMServiceError('sensitive upstream detail')
    monkeypatch.setattr(fake,'chat',fail)
    response=client.post(path+'/messages',json=body)
    assert response.status_code==502
    assert 'sensitive' not in response.text
    rows=client.get(path+'/messages').json()
    assert [m['role'] for m in rows]==['assistant','user']
    assert rows[-1]['content']==body['content']
    monkeypatch.setattr(fake,'chat',lambda _: '后来呢？')
    successful=client.post(path+'/messages',json=body)
    assert successful.status_code==201 and len(successful.json()['messages'])==3
    assert client.post(path+'/messages',json=body).json()==successful.json()

def test_broken_ai_structure_does_not_save_memory(context,monkeypatch):
    client,fake,family,session=context
    path=f'/api/v1/chat/sessions/{session}'
    client.post(path+'/messages',json={'content':'我记得爷爷教我骑车。'})
    def fail(_):raise LLMResponseFormatError('invalid JSON')
    monkeypatch.setattr(fake,'extract_memory',fail)
    assert client.post(path+'/draft').status_code==502
    assert client.get('/api/v1/memories/',params={'family_id':family}).json()==[]
    assert client.get(path+'/messages').json()[0]['content']=='我记得爷爷教我骑车。'

def test_unknown_date_remains_null_and_draft_replay(context):
    client,_,family,session=context
    path=f'/api/v1/chat/sessions/{session}'
    client.post(path+'/messages',json={'content':'记不得是哪一天，爷爷教我骑车。'})
    draft=client.post(path+'/draft').json()
    assert draft['memory']['memory_date'] is None
    assert client.post(path+'/draft').json()==draft
    saved=client.post('/api/v1/memory-drafts/'+draft['id']+'/confirm',json={'revision':draft['revision']})
    assert saved.status_code==200 and saved.json()['memory_date'] is None
    assert len(client.get('/api/v1/memories/',params={'family_id':family}).json())==1

def test_foreign_family_person_rejected(context):
    client,_,_,session=context
    other=client.post('/api/v1/families/',json={'name':'不同的测试家庭'}).json()['id']
    original=workflow.chat.get_session(session)
    try:
        response=client.post('/api/v1/chat/sessions',json={'family_id':other,'primary_person_id':str(original.primary_person_id),'title':'越界人物'})
        assert response.status_code==400
    finally:
        with SessionLocal.begin() as db:db.execute(delete(FamilyModel).where(FamilyModel.id==other))

def test_missing_session_and_whitespace_rejected(context):
    client,_,_,session=context
    assert client.post(f'/api/v1/chat/sessions/{uuid4()}/start').status_code==404
    assert client.post(f'/api/v1/chat/sessions/{session}/messages',json={'content':'   '}).status_code==422

def test_stale_revision_cannot_confirm(context):
    client,_,_,session=context
    path=f'/api/v1/chat/sessions/{session}'
    client.post(path+'/messages',json={'content':'爷爷教我骑车。'})
    draft=client.post(path+'/draft').json()
    assert client.post('/api/v1/memory-drafts/'+draft['id']+'/confirm',json={'revision':str(uuid4())}).status_code==409
