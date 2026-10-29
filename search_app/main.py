import logging

import uvicorn

from search_app.config import config
from search_app.web.app import create_app
from shared.logger import setup_logging


def run() -> None:
    setup_logging(logging.INFO)
    app = create_app(config)
    uvicorn.run(app, host=config.search_host, port=config.search_port, log_config=None)
