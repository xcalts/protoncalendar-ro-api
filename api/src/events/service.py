import datetime
import zoneinfo

import fastapi
import httpx
import icalendar
import recurring_ical_events

import api.core.config
import api.core.proton
import api.src.events.models

HTTP_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 5

# Upstream 4xx responses mean the link is wrong, expired or revoked. Timeouts and rate
# limiting are transient and therefore reported as "unavailable" instead.
_TRANSIENT_CLIENT_ERRORS = frozenset({408, 429})


class CalendarError(Exception):
    """Base class for calendar errors.

    Messages must never include the calendar URL: the Proton share link embeds the
    passphrase key and is therefore a secret.
    """


class CalendarNotFoundError(CalendarError):
    """Proton rejected the share link (wrong, expired or revoked)."""


class CalendarUnavailableError(CalendarError):
    """The calendar could not be downloaded or is not valid iCalendar data."""


def _only_contact_proton(request: httpx.Request) -> None:
    """httpx request hook: refuse to talk to any host but Proton Calendar.

    It runs for every request, including each redirect hop, so the share link can
    never be forwarded to (or the server pointed at) another host.
    """

    if (
        request.url.scheme != "https"
        or request.url.host != api.core.proton.PROTON_CALENDAR_HOST
    ):
        raise CalendarUnavailableError(
            "Refused to contact a host other than Proton Calendar."
        )


def create_http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Create the HTTP client used to download calendars."""

    return httpx.Client(
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        event_hooks={"request": [_only_contact_proton]},
        transport=transport,
    )


class EventService:
    """Service for reading events from a Proton calendar share link."""

    def __init__(
        self, client: httpx.Client, timezone: zoneinfo.ZoneInfo, calendar_url: str
    ):
        self._client = client
        self._tz = timezone
        self._calendar_url = calendar_url

    def get_by_date(self, day: datetime.date) -> list[api.src.events.models.Event]:
        """Get the Proton calendar events that take place on ``day``.

        Args:
            day: The day, interpreted in the configured time zone.

        Returns:
            The events of that day: all-day events first, then by start time.

        Raises:
            CalendarNotFoundError: Proton rejected the link.
            CalendarUnavailableError: The calendar could not be downloaded or parsed.
        """

        calendar = self._parse(self._download(self._calendar_url))
        return self._events_on(calendar, day)

    def _download(self, url: str) -> bytes:
        """Download the Proton calendar in iCalendar format."""

        try:
            response = self._client.get(url)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            # "from None": httpx exceptions can embed the (secret) URL.
            raise CalendarUnavailableError(
                f"Could not download the calendar ({type(exc).__name__})."
            ) from None

        status = response.status_code
        if 400 <= status < 500 and status not in _TRANSIENT_CLIENT_ERRORS:
            raise CalendarNotFoundError(
                f"Proton Calendar rejected the link (HTTP {status})."
            )
        if not response.is_success:
            raise CalendarUnavailableError(
                f"Proton Calendar responded with HTTP {status}."
            )

        # Bytes, not text: iCalendar is UTF-8 by default (RFC 5545), and icalendar
        # treats a single-line *string* as a local file path to read from disk.
        return response.content

    def _parse(self, raw_calendar: bytes) -> icalendar.Calendar:
        """Parse the downloaded calendar."""

        try:
            calendar = icalendar.Calendar.from_ical(raw_calendar)
        except ValueError:
            calendar = None
        if not isinstance(calendar, icalendar.Calendar):
            raise CalendarUnavailableError(
                "The downloaded file is not a valid iCalendar calendar."
            )
        return calendar

    def _events_on(
        self, calendar: icalendar.Calendar, day: datetime.date
    ) -> list[api.src.events.models.Event]:
        """Expand the calendar into the events that overlap ``day``."""

        # Search window: [day 00:00, next day 00:00) in the configured time zone.
        # The bounds must be built *in* the time zone: calling .astimezone() on a
        # naive datetime would interpret it in the host's local time zone instead.
        start = datetime.datetime.combine(day, datetime.time.min, tzinfo=self._tz)
        end = datetime.datetime.combine(
            day + datetime.timedelta(days=1), datetime.time.min, tzinfo=self._tz
        )

        try:
            # Expands RRULE/RDATE/EXDATE and applies overrides (RECURRENCE-ID).
            # Broken recurring series are skipped instead of failing the whole day.
            occurrences = recurring_ical_events.of(
                calendar, skip_bad_series=True
            ).between(start, end)
        except (ValueError, KeyError):
            raise CalendarUnavailableError(
                "The calendar contains invalid events."
            ) from None

        calendar_name = str(calendar.get("X-WR-CALNAME", "Unnamed calendar"))
        events = [
            api.src.events.models.Event(
                calendar=calendar_name,
                name=str(component.get("SUMMARY", "No title")),
                time_start=self._format_time(component.get("DTSTART")),
                time_end=self._format_time(component.get("DTEND")),
                timezone=str(self._tz),
            )
            for component in occurrences
        ]

        # All-day events first, then by start time (name as a stable tie-breaker).
        events.sort(key=lambda e: (e.time_start != "", e.time_start, e.name))
        return events

    def _format_time(self, prop) -> str:
        """Format a DTSTART/DTEND property as ``HH:MM`` in the configured time zone.

        Returns ``""`` for all-day (date-only) values. Floating times (no time zone)
        are returned as written.
        """

        value = getattr(prop, "dt", None)
        if not isinstance(value, datetime.datetime):
            return ""
        if value.tzinfo is not None:
            value = value.astimezone(self._tz)
        return value.strftime("%H:%M")


def get_event_service(request: fastapi.Request) -> EventService:
    """Dependency providing an EventService bound to the shared HTTP client and to
    the configured calendar."""

    return EventService(
        client=request.app.state.http_client,
        timezone=api.core.config.tz,
        calendar_url=api.core.config.settings.PROTON_CALENDAR_URL.get_secret_value(),
    )
