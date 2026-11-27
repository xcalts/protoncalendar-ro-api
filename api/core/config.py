import zoneinfo

import pydantic
import pydantic_settings

import api.core.proton


class Settings(pydantic_settings.BaseSettings):
    """Application settings."""

    PROJECT_NAME: str = "Proton calendar read-only API"
    DEBUG: bool = False
    TIMEZONE: str
    X_API_KEY: pydantic.SecretStr
    PROTON_CALENDAR_URL: pydantic.SecretStr

    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    @pydantic.field_validator("TIMEZONE")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown IANA time zone: {value!r}") from exc
        return value

    @pydantic.field_validator("X_API_KEY")
    @classmethod
    def _validate_api_key(cls, value: pydantic.SecretStr) -> pydantic.SecretStr:
        # An empty key would make the API unusable at best; refuse to start instead.
        if not value.get_secret_value().strip():
            raise ValueError("X_API_KEY must be set to a non-empty value")
        return value

    @pydantic.field_validator("PROTON_CALENDAR_URL")
    @classmethod
    def _validate_calendar_url(cls, value: pydantic.SecretStr) -> pydantic.SecretStr:
        # Stray whitespace (e.g. from a ".env" file) would otherwise end up in the
        # request and make Proton reject the link.
        url = value.get_secret_value().strip()
        # The message must never include the value: it is a secret.
        if not api.core.proton.is_proton_calendar_url(url):
            raise ValueError(
                "PROTON_CALENDAR_URL must be a Proton Calendar share link starting "
                f"with '{api.core.proton.PROTON_CALENDAR_PREFIX}'"
            )
        return pydantic.SecretStr(url)


settings = Settings()
tz = zoneinfo.ZoneInfo(settings.TIMEZONE)
