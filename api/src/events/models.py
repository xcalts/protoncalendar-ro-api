import dataclasses


@dataclasses.dataclass
class Event:
    """It represents a Proton calendar event."""

    calendar: str
    name: str
    time_start: str
    time_end: str
    timezone: str
