#!/usr/bin/env python3
"""Delete media from MinIO and the database using a SQL WHERE clause."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import BaseConfig
from shared.logger import setup_logging
from shared.storage import MediaMetadata, MediaStorage


def build_storage() -> MediaStorage:
    config = BaseConfig()
    return MediaStorage(
        config.database_url,
        config.minio_endpoint,
        config.minio_access_key,
        config.minio_secret_key,
        config.minio_bucket,
        config.minio_secure,
    )


def _fmt_size(file_size: int | None) -> str:
    if file_size is None:
        return "-"
    if file_size < 1024:
        return f"{file_size} B"
    if file_size < 1024 ** 2:
        return f"{file_size / 1024:.1f} KB"
    return f"{file_size / 1024 ** 2:.1f} MB"


def _fmt_dims(media: MediaMetadata) -> str:
    if media.width is None or media.height is None:
        return "-"
    return f"{media.width}x{media.height}"


def print_media_list(items: list[MediaMetadata], where_expr: str) -> None:
    print(f"Found {len(items)} media matching: {where_expr}")
    print("=" * 70)
    for idx, media in enumerate(items, 1):
        print(
            f"{idx}. id={media.id}  {media.media_type}  {_fmt_dims(media)}  "
            f"{_fmt_size(media.file_size)}  path={media.file_path}"
        )
        print(
            f"   sender={media.sender_name or '-'}  chat={media.chat_id}  "
            f"msg={media.message_id}  sent_tg={media.is_sent_tg}"
        )
    print("=" * 70)
    print(f"Total: {len(items)}")


def confirm_delete(count: int) -> bool:
    answer = input(
        f"Delete these {count} objects from MinIO and the database? [y/N] "
    ).strip().lower()
    return answer in {"y", "yes"}


def delete_items(storage: MediaStorage, items: list[MediaMetadata]) -> int:
    deleted = 0
    failed = 0
    for media in items:
        print(f"Deleting #{media.id} ({media.file_path}) ...", end=" ", flush=True)
        try:
            storage.delete_minio_object(media.file_path)
        except Exception as exc:
            failed += 1
            print(f"minio FAILED: {exc} (db row kept)")
            continue
        if storage.delete_media_row(media.id):
            deleted += 1
            print("minio ok, db ok")
        else:
            failed += 1
            print("minio ok, db row already gone")
    print(f"Done: {deleted} deleted, {failed} failed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List media matching a SQL WHERE clause, then delete them from MinIO and the database."
    )
    parser.add_argument(
        "where",
        help=(
            "SQL WHERE clause against medias. Example: "
            "sender_name like '%%СЛАВА%%' and media_type = 'video' and width = 384 and height = 384"
        ),
    )
    args = parser.parse_args()

    setup_logging(logging.WARNING)
    storage = build_storage()
    try:
        items = storage.find_media_by_where(args.where)
    except Exception as exc:
        print(f"Query failed: {exc}")
        return 1

    if not items:
        print("No media matched the WHERE expression.")
        return 0

    print_media_list(items, args.where)
    if not confirm_delete(len(items)):
        print("Aborted.")
        return 0
    return delete_items(storage, items)


if __name__ == "__main__":
    sys.exit(main())
