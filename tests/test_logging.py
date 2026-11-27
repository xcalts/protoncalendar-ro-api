import logging
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.parse

import httpx
import pytest

import api.core.logging
import tests.conftest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _access_record(path: str) -> logging.LogRecord:
    """A record shaped exactly like uvicorn's access log records."""

    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:5000", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_filter_redacts_query_string():
    record = _access_record(
        f"/events/11-Dec-2025?url={urllib.parse.quote(tests.conftest.CALENDAR_URL)}"
    )

    assert api.core.logging.RedactQueryStringFilter().filter(record) is True

    message = record.getMessage()
    assert tests.conftest.SECRET not in message
    assert "calendar.proton.me" not in message
    assert message == (
        '127.0.0.1:5000 - "GET /events/11-Dec-2025?'
        f'{api.core.logging.REDACTED} HTTP/1.1" 200'
    )


def test_filter_keeps_paths_without_query_string():
    record = _access_record("/health")
    assert api.core.logging.RedactQueryStringFilter().filter(record) is True
    assert record.getMessage() == '127.0.0.1:5000 - "GET /health HTTP/1.1" 200'


@pytest.mark.parametrize("args", [None, (), ("only", "two"), ("a", "b", 3)])
def test_filter_ignores_records_of_other_shapes(args):
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "message", args, None)
    assert api.core.logging.RedactQueryStringFilter().filter(record) is True
    assert record.args == args


def test_setup_logging_is_idempotent_and_silences_url_loggers():
    api.core.logging.setup_logging()
    api.core.logging.setup_logging()

    access_filters = [
        f
        for f in logging.getLogger("uvicorn.access").filters
        if isinstance(f, api.core.logging.RedactQueryStringFilter)
    ]
    assert len(access_filters) == 1
    for name in ("httpx", "httpcore", "httpx2", "httpcore2"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


def test_get_logger_returns_named_logger():
    assert api.core.logging.get_logger("api.test").name == "api.test"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_running_server_never_logs_the_calendar_link(tmp_path):
    """End-to-end: start the real server and inspect everything it prints."""

    port = _free_port()
    log_file = tmp_path / "server.log"
    env = os.environ | {
        "TIMEZONE": "Europe/Athens",
        "X_API_KEY": "test-api-key",
        "PROTON_CALENDAR_URL": tests.conftest.CALENDAR_URL,
        "PYTHONUNBUFFERED": "1",
    }
    with log_file.open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 30
            while True:
                try:
                    httpx.get(f"{base}/health", timeout=1)
                    break
                except httpx.TransportError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        pytest.fail(f"Server did not start:\n{log_file.read_text()}")
                    time.sleep(0.1)

            # A client of an older version, still sending the link in the query
            # string, with a wrong API key: the request is rejected before anything
            # is fetched, but the access log line is still written.
            response = httpx.get(
                f"{base}/events/11-Dec-2025",
                params={"url": tests.conftest.CALENDAR_URL},
                headers={"X-API-KEY": "wrong"},
            )
            assert response.status_code == 401
        finally:
            server.terminate()
            server.wait(timeout=10)

    output = log_file.read_text()
    assert f"/events/11-Dec-2025?{api.core.logging.REDACTED}" in output
    assert tests.conftest.SECRET not in output
    assert "calendar.proton.me" not in output
    assert urllib.parse.quote(tests.conftest.SECRET) not in output
