import os

API_KEY = "test-api-key"
AUTH = {"X-API-KEY": API_KEY}
SECRET = "Sup3rS3cretPassphraseKey"
CALENDAR_URL = (
    "https://calendar.proton.me/api/calendar/v1/url/"
    f"AbCdEf/calendar.ics?CacheKey=ck&PassphraseKey={SECRET}"
)

# The settings are read at import time, so the environment must be prepared before
# anything from "api" is imported. Values are forced (not defaulted) so a developer's
# local ".env" or shell cannot change the outcome of the tests.
os.environ["TIMEZONE"] = "Europe/Athens"
os.environ["X_API_KEY"] = API_KEY
os.environ["PROTON_CALENDAR_URL"] = CALENDAR_URL
os.environ["DEBUG"] = "false"

import collections.abc  # noqa: E402

import fastapi.testclient  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

import api.core.config  # noqa: E402
import api.main  # noqa: E402
import api.src.events.service  # noqa: E402


def ics(*events: list[str], name: str | None = "Personal", extra=()) -> bytes:
    """Build an iCalendar file. Each event is a list of content lines."""

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//tests//tests//EN"]
    if name is not None:
        lines.append(f"X-WR-CALNAME:{name}")
    lines.extend(extra)
    for event in events:
        lines += ["BEGIN:VEVENT", "DTSTAMP:20250101T000000Z", *event, "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


Handler = collections.abc.Callable[[httpx.Request], httpx.Response]


class RecordingTransport(httpx.MockTransport):
    """MockTransport that remembers every request it received."""

    def __init__(self, handler: Handler):
        self.requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        super().__init__(record)


def serve(body: bytes = b"", status: int = 200, headers=None) -> RecordingTransport:
    return RecordingTransport(
        lambda request: httpx.Response(status, content=body, headers=headers)
    )


@pytest.fixture
def make_service() -> collections.abc.Iterator[
    collections.abc.Callable[..., api.src.events.service.EventService]
]:
    """Build an EventService whose HTTP client talks to a mock transport."""

    clients: list[httpx.Client] = []

    def factory(
        transport: httpx.BaseTransport, url: str = CALENDAR_URL
    ) -> api.src.events.service.EventService:
        client = api.src.events.service.create_http_client(transport=transport)
        clients.append(client)
        return api.src.events.service.EventService(
            client=client, timezone=api.core.config.tz, calendar_url=url
        )

    yield factory
    for client in clients:
        client.close()


@pytest.fixture
def client() -> collections.abc.Iterator[fastapi.testclient.TestClient]:
    """Test client with the application lifespan running."""

    api.main.app.dependency_overrides.clear()
    with fastapi.testclient.TestClient(api.main.app) as test_client:
        yield test_client
    api.main.app.dependency_overrides.clear()
