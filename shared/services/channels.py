import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from telethon import TelegramClient, functions, types
from telethon.errors import FloodWaitError, UserAlreadyParticipantError, UserNotParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import ChatInviteAlready
from telethon.utils import get_peer_id

from shared.redis import AllowedChatsRepository

logger = logging.getLogger(__name__)

_MUTE_UNTIL = 2147483647

_INVITE_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_C_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/c/(\d+)",
    re.IGNORECASE,
)
_USERNAME_URL_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,})",
    re.IGNORECASE,
)
_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,}$")
_RESERVED_PATHS = frozenset({
    "joinchat",
    "addstickers",
    "socks",
    "proxy",
    "share",
    "c",
    "s",
    "iv",
    "login",
    "confirmphone",
    "boost",
})


class ChannelTargetKind(StrEnum):
    USERNAME = "username"
    INVITE = "invite"
    ID = "id"


@dataclass(frozen=True, slots=True)
class ChannelTarget:
    kind: ChannelTargetKind
    value: str


@dataclass(slots=True)
class ChannelResult:
    chat_id: int | None = None
    title: str | None = None
    username: str | None = None
    label: str | None = None
    already_member: bool = False


def parse_channel_target(raw: str) -> ChannelTarget | None:
    text = raw.strip()
    if not text:
        return None

    invite = _INVITE_RE.search(text)
    if invite is not None:
        return ChannelTarget(ChannelTargetKind.INVITE, invite.group(1))

    private = _C_RE.search(text)
    if private is not None:
        return ChannelTarget(ChannelTargetKind.ID, f"-100{private.group(1)}")

    if text.startswith("@"):
        username = text[1:]
        if _USERNAME_RE.fullmatch(username):
            return ChannelTarget(ChannelTargetKind.USERNAME, username)
        return None

    if re.fullmatch(r"-100\d+", text):
        return ChannelTarget(ChannelTargetKind.ID, text)

    url = _USERNAME_URL_RE.search(text)
    if url is not None:
        username = url.group(1)
        if username.lower() not in _RESERVED_PATHS:
            return ChannelTarget(ChannelTargetKind.USERNAME, username)
        return None

    if _USERNAME_RE.fullmatch(text):
        return ChannelTarget(ChannelTargetKind.USERNAME, text)

    return None


def _label_for(entity) -> str:
    title = getattr(entity, "title", None) or "Unknown"
    username = getattr(entity, "username", None)
    username_part = f"@{username}" if username else "no username"
    return f"{title} ({username_part})"


def _from_entity(entity, *, already_member: bool = False) -> ChannelResult:
    username = getattr(entity, "username", None)
    return ChannelResult(
        already_member=already_member,
        chat_id=int(get_peer_id(entity)),
        title=getattr(entity, "title", None) or "Unknown",
        username=username,
        label=_label_for(entity),
    )


def _chat_from_updates(result):
    chats = getattr(result, "chats", None) or []
    for chat in chats:
        if getattr(chat, "broadcast", False) or getattr(chat, "megagroup", False):
            return chat
    if chats:
        return chats[0]
    return None


async def _mute(client: TelegramClient, entity) -> None:
    await client(functions.account.UpdateNotifySettingsRequest(
        peer=entity,
        settings=types.InputPeerNotifySettings(
            show_previews=False,
            silent=True,
            mute_until=_MUTE_UNTIL,
        ),
    ))


async def _get_entity(client: TelegramClient, target: ChannelTarget):
    if target.kind is ChannelTargetKind.USERNAME:
        return await client.get_entity(f"@{target.value}")
    if target.kind is ChannelTargetKind.ID:
        return await client.get_entity(int(target.value))
    raise ValueError(f"unsupported target kind {target.kind}")


async def resolve_channel(
    client: TelegramClient,
    target: ChannelTarget,
) -> ChannelResult:
    if target.kind is ChannelTargetKind.INVITE:
        invite = await client(CheckChatInviteRequest(target.value))
        if isinstance(invite, ChatInviteAlready):
            return _from_entity(invite.chat, already_member=True)
        title = getattr(invite, "title", None) or "Unknown"
        return ChannelResult(title=title, label=title)
    return _from_entity(await _get_entity(client, target))


async def _join_public(client: TelegramClient, target: ChannelTarget) -> tuple[object, bool]:
    entity = await _get_entity(client, target)
    try:
        await client(JoinChannelRequest(entity))
        return entity, False
    except UserAlreadyParticipantError:
        return entity, True


async def _join_invite(client: TelegramClient, invite_hash: str) -> tuple[object, bool]:
    try:
        result = await client(ImportChatInviteRequest(invite_hash))
        entity = _chat_from_updates(result)
        if entity is None:
            checked = await client(CheckChatInviteRequest(invite_hash))
            if isinstance(checked, ChatInviteAlready):
                entity = checked.chat
        if entity is None:
            raise RuntimeError("invite imported but channel entity is missing")
        return entity, False
    except UserAlreadyParticipantError:
        checked = await client(CheckChatInviteRequest(invite_hash))
        if isinstance(checked, ChatInviteAlready):
            return checked.chat, True
        raise


async def join_and_allow(
    client: TelegramClient,
    allowed_chats: AllowedChatsRepository,
    target: ChannelTarget,
) -> ChannelResult:
    if target.kind is ChannelTargetKind.INVITE:
        entity, already = await _join_invite(client, target.value)
    else:
        entity, already = await _join_public(client, target)

    try:
        await _mute(client, entity)
    except Exception:
        logger.warning("Failed to mute channel %s", target, exc_info=True)

    result = _from_entity(entity, already_member=already)
    await allowed_chats.add(chat_id=int(get_peer_id(entity)), label=_label_for(entity))
    return result


async def leave_and_unallow(
    client: TelegramClient,
    allowed_chats: AllowedChatsRepository,
    chat_id: int,
) -> ChannelResult:
    stored = await allowed_chats.all()
    label = stored.get(chat_id, str(chat_id))
    result = ChannelResult(chat_id=chat_id, title=label, label=label)

    try:
        entity = await client.get_entity(chat_id)
    except FloodWaitError:
        raise
    except Exception:
        logger.warning("Could not resolve channel %s while leaving", chat_id, exc_info=True)
        await allowed_chats.remove(chat_id=chat_id)
        return result

    result = _from_entity(entity)
    try:
        await client(LeaveChannelRequest(entity))
    except UserNotParticipantError:
        pass

    await allowed_chats.remove(chat_id=chat_id)
    return result


async def _refresh_label(
    client: TelegramClient,
    allowed_chats: AllowedChatsRepository,
    chat_id: int,
) -> None:
    entity = await client.get_entity(chat_id)
    await allowed_chats.add(chat_id=chat_id, label=_label_for(entity))


async def refresh_allowed_chat_labels(
    client: TelegramClient,
    allowed_chats: AllowedChatsRepository,
) -> None:
    chats = await allowed_chats.all()
    for chat_id in chats:
        try:
            await _refresh_label(client, allowed_chats, chat_id)
        except FloodWaitError as exc:
            logger.warning("FloodWait %ss while refreshing label for %s", exc.seconds, chat_id)
            if exc.seconds > 30:
                continue
            try:
                await asyncio.sleep(exc.seconds)
                await _refresh_label(client, allowed_chats, chat_id)
            except Exception:
                logger.warning(
                    "Could not refresh label for %s after FloodWait",
                    chat_id,
                    exc_info=True,
                )
        except Exception:
            logger.warning("Could not refresh label for %s", chat_id, exc_info=True)
