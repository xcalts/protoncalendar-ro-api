import pytest

import api.core.proton
import tests.conftest


@pytest.mark.parametrize(
    "url",
    [
        tests.conftest.CALENDAR_URL,
        f"{api.core.proton.PROTON_CALENDAR_PREFIX}XXXXXXXX",
        "https://CALENDAR.PROTON.ME/api/calendar/v1/url/X/calendar.ics",
        "https://calendar.proton.me:443/api/calendar/v1/url/X",
    ],
)
def test_accepts_proton_share_links(url):
    assert api.core.proton.is_proton_calendar_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://calendar.proton.me/api/calendar/v1/url/X",  # not https
        "https://calendar.proton.me.evil.example/api/calendar/v1/url/X",
        "https://evil.example/api/calendar/v1/url/X",
        "https://calendar.proton.me@evil.example/api/calendar/v1/url/X",
        "https://user:pass@calendar.proton.me/api/calendar/v1/url/X",
        "https://calendar.proton.me:8443/api/calendar/v1/url/X",
        "https://calendar.proton.me/api/calendar/v1/urlX",
        "https://calendar.proton.me/api/calendar/v1/",
        "https://calendar.proton.me/",
        "https://mail.proton.me/api/calendar/v1/url/X",
        "not a url",
        "https://[::1",  # unparsable
    ],
)
def test_rejects_anything_else(url):
    assert not api.core.proton.is_proton_calendar_url(url)
