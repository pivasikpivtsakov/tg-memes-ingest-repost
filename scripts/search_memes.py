import argparse
import asyncio
import logging
import sys
from pathlib import Path
from time import perf_counter

_import_started = perf_counter()
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import BaseConfig
from shared.logger import setup_logging
from shared.search.service import SearchHit, SearchService, SearchTimings

_import_elapsed = perf_counter() - _import_started

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


def _format_timings(timings: SearchTimings) -> str:
    return (
        f"{timings.total:.2f}s search"
        f" | parallel {timings.parallel:.2f}s"
        f" (exact {timings.exact:.2f}s, trgm {timings.trigram:.2f}s, encode {timings.encode:.2f}s)"
        f" | clip {timings.clip:.2f}s"
        f" | hydrate {timings.hydrate:.2f}s"
        f" | import {_import_elapsed:.2f}s"
    )


async def main(query: str, limit: int, explain: bool) -> None:
    config = BaseConfig()
    service = SearchService(database_url=config.database_url, models_dir=config.models_dir)
    try:
        hits = await service.search(query, limit=limit)
        timings = service.last_timings
    finally:
        await service.dispose()

    if not hits:
        print("Nothing found")
    else:
        for position, hit in enumerate(hits, start=1):
            print(_format_hit(position, hit, explain=explain))
    if timings is not None:
        print(_format_timings(timings))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Search memes by remembered text, template or scene")
    parser.add_argument('query')
    parser.add_argument('-k', '--limit', type=int, default=20)
    parser.add_argument('--explain', action='store_true', help="show which channels matched each meme")
    args = parser.parse_args()
    setup_logging(logging.WARNING)
    asyncio.run(main(query=args.query, limit=args.limit, explain=args.explain))
