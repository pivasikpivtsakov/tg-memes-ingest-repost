from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from shared.db.models import MediaType
from shared.search.ranking import Channel


def rank_line(hit: Any) -> str:
    parts: list[str] = []
    for channel in Channel:
        match = hit.channels.get(channel)
        if match is None:
            continue
        parts.append(f"{channel} #{match.rank} ({match.score:.2f})")
    return " · ".join(parts)


def _enums(_request: Request) -> dict[str, Any]:
    return {"Channel": Channel, "MediaType": MediaType, "rank_line": rank_line}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[_enums],
)
