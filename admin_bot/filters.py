from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


class IsSuperAdmin(BaseFilter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        is_super_admin: bool,
    ) -> bool:
        return is_super_admin
