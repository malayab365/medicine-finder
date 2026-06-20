"""Apply the configured log level at startup.

`settings.log_level` was previously defined but never wired up, so the app
relied on whatever root config uvicorn happened to install. We set a basic
config and pin the `app.*` logger tree to the configured level so module loggers
(e.g. `app.medicines.providers.triage`) emit at the intended verbosity.
"""

import logging

from app.core.config import settings


def configure_logging() -> None:
    level = settings.log_level.upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("app").setLevel(level)
