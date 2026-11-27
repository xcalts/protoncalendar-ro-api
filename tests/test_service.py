import datetime
import time
import types

import httpx
import pytest

import api.core.config
import api.core.proton
import api.src.events.models
import api.src.events.service
import tests.conftest

DAY = datetime.date(2025, 12, 11)


def _summary(events: list[api.src.events.models.Event]) -> list[tuple[str, str, str]]:
    return [(e.name, e.time_start, e.time_end) for e in events]


def _assert_no_secret(exc_info: pytest.ExceptionInfo) -> None:
    message = str(exc_info.value)
    assert tests.conftest.SECRET not in message
    assert "calendar.proton.me" not in message
    # No chained exception (which may embed the URL) may surface in tracebacks.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None or exc_info.value.__suppress_context__


# -----------------
# HTTP client
# -----------------


def test_http_client_configuration():
    with api.src.events.service.create_http_client() as client:
        assert client.timeout == httpx.Timeout(
            api.src.events.service.HTTP_TIMEOUT_SECONDS
        )
        assert client.follow_redirects is True
        assert client.max_redirects == api.src.events.service.MAX_REDIRECTS


def test_follows_redirects_within_proton(make_service):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/old"):
            return httpx.Response(302, headers={"Location": "/api/calendar/v1/url/new"})
        return httpx.Response(
            200, content=tests.conftest.ics(["SUMMARY:Moved", "DTSTART:20251211"])
        )

    transport = tests.conftest.RecordingTransport(handler)
    events = make_service(
        transport, url=f"{api.core.proton.PROTON_CALENDAR_PREFIX}old"
    ).get_by_date(DAY)

    assert [e.name for e in events] == ["Moved"]
    assert [r.url.path for r in transport.requests] == [
        "/api/calendar/v1/url/old",
        "/api/calendar/v1/url/new",
    ]


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/steal",
        "http://calendar.proton.me/api/calendar/v1/url/X",  # https downgrade
    ],
)
def test_never_follows_redirects_away_from_proton(make_service, location):
    transport = tests.conftest.RecordingTransport(
        lambda request: httpx.Response(302, headers={"Location": location})
    )

    with pytest.raises(api.src.events.service.CalendarUnavailableError) as exc_info:
        make_service(transport).get_by_date(DAY)

    # The off-site request was blocked before it reached the transport.
    assert [str(r.url) for r in transport.requests] == [tests.conftest.CALENDAR_URL]
    _assert_no_secret(exc_info)


def test_refuses_to_contact_other_hosts_directly(make_service):
    transport = tests.conftest.serve(tests.conftest.ics())
    with pytest.raises(api.src.events.service.CalendarUnavailableError):
        make_service(transport, url="https://evil.example/x.ics").get_by_date(DAY)
    assert transport.requests == []


def test_stops_after_too_many_redirects(make_service):
    transport = tests.conftest.RecordingTransport(
        lambda request: httpx.Response(302, headers={"Location": request.url.path})
    )
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match="TooManyRedirects"
    ) as exc_info:
        make_service(transport).get_by_date(DAY)
    assert len(transport.requests) == api.src.events.service.MAX_REDIRECTS + 1
    _assert_no_secret(exc_info)


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError(f"cannot connect to {tests.conftest.CALENDAR_URL}"),
        httpx.ReadTimeout(f"timed out reading {tests.conftest.CALENDAR_URL}"),
        httpx.RemoteProtocolError(f"bad response from {tests.conftest.CALENDAR_URL}"),
    ],
)
def test_network_errors_are_unavailable_and_do_not_leak_the_url(make_service, error):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(api.src.events.service.CalendarUnavailableError) as exc_info:
        make_service(httpx.MockTransport(handler)).get_by_date(DAY)

    assert type(error).__name__ in str(exc_info.value)
    _assert_no_secret(exc_info)


def test_invalid_url_is_unavailable(make_service):
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match="InvalidURL"
    ):
        make_service(
            tests.conftest.serve(tests.conftest.ics()),
            url=f"{api.core.proton.PROTON_CALENDAR_PREFIX}\x07",
        ).get_by_date(DAY)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_rejected_links_are_not_found(make_service, status):
    with pytest.raises(
        api.src.events.service.CalendarNotFoundError, match=str(status)
    ) as exc_info:
        make_service(tests.conftest.serve(b"nope", status)).get_by_date(DAY)
    _assert_no_secret(exc_info)


@pytest.mark.parametrize("status", [304, 408, 429, 500, 502, 503])
def test_other_statuses_are_unavailable(make_service, status):
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match=str(status)
    ) as exc_info:
        make_service(tests.conftest.serve(b"", status)).get_by_date(DAY)
    _assert_no_secret(exc_info)


def test_errors_share_a_base_class():
    assert issubclass(
        api.src.events.service.CalendarNotFoundError,
        api.src.events.service.CalendarError,
    )
    assert issubclass(
        api.src.events.service.CalendarUnavailableError,
        api.src.events.service.CalendarError,
    )


