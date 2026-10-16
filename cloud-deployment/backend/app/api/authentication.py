from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.schemas.authentication import AccountCredentials, AccountIdentity, LoginResponse
from app.services import authentication as auth

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])
bearer = HTTPBearer(auto_error=False)


def current_session(authorization: HTTPAuthorizationCredentials | None = Depends(bearer)):
    return auth.authenticate(authorization.credentials if authorization and authorization.scheme.lower() == 'bearer' else None)


def limit(request, operation, username):
    address = request.client.host if request.client else 'unknown'
    auth.throttle(operation + ':ip:' + address, 10 if operation == 'register' else 30, 3600 if operation == 'register' else 60)
    if operation == 'login':
        auth.throttle('login:account:' + username, 10, 60)


@router.post('/register', response_model=LoginResponse, status_code=201)
def register(body: AccountCredentials, request: Request, response: Response):
    limit(request, 'register', body.username)
    response.headers['Cache-Control'] = 'no-store'
    return auth.register(body.username, body.password.get_secret_value())


@router.post('/login', response_model=LoginResponse)
def login(body: AccountCredentials, request: Request, response: Response):
    limit(request, 'login', body.username)
    response.headers['Cache-Control'] = 'no-store'
    return auth.login(body.username, body.password.get_secret_value())


@router.get('/me', response_model=AccountIdentity)
def me(response: Response, principal=Depends(current_session)):
    response.headers['Cache-Control'] = 'no-store'
    return principal.identity()


@router.post('/logout', status_code=204)
def logout(principal=Depends(current_session)):
    auth.logout(principal)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
