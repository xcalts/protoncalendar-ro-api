import secrets

import fastapi
import fastapi.security.api_key

import api.core.config

api_key_header = fastapi.security.api_key.APIKeyHeader(
    name="X-API-KEY",
    scheme_name="X-API-KEY",
    description="Provide a valid API key to access the API.",
    auto_error=False,
)


def verify_api_key(api_key: str | None = fastapi.Security(api_key_header)) -> None:
    """Reject the request unless it carries the configured API key.

    The comparison is constant-time to avoid leaking the key through timing, and is
    done on UTF-8 bytes so that non-ASCII header values are rejected instead of
    raising (``secrets.compare_digest`` refuses non-ASCII ``str`` input).
    """

    expected = api.core.config.settings.X_API_KEY.get_secret_value().encode("utf-8")
    if api_key is None or not secrets.compare_digest(api_key.encode("utf-8"), expected):
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
