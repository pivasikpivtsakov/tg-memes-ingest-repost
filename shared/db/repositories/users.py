from sqlalchemy.exc import IntegrityError

from shared.db.models import User
from shared.db.repositories.base import PostgresRepository


class UserRepository(PostgresRepository):
    async def exists(self, user_id: int) -> bool:
        async with self._session() as session:
            user = await session.get(User, user_id)
            return user is not None

    async def ensure(
        self,
        *,
        user_id: int,
        first_name: str,
        last_name: str | None,
        username: str | None,
    ) -> None:
        found = await self.exists(user_id)
        if found:
            return
        try:
            async with self._session() as session:
                session.add(User(
                    id=user_id,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                ))
        except IntegrityError:
            # Two first sign-ins of the same id raced; the other one inserted the row.
            found = await self.exists(user_id)
            if not found:
                raise
