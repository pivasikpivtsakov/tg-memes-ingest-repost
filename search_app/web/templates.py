from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from shared.db.models import MediaType
from shared.search.ranking import Channel


def _enums(_request: Request) -> dict[str, Any]:
    return {"Channel": Channel, "MediaType": MediaType}


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates",
    context_processors=[_enums],
)