# -----------------
# Parsing
# -----------------


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html><body>Maintenance</body></html>",
        b"\xff\xfe\x00garbage",
        b"BEGIN:VCALENDAR\r\n",
        # A lone event is valid iCalendar, but not a calendar.
        b"BEGIN:VEVENT\r\nUID:1\r\nDTSTART:20251211T100000Z\r\nEND:VEVENT\r\n",
    ],
)
def test_invalid_calendars_are_unavailable(make_service, body):
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match="not a valid iCalendar"
    ):
        make_service(tests.conftest.serve(body)).get_by_date(DAY)


def test_response_body_is_never_treated_as_a_local_file_path(make_service, tmp_path):
    """icalendar reads a single-line *string* from disk if it names a file."""

    local_file = tmp_path / "local.ics"
    local_file.write_bytes(
        tests.conftest.ics(["SUMMARY:Local file content", "DTSTART:20251211"])
    )

    with pytest.raises(api.src.events.service.CalendarUnavailableError):
        make_service(tests.conftest.serve(str(local_file).encode())).get_by_date(DAY)


def test_events_without_start_make_the_calendar_unavailable(make_service):
    body = tests.conftest.ics(["UID:1", "SUMMARY:No start"])
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match="invalid events"
    ):
        make_service(tests.conftest.serve(body)).get_by_date(DAY)


def test_unsupported_calendar_scale_is_unavailable(make_service):
    body = tests.conftest.ics(
        ["SUMMARY:A", "DTSTART:20251211"], extra=["CALSCALE:CHINESE"]
    )
    with pytest.raises(
        api.src.events.service.CalendarUnavailableError, match="invalid events"
    ):
        make_service(tests.conftest.serve(body)).get_by_date(DAY)


