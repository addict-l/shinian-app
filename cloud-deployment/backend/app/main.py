import logging, os
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import engine
from app.api.family import router as families_router
from app.api.family_members import router as family_members_router
from app.api.memories import router as memories_router
from app.api.chat import router as chat_router, workflow as chat_workflow
from app.api.workflow import router as workflow_router
from app.api.memoirs import router as memoirs_router
from app.ai.llm_client import LLMServiceError, LLMConfigurationError, LLMResponseFormatError
from app.services.chat_service import ChatSessionNotFoundError
from app.services.family_service import FamilyNotFoundError
from app.services.family_member_service import FamilyMemberNotFoundError
from app.services.memory_service import InvalidFamilyMemberError
from app.schemas.workflow import HealthResponse
from app.services.media_storage import MediaStorageError

allowed_hosts = [
    host.strip()
    for host in os.getenv(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,testserver',
    ).split(',')
    if host.strip()
]

import asyncio
from contextlib import asynccontextmanager
from app.services.memory_maintenance import drain_cleanup

@asynccontextmanager
async def lifespan(app):
    # Opt-in turn deployments prepare their SDK and pooled API connections at
    # startup. No model inference or user data is sent by the models-list call.
    if os.getenv('LLM_TURN_MODEL', '').strip():
        try:
            client = await asyncio.to_thread(chat_workflow.chat._get_llm_client)
            await asyncio.to_thread(client.warm_transport)
        except Exception as error:
            logging.getLogger('aimemories').warning('AI connection preparation deferred: %s', type(error).__name__)
    async def cleanup():
        while True:
            try:
                await asyncio.to_thread(drain_cleanup)
            except Exception as error:
                logging.getLogger('aimemories').error('Photo cleanup retry deferred: %s', type(error).__name__)
            await asyncio.sleep(15)
    worker = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

app = FastAPI(title='AI Memories API', version='0.6.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
from app.api.authentication import router as authentication_router
from app.api.family_access import authorize_business_request
app.include_router(authentication_router)
for router in [families_router,family_members_router,memories_router,chat_router,workflow_router,memoirs_router]:
    app.include_router(router, dependencies=[Depends(authorize_business_request)])

@app.middleware('http')
async def private_api_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/health', response_model=HealthResponse)
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return HealthResponse(status='ok', database='ok', llm_configured=bool(
        (os.getenv('LLM_API_KEY_B64') or os.getenv('LLM_API_KEY') or os.getenv('DASHSCOPE_API_KEY'))
        and (os.getenv('LLM_BASE_URL') or os.getenv('DASHSCOPE_BASE_URL'))
        and os.getenv('LLM_MODEL')
    ))

async def known_error(request: Request, error: Exception):
    if isinstance(error, MediaStorageError):
        return JSONResponse(status_code=503, content={'detail':'照片存储暂时不可用，请稍后重试'})
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

for error_type in [MediaStorageError,ChatSessionNotFoundError,FamilyNotFoundError,FamilyMemberNotFoundError,InvalidFamilyMemberError,
                   LLMConfigurationError,LLMServiceError,LLMResponseFormatError,SQLAlchemyError]:
    app.add_exception_handler(error_type,known_error)
