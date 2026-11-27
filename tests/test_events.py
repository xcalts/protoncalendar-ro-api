import datetime
import logging
import unittest.mock

import httpx
import pytest

import api.core.proton
import api.main
import api.src.events.models
import api.src.events.service
import tests.conftest

DAY = "11-Dec-2025"


def _use_service(service) -> None:
    api.main.app.dependency_overrides[api.src.events.service.get_event_service] = (
        lambda: service
    )


def _mock_service(events=None, error=None) -> unittest.mock.MagicMock:
    service = unittest.mock.MagicMock()
    service.get_by_date.return_value = events or []
    service.get_by_date.side_effect = error
    _use_service(service)
    return service


# -------
# Success
# -------


def test_returns_events(client):
    events = [
        api.src.events.models.Event(
            "Common", "Standup", "09:00", "09:15", "Europe/Athens"
        ),
        api.src.events.models.Event(
            "Common", "Planning", "10:00", "11:00", "Europe/Athens"
        ),
    ]
    service = _mock_service(events)

    resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "calendar": "Common",
            "name": "Standup",
            "time_start": "09:00",
            "time_end": "09:15",
            "timezone": "Europe/Athens",
        },
        {
            "calendar": "Common",
            "name": "Planning",
            "time_start": "10:00",
            "time_end": "11:00",
            "timezone": "Europe/Athens",
        },
    ]
    service.get_by_date.assert_called_once_with(datetime.date(2025, 12, 11))


def test_returns_empty_list(client):
    _mock_service([])
    resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)
    assert resp.status_code == 200
    assert resp.json() == []


def test_private_responses_are_not_cacheable(client):
    _mock_service([])
    resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)
    assert resp.headers["Cache-Control"] == "no-store"


def test_day_is_case_insensitive(client):
    service = _mock_service([])
    resp = client.get("/events/01-jan-2026", headers=tests.conftest.AUTH)
    assert resp.status_code == 200
    service.get_by_date.assert_called_once_with(datetime.date(2026, 1, 1))


def test_end_to_end_with_the_real_service(client, make_service):
    body = tests.conftest.ics(
        ["UID:1", "SUMMARY:Standup", "DTSTART:20251211T070000Z", "DURATION:PT15M"],
        ["UID:2", "SUMMARY:Holiday", "DTSTART;VALUE=DATE:20251211"],
    )
    transport = tests.conftest.serve(body)
    _use_service(make_service(transport))

    resp = client.get(
        f"/events/{DAY}",
        headers=tests.conftest.AUTH,
    )

    assert resp.status_code == 200
    assert [(e["name"], e["time_start"], e["time_end"]) for e in resp.json()] == [
        ("Holiday", "", ""),
        ("Standup", "09:00", "09:15"),
    ]
    # The full share link, including its secret parameters, reached Proton intact.
    [request] = transport.requests
    assert str(request.url) == tests.conftest.CALENDAR_URL


def test_clients_cannot_choose_the_calendar(client, make_service):
    """A "url" query parameter (as sent by clients of older versions) is ignored."""

    transport = tests.conftest.serve(tests.conftest.ics())
    _use_service(make_service(transport))

    resp = client.get(
        f"/events/{DAY}",
        params={"url": f"{api.core.proton.PROTON_CALENDAR_PREFIX}SomeoneElse"},
        headers=tests.conftest.AUTH,
    )

    assert resp.status_code == 200
    assert [str(r.url) for r in transport.requests] == [tests.conftest.CALENDAR_URL]


def test_uses_the_configured_calendar(client):
    """Without overrides, the endpoint downloads PROTON_CALENDAR_URL."""

    with unittest.mock.patch.object(
        api.main.app.state.http_client,
        "get",
        return_value=httpx.Response(200, content=tests.conftest.ics()),
    ) as get:
        resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)

    assert resp.status_code == 200
    get.assert_called_once_with(tests.conftest.CALENDAR_URL)


# --------------
# Authentication
# --------------


