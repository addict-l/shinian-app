"""Scoped test setup/audit. Run ONLY inside the isolated candidate container.

Synthetic target checkpoints avoid replaying unrelated modules for every case.
No provider reply is supplied. All evaluated answers use actual HTTPS/model calls.
"""
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from app.db.database import SessionLocal, engine
from app.models.chat_session import ChatSessionModel
from app.models.chat_message import ChatMessageModel
from app.models.family_member import FamilyMemberModel
from app.schemas.story_information import StoryInformation
from app.schemas.guided_interview import GuidedInterviewState
from app.services.contract_interview_state import questions, v3j_runtime
from app.services.contract_v3j_interview import fresh
from app.services.contract_life_overview import new_data
from app.services.guided_interview import opening_text

req = json.load(sys.stdin)
assert engine.url.database == 'shinian_story_v5f_20261026', 'isolated DB only'
with SessionLocal.begin() as db:
    session = db.get(ChatSessionModel, req['session'])
    assert session and session.family_id == req['family']
    person = db.get(FamilyMemberModel, session.primary_person_id)
    assert person.family_id == req['family']
    if req['action'] == 'seed':
        assert not list(db.scalars(select(ChatMessageModel).where(
            ChatMessageModel.session_id == session.id, ChatMessageModel.role == 'user')))
        life = new_data()
        for item in life['questions'].values():
            item['status'] = 'skipped'
        life.update(status='confirmed', confirmed_version=2, version=2)
        person.life_interview = life
        module = req['module']
        qids = [q['id'] for q in questions(module)]
        state = GuidedInterviewState(version=3, module=module, module_selected=True,
            runtime_version=v3j_runtime().version, topic_index=qids.index(req['qid']))
        if req.get('old_flow'):
            state.contract_state = fresh(req['qid'], v3j_runtime())
        info = StoryInformation.model_validate(session.information or {})
        info.guided_interview = state
        session.information = info.model_dump(mode='json')
        session.version += 1
        db.add(ChatMessageModel(id=str(uuid4()), session_id=session.id, role='assistant',
            type='text', content=opening_text(state), created_at=datetime.now(timezone.utc)))
    elif req['action'] != 'audit':
        raise ValueError('unknown action')
    print(json.dumps({'life': person.life_interview,
        'guide': (session.information or {}).get('guided_interview')}, ensure_ascii=False))
