import logging
import subprocess
import sys
from pathlib import Path

from aiogram.utils.i18n import I18n

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DOMAIN = "bot"
LANGUAGE_NAMES: dict[str, str] = {"ru": "Русский", "en": "English"}


def compile_locales() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            "compile",
            "-d",
            str(LOCALES_DIR),
            "-D",
            DOMAIN,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        logger.warning("Failed to compile locales: %s", completed.stderr or completed.stdout)


def build_i18n(*, default_locale: str) -> I18n:
    compile_locales()
    return I18n(
        path=str(LOCALES_DIR),
        default_locale=default_locale,
        domain=DOMAIN,
    )
