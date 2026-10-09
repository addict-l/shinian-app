import logging, os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import engine
from app.api.family import router as families_router
from app.api.family_members import router as family_members_router
from app.api.memories import router as memories_router
from app.api.chat import router as chat_router
from app.api.workflow import router as workflow_router
from app.ai.llm_client import LLMServiceError, LLMConfigurationError, LLMResponseFormatError
from app.services.chat_service import ChatSessionNotFoundError
from app.services.family_service import FamilyNotFoundError
from app.services.family_member_service import FamilyMemberNotFoundError
from app.services.memory_service import InvalidFamilyMemberError
from app.schemas.workflow import HealthResponse

allowed_hosts = [
    host.strip()
    for host in os.getenv(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,testserver',
    ).split(',')
    if host.strip()
]

app = FastAPI(title='AI Memories API', version='0.3.0')
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
for router in [families_router,family_members_router,memories_router,chat_router,workflow_router]:
    app.include_router(router)

@app.get('/health', response_model=HealthResponse)
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return HealthResponse(status='ok', database='ok', llm_configured=all(os.getenv(k) for k in ['DASHSCOPE_API_KEY','DASHSCOPE_BASE_URL','LLM_MODEL']))

async def known_error(request: Request, error: Exception):
    if isinstance(error, (ChatSessionNotFoundError,FamilyNotFoundError,FamilyMemberNotFoundError)):
        return JSONResponse(status_code=404, content={'detail':str(error)})
    if isinstance(error, InvalidFamilyMemberError):
        return JSONResponse(status_code=400, content={'detail':str(error)})
    if isinstance(error, LLMConfigurationError):
        return JSONResponse(status_code=503, content={'detail':'AI 服务尚未配置'})
    if isinstance(error, (LLMServiceError,LLMResponseFormatError)):
        return JSONResponse(status_code=502, content={'detail':'AI 暂时未能完成请求，你的原文已保留，请重试'})
    logging.getLogger('aimemories').error('Database operation failed: %s',type(error).__name__)
    return JSONResponse(status_code=503, content={'detail':'数据库暂时不可用，请重试'})

for error_type in [ChatSessionNotFoundError,FamilyNotFoundError,FamilyMemberNotFoundError,InvalidFamilyMemberError,
                   LLMConfigurationError,LLMServiceError,LLMResponseFormatError,SQLAlchemyError]:
    app.add_exception_handler(error_type,known_error)
