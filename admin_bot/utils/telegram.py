from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager

from aiogram.exceptions import TelegramBadRequest

_NOT_MODIFIED = ("message is not modified",)
_MESSAGE_GONE = ("message to delete not found", "message can't be deleted", "message to edit not found")


@contextmanager
def _ignore_bad_request(reasons: tuple[str, ...]) -> Generator[None]:
    try:
        yield
    except TelegramBadRequest as error:
        if not any(reason in error.message.lower() for reason in reasons):
            raise


def ignore_not_modified() -> AbstractContextManager[None]:
    return _ignore_bad_request(_NOT_MODIFIED)


def ignore_message_gone() -> AbstractContextManager[None]:
    return _ignore_bad_request(_MESSAGE_GONE)
