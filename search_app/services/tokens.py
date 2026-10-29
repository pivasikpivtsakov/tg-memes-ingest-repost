from datetime import UTC, datetime, timedelta

import jwt
from pydantic import ValidationError

from search_app.schemas import UserAuth

_ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    pass


class TokensService:
    def __init__(self, *, secret: str, expiration: timedelta) -> None:
        self._secret = secret
        self._expiration = expiration

    def issue(self, user_id: int) -> str:
        now = datetime.now(UTC)
        payload = {"user_id": user_id, "iat": now, "exp": now + self._expiration}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def decode(self, token: str) -> UserAuth:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            return UserAuth.model_validate(payload)
        except (jwt.InvalidTokenError, ValidationError) as e:
            raise InvalidTokenError("Invalid or expired token") from e
