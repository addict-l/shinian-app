from uuid import UUID
from fastapi import APIRouter
from app.schemas.chat import ChatSession, ChatSessionCreate, ChatMessage, ChatMessageCreate
from app.schemas.workflow import ChatState, DraftResponse
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix='/api/v1/chat', tags=['chat'])
workflow = WorkflowService()

@router.get('/sessions/{session_id}/state', response_model=ChatState)
def get_state(session_id: UUID):
    return workflow.state(session_id)

@router.post('/sessions', response_model=ChatSession, status_code=201)
def create_session(body: ChatSessionCreate):
    return workflow.create_session(body)

@router.post('/members/{person_id}/conversation', response_model=ChatState)
def open_person_conversation(person_id: UUID, family_id: UUID):
    return workflow.open_person(family_id, person_id)

@router.get('/sessions/{session_id}/conversation', response_model=ChatState)
def person_conversation_state(session_id: UUID):
    return workflow.person_state(session_id)

@router.post('/sessions/{session_id}/conversation/messages', response_model=ChatState, status_code=201)
def send_person_message(session_id: UUID, body: ChatMessageCreate):
    workflow.send(session_id, body)
    return workflow.person_state(session_id)

@router.get('/sessions', response_model=list[ChatSession])
def list_sessions(family_id: UUID | None = None):
    return workflow.chat.list_sessions(family_id)

@router.post('/sessions/{session_id}/start', response_model=ChatState)
def start_session(session_id: UUID):
    return workflow.start(session_id)

@router.get('/sessions/{session_id}/messages', response_model=list[ChatMessage])
def list_messages(session_id: UUID):
    return workflow.chat.list_messages(session_id)

@router.post('/sessions/{session_id}/messages', response_model=ChatState, status_code=201)
def send_message(session_id: UUID, body: ChatMessageCreate):
    return workflow.send(session_id, body)

@router.post('/sessions/{session_id}/draft', response_model=DraftResponse)
def generate_draft(session_id: UUID):
    return workflow.generate(session_id)
