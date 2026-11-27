import datetime

import fastapi

import api.core.logging
import api.core.security
import api.src.events.models
import api.src.events.service

DAY_FORMAT = "%d-%b-%Y"

logger = api.core.logging.get_logger(__name__)
router = fastapi.APIRouter(prefix="/events", tags=["Events"])


@router.get(
    "/{day}",
    response_model=list[api.src.events.models.Event],
    summary="Get the Proton calendar events by date.",
    description=(
        "The API downloads and parses the configured Proton Calendar iCal file "
        "(`PROTON_CALENDAR_URL`), then extracts events for the specified day."
    ),
    dependencies=[fastapi.Depends(api.core.security.verify_api_key)],
    responses={
        fastapi.status.HTTP_401_UNAUTHORIZED: {
            "description": "Invalid or missing API key."
        },
        fastapi.status.HTTP_404_NOT_FOUND: {
            "description": "Proton rejected the configured calendar link."
        },
        fastapi.status.HTTP_502_BAD_GATEWAY: {
            "description": "The calendar could not be downloaded or parsed."
        },
    },
)
# A plain "def" (not "async def"): the download and the recurrence expansion are
# blocking, so FastAPI must run this endpoint in its thread pool to keep the event
# loop (and every other request) responsive.
def get_events(
    response: fastapi.Response,
    day: str = fastapi.Path(
        ...,
        description="The day in the following format: 'DD-Mon-YYYY'.",
        examples=["11-Dec-2025"],
        pattern=r"^\d{2}-[A-Za-z]{3}-\d{4}$",
    ),
    event_service: api.src.events.service.EventService = fastapi.Depends(
        api.src.events.service.get_event_service
    ),
) -> list[api.src.events.models.Event]:
    """Get the Proton calendar events by date."""

    logger.debug("Fetching the Proton calendar events by date.")

    try:
        parsed_day = datetime.datetime.strptime(day, DAY_FORMAT).date()
    except ValueError:
        raise fastapi.HTTPException(
            fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Date must be in format DD-Mon-YYYY (e.g. 11-Dec-2025)",
        ) from None

    # Never log the URL or the upstream exception chain: the link is a secret.
    try:
        events = event_service.get_by_date(parsed_day)
    except api.src.events.service.CalendarNotFoundError as exc:
        logger.warning("Calendar not found (check PROTON_CALENDAR_URL): %s", exc)
        raise fastapi.HTTPException(
            fastapi.status.HTTP_404_NOT_FOUND, "Calendar not found."
        ) from None
    except api.src.events.service.CalendarUnavailableError as exc:
        logger.error("Failed to load the calendar: %s", exc)
        raise fastapi.HTTPException(
            fastapi.status.HTTP_502_BAD_GATEWAY,
            "Could not load the calendar from Proton.",
        ) from None

    # The response contains private calendar data: no shared/proxy caching.
    response.headers["Cache-Control"] = "no-store"
    logger.info("Retrieved %d events.", len(events))

    return events