@pytest.mark.parametrize("headers", [{}, {"X-API-KEY": ""}, {"X-API-KEY": "wrong"}])
def test_rejects_missing_or_invalid_api_key(client, headers):
    service = _mock_service([])

    resp = client.get(f"/events/{DAY}", headers=headers)

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or missing API Key"}
    service.get_by_date.assert_not_called()


def test_authentication_happens_before_validation(client):
    """Unauthenticated callers must not learn anything from validation errors."""

    _mock_service([])
    resp = client.get("/events/not-a-day")
    assert resp.status_code == 401


# ----------
# Validation
# ----------


@pytest.mark.parametrize("day", ["2025-12-11", "1-Dec-2025", "11-December-2025"])
def test_day_with_wrong_pattern_returns_422(client, day):
    _mock_service([])
    resp = client.get(f"/events/{day}", headers=tests.conftest.AUTH)
    assert resp.status_code == 422
    assert any(err["loc"] == ["path", "day"] for err in resp.json()["detail"])


@pytest.mark.parametrize("day", ["31-Feb-2025", "11-Foo-2025", "00-Jan-2025"])
def test_invalid_calendar_date_returns_422(client, day):
    _mock_service([])
    resp = client.get(f"/events/{day}", headers=tests.conftest.AUTH)
    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "Date must be in format DD-Mon-YYYY (e.g. 11-Dec-2025)"
    )


# --------------
# Error mapping
# --------------


def test_calendar_not_found_returns_404(client):
    _mock_service(
        error=api.src.events.service.CalendarNotFoundError(
            "Proton Calendar rejected the link."
        )
    )
    resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Calendar not found."}


def test_calendar_unavailable_returns_502(client):
    _mock_service(
        error=api.src.events.service.CalendarUnavailableError("Proton is down.")
    )
    resp = client.get(f"/events/{DAY}", headers=tests.conftest.AUTH)
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Could not load the calendar from Proton."}


def test_unexpected_errors_return_500(client):
    _mock_service(error=RuntimeError("bug"))
    client_no_raise = type(client)(api.main.app, raise_server_exceptions=False)
    resp = client_no_raise.get(f"/events/{DAY}", headers=tests.conftest.AUTH)
    assert resp.status_code == 500


# -------
# Privacy
# -------


@pytest.mark.parametrize(
    ("transport", "expected_status"),
    [
        (tests.conftest.serve(b"Not found", 404), 404),
        (tests.conftest.serve(b"Oops", 500), 502),
        (tests.conftest.serve(b"<html>not a calendar</html>"), 502),
        (
            httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    httpx.ConnectError(f"failed to connect to {request.url}")
                )
            ),
            502,
        ),
        (
            httpx.MockTransport(
                lambda request: httpx.Response(
                    302,
                    headers={
                        "Location": f"https://evil.example/?{tests.conftest.SECRET}"
                    },
                )
            ),
            502,
        ),
    ],
)
def test_failures_never_log_or_return_the_calendar_link(
    client, make_service, caplog, transport, expected_status
):
    _use_service(make_service(transport))

    with caplog.at_level(logging.DEBUG):
        resp = client.get(
            f"/events/{DAY}",
            headers=tests.conftest.AUTH,
        )

    assert resp.status_code == expected_status
    assert caplog.records, "the failure should be logged"
    for text in (caplog.text, resp.text):
        assert tests.conftest.SECRET not in text
        assert "calendar.proton.me" not in text
        assert "evil.example" not in text


def test_success_never_logs_the_calendar_link(client, make_service, caplog):
    _use_service(
        make_service(
            tests.conftest.serve(tests.conftest.ics(["SUMMARY:A", "DTSTART:20251211"]))
        )
    )

    with caplog.at_level(logging.DEBUG):
        resp = client.get(
            f"/events/{DAY}",
            headers=tests.conftest.AUTH,
        )

    assert resp.status_code == 200
    assert tests.conftest.SECRET not in caplog.text
    assert "calendar.proton.me" not in caplog.text
