from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from search_app.schemas import TelegramUser, UserAuth
from search_app.services import InvalidHashError, InvalidInitDataError, InvalidTokenError
from search_app.store import Store

_bearer = HTTPBearer()


def get_store(request: Request) -> Store:
    return request.state.store


StoreDep = Annotated[Store, Depends(get_store)]


def get_telegram_user(store: StoreDep, init_data: Annotated[str, Query()]) -> TelegramUser:
    try:
        return store.telegram_auth.validate(init_data)
    except InvalidInitDataError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except InvalidHashError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


def get_user_auth(
    store: StoreDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> UserAuth:
    try:
        return store.tokens.decode(credentials.credentials)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


TelegramUserDep = Annotated[TelegramUser, Depends(get_telegram_user)]
