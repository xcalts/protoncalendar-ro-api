import httpx

PROTON_CALENDAR_HOST = "calendar.proton.me"
PROTON_CALENDAR_PATH_PREFIX = "/api/calendar/v1/url/"
PROTON_CALENDAR_PREFIX = f"https://{PROTON_CALENDAR_HOST}{PROTON_CALENDAR_PATH_PREFIX}"


def is_proton_calendar_url(url: object) -> bool:
    """Whether ``url`` is a Proton Calendar share link.

    The check is done on the parsed URL rather than on its string prefix, so that
    look-alikes such as ``https://calendar.proton.me@evil.example/...`` or
    ``https://calendar.proton.me.evil.example/...`` are rejected.
    """

    try:
        parsed = httpx.URL(str(url))
    except httpx.InvalidURL:
        return False
    return (
        parsed.scheme == "https"
        and parsed.host == PROTON_CALENDAR_HOST
        and parsed.port is None
        and not parsed.userinfo
        and parsed.path.startswith(PROTON_CALENDAR_PATH_PREFIX)
    )
