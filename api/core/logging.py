import logging
import sys

import api.core.config

REDACTED = "<redacted>"

# Third-party loggers that would otherwise print the full upstream request URL.
# The Proton calendar link is a bearer secret (it embeds the passphrase key), so
# these must never log at INFO/DEBUG level. "httpx2" is the fork Starlette now
# prefers; it is listed so that switching clients cannot reintroduce the leak.
_URL_LOGGING_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2")


class RedactQueryStringFilter(logging.Filter):
    """Strip the query string from uvicorn access log records.

    The calendar link is configured with ``PROTON_CALENDAR_URL``, but clients written
    for older versions still send it in the ``url`` query parameter. uvicorn's
    default access log line (``"GET /events/...?url=... HTTP/1.1" 200``) would
    otherwise persist the secret link in the server logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path, sep, _ = args[2].partition("?")
            if sep:
                record.args = (*args[:2], f"{path}?{REDACTED}", *args[3:])
        return True


_access_log_filter = RedactQueryStringFilter()


def setup_logging() -> None:
    """Set up logging configuration."""
    format_string = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if api.core.config.settings.DEBUG else logging.INFO,
        format=format_string,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    for name in _URL_LOGGING_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    access_logger = logging.getLogger("uvicorn.access")
    if _access_log_filter not in access_logger.filters:
        access_logger.addFilter(_access_log_filter)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
