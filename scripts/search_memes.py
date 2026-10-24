import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import BaseConfig
from shared.logger import setup_logging
from shared.search.service import SearchHit, SearchService

_TEXT_PREVIEW_CHARS = 90


def _format_hit(position: int, hit: SearchHit, *, explain: bool) -> str:
    text = " ".join((hit.text or "").split())
    if len(text) > _TEXT_PREVIEW_CHARS:
        text = text[:_TEXT_PREVIEW_CHARS] + "…"
    marker = "EXACT " if hit.exact else ""
    line = f"{position:>3}. #{hit.media.id} {hit.media.media_type:<5} {marker}{text}"
    if explain:
        channels = ", ".join(
            f"{channel} #{match.rank} ({match.score:.2f})"
            for channel, match in hit.channels.items()
        )
        line += f"\n     rrf {hit.score:.4f} | {channels} | {hit.media.file_path}"
    return line


async def main(query: str, limit: int, explain: bool) -> None:
    config = BaseConfig()
    service = SearchService(database_url=config.database_url, models_dir=config.models_dir)
    try:
        hits = await service.search(query, limit=limit)
    finally:
        await service.dispose()

    if not hits:
        print("Nothing found")
        return
    for position, hit in enumerate(hits, start=1):
        print(_format_hit(position, hit, explain=explain))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Search memes by remembered text, template or scene")
    parser.add_argument('query')
    parser.add_argument('-k', '--limit', type=int, default=20)
    parser.add_argument('--explain', action='store_true', help="show which channels matched each meme")
    args = parser.parse_args()
    setup_logging(logging.WARNING)
    asyncio.run(main(query=args.query, limit=args.limit, explain=args.explain))