def test_a_broken_series_does_not_hide_the_other_events(make_service):
    body = tests.conftest.ics(
        ["UID:bad", "SUMMARY:Broken", "DTSTART:20251211T080000Z", "RRULE:FREQ=NOPE"],
        ["UID:ok", "SUMMARY:Fine", "DTSTART:20251211T090000Z"],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    assert [e.name for e in events] == ["Fine"]


def test_decodes_utf8_without_charset_header(make_service):
    body = tests.conftest.ics(
        ["SUMMARY:Συνάντηση ☕", "DTSTART:20251211"], name="Ημερολόγιο"
    )
    transport = tests.conftest.serve(body, headers={"Content-Type": "text/calendar"})

    [event] = make_service(transport).get_by_date(DAY)

    assert event.name == "Συνάντηση ☕"
    assert event.calendar == "Ημερολόγιο"


# -----------------
# Event extraction
# -----------------


def test_maps_events(make_service):
    body = tests.conftest.ics(
        [
            "UID:1",
            "SUMMARY:Standup",
            "DTSTART:20251211T070000Z",
            "DTEND:20251211T071500Z",
        ]
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)

    assert events == [
        api.src.events.models.Event(
            calendar="Personal",
            name="Standup",
            time_start="09:00",
            time_end="09:15",
            timezone="Europe/Athens",
        )
    ]


def test_converts_other_time_zones_and_keeps_floating_times(make_service):
    body = tests.conftest.ics(
        [
            "UID:ny",
            "SUMMARY:New York",
            "DTSTART;TZID=America/New_York:20251211T040000",
            "DTEND;TZID=America/New_York:20251211T050000",
        ],
        ["UID:fl", "SUMMARY:Floating", "DTSTART:20251211T120000", "DURATION:PT30M"],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    assert _summary(events) == [
        ("New York", "11:00", "12:00"),
        ("Floating", "12:00", "12:30"),
    ]


def test_all_day_events_and_defaults(make_service):
    body = tests.conftest.ics(
        ["UID:1", "DTSTART;VALUE=DATE:20251211"],
        ["UID:2", "SUMMARY:Yesterday", "DTSTART;VALUE=DATE:20251210"],
        ["UID:3", "SUMMARY:Tomorrow", "DTSTART;VALUE=DATE:20251212"],
        [
            "UID:4",
            "SUMMARY:Trip",
            "DTSTART;VALUE=DATE:20251210",
            "DTEND;VALUE=DATE:20251213",
        ],
        name=None,
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)

    assert _summary(events) == [("No title", "", ""), ("Trip", "", "")]
    assert {e.calendar for e in events} == {"Unnamed calendar"}


def test_sorts_all_day_first_then_by_start_then_by_name(make_service):
    body = tests.conftest.ics(
        ["UID:1", "SUMMARY:Late", "DTSTART:20251211T150000Z"],
        ["UID:2", "SUMMARY:B early", "DTSTART:20251211T060000Z"],
        ["UID:3", "SUMMARY:A early", "DTSTART:20251211T060000Z"],
        ["UID:4", "SUMMARY:All day", "DTSTART;VALUE=DATE:20251211"],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    assert [e.name for e in events] == ["All day", "A early", "B early", "Late"]


def test_day_window_is_midnight_to_midnight_in_the_configured_zone(make_service):
    """Regression: the window used to be computed in the host's time zone."""

    body = tests.conftest.ics(
        # 23:30 Athens on the previous day: excluded.
        ["UID:1", "SUMMARY:Previous night", "DTSTART:20251210T213000Z"],
        # 00:30 and 01:30 Athens: included (were missed on UTC hosts).
        ["UID:2", "SUMMARY:Just after midnight", "DTSTART:20251210T223000Z"],
        ["UID:3", "SUMMARY:Early", "DTSTART:20251210T233000Z"],
        # 23:59 Athens: included.
        ["UID:4", "SUMMARY:Last minute", "DTSTART:20251211T215900Z"],
        # 00:30 Athens on the next day: excluded (was included on UTC hosts).
        ["UID:5", "SUMMARY:Next day", "DTSTART:20251211T223000Z"],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    assert _summary(events) == [
        ("Just after midnight", "00:30", "00:30"),
        ("Early", "01:30", "01:30"),
        ("Last minute", "23:59", "23:59"),
    ]


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset()")
@pytest.mark.parametrize("host_tz", ["UTC", "America/Los_Angeles", "Asia/Tokyo"])
def test_results_do_not_depend_on_the_host_time_zone(
    make_service, monkeypatch, host_tz
):
    body = tests.conftest.ics(
        ["UID:1", "SUMMARY:Just after midnight", "DTSTART:20251210T223000Z"],
        ["UID:2", "SUMMARY:Next day", "DTSTART:20251211T223000Z"],
    )
    monkeypatch.setenv("TZ", host_tz)
    time.tzset()
    try:
        events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    finally:
        monkeypatch.undo()
        time.tzset()
    assert [e.name for e in events] == ["Just after midnight"]


def test_daylight_saving_day_has_25_hours(make_service):
    # Athens leaves DST on 26 Oct 2025: the day lasts from 21:00Z to 22:00Z next day.
    body = tests.conftest.ics(
        ["UID:1", "SUMMARY:First", "DTSTART:20251025T210000Z"],
        ["UID:2", "SUMMARY:Last", "DTSTART:20251026T213000Z"],
        ["UID:3", "SUMMARY:Next day", "DTSTART:20251026T220000Z"],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(
        datetime.date(2025, 10, 26)
    )
    assert _summary(events) == [("First", "00:00", "00:00"), ("Last", "23:30", "23:30")]


def test_events_overlapping_the_day_are_included(make_service):
    body = tests.conftest.ics(
        [
            "UID:1",
            "SUMMARY:Overnight",
            "DTSTART:20251210T200000Z",
            "DTEND:20251211T010000Z",
        ],
        [
            "UID:2",
            "SUMMARY:Ended at midnight",
            "DTSTART:20251210T200000Z",
            "DTEND:20251210T220000Z",
        ],
    )
    events = make_service(tests.conftest.serve(body)).get_by_date(DAY)
    assert _summary(events) == [("Overnight", "22:00", "03:00")]


def test_expands_recurring_events_with_exceptions_and_overrides(make_service):
    body = tests.conftest.ics(
        [
            "UID:weekly",
            "SUMMARY:Weekly sync",
            "DTSTART;TZID=Europe/Athens:20251127T100000",
            "DTEND;TZID=Europe/Athens:20251127T110000",
            "RRULE:FREQ=WEEKLY;COUNT=10",
            "EXDATE;TZID=Europe/Athens:20251204T100000",
        ],
        [
            "UID:weekly",
            "RECURRENCE-ID;TZID=Europe/Athens:20251211T100000",
            "SUMMARY:Weekly sync (moved)",
            "DTSTART;TZID=Europe/Athens:20251211T140000",
            "DTEND;TZID=Europe/Athens:20251211T150000",
        ],
        [
            "UID:daily",
            "SUMMARY:Daily",
            "DTSTART;VALUE=DATE:20251201",
            "RRULE:FREQ=DAILY;UNTIL=20251210",
        ],
    )
    service = make_service(tests.conftest.serve(body))

    assert _summary(service.get_by_date(DAY)) == [
        ("Weekly sync (moved)", "14:00", "15:00")
    ]
    # EXDATE removed the weekly occurrence; the daily series (until 10 Dec) remains.
    assert _summary(service.get_by_date(datetime.date(2025, 12, 4))) == [
        ("Daily", "", "")
    ]
    assert _summary(service.get_by_date(datetime.date(2025, 12, 18))) == [
        ("Weekly sync", "10:00", "11:00")
    ]
    assert _summary(service.get_by_date(datetime.date(2025, 12, 10))) == [
        ("Daily", "", "")
    ]
    # Past the end of both series.
    assert service.get_by_date(datetime.date(2026, 6, 1)) == []


def test_dependency_uses_the_shared_client():
    shared = httpx.Client()
    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace(http_client=shared))
    )
    try:
        service = api.src.events.service.get_event_service(request)
    finally:
        shared.close()
    assert isinstance(service, api.src.events.service.EventService)
    assert service._client is shared
    assert service._tz is api.core.config.tz
    assert service._calendar_url == tests.conftest.CALENDAR_URL
