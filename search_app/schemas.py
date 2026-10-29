from pydantic import BaseModel


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    allows_write_to_pm: bool | None = None
    photo_url: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: TelegramUser


class UserAuth(BaseModel):
    user_id: int
