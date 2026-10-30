import hashlib
import hmac
import json
from collections.abc import Mapping
from urllib.parse import parse_qsl

from search_app.schemas import TelegramUser


class InvalidInitDataError(ValueError):
    pass


class InvalidHashError(Exception):
    pass


class TelegramAuthService:
    def __init__(self, *, bot_token: str, mock_init_data: str | None = None) -> None:
        self._secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        self._mock_init_data = (mock_init_data or "").strip() or None

    def validate(self, init_data: str) -> TelegramUser:
        if self._mock_init_data is not None:
            init_data = self._mock_init_data
        elif not init_data.strip():
            raise InvalidInitDataError("Missing init_data")

        try:
            fields = dict(parse_qsl(init_data, strict_parsing=True))
        except ValueError as e:
            raise InvalidInitDataError(f"Invalid init_data format: {e}") from e

        if self._mock_init_data is None and not self._has_valid_hash(fields):
            raise InvalidHashError("Invalid hash - authentication failed")

        try:
            return TelegramUser.model_validate(json.loads(fields["user"]))
        except (KeyError, ValueError) as e:
            raise InvalidInitDataError(f"Failed to extract user data: {e}") from e

    def _has_valid_hash(self, fields: Mapping[str, str]) -> bool:
        received_hash = fields.get("hash")
        if not received_hash:
            return False
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()) if k != "hash")
        calculated_hash = hmac.new(self._secret, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_hash, calculated_hash)
